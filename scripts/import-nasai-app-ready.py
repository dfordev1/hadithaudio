#!/usr/bin/env python3
"""Replace Nasa'i matn-only reader tokens with canonical full isnad + matn.

Existing token IDs are retained wherever the previous matn sequence matches so
the compact gloss bundle keeps working. Newly exposed isnad/editorial tokens
use the reviewed alignment package's stable source-token IDs.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ARABIC_OR_LATIN = re.compile(r"[\u0621-\u064aA-Za-z0-9]")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, payload: Any) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("ـ", "").replace("ٱ", "ا")
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))
    return "".join(char for char in value if ARABIC_OR_LATIN.match(char)).lower()


def load_repairs(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    payload = load_json(path)
    return {str(entry["tokenId"]): entry for entry in payload.get("entries") or []}


def reuse_token_ids(old_tokens: list[dict[str, Any]], new_tokens: list[dict[str, Any]], repairs: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    old_filtered = [(index, normalize(str(token.get("text") or ""))) for index, token in enumerate(old_tokens)]
    new_filtered = [(index, normalize(str(token.get("text") or ""))) for index, token in enumerate(new_tokens)]
    old_filtered = [(index, text) for index, text in old_filtered if text]
    new_filtered = [(index, text) for index, text in new_filtered if text]

    matcher = difflib.SequenceMatcher(
        None,
        [text for _, text in old_filtered],
        [text for _, text in new_filtered],
        autojunk=False,
    )
    new_to_old: dict[int, int] = {}
    for old_start, new_start, size in matcher.get_matching_blocks():
        for offset in range(size):
            old_index = old_filtered[old_start + offset][0]
            new_index = new_filtered[new_start + offset][0]
            new_to_old[new_index] = old_index

    output: list[dict[str, str]] = []
    reused = 0
    for index, token in enumerate(new_tokens):
        old_index = new_to_old.get(index)
        token_id = str(token.get("id"))
        if old_index is not None:
            token_id = str(old_tokens[old_index]["id"])
            reused += 1
        source_token_id = str(token.get("id"))
        repair = repairs.get(source_token_id)
        text = str(token.get("text") or "")
        if repair:
            if text != repair["from"]:
                raise ValueError(f"repair source mismatch for {source_token_id}")
            text = repair["to"]
        output.append({"id": token_id, "text": text})

    old_lexical = len(old_filtered)
    coverage = reused / old_lexical if old_lexical else 1.0
    return output, {
        "oldTokens": len(old_tokens),
        "oldLexicalTokens": old_lexical,
        "fullTokens": len(new_tokens),
        "reusedTokenIds": reused,
        "oldLexicalCoverage": round(coverage, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--reader-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--minimum-old-token-coverage", type=float, default=0.8)
    parser.add_argument("--repairs", type=Path, default=Path(__file__).resolve().parents[1] / "qc" / "nasai-canonical-repairs.json")
    args = parser.parse_args()
    repairs = load_repairs(args.repairs)

    manifest = load_json(args.package_dir / "manifest.json")
    alignments: dict[str, dict[str, Any]] = {}
    empty_sources: list[str] = []
    for entry in manifest.get("recordings") or []:
        payload = load_json(args.package_dir / entry["resultFile"])
        for report in payload.get("reports") or []:
            source = str(report.get("sourceHadithNumber"))
            reader_value = report.get("readerHadithNumber")
            if reader_value is None:
                if int(report.get("lexicalTokenCount") or 0) == 0:
                    empty_sources.append(source)
                    continue
                raise ValueError(f"text-bearing source report lacks reader mapping: {source}")
            reader_id = str(reader_value)
            if reader_id in alignments:
                raise ValueError(f"duplicate reader mapping in alignment package: {reader_id}")
            alignments[reader_id] = report

    details: list[dict[str, Any]] = []
    low_coverage: list[dict[str, Any]] = []
    reader_ids: set[str] = set()
    all_token_ids: list[str] = []
    pending_writes: list[tuple[Path, dict[str, Any]]] = []

    for book_path in sorted(args.reader_dir.glob("book-*.json"), key=lambda path: int(path.stem.split("-")[-1])):
        payload = load_json(book_path)
        book = int(payload["book"])
        for row in payload.get("hadith") or []:
            reader_id = str(row["n"])
            reader_ids.add(reader_id)
            report = alignments.get(reader_id)
            if report is None:
                raise ValueError(f"reader report missing from alignment package: {reader_id}")
            reference_book = int((report.get("reference") or {}).get("book") or 0)
            if reference_book and reference_book != book:
                raise ValueError(f"book mismatch for {reader_id}: reader={book}, alignment={reference_book}")
            full_tokens, metrics = reuse_token_ids(row.get("tokens") or [], report.get("tokens") or [], repairs)
            if metrics["oldLexicalCoverage"] < args.minimum_old_token_coverage:
                low_coverage.append({"n": reader_id, "book": book, **metrics})
            row["tokens"] = full_tokens
            all_token_ids.extend(token["id"] for token in full_tokens)
            details.append({
                "n": reader_id,
                "source": str(report.get("sourceHadithNumber")),
                "book": book,
                "timed": any(token.get("start") is not None for token in report.get("tokens") or []),
                **metrics,
            })
        pending_writes.append((book_path, payload))

    missing_alignment_ids = sorted(set(alignments) - reader_ids)
    duplicate_token_ids = sorted(key for key, count in Counter(all_token_ids).items() if count > 1)
    result = {
        "schema": "hadith/nasai-full-reader-import/v1",
        "mode": "write" if args.write else "dry-run",
        "summary": {
            "readerReports": len(reader_ids),
            "alignmentReaderReports": len(alignments),
            "emptySourceReportsExcluded": len(empty_sources),
            "reportsUpdated": len(details),
            "oldTokens": sum(item["oldTokens"] for item in details),
            "fullTokens": sum(item["fullTokens"] for item in details),
            "reusedTokenIds": sum(item["reusedTokenIds"] for item in details),
            "lowCoverageReports": len(low_coverage),
            "missingAlignmentIds": len(missing_alignment_ids),
            "duplicateTokenIds": len(duplicate_token_ids),
            "canonicalRepairs": len(repairs),
        },
        "emptySourceReportsExcluded": sorted(empty_sources),
        "missingAlignmentIds": missing_alignment_ids,
        "lowCoverageReports": low_coverage,
        "duplicateTokenIds": duplicate_token_ids,
        "reports": details,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.report, result)

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"report={args.report}")
    if low_coverage or missing_alignment_ids or duplicate_token_ids:
        return 1
    if args.write:
        for path, payload in pending_writes:
            atomic_json(path, payload)
        print(f"updated {len(pending_writes)} reader book files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
