#!/usr/bin/env python3
"""Convert full-corpus Sahih Muslim alignments into per-hadith site assets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALIGNMENTS = ROOT / "qc" / "muslim-full-alignments" / "alignment"
AUDIO = Path(r"C:\Users\Dv\Downloads\Hadith\Muslim\audio\saheh-muslim-mp3")
OUT = ROOT / "qc" / "muslim-full"
TIMINGS = OUT / "timings"
CLIPS = OUT / "clips"


def source_audio(recording: str) -> Path:
    matches = sorted(AUDIO.glob(f"{recording}*.mp3"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one source MP3 for recording {recording}, found {len(matches)}")
    return matches[0]


def report_paths() -> list[Path]:
    return sorted(ALIGNMENTS.glob("*/reports/*.json"), key=lambda path: int(path.stem))


def add_display_timings(tokens: list[dict]) -> int:
    """Interpolate unmatched runs only when enclosed by acoustic anchors."""
    changed = 0
    index = 0
    while index < len(tokens):
        if tokens[index].get("status") != "unmatched" or tokens[index].get("start") is not None:
            index += 1
            continue
        first = index
        while (index + 1 < len(tokens) and tokens[index + 1].get("status") == "unmatched"
               and tokens[index + 1].get("start") is None):
            index += 1
        last = index
        left = next((i for i in range(first - 1, -1, -1) if tokens[i].get("end") is not None), None)
        right = next((i for i in range(last + 1, len(tokens)) if tokens[i].get("start") is not None), None)
        if left is not None and right is not None:
            start = float(tokens[left]["end"])
            end = float(tokens[right]["start"])
            if end > start:
                group = tokens[first:last + 1]
                weights = [max(1, len(re.sub(r"[^\u0621-\u064a]", "", token["text"]))) for token in group]
                total = sum(weights)
                cursor = start
                for offset, (token, token_weight) in enumerate(zip(group, weights)):
                    token_end = end if offset == len(group) - 1 else cursor + (end - start) * token_weight / total
                    token["displayStart"] = round(cursor, 3)
                    token["displayEnd"] = round(token_end, 3)
                    token["timingEvidence"] = "interpolated_between_acoustic_anchors"
                    cursor = token_end
                    changed += 1
        index += 1
    return changed


def add_constrained_display_timings(tokens: list[dict], duration: float | None) -> int:
    """Repair remaining edge and zero-gap orphans without changing acoustic evidence."""
    changed = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.get("start") is not None or token.get("displayStart") is not None:
            index += 1
            continue
        first = index
        while (index + 1 < len(tokens) and tokens[index + 1].get("start") is None
               and tokens[index + 1].get("displayStart") is None):
            index += 1
        last = index
        orphan_indices = [
            i for i in range(first, last + 1) if tokens[i].get("status") == "unmatched"
        ]
        if not orphan_indices:
            index += 1
            continue
        left = next((i for i in range(first - 1, -1, -1) if tokens[i].get("end") is not None), None)
        right = next((i for i in range(last + 1, len(tokens)) if tokens[i].get("start") is not None), None)
        allocation = list(orphan_indices)
        evidence = None
        if left is not None and right is not None:
            start, end = float(tokens[left]["end"]), float(tokens[right]["start"])
            if end <= start:
                allocation = [left, *orphan_indices, right]
                start, end = float(tokens[left]["start"]), float(tokens[right]["end"])
                evidence = "redistributed_with_adjacent_acoustic_anchors"
        elif left is None and right is not None and duration is not None:
            start, end = 0.0, float(tokens[right]["start"])
            if end <= start:
                allocation = [*orphan_indices, right]
                end = float(tokens[right]["end"])
            evidence = "interpolated_from_clip_start"
        elif left is not None and right is None and duration is not None:
            start, end = float(tokens[left]["end"]), float(duration)
            if end <= start:
                allocation = [left, *orphan_indices]
                start = float(tokens[left]["start"])
            evidence = "interpolated_to_clip_end"
        else:
            index += 1
            continue
        if end <= start:
            index += 1
            continue
        weights = [
            max(1, len(re.sub(r"[^\u0621-\u064a]", "", tokens[i]["text"]))) for i in allocation
        ]
        total = sum(weights)
        cursor = start
        for offset, (token_index, token_weight) in enumerate(zip(allocation, weights)):
            token_end = end if offset == len(allocation) - 1 else cursor + (end - start) * token_weight / total
            target = tokens[token_index]
            target["displayStart"] = round(cursor, 3)
            target["displayEnd"] = round(token_end, 3)
            target["timingEvidence"] = evidence
            if token_index in orphan_indices:
                changed += 1
            cursor = token_end
        index += 1
    return changed


def normalize_display_timeline(tokens: list[dict]) -> int:
    """Remove collisions introduced when adjacent repairs share an anchor."""
    changed: set[int] = set()
    for _ in range(256):
        sequence = [
            i for i, token in enumerate(tokens)
            if (token.get("displayStart", token.get("start")) is not None
                and token.get("displayEnd", token.get("end")) is not None)
        ]
        runs: list[tuple[int, int]] = []
        run_start = None
        for offset in range(1, len(sequence)):
            previous = tokens[sequence[offset - 1]]
            current = tokens[sequence[offset]]
            previous_end = float(previous.get("displayEnd", previous.get("end")))
            current_start = float(current.get("displayStart", current.get("start")))
            current_end = float(current.get("displayEnd", current.get("end")))
            collides = current_start < previous_end - 0.0005 or current_end <= current_start
            if collides and run_start is None:
                run_start = offset - 1
            if run_start is not None and (not collides or offset == len(sequence) - 1):
                run_end = offset if collides and offset == len(sequence) - 1 else offset - 1
                runs.append((run_start, run_end))
                run_start = None
        if not runs:
            break
        for first, last in runs:
            indices = sequence[first:last + 1]
            start = min(float(tokens[i].get("displayStart", tokens[i].get("start"))) for i in indices)
            end = max(float(tokens[i].get("displayEnd", tokens[i].get("end"))) for i in indices)
            if end <= start:
                continue
            weights = [
                max(1, len(re.sub(r"[^\u0621-\u064a]", "", tokens[i]["text"]))) for i in indices
            ]
            total = sum(weights)
            cursor = start
            for offset, (token_index, token_weight) in enumerate(zip(indices, weights)):
                token_end = end if offset == len(indices) - 1 else cursor + (end - start) * token_weight / total
                target = tokens[token_index]
                target["displayStart"] = round(cursor, 4)
                target["displayEnd"] = round(token_end, 4)
                target["timingEvidence"] = "normalized_derived_display_timeline"
                changed.add(token_index)
                cursor = token_end
    return len(changed)


def convert(path: Path, make_clip: bool) -> dict:
    source = json.loads(path.read_text(encoding="utf-8"))
    number = int(source["report"]["hadithNumber"])
    recording = str(source["recording"]).zfill(3)
    clip_start = float(source["start"]) if source.get("start") is not None else None
    clip_end = float(source["end"]) if source.get("end") is not None else None
    duration = clip_end - clip_start if clip_start is not None and clip_end is not None else None
    if duration is not None and duration <= 0:
        raise RuntimeError(f"invalid report boundary for Muslim {number}: {clip_start}..{clip_end}")
    tokens = []
    for token in source["tokens"]:
        start, end = token.get("start"), token.get("end")
        tokens.append({
            "id": token["id"],
            "position": token["position"],
            "text": token["text"],
            "start": round(float(start) - clip_start, 3) if start is not None and clip_start is not None else None,
            "end": round(float(end) - clip_start, 3) if end is not None and clip_start is not None else None,
            "asrText": token.get("asrText"),
            "similarity": token.get("similarity"),
            "status": token.get("status"),
        })
    derived_display_tokens = add_display_timings(tokens)
    constrained_display_tokens = add_constrained_display_timings(tokens, duration)
    normalized_display_tokens = normalize_display_timeline(tokens)
    payload = {
        "kind": "muslim-full-acoustic-alignment",
        "collection": "muslim",
        "n": number,
        "audio": f"{number:04d}.mp3" if duration is not None else None,
        "duration": round(duration, 3) if duration is not None else None,
        "recording": recording,
        "sourceAudio": source_audio(recording).name,
        "sourceStart": clip_start,
        "sourceEnd": clip_end,
        "coverage": source.get("coverage"),
        "meanSimilarity": source.get("meanSimilarity"),
        "status": source.get("status"),
        "timestampPolicy": source.get("timestampPolicy"),
        "tokens": tokens,
        "derivedDisplayTokens": derived_display_tokens,
        "constrainedDisplayTokens": constrained_display_tokens,
        "normalizedDisplayTokens": normalized_display_tokens,
    }
    TIMINGS.mkdir(parents=True, exist_ok=True)
    timing_path = TIMINGS / f"m{number:04d}.json"
    timing_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if make_clip and duration is not None:
        CLIPS.mkdir(parents=True, exist_ok=True)
        clip_path = CLIPS / payload["audio"]
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{clip_start:.3f}", "-i", str(source_audio(recording)),
            "-t", f"{duration:.3f}", "-map_metadata", "-1",
            "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "32k",
            str(clip_path),
        ]
        subprocess.run(command, check=True)
    return {
        "n": number, "recording": recording,
        "duration": round(duration, 3) if duration is not None else None,
        "tokens": len(tokens), "timedTokens": sum(token["start"] is not None for token in tokens),
        "coverage": source.get("coverage"), "status": source.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbers", help="comma-separated Muslim report numbers")
    parser.add_argument("--all", action="store_true", help="convert every report")
    parser.add_argument("--clips", action="store_true", help="also create per-hadith MP3 clips")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    wanted = {int(value) for value in args.numbers.split(",")} if args.numbers else None
    paths = [path for path in report_paths() if wanted is None or int(path.stem) in wanted]
    if not args.all and wanted is None:
        raise SystemExit("Pass --numbers or --all")
    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda path: convert(path, args.clips), paths))
    else:
        results = [convert(path, args.clips) for path in paths]
    manifest = {
        "kind": "muslim-full-site-assets-v1",
        "summary": {
            "reports": len(results),
            "tokens": sum(item["tokens"] for item in results),
            "timedTokens": sum(item["timedTokens"] for item in results),
            "review": sum(item["status"] != "aligned" for item in results),
        },
        "items": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest["summary"], indent=2))


if __name__ == "__main__":
    main()


