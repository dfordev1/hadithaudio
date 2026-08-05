#!/usr/bin/env python3
"""Build resumable per-report Nasa'i MP3 clips and reader timing sidecars."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

LEAD_PAD = 0.12
TAIL_PAD = 0.06
SEPARATION_GUARD = 0.08


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_repairs(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    payload = load_json(path)
    return {str(entry["tokenId"]): entry for entry in payload.get("entries") or []}


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


def stem(locator: str) -> str:
    return locator.zfill(4) if locator.isdigit() else locator


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def timed_lexical(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        token for token in report.get("tokens") or []
        if any("\u0621" <= char <= "\u064a" for char in str(token.get("text") or ""))
        and isinstance(token.get("start"), (int, float))
        and isinstance(token.get("end"), (int, float))
    ]


def report_span(report: dict[str, Any] | None) -> tuple[float, float] | None:
    tokens = timed_lexical(report or {})
    if not tokens:
        return None
    return min(float(token["start"]) for token in tokens), max(float(token["end"]) for token in tokens)


def same_audio_report(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not left or not right:
        return False
    left_span = report_span(left)
    right_span = report_span(right)
    return bool(
        left_span and right_span
        and abs(left_span[0] - right_span[0]) < 1e-6
        and abs(left_span[1] - right_span[1]) < 1e-6
        and str(left.get("fullText") or "") == str(right.get("fullText") or "")
    )


def repair_adjacent_boundaries(reports: list[dict[str, Any]], recording: str) -> list[dict[str, Any]]:
    """Partition conflicting edge-token intervals without altering source files."""
    repairs: list[dict[str, Any]] = []
    for previous, current in zip(reports, reports[1:]):
        if same_audio_report(previous, current):
            continue
        previous_tokens = timed_lexical(previous)
        current_tokens = timed_lexical(current)
        if not previous_tokens or not current_tokens:
            continue
        previous_end = max(float(token["end"]) for token in previous_tokens)
        current_start = min(float(token["start"]) for token in current_tokens)
        if previous_end <= current_start:
            continue
        previous_crossing = [token for token in previous_tokens if float(token["end"]) > current_start]
        current_crossing = [token for token in current_tokens if float(token["start"]) < previous_end]
        raw_boundary = (previous_end + current_start) / 2
        feasible_low = max(float(token["start"]) for token in previous_crossing) + 0.01
        feasible_high = min(float(token["end"]) for token in current_crossing) - 0.01
        if feasible_low > feasible_high:
            raise ValueError(
                f"no feasible boundary for {previous.get('readerHadithNumber')} -> "
                f"{current.get('readerHadithNumber')} in recording {recording}"
            )
        boundary = min(feasible_high, max(feasible_low, raw_boundary))
        for token in previous_crossing:
            raw_end = float(token["end"])
            if raw_end > boundary:
                token["rawBoundaryEnd"] = raw_end
                token["end"] = round(boundary, 6)
        for token in current_crossing:
            raw_start = float(token["start"])
            if raw_start < boundary:
                token["rawBoundaryStart"] = raw_start
                token["start"] = round(boundary, 6)
        repair = {
            "recording": recording,
            "previous": str(previous["readerHadithNumber"]),
            "next": str(current["readerHadithNumber"]),
            "rawOverlapSeconds": round(previous_end - current_start, 3),
            "boundary": round(boundary, 6),
            "method": "canonical-order midpoint partition constrained inside crossing edge tokens",
        }
        previous["_boundaryRepairAfter"] = repair
        current["_boundaryRepairBefore"] = repair
        repairs.append(repair)
    return repairs


def parse_selection(value: str | None) -> set[str] | None:
    if not value or value.lower() == "all":
        return None
    selected: set[str] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part and all(item.strip().isdigit() for item in part.split("-", 1)):
            low, high = (int(item) for item in part.split("-", 1))
            selected.update(str(number) for number in range(low, high + 1))
        else:
            selected.add(part)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reports", help="comma IDs/ranges; default all")
    parser.add_argument("--recordings", help="comma recording numbers; default all")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repairs", type=Path, default=Path(__file__).resolve().parents[1] / "qc" / "nasai-canonical-repairs.json")
    args = parser.parse_args()
    repairs = load_repairs(args.repairs)

    selected_reports = parse_selection(args.reports)
    selected_recordings = {item.strip().zfill(2) for item in args.recordings.split(",")} if args.recordings else None
    clips_dir = args.output_dir / "clips"
    timings_dir = args.output_dir / "timings"
    progress_path = args.output_dir / "progress.json"
    manifest_path = args.output_dir / "manifest.json"
    clips_dir.mkdir(parents=True, exist_ok=True)
    timings_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_json(args.package_dir / "manifest.json")
    jobs: list[dict[str, Any]] = []
    nonplayable: list[dict[str, Any]] = []
    shared_groups: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    recording_durations: dict[str, float] = {}
    boundary_repairs: list[dict[str, Any]] = []

    for entry in manifest.get("recordings") or []:
        number = str(entry["recording"]).zfill(2)
        if selected_recordings is not None and number not in selected_recordings:
            continue
        payload = load_json(args.package_dir / entry["resultFile"])
        source_audio = args.audio_dir / f"{number}.mp3"
        recording_durations[number] = ffprobe_duration(source_audio)
        reports = payload.get("reports") or []
        mapped = [report for report in reports if report.get("readerHadithNumber") is not None]
        boundary_repairs.extend(repair_adjacent_boundaries(mapped, number))

        for index, report in enumerate(mapped):
            locator = str(report["readerHadithNumber"])
            if selected_reports is not None and locator not in selected_reports:
                continue
            lexical_tokens = [token for token in report.get("tokens") or [] if any("\u0621" <= char <= "\u064a" for char in str(token.get("text") or ""))]
            timed_tokens = timed_lexical(report)
            if not timed_tokens:
                nonplayable.append({
                    "n": locator,
                    "source": str(report.get("sourceHadithNumber")),
                    "recording": number,
                    "reason": "explicit_audio_variant_without_independent_timestamps",
                    "lexicalTokens": len(lexical_tokens),
                })
                continue

            report_start = float(min(token["start"] for token in timed_tokens))
            report_end = float(max(token["end"] for token in timed_tokens))
            previous_report = mapped[index - 1] if index > 0 else None
            next_report = mapped[index + 1] if index + 1 < len(mapped) else None
            previous_span = None if same_audio_report(previous_report, report) else report_span(previous_report)
            next_span = None if same_audio_report(report, next_report) else report_span(next_report)
            previous_end = previous_span[1] if previous_span else None
            next_start = next_span[0] if next_span else None

            clip_start = max(0.0, report_start - LEAD_PAD)
            clip_end = min(recording_durations[number], report_end + TAIL_PAD)
            overlap_before = 0.0
            overlap_after = 0.0
            if isinstance(previous_end, (int, float)):
                overlap_before = max(0.0, float(previous_end) - report_start)
                if overlap_before == 0:
                    clip_start = max(clip_start, float(previous_end) + SEPARATION_GUARD)
            if isinstance(next_start, (int, float)):
                overlap_after = max(0.0, report_end - float(next_start))
                if overlap_after == 0:
                    clip_end = min(clip_end, float(next_start) - SEPARATION_GUARD)
            clip_start = min(clip_start, report_start)
            clip_end = max(clip_end, report_end)

            group_key = (
                number,
                round(report_start, 6),
                round(report_end, 6),
                str(report.get("fullText") or ""),
            )
            shared_groups[group_key].append(locator)
            jobs.append({
                "n": locator,
                "source": str(report.get("sourceHadithNumber")),
                "book": int((report.get("reference") or {}).get("book") or 0),
                "recording": number,
                "sourceAudio": source_audio,
                "report": report,
                "clipStart": clip_start,
                "clipEnd": clip_end,
                "overlapBefore": round(overlap_before, 3),
                "overlapAfter": round(overlap_after, 3),
                "groupKey": group_key,
                "boundaryRepairBefore": report.get("_boundaryRepairBefore"),
                "boundaryRepairAfter": report.get("_boundaryRepairAfter"),
            })

    master_for: dict[str, str] = {}
    for members in shared_groups.values():
        master = members[0]
        for member in members:
            master_for[member] = master

    jobs_by_id = {job["n"]: job for job in jobs}
    selected_jobs = [job for job in jobs if master_for[job["n"]] == job["n"]]
    state = {
        "phase": "nasai_clip_build",
        "status": "dry_run" if args.dry_run else "running",
        "processed": 0,
        "total": len(selected_jobs),
        "timingReports": len(jobs),
        "nonplayable": len(nonplayable),
        "failures": [],
    }
    atomic_json(progress_path, state)

    def build_master(job: dict[str, Any]) -> dict[str, Any]:
        locator = job["n"]
        output_audio = clips_dir / f"{stem(locator)}.mp3"
        if args.dry_run:
            return {"n": locator, "audio": output_audio.name, "skipped": True}
        existing_duration = 0.0
        if output_audio.exists() and output_audio.stat().st_size > 1024:
            try:
                existing_duration = ffprobe_duration(output_audio)
            except (subprocess.CalledProcessError, ValueError):
                existing_duration = 0.0
        if args.force or existing_duration <= 0.1:
            duration = job["clipEnd"] - job["clipStart"]
            command = [
                "ffmpeg", "-v", "error", "-y",
                "-ss", f"{job['clipStart']:.3f}",
                "-i", str(job["sourceAudio"]),
                "-t", f"{duration:.3f}",
                "-c:a", "libmp3lame", "-b:a", "32k", "-ar", "16000", "-ac", "1",
                str(output_audio),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0 or not output_audio.exists():
                raise RuntimeError(result.stderr.strip() or "ffmpeg did not create output")
            existing_duration = ffprobe_duration(output_audio)
        return {"n": locator, "audio": output_audio.name, "duration": existing_duration}

    results: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        future_jobs = {pool.submit(build_master, job): job for job in selected_jobs}
        for future in as_completed(future_jobs):
            job = future_jobs[future]
            try:
                results[job["n"]] = future.result()
            except Exception as error:  # continue and preserve the failure queue
                failures.append({"n": job["n"], "error": str(error)})
            state.update({"processed": len(results) + len(failures), "failures": failures})
            atomic_json(progress_path, state)
            if state["processed"] % 50 == 0 or state["processed"] == state["total"]:
                print(f"processed {state['processed']}/{state['total']} failures={len(failures)}", flush=True)

    emitted_timings: list[str] = []
    if not args.dry_run:
        for job in jobs:
            locator = job["n"]
            master = master_for[locator]
            master_result = results.get(master)
            if master_result is None:
                existing = clips_dir / f"{stem(master)}.mp3"
                if not existing.exists():
                    continue
                master_result = {"audio": existing.name, "duration": ffprobe_duration(existing)}
            tokens = []
            for token in job["report"].get("tokens") or []:
                start = token.get("start")
                end = token.get("end")
                token_id = str(token.get("id"))
                token_text = str(token.get("text") or "")
                repair = repairs.get(token_id)
                if repair:
                    if token_text != repair["from"]:
                        raise ValueError(f"repair source mismatch for {token_id}")
                    token_text = repair["to"]
                item: dict[str, Any] = {
                    "id": token_id,
                    "text": token_text,
                    "start": round(float(start) - job["clipStart"], 3) if isinstance(start, (int, float)) else None,
                    "end": round(float(end) - job["clipStart"], 3) if isinstance(end, (int, float)) else None,
                    "status": token.get("status"),
                }
                if token.get("similarity") is not None:
                    item["similarity"] = token.get("similarity")
                if token.get("audioStatus") is not None:
                    item["audioStatus"] = token.get("audioStatus")
                tokens.append(item)
            sidecar = {
                "kind": "hadith/timing/v1",
                "collection": "nasai",
                "n": locator,
                "book": job["book"],
                "audio": master_result["audio"],
                "duration": round(float(master_result["duration"]), 3),
                "clipStartInRecording": round(job["clipStart"], 3),
                "clipEndInRecording": round(job["clipEnd"], 3),
                "recording": f"{job['recording']}.mp3",
                "sourceHadithNumber": job["source"],
                "synthetic": False,
                "source": "reviewed CTC acoustic alignment over the original Nasa'i recitation",
                "publicationState": job["report"].get("status"),
                "coverage": job["report"].get("coverage"),
                "quality": {
                    "overlapBeforeSeconds": job["overlapBefore"],
                    "overlapAfterSeconds": job["overlapAfter"],
                    "boundaryReviewRecommended": bool(job["overlapBefore"] or job["overlapAfter"]),
                    "sharedAudioWith": master if master != locator else None,
                    "boundaryRepairBefore": job.get("boundaryRepairBefore"),
                    "boundaryRepairAfter": job.get("boundaryRepairAfter"),
                    "canonicalRepairTokenIds": [
                        str(token.get("id")) for token in job["report"].get("tokens") or []
                        if str(token.get("id")) in repairs
                    ],
                },
                "tokens": tokens,
            }
            timing_path = timings_dir / f"n{stem(locator)}.json"
            atomic_json(timing_path, sidecar)
            emitted_timings.append(locator)

    output_manifest = {
        "schema": "hadith/nasai-app-ready-clip-build/v1",
        "mode": "dry-run" if args.dry_run else "build",
        "sourcePackage": str(args.package_dir),
        "sourceAudio": str(args.audio_dir),
        "settings": {"leadPad": LEAD_PAD, "tailPad": TAIL_PAD, "separationGuard": SEPARATION_GUARD},
        "summary": {
            "selectedTimingReports": len(jobs),
            "uniqueAudioClips": len(selected_jobs),
            "emittedTimingReports": len(emitted_timings),
            "fullyUntimedReports": len(nonplayable),
            "sharedAudioReports": sum(1 for locator, master in master_for.items() if locator != master),
            "boundaryReviewReports": sum(1 for job in jobs if job["overlapBefore"] or job["overlapAfter"]),
            "boundaryRepairs": len(boundary_repairs),
            "canonicalRepairs": len(repairs),
            "failures": len(failures),
        },
        "nonplayable": nonplayable,
        "failures": failures,
        "boundaryRepairs": boundary_repairs,
        "boundaryReview": [
            {key: job[key] for key in ("n", "source", "recording", "overlapBefore", "overlapAfter")}
            for job in jobs if job["overlapBefore"] or job["overlapAfter"]
        ],
    }
    atomic_json(manifest_path, output_manifest)
    state.update({"status": "complete" if not failures else "complete_with_failures", "failures": failures})
    atomic_json(progress_path, state)
    print(json.dumps(output_manifest["summary"], indent=2))
    print(f"manifest={manifest_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
