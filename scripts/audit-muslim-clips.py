#!/usr/bin/env python3
"""Audit generated Sahih Muslim clips against their timing maps."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "qc" / "muslim-full"
TIMINGS = BASE / "timings"
CLIPS = BASE / "clips"
REPORT = BASE / "clip-audit.json"


def probe(path: Path, decode: bool) -> tuple[float | None, str | None]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode:
        return None, result.stderr.strip() or "ffprobe failed"
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None, f"invalid ffprobe duration: {result.stdout!r}"
    if decode:
        decoded = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True,
        )
        if decoded.returncode or decoded.stderr.strip():
            return duration, decoded.stderr.strip() or "decode failed"
    return duration, None


def inspect(path: Path, decode: bool) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    number = int(data["n"])
    issues: list[str] = []
    tokens = data.get("tokens") or []
    timed = [token for token in tokens if token.get("start") is not None]
    if [token.get("position") for token in tokens] != list(range(1, len(tokens) + 1)):
        issues.append("token-position-sequence")
    duration = data.get("duration")
    audio_name = data.get("audio")
    media_duration = None
    if duration is None:
        if audio_name is not None or timed:
            issues.append("boundaryless-report-has-media")
    else:
        if not audio_name:
            issues.append("bounded-report-missing-audio-name")
        for token in timed:
            start, end = token.get("start"), token.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                issues.append("partial-token-range")
            elif start < 0 or end <= start or end > duration + 0.1:
                issues.append("invalid-token-range")
        if any(timed[index]["start"] < timed[index - 1]["end"] - 0.005
               for index in range(1, len(timed))):
            issues.append("overlapping-token-ranges")
        clip = CLIPS / str(audio_name)
        if not clip.exists():
            issues.append("missing-clip")
        elif clip.stat().st_size == 0:
            issues.append("empty-clip")
        else:
            media_duration, media_error = probe(clip, decode)
            if media_error:
                issues.append("media-error")
            if media_duration is not None and abs(media_duration - float(duration)) > 0.15:
                issues.append("duration-mismatch")
    return {
        "n": number, "status": data.get("status"), "issues": sorted(set(issues)),
        "expectedDuration": duration, "mediaDuration": media_duration,
        "tokens": len(tokens), "timedTokens": len(timed),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    paths = sorted(TIMINGS.glob("m*.json"))
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        items = list(pool.map(lambda path: inspect(path, args.decode), paths))
    referenced = {f"{item['n']:04d}.mp3" for item in items if item["expectedDuration"] is not None}
    actual = {path.name for path in CLIPS.glob("*.mp3")}
    failures = [item for item in items if item["issues"]]
    issue_counts = Counter(issue for item in failures for issue in item["issues"])
    payload = {
        "kind": "muslim-clip-audit-v1",
        "decodeChecked": args.decode,
        "summary": {
            "timingMaps": len(items), "expectedClips": len(referenced), "actualClips": len(actual),
            "missingClips": len(referenced - actual), "extraClips": len(actual - referenced),
            "failedReports": len(failures), "issues": dict(issue_counts),
        },
        "missing": sorted(referenced - actual), "extra": sorted(actual - referenced),
        "failures": failures,
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    if failures or referenced != actual:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


