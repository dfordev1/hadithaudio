#!/usr/bin/env python3
"""Slice gloss-compact pools into per-report gzip files for lazy client loading.

Each output file is a resolved hadith gloss object (meta + glosses) identical to
what the reader reconstructs from pool + bundle. Run before deploy when
public/gloss-lazy/ is absent; the reader falls back to full compact bundles.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPACT_DIR = ROOT / "public" / "gloss-compact"
OUTPUT_DIR = ROOT / "public" / "gloss-lazy"


def load_gz_json(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def write_gz_json(path: Path, value: dict) -> int:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    data = buffer.getvalue()
    path.write_bytes(data)
    return len(data)


def build_collection(slug: str, *, force: bool) -> dict:
    pool_path = COMPACT_DIR / f"{slug}-pool.json.gz"
    bundle_path = COMPACT_DIR / f"{slug}-bundle.json.gz"
    if not pool_path.exists() or not bundle_path.exists():
        raise FileNotFoundError(f"missing compact gloss for {slug}")

    pool = load_gz_json(pool_path)
    bundle = load_gz_json(bundle_path)
    values = [entry["value"] for entry in pool["entries"]]
    out_dir = OUTPUT_DIR / slug

    written = 0
    skipped = 0
    total_bytes = 0
    for report in bundle["reports"]:
        report_id = str(report["report"])
        out_path = out_dir / f"{report_id}.json.gz"
        if out_path.exists() and not force:
            skipped += 1
            total_bytes += out_path.stat().st_size
            continue
        glosses = {
            token_id: values[pool_id]
            for token_id, pool_id in report["tokenRefs"]
        }
        payload = {**report["meta"], "glosses": glosses}
        total_bytes += write_gz_json(out_path, payload)
        written += 1

    return {
        "collection": slug,
        "reports": len(bundle["reports"]),
        "written": written,
        "skipped": skipped,
        "bytes": total_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", action="append", help="only build named collection(s)")
    parser.add_argument("--force", action="store_true", help="rewrite existing lazy files")
    parser.add_argument(
        "--if-missing",
        action="store_true",
        help="skip collections that already have a complete lazy directory",
    )
    args = parser.parse_args()

    manifest_path = COMPACT_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slugs = args.slug or [entry["collection"] for entry in manifest["collections"]]

    summaries = []
    for slug in slugs:
        out_dir = OUTPUT_DIR / slug
        expected = next(c["reports"] for c in manifest["collections"] if c["collection"] == slug)
        if args.if_missing and out_dir.is_dir():
            existing = len(list(out_dir.glob("*.json.gz")))
            if existing >= expected:
                print(f"skip {slug}: {existing}/{expected} lazy files present", flush=True)
                continue
        print(f"building gloss-lazy/{slug} ...", flush=True)
        summaries.append(build_collection(slug, force=args.force))
        print(
            f"  {slug}: wrote {summaries[-1]['written']}, skipped {summaries[-1]['skipped']}, "
            f"{summaries[-1]['bytes'] / 1024 / 1024:.2f} MiB",
            flush=True,
        )

    if summaries:
        index = {
            "schema": "hadith/gloss-lazy-index/v1",
            "collections": summaries,
            "outputDir": "public/gloss-lazy",
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "manifest.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
