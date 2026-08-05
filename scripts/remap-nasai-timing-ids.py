#!/usr/bin/env python3
"""Remap Nasa'i timing token IDs to match the current reader IDs.

The full-isnad import reuses legacy matn token IDs for gloss compatibility.
Clip timings originally carried source-token IDs. This remapper aligns them
1:1 by token text/order so highlight sync and the publication verifier pass.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_READER = ROOT / "public" / "nasai"
DEFAULT_TIMINGS = ROOT / "qc" / "nasai-app-ready-full" / "timings"
DEFAULT_OUTPUT = ROOT / "qc" / "nasai-app-ready-full" / "qa" / "timing-id-remap.json"


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.025 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_reader(reader_dir: Path) -> dict[str, list[dict[str, Any]]]:
    reports: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(reader_dir.glob("book-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for report in data.get("hadith") or []:
            locator = str(report["n"])
            if locator in reports:
                raise ValueError(f"duplicate reader report {locator}")
            reports[locator] = list(report.get("tokens") or [])
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", type=Path, default=DEFAULT_READER)
    parser.add_argument("--timings", type=Path, default=DEFAULT_TIMINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reader = load_reader(args.reader)
    updated = 0
    unchanged = 0
    mismatched: list[dict[str, Any]] = []

    for path in sorted(args.timings.glob("n*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        locator = str(data.get("n"))
        reader_tokens = reader.get(locator)
        timing_tokens = data.get("tokens") or []
        if reader_tokens is None:
            mismatched.append({"n": locator, "reason": "missing_reader"})
            continue
        if len(reader_tokens) != len(timing_tokens):
            mismatched.append({
                "n": locator,
                "reason": "length",
                "reader": len(reader_tokens),
                "timing": len(timing_tokens),
            })
            continue

        changed = False
        remapped: list[dict[str, Any]] = []
        text_mismatch = False
        for reader_token, timing_token in zip(reader_tokens, timing_tokens):
            reader_text = str(reader_token.get("text") or "")
            timing_text = str(timing_token.get("text") or "")
            if reader_text != timing_text:
                mismatched.append({
                    "n": locator,
                    "reason": "text",
                    "readerId": reader_token.get("id"),
                    "timingId": timing_token.get("id"),
                })
                text_mismatch = True
                break
            item = dict(timing_token)
            reader_id = str(reader_token["id"])
            old_id = str(item.get("id") or "")
            if old_id != reader_id:
                if "sourceTokenId" not in item and old_id:
                    item["sourceTokenId"] = old_id
                item["id"] = reader_id
                changed = True
            remapped.append(item)
        if text_mismatch:
            continue
        if changed:
            if not args.dry_run:
                data["tokens"] = remapped
                atomic_json(path, data)
            updated += 1
        else:
            unchanged += 1

    report = {
        "schema": "hadith/nasai-timing-id-remap/v1",
        "dryRun": bool(args.dry_run),
        "updated": updated,
        "unchanged": unchanged,
        "mismatchCount": len(mismatched),
        "mismatched": mismatched[:100],
    }
    atomic_json(args.output, report)
    print(json.dumps({k: report[k] for k in ("updated", "unchanged", "mismatchCount", "dryRun")}, indent=2))
    return 1 if mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
