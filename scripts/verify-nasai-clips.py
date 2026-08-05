#!/usr/bin/env python3
"""Verify every generated Nasa'i timing sidecar and unique MP3 clip.

This is the publication gate between the local clip build and the R2 uploader.
It derives the expected report set from the current reader, validates timing
structure and canonical token identity, probes every unique audio file, and
writes a machine-readable QA report without modifying corpus data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "qc" / "nasai-app-ready-full"
DEFAULT_READER = ROOT / "public" / "nasai"
EXPECTED_TIMINGS = 5673
EXPECTED_AUDIO = 5672
EXPECTED_TEXT_REPORTS = 5679
EXPECTED_NONPLAYABLE = {"17", "434b", "731", "1343", "2827", "2927"}
EXPECTED_SHARED = {"352": "0352.mp3", "353": "0352.mp3"}
ARABIC_RE = re.compile(r"[\u0621-\u064a]")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    return {
        "duration": float((data.get("format") or {}).get("duration") or 0),
        "codec": stream.get("codec_name"),
        "sampleRate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "bytes": path.stat().st_size,
    }


def reader_tokens(reader_dir: Path) -> dict[str, dict[str, str]]:
    reports: dict[str, dict[str, str]] = {}
    for path in sorted(reader_dir.glob("book-*.json")):
        data = load_json(path)
        for report in data.get("hadith") or []:
            locator = str(report["n"])
            if locator in reports:
                raise ValueError(f"duplicate reader report {locator}")
            tokens: dict[str, str] = {}
            for token in report.get("tokens") or []:
                token_id = str(token["id"])
                if token_id in tokens:
                    raise ValueError(f"duplicate token ID in reader report {locator}: {token_id}")
                tokens[token_id] = str(token.get("text") or "")
            reports[locator] = tokens
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--reader", type=Path, default=DEFAULT_READER)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--quick", action="store_true", help="skip probing every MP3")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    clips_dir = args.base / "clips"
    timings_dir = args.base / "timings"
    manifest_path = args.base / "manifest.json"
    output_path = args.output or args.base / "qa" / "clip-verification.json"
    errors: list[str] = []
    warnings: list[str] = []

    if not manifest_path.exists():
        raise SystemExit(f"missing build manifest: {manifest_path}")
    manifest = load_json(manifest_path)
    reader = reader_tokens(args.reader)
    timing_files = sorted(timings_dir.glob("n*.json"))
    timing_ids = {
        str(int(path.stem[1:])) if path.stem[1:].isdigit() else path.stem[1:]
        for path in timing_files
    }
    nonplayable = {str(item["n"]) for item in manifest.get("nonplayable") or []}

    if len(reader) != EXPECTED_TEXT_REPORTS:
        errors.append(f"reader reports {len(reader)} != {EXPECTED_TEXT_REPORTS}")
    if len(timing_files) != EXPECTED_TIMINGS:
        errors.append(f"timing files {len(timing_files)} != {EXPECTED_TIMINGS}")
    if nonplayable != EXPECTED_NONPLAYABLE:
        errors.append(f"nonplayable IDs {sorted(nonplayable)} != {sorted(EXPECTED_NONPLAYABLE)}")
    expected_timed = set(reader) - EXPECTED_NONPLAYABLE
    if timing_ids != expected_timed:
        missing = sorted(expected_timed - timing_ids)
        extra = sorted(timing_ids - expected_timed)
        errors.append(f"timing ID mismatch: missing={missing[:20]} extra={extra[:20]}")

    referenced_audio: dict[str, list[str]] = {}
    total_tokens = 0
    timed_tokens = 0
    null_lexical_tokens = 0
    timing_bytes = 0
    canonical_mismatches = 0
    for path in timing_files:
        try:
            data = load_json(path)
        except Exception as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        timing_bytes += path.stat().st_size
        locator = str(data.get("n"))
        expected_name = f"n{locator.zfill(4) if locator.isdigit() else locator}.json"
        if path.name != expected_name:
            errors.append(f"{path.name}: locator/name mismatch ({locator})")
        if data.get("kind") != "hadith/timing/v1" or data.get("collection") != "nasai":
            errors.append(f"{path.name}: invalid kind/collection")
        if data.get("synthetic") is not False:
            errors.append(f"{path.name}: synthetic disclosure must be false")
        audio = str(data.get("audio") or "")
        if not re.fullmatch(r"(?:\d{4}|\d+[a-z])\.mp3", audio):
            errors.append(f"{path.name}: invalid audio filename {audio!r}")
        referenced_audio.setdefault(audio, []).append(locator)
        duration = data.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            errors.append(f"{path.name}: invalid duration {duration!r}")
            duration = 0.0
        seen_ids: set[str] = set()
        last_start = -1.0
        report_reader = reader.get(locator, {})
        for index, token in enumerate(data.get("tokens") or []):
            total_tokens += 1
            token_id = str(token.get("id"))
            text = str(token.get("text") or "")
            if token_id in seen_ids:
                errors.append(f"{path.name}: duplicate token ID {token_id}")
            seen_ids.add(token_id)
            if report_reader.get(token_id) != text:
                canonical_mismatches += 1
                if canonical_mismatches <= 20:
                    errors.append(f"{path.name}: reader mismatch at {token_id}")
            start, end = token.get("start"), token.get("end")
            if start is None and end is None:
                if ARABIC_RE.search(text):
                    null_lexical_tokens += 1
                continue
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                errors.append(f"{path.name}: partial/invalid interval at token {index}")
                continue
            timed_tokens += 1
            if start < -0.001 or end <= start or end > float(duration) + 0.08:
                errors.append(f"{path.name}: out-of-bounds interval {start}..{end} / {duration} at {token_id}")
            if start + 0.001 < last_start:
                errors.append(f"{path.name}: token start reversal at {token_id}")
            last_start = max(last_start, float(start))
        if set(report_reader) != seen_ids:
            missing_ids = sorted(set(report_reader) - seen_ids)
            extra_ids = sorted(seen_ids - set(report_reader))
            errors.append(f"{path.name}: token-set mismatch missing={missing_ids[:5]} extra={extra_ids[:5]}")

    if len(referenced_audio) != EXPECTED_AUDIO:
        errors.append(f"referenced audio {len(referenced_audio)} != {EXPECTED_AUDIO}")
    for locator, expected_audio in EXPECTED_SHARED.items():
        timing_path = timings_dir / f"n{locator.zfill(4)}.json"
        if timing_path.exists() and load_json(timing_path).get("audio") != expected_audio:
            errors.append(f"report {locator} must reference {expected_audio}")
    shared = {name: ids for name, ids in referenced_audio.items() if len(ids) > 1}
    if shared != {"0352.mp3": ["352", "353"]}:
        errors.append(f"unexpected shared-audio map: {shared}")

    present_audio = {path.name for path in clips_dir.glob("*.mp3")}
    missing_audio = sorted(set(referenced_audio) - present_audio)
    extra_audio = sorted(present_audio - set(referenced_audio))
    if missing_audio:
        errors.append(f"missing audio files: {missing_audio[:20]}")
    if extra_audio:
        warnings.append(f"unreferenced audio files: {extra_audio[:20]}")

    probe_results: dict[str, dict[str, Any]] = {}
    probe_failures: list[str] = []
    if not args.quick:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {pool.submit(ffprobe, clips_dir / name): name for name in referenced_audio if name in present_audio}
            for completed, future in enumerate(as_completed(futures), 1):
                name = futures[future]
                try:
                    probe_results[name] = future.result()
                except Exception as exc:
                    probe_failures.append(f"{name}: {exc}")
                if completed % 500 == 0 or completed == len(futures):
                    print(f"probed {completed}/{len(futures)}; failures={len(probe_failures)}", flush=True)
        errors.extend(f"ffprobe failed: {item}" for item in probe_failures[:20])
        for name, probe in probe_results.items():
            if probe["codec"] != "mp3" or probe["sampleRate"] != 16000 or probe["channels"] != 1:
                errors.append(f"{name}: unexpected media {probe}")
            for locator in referenced_audio[name]:
                timing = load_json(timings_dir / f"n{locator.zfill(4) if locator.isdigit() else locator}.json")
                if abs(float(timing["duration"]) - probe["duration"]) > 0.08:
                    errors.append(f"{name}: duration mismatch for {locator}")

    boundary_repairs = manifest.get("boundaryRepairs") or []
    if len(boundary_repairs) != 50:
        errors.append(f"boundary repairs {len(boundary_repairs)} != 50")
    for repair in boundary_repairs:
        previous = load_json(timings_dir / f"n{str(repair['previous']).zfill(4)}.json")
        current = load_json(timings_dir / f"n{str(repair['next']).zfill(4)}.json")
        if not previous.get("quality", {}).get("boundaryRepairAfter"):
            errors.append(f"missing boundaryRepairAfter metadata on {repair['previous']}")
        if not current.get("quality", {}).get("boundaryRepairBefore"):
            errors.append(f"missing boundaryRepairBefore metadata on {repair['next']}")

    audio_bytes = sum(result["bytes"] for result in probe_results.values()) if probe_results else sum(
        (clips_dir / name).stat().st_size for name in referenced_audio if (clips_dir / name).exists()
    )
    report = {
        "schema": "hadith/nasai-clip-verification/v1",
        "status": "pass" if not errors else "fail",
        "summary": {
            "readerReports": len(reader),
            "timingReports": len(timing_files),
            "uniqueAudioClips": len(referenced_audio),
            "nonplayableReports": len(nonplayable),
            "sharedAudioMappings": len(shared),
            "tokens": total_tokens,
            "timedTokens": timed_tokens,
            "untimedLexicalTokens": null_lexical_tokens,
            "boundaryRepairs": len(boundary_repairs),
            "probedAudio": len(probe_results),
            "audioBytes": audio_bytes,
            "timingBytes": timing_bytes,
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "expectedNonplayable": sorted(EXPECTED_NONPLAYABLE),
        "sharedAudio": shared,
        "errors": errors,
        "warnings": warnings,
    }
    atomic_json(output_path, report)
    print(json.dumps(report["summary"], indent=2))
    print(f"verification={output_path}")
    if errors:
        print("first errors:")
        print("\n".join(errors[:30]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
