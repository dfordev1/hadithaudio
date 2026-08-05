#!/usr/bin/env python3
"""Validate the reviewed Nasa'i recording alignments before clip generation.

The validator is intentionally independent from the clip builder.  It checks
the supplied manifest, the twelve source recordings, canonical Arabic, reader
IDs, token IDs, timestamp bounds, and cross-report boundary behavior.  It does
not repair or invent timestamps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ARABIC_LETTER = re.compile(r"[\u0621-\u064a]")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name,bit_rate:stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    return {
        "duration": float(fmt.get("duration") or 0),
        "format": fmt.get("format_name"),
        "bitRate": int(fmt.get("bit_rate") or 0),
        "codec": stream.get("codec_name"),
        "sampleRate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
    }


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def canonical_map(path: Path) -> dict[str, str]:
    payload = load_json(path)
    rows = payload.get("hadiths", payload) if isinstance(payload, dict) else payload
    result: dict[str, str] = {}
    for row in rows:
        locator = row.get("hadithnumber", row.get("n"))
        if locator is None:
            continue
        result[str(locator)] = str(row.get("text", row.get("arabic", "")))
    return result


def reader_map(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for book_path in sorted(path.glob("book-*.json")):
        payload = load_json(book_path)
        rows = payload.get("hadith", payload) if isinstance(payload, dict) else payload
        for row in rows:
            locator = str(row.get("n"))
            if locator in result:
                raise ValueError(f"duplicate reader report ID {locator}")
            result[locator] = {"book": payload.get("book"), "row": row, "file": book_path.name}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--canonical-json", type=Path, required=True)
    parser.add_argument("--reader-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.package_dir / "manifest.json"
    manifest = load_json(manifest_path)
    canonical = canonical_map(args.canonical_json)
    reader = reader_map(args.reader_dir)

    source_report_ids: list[str] = []
    effective_report_ids: list[str] = []
    mapped_reader_ids: list[str] = []
    unmapped_reader_sources: list[str] = []
    token_ids: list[str] = []
    canonical_mismatches: list[dict[str, str]] = []
    invalid_intervals: list[dict[str, Any]] = []
    token_order_reversals: list[dict[str, Any]] = []
    report_boundary_overlaps: list[dict[str, Any]] = []
    report_boundary_gaps: list[dict[str, Any]] = []
    untimed_lexical_statuses: Counter[str] = Counter()
    token_statuses: Counter[str] = Counter()
    recording_rows: list[dict[str, Any]] = []
    empty_reports: list[dict[str, Any]] = []
    fully_untimed_reports: list[dict[str, Any]] = []
    timed_reports: list[str] = []
    manifest_count_mismatches: list[dict[str, Any]] = []
    hash_failures: list[dict[str, str]] = []
    lexical_tokens = 0
    timestamped_lexical_tokens = 0
    explicit_untimed_lexical_tokens = 0

    previous_recording_last: tuple[str, str, float] | None = None
    for entry in manifest.get("recordings", []):
        number = str(entry["recording"]).zfill(2)
        result_path = args.package_dir / entry["resultFile"]
        expected_hash = str(entry.get("resultSha256", "")).lower()
        actual_hash = sha256(result_path)
        if expected_hash and expected_hash != actual_hash:
            hash_failures.append({"file": str(result_path), "expected": expected_hash, "actual": actual_hash})

        payload = load_json(result_path)
        reports = payload.get("reports") or []
        declared_report_count = (entry.get("validation") or {}).get("reportObjects")
        if declared_report_count is not None and int(declared_report_count) != len(reports):
            manifest_count_mismatches.append({
                "recording": number,
                "manifest": int(declared_report_count),
                "actual": len(reports),
            })
        audio_path = args.audio_dir / f"{number}.mp3"
        audio = ffprobe(audio_path)
        declared_duration = float(payload.get("durationSeconds") or 0)
        duration_delta = abs(audio["duration"] - declared_duration)

        previous: tuple[str, float, float, str] | None = None
        recording_token_count = 0
        recording_timed_count = 0
        recording_untimed_count = 0
        for report in reports:
            source_locator = str(report.get("sourceHadithNumber"))
            reader_value = report.get("readerHadithNumber")
            reader_locator = str(reader_value) if reader_value is not None else None
            locator = reader_locator or source_locator
            source_report_ids.append(source_locator)
            effective_report_ids.append(locator)
            if reader_locator is None:
                unmapped_reader_sources.append(source_locator)
            else:
                mapped_reader_ids.append(reader_locator)
            full_text = str(report.get("fullText") or "")
            if source_locator in canonical and canonical[source_locator] != full_text:
                canonical_mismatches.append({
                    "source": source_locator,
                    "reader": reader_locator,
                    "recording": number,
                    "canonicalSha256": hashlib.sha256(canonical[source_locator].encode("utf-8")).hexdigest(),
                    "alignmentSha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                })

            report_start = report.get("start")
            report_end = report.get("end")
            if isinstance(report_start, (int, float)) and isinstance(report_end, (int, float)):
                if report_start < 0 or report_end < report_start or report_end > audio["duration"] + 0.1:
                    invalid_intervals.append({"recording": number, "n": locator, "start": report_start, "end": report_end})
                if previous:
                    prior_id, prior_start, prior_end, prior_text = previous
                    delta = float(report_start) - prior_end
                    if delta < 0:
                        report_boundary_overlaps.append({
                            "recording": number,
                            "previous": prior_id,
                            "next": locator,
                            "seconds": round(-delta, 3),
                            "sameRange": abs(prior_start - float(report_start)) < 1e-6 and abs(prior_end - float(report_end)) < 1e-6,
                            "sameText": prior_text == full_text,
                        })
                    elif delta > 2.0:
                        report_boundary_gaps.append({
                            "recording": number,
                            "previous": prior_id,
                            "next": locator,
                            "seconds": round(delta, 3),
                        })
                previous = (locator, float(report_start), float(report_end), full_text)

            prior_start: float | None = None
            report_lexical_count = 0
            report_timed_lexical_count = 0
            for token in report.get("tokens") or []:
                token_id = str(token.get("id"))
                token_ids.append(token_id)
                text = str(token.get("text") or "")
                lexical = bool(ARABIC_LETTER.search(text))
                start = token.get("start")
                end = token.get("end")
                status = str(token.get("status") or "unknown")
                token_statuses[status] += 1
                if lexical:
                    report_lexical_count += 1
                    lexical_tokens += 1
                    recording_token_count += 1
                    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                        timestamped_lexical_tokens += 1
                        report_timed_lexical_count += 1
                        recording_timed_count += 1
                    else:
                        explicit_untimed_lexical_tokens += 1
                        recording_untimed_count += 1
                        untimed_lexical_statuses[status] += 1
                if start is None and end is None:
                    continue
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                    invalid_intervals.append({"recording": number, "n": locator, "token": token_id, "start": start, "end": end})
                    continue
                if start < 0 or end < start or end > audio["duration"] + 0.1:
                    invalid_intervals.append({"recording": number, "n": locator, "token": token_id, "start": start, "end": end})
                if prior_start is not None and start < prior_start - 1e-6:
                    token_order_reversals.append({"recording": number, "n": locator, "token": token_id, "start": start, "priorStart": prior_start})
                prior_start = float(start)

            report_descriptor = {
                "source": source_locator,
                "reader": reader_locator,
                "effective": locator,
                "recording": number,
                "book": (report.get("reference") or {}).get("book"),
                "lexicalTokens": report_lexical_count,
                "timestampedLexicalTokens": report_timed_lexical_count,
                "status": report.get("status"),
            }
            if report_lexical_count == 0:
                empty_reports.append(report_descriptor)
            elif report_timed_lexical_count == 0:
                fully_untimed_reports.append(report_descriptor)
            else:
                timed_reports.append(locator)

        if previous:
            if previous_recording_last and number == previous_recording_last[0]:
                raise AssertionError("recording accounting error")
            previous_recording_last = (number, previous[0], previous[2])
        recording_rows.append({
            "recording": number,
            "file": str(audio_path),
            "declaredDuration": declared_duration,
            "audio": audio,
            "durationDelta": round(duration_delta, 6),
            "reports": len(reports),
            "lexicalTokens": recording_token_count,
            "timestampedLexicalTokens": recording_timed_count,
            "explicitUntimedLexicalTokens": recording_untimed_count,
        })

    source_report_counts = Counter(source_report_ids)
    effective_report_counts = Counter(effective_report_ids)
    token_counts = Counter(token_ids)
    duplicate_source_reports = sorted({key: count for key, count in source_report_counts.items() if count > 1}.items())
    duplicate_effective_reports = sorted({key: count for key, count in effective_report_counts.items() if count > 1}.items())
    duplicate_tokens = sorted({key: count for key, count in token_counts.items() if count > 1}.items())
    source_alignment_ids = set(source_report_ids)
    effective_alignment_ids = set(effective_report_ids)
    mapped_alignment_ids = set(mapped_reader_ids)
    reader_ids = set(reader)
    canonical_ids = set(canonical)

    result = {
        "schema": "hadith/nasai-app-ready-validation/v1",
        "inputs": {
            "manifest": str(manifest_path),
            "audioDir": str(args.audio_dir),
            "canonical": str(args.canonical_json),
            "readerDir": str(args.reader_dir),
        },
        "summary": {
            "recordings": len(recording_rows),
            "reports": len(source_report_ids),
            "uniqueSourceReports": len(source_alignment_ids),
            "uniqueEffectiveReaderReports": len(effective_alignment_ids),
            "explicitReaderMappings": len(mapped_reader_ids),
            "unmappedReaderSources": len(unmapped_reader_sources),
            "readerReports": len(reader_ids),
            "canonicalReports": len(canonical_ids),
            "lexicalTokens": lexical_tokens,
            "timestampedLexicalTokens": timestamped_lexical_tokens,
            "explicitUntimedLexicalTokens": explicit_untimed_lexical_tokens,
            "timestampCoverage": round(timestamped_lexical_tokens / lexical_tokens, 8) if lexical_tokens else 0,
            "tokenIds": len(token_ids),
            "uniqueTokenIds": len(set(token_ids)),
            "hashFailures": len(hash_failures),
            "canonicalMismatches": len(canonical_mismatches),
            "invalidIntervals": len(invalid_intervals),
            "tokenOrderReversals": len(token_order_reversals),
            "reportBoundaryOverlaps": len(report_boundary_overlaps),
            "sharedExactReportRanges": sum(1 for item in report_boundary_overlaps if item["sameRange"] and item["sameText"]),
            "nonSharedReportBoundaryOverlaps": sum(1 for item in report_boundary_overlaps if not (item["sameRange"] and item["sameText"])),
            "reportBoundaryGapsOver2s": len(report_boundary_gaps),
            "emptyReports": len(empty_reports),
            "timedReports": len(timed_reports),
            "fullyUntimedReports": len(fully_untimed_reports),
            "manifestCountMismatches": len(manifest_count_mismatches),
        },
        "recordings": recording_rows,
        "sets": {
            "effectiveAlignmentNotInReader": sorted(effective_alignment_ids - reader_ids),
            "readerNotInMappedAlignment": sorted(reader_ids - mapped_alignment_ids),
            "mappedAlignmentNotInReader": sorted(mapped_alignment_ids - reader_ids),
            "sourceAlignmentNotInCanonical": sorted(source_alignment_ids - canonical_ids),
            "canonicalNotInSourceAlignment": sorted(canonical_ids - source_alignment_ids),
            "unmappedReaderSources": sorted(unmapped_reader_sources),
        },
        "statusCounts": dict(token_statuses.most_common()),
        "untimedLexicalStatusCounts": dict(untimed_lexical_statuses.most_common()),
        "emptyReports": empty_reports,
        "fullyUntimedReports": fully_untimed_reports,
        "manifestCountMismatches": manifest_count_mismatches,
        "duplicateSourceReports": duplicate_source_reports,
        "duplicateEffectiveReports": duplicate_effective_reports,
        "duplicateTokens": duplicate_tokens,
        "hashFailures": hash_failures,
        "canonicalMismatches": canonical_mismatches,
        "invalidIntervals": invalid_intervals,
        "tokenOrderReversals": token_order_reversals,
        "reportBoundaryOverlaps": report_boundary_overlaps,
        "reportBoundaryGapsOver2s": report_boundary_gaps,
    }
    atomic_json(args.output, result)

    summary = result["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"effective_alignment_not_in_reader={len(result['sets']['effectiveAlignmentNotInReader'])}")
    print(f"reader_not_in_mapped_alignment={len(result['sets']['readerNotInMappedAlignment'])}")
    print(f"report_boundary_overlaps={len(report_boundary_overlaps)}")
    print(f"report={args.output}")

    structural_errors = (
        hash_failures
        or duplicate_source_reports
        or duplicate_effective_reports
        or duplicate_tokens
        or canonical_mismatches
        or invalid_intervals
        or token_order_reversals
    )
    return 1 if structural_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
