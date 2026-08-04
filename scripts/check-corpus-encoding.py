#!/usr/bin/env python3
"""Fail when new U+FFFD replacement characters enter the canonical Arabic corpus.

A U+FFFD marks a byte lost in an encoding conversion. It silently corrupts a
canonical word, and because glosses are keyed by token id rather than by text a
corrupted token can still carry a gloss, so nothing downstream reports it.

76 occurrences already exist and are inherited from upstream
fawazahmed0/hadith-api (verified identical at the pinned commit and at tag 1),
so this check works against a recorded baseline: it fails on anything new, and
also fails when a baseline entry disappears without the baseline being updated,
so genuine repairs stay deliberate and reviewed.

Repairs must come from an identified reliable edition with provenance recorded
(handoff section 18). Do not guess replacements from context.

Usage:
    python scripts/check-corpus-encoding.py
    python scripts/check-corpus-encoding.py --update-baseline
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

FFFD = "�"
COLLECTIONS = ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah", "malik"]
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(REPO_ROOT, "public")
BASELINE_PATH = os.path.join(REPO_ROOT, "qc", "corpus-encoding-baseline.json")


def scan(public_dir: str) -> list[dict]:
    findings: list[dict] = []
    for slug in COLLECTIONS:
        for path in sorted(glob.glob(os.path.join(public_dir, slug, "book-*.json"))):
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            for hadith in data.get("hadith", []):
                for token in hadith.get("tokens", []):
                    if FFFD in token["text"]:
                        findings.append({
                            "collection": slug,
                            "report": hadith["n"],
                            "field": "token",
                            "ref": token["id"],
                        })
                if FFFD in (hadith.get("isnad") or ""):
                    findings.append({
                        "collection": slug,
                        "report": hadith["n"],
                        "field": "isnad",
                        "ref": f"{slug}:{hadith['n']}:isnad",
                    })
    return findings


def key(finding: dict) -> str:
    return f"{finding['collection']}|{finding['report']}|{finding['field']}|{finding['ref']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true",
                        help="rewrite the baseline to match the corpus as it stands")
    args = parser.parse_args()

    findings = scan(PUBLIC_DIR)
    current = {key(f) for f in findings}

    if args.update_baseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
            json.dump({
                "schema": "hadith/corpus-encoding-baseline/v1",
                "note": "Known U+FFFD occurrences inherited from upstream. "
                        "Shrink this list only via a documented repair.",
                "count": len(findings),
                "keys": sorted(current),
            }, handle, ensure_ascii=False, indent=1)
        print(f"baseline updated: {len(findings)} known occurrences")
        return 0

    if not os.path.exists(BASELINE_PATH):
        print(f"FAIL missing baseline {BASELINE_PATH}; run --update-baseline once", file=sys.stderr)
        return 1

    with open(BASELINE_PATH, encoding="utf-8") as handle:
        baseline = set(json.load(handle)["keys"])

    added = sorted(current - baseline)
    removed = sorted(baseline - current)

    if added:
        print(f"FAIL {len(added)} new U+FFFD occurrence(s) in canonical Arabic:", file=sys.stderr)
        for item in added[:20]:
            print(f"  + {item}", file=sys.stderr)
        if len(added) > 20:
            print(f"  … and {len(added) - 20} more", file=sys.stderr)
    if removed:
        print(f"FAIL {len(removed)} baseline occurrence(s) no longer present.", file=sys.stderr)
        print("     If this was a deliberate repair, record provenance and rerun "
              "with --update-baseline.", file=sys.stderr)
        for item in removed[:20]:
            print(f"  - {item}", file=sys.stderr)

    if added or removed:
        return 1

    print(f"OK corpus encoding unchanged ({len(current)} known upstream occurrences)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
