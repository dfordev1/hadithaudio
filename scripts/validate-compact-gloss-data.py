#!/usr/bin/env python3
"""Validate public/gloss-compact against every legacy public/gloss/*.json."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "public" / "gloss"
DEFAULT_COMPACT_DIR = ROOT / "public" / "gloss-compact"

REPORT_RE = re.compile(r"^(?P<collection>.+)-(?P<report>[^.]+)\.json$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gz_json(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def split_report_name(path: Path) -> tuple[str, str]:
    match = REPORT_RE.match(path.name)
    if not match:
        raise ValueError(f"unexpected gloss filename: {path.name}")
    return match.group("collection"), match.group("report")


def reconstruct_report(entry: dict[str, Any], pool_entries: list[dict[str, Any]]) -> dict[str, Any]:
    report = dict(entry["meta"])
    report["glosses"] = {
        token_id: pool_entries[pool_id]["value"]
        for token_id, pool_id in entry.get("tokenRefs", [])
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--compact-dir", type=Path, default=DEFAULT_COMPACT_DIR)
    args = parser.parse_args()

    source_dir: Path = args.source_dir
    compact_dir: Path = args.compact_dir
    manifest_path = compact_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing manifest: {manifest_path}")

    manifest = load_json(manifest_path)
    total_files = 0
    total_roundtripped = 0
    mismatches: list[str] = []
    source_available = source_dir.exists()

    for collection_entry in manifest.get("collections", []):
        collection = collection_entry["collection"]
        pool_path = compact_dir / collection_entry["pool"]["file"]
        bundle_path = compact_dir / collection_entry["bundle"]["file"]
        for path, metadata in ((pool_path, collection_entry["pool"]), (bundle_path, collection_entry["bundle"])):
            data = path.read_bytes()
            if len(data) != metadata["bytes"] or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
                raise SystemExit(f"asset integrity mismatch: {path}")
        pool = load_gz_json(pool_path)
        bundle = load_gz_json(bundle_path)
        if pool.get("schema") != "hadith/gloss-pool/v1":
            raise SystemExit(f"unexpected pool schema in {pool_path}")
        if bundle.get("schema") != "hadith/gloss-bundle/v1":
            raise SystemExit(f"unexpected bundle schema in {bundle_path}")
        pool_entries = pool.get("entries", [])
        if not isinstance(pool_entries, list):
            raise TypeError(f"{pool_path} pool entries are not a list")
        if len(pool_entries) != collection_entry["uniqueGlossValues"]:
            raise SystemExit(f"pool size mismatch in {pool_path}")
        seen_pool_ids = {entry.get("id") for entry in pool_entries}
        if seen_pool_ids != set(range(len(pool_entries))):
            raise SystemExit(f"non-deterministic pool ids in {pool_path}")
        if len(bundle.get("reports", [])) != collection_entry["reports"]:
            raise SystemExit(f"report count mismatch in {bundle_path}")

        for report_entry in bundle.get("reports", []):
            report_file = report_entry["file"]
            source_path = source_dir / report_file
            total_files += 1
            if split_report_name(source_path)[0] != collection:
                mismatches.append(f"collection mismatch for {source_path}")
                continue
            if any(not isinstance(ref, list) or len(ref) != 2 or not isinstance(ref[1], int) or ref[1] < 0 or ref[1] >= len(pool_entries)
                   for ref in report_entry.get("tokenRefs", [])):
                mismatches.append(f"invalid pool reference: {collection}/{report_file}")
                continue
            if not source_available:
                continue
            if not source_path.exists():
                mismatches.append(f"missing source file: {source_path}")
                continue
            source = load_json(source_path)
            reconstructed = reconstruct_report(report_entry, pool_entries)
            if source != reconstructed:
                mismatches.append(f"round-trip mismatch: {collection}/{report_file}")
                if len(mismatches) >= 5:
                    break
            else:
                total_roundtripped += 1
        if len(mismatches) >= 5:
            break

    if mismatches:
        print(json.dumps({"ok": False, "mismatches": mismatches[:5]}, ensure_ascii=False, separators=(",", ":")))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "sourceFiles": total_files,
                "roundTripped": total_roundtripped,
                "sourceAvailable": source_available,
                "collections": len(manifest.get("collections", [])),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
