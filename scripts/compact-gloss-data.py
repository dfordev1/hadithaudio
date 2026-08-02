#!/usr/bin/env python3
"""Compact public/gloss/*.json into per-collection gzipped pools and bundles.

The compact form is lossless: every legacy gloss file can be reconstructed
byte-for-byte at the JSON object level from the compact bundle + shared pool.
No legacy gloss files are deleted by this script.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import shutil
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "public" / "gloss"
DEFAULT_OUTPUT_DIR = ROOT / "public" / "gloss-compact"

REPORT_RE = re.compile(r"^(?P<collection>.+)-(?P<report>[^.]+)\.json$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def write_gz_json(path: Path, value: Any) -> tuple[int, str]:
    raw = dumps_json(value).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    data = buffer.getvalue()
    path.write_bytes(data)
    return len(data), hashlib.sha256(data).hexdigest()


def split_report_name(path: Path) -> tuple[str, str]:
    match = REPORT_RE.match(path.name)
    if not match:
        raise ValueError(f"unexpected gloss filename: {path.name}")
    return match.group("collection"), match.group("report")


def report_sort_key(report_id: str) -> tuple[Any, ...]:
    key: list[tuple[int, Any]] = []
    for part in report_id.split("."):
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def canonical_gloss_key(value: dict[str, Any]) -> str:
    return dumps_json(value)


def compact_collection(paths: list[Path], output_dir: Path) -> dict[str, Any]:
    collection = split_report_name(paths[0])[0]
    pool_by_key: dict[str, int] = {}
    pool_entries: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    total_gloss_refs = 0

    for path in sorted(paths, key=lambda p: report_sort_key(split_report_name(p)[1])):
        data = load_json(path)
        if not isinstance(data, dict):
            raise TypeError(f"{path} did not contain a JSON object")
        meta = {key: value for key, value in data.items() if key != "glosses"}
        glosses = data.get("glosses") or {}
        if not isinstance(glosses, dict):
            raise TypeError(f"{path} glosses field is not an object")

        token_refs: list[list[Any]] = []
        for token_id, gloss in glosses.items():
            if not isinstance(gloss, dict):
                raise TypeError(f"{path} gloss entry {token_id!r} is not an object")
            key = canonical_gloss_key(gloss)
            pool_id = pool_by_key.get(key)
            if pool_id is None:
                pool_id = len(pool_entries)
                pool_by_key[key] = pool_id
                pool_entries.append({"id": pool_id, "value": gloss, "count": 0})
            pool_entries[pool_id]["count"] += 1
            token_refs.append([token_id, pool_id])

        total_gloss_refs += len(token_refs)
        reports.append(
            {
                "file": path.name,
                "report": split_report_name(path)[1],
                "meta": meta,
                "tokenRefs": token_refs,
            }
        )

    pool_path = output_dir / f"{collection}-pool.json.gz"
    bundle_path = output_dir / f"{collection}-bundle.json.gz"
    pool_bytes, pool_sha = write_gz_json(
        pool_path,
        {
            "schema": "hadith/gloss-pool/v1",
            "collection": collection,
            "entries": pool_entries,
        },
    )
    bundle_bytes, bundle_sha = write_gz_json(
        bundle_path,
        {
            "schema": "hadith/gloss-bundle/v1",
            "collection": collection,
            "reports": reports,
        },
    )

    return {
        "collection": collection,
        "sourceFiles": len(paths),
        "reports": len(reports),
        "glossRefs": total_gloss_refs,
        "uniqueGlossValues": len(pool_entries),
        "pool": {
            "file": pool_path.name,
            "bytes": pool_bytes,
            "sha256": pool_sha,
        },
        "bundle": {
            "file": bundle_path.name,
            "bytes": bundle_bytes,
            "sha256": bundle_sha,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-clean", action="store_true", help="keep existing compact assets in place")
    args = parser.parse_args()

    source_dir: Path = args.source_dir
    output_dir: Path = args.output_dir

    if not source_dir.exists():
        raise SystemExit(f"missing source directory: {source_dir}")
    if output_dir.exists() and not args.no_clean:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(source_dir.glob("*.json"))
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        collection, _ = split_report_name(path)
        groups[collection].append(path)

    collections: list[dict[str, Any]] = []
    for collection in sorted(groups):
        collections.append(compact_collection(groups[collection], output_dir))

    source_bytes = sum(path.stat().st_size for path in files)
    compact_files = sorted(output_dir.glob("*"))
    compact_bytes = sum(path.stat().st_size for path in compact_files)

    manifest = {
        "schema": "hadith/gloss-compact-manifest/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "dir": str(source_dir.relative_to(ROOT)).replace("\\", "/"),
            "files": len(files),
            "bytes": source_bytes,
        },
        "compact": {
            "dir": str(output_dir.relative_to(ROOT)).replace("\\", "/"),
            "files": len(compact_files),
            "bytes": compact_bytes,
        },
        "manifest": {"file": "manifest.json"},
        "collections": collections,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(dumps_json(manifest), encoding="utf-8")

    print(
        json.dumps(
            {
                "collections": len(collections),
                "sourceFiles": len(files),
                "sourceBytes": source_bytes,
                "compactFiles": len(compact_files) + 1,
                "compactBytes": compact_bytes + manifest_path.stat().st_size,
                "manifest": manifest_path.name,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
