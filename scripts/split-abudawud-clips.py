#!/usr/bin/env python3
"""Create one web MP3 and clip-relative timing JSON per strong Abu Dawud report."""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


RECORDING_RANGES = (
    (1, 500, 1), (501, 1000, 2), (1001, 1500, 3),
    (1501, 2000, 4), (2001, 2500, 5), (2501, 3000, 6),
    (3001, 3500, 7), (3501, 4000, 8), (4001, 4500, 9),
    (4501, 4900, 10), (4901, 5274, 11),
)
SOURCE_DURATIONS = {
    "01_restored.flac": 16320.960, "02_restored.flac": 16322.688,
    "03_restored.flac": 16689.024,
    "04A_restored_000000-023000.flac": 9000.0, "04B_restored_from_023000.flac": 8221.248,
    "05A_restored_000000-023000.flac": 9000.0, "05B_restored_from_023000.flac": 8262.720,
    "06A_restored_000000-023000.flac": 9000.0, "06B_restored_from_023000.flac": 9686.592,
    "07A_restored_000000-023000.flac": 9000.0, "07B_restored_from_023000.flac": 7182.720,
    "08_restored.flac": 14048.640, "09_restored.flac": 16331.328,
    "10_restored.flac": 13939.776, "11_restored.flac": 11558.592,
}


def expected_recording(number: int) -> int:
    for start, end, recording in RECORDING_RANGES:
        if start <= number <= end:
            return recording
    raise ValueError(number)


def audio_filename(recording: int, timestamp: float) -> tuple[str, float]:
    if recording in {4, 5, 6, 7}:
        if timestamp < 9000:
            return f"{recording:02d}A_restored_000000-023000.flac", timestamp
        return f"{recording:02d}B_restored_from_023000.flac", timestamp - 9000
    return f"{recording:02d}_restored.flac", timestamp


def build_pieces(data: dict, padding: float) -> list[dict]:
    explicit = data.get("audioSegments") or []
    if explicit:
        pieces = []
        for segment in explicit:
            recording = int(segment["recording"])
            if segment.get("source"):
                source = segment["source"]
                end_source = source
                local_start = float(segment["start"])
                local_end = float(segment["end"])
                if local_end < local_start:
                    # Legacy cross-file sidecars stored the next file's local
                    # endpoint on the current Part A row.
                    local_end = SOURCE_DURATIONS[source]
                # Some sidecars retain recording-global timestamps while also
                # naming a Part B source; normalize those to file-local time.
                if "_from_023000" in source and local_end > SOURCE_DURATIONS[source]:
                    local_start -= 9000
                    local_end -= 9000
            else:
                source, local_start = audio_filename(recording, float(segment["start"]))
                end_source, local_end = audio_filename(recording, float(segment["end"]))
            if source != end_source:
                raise ValueError("explicit segment crosses a split source file")
            pieces.append({"source": source, "start": local_start, "end": local_end})
        if not pieces:
            raise ValueError("no explicit audio segments")
        for index in range(1, len(pieces)):
            previous, current = pieces[index - 1], pieces[index]
            if ("_000000-023000" in previous["source"]
                    and "_from_023000" in current["source"]
                    and current["start"] <= 0.5):
                current["start"] = 0.0
        pieces[0]["start"] = max(0.0, pieces[0]["start"] - padding)
        pieces[-1]["end"] = min(SOURCE_DURATIONS[pieces[-1]["source"]], pieces[-1]["end"] + padding)
        return pieces
    tokens = [t for t in data["tokens"] if t.get("recording") is not None]
    if not tokens:
        raise ValueError("no tokens in expected recording")
    pieces: list[dict] = []
    for token in tokens:
        source, local_start = audio_filename(recording, float(token["start"]))
        end_source, local_end = audio_filename(recording, float(token["end"]))
        if not pieces or pieces[-1]["source"] != source:
            pieces.append({"source": source, "start": local_start, "end": local_start})
        if source != end_source:
            pieces[-1]["end"] = SOURCE_DURATIONS[source]
            pieces.append({"source": end_source, "start": 0.0, "end": local_end})
        else:
            pieces[-1]["end"] = max(pieces[-1]["end"], local_end)
    pieces[0]["start"] = max(0.0, pieces[0]["start"] - padding)
    pieces[-1]["end"] = min(SOURCE_DURATIONS[pieces[-1]["source"]], pieces[-1]["end"] + padding)
    return pieces


def encode(source_dir: Path, destination: Path, pieces: list[dict]) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for piece in pieces:
        duration = piece["end"] - piece["start"]
        command += ["-ss", f'{piece["start"]:.3f}', "-t", f"{duration:.3f}",
                    "-i", str(source_dir / piece["source"])]
    if len(pieces) > 1:
        streams = "".join(f"[{i}:a]" for i in range(len(pieces)))
        command += ["-filter_complex", f"{streams}concat=n={len(pieces)}:v=0:a=1[out]", "-map", "[out]"]
    command += ["-vn", "-ac", "1", "-ar", "8000", "-codec:a", "libmp3lame",
                "-b:a", "32k", "-write_xing", "1", str(destination)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip()[-1000:])


def relative_tokens(data: dict, pieces: list[dict]) -> list[dict]:
    offsets = []
    elapsed = 0.0
    for piece in pieces:
        offsets.append((piece["source"], elapsed, piece["start"], piece["end"]))
        elapsed += piece["end"] - piece["start"]
    output = []
    clip_duration = sum(piece["end"] - piece["start"] for piece in pieces)
    for token in data["tokens"]:
        if token.get("recording") is None:
            continue
        recording = int(token["recording"])
        source, local_start = audio_filename(recording, float(token["start"]))
        end_source, local_end = audio_filename(recording, float(token["end"]))
        candidates = [row for row in offsets if row[0] == source and row[2] - .001 <= local_start <= row[3] + .001]
        end_candidates = [row for row in offsets if row[0] == end_source and row[2] - .001 <= local_end <= row[3] + .1]
        if not candidates or not end_candidates:
            continue
        _, base, piece_start, _ = candidates[0]
        _, end_base, end_piece_start, _ = end_candidates[-1]
        item = dict(token)
        relative_start = min(clip_duration, max(0.0, base + local_start - piece_start))
        relative_end = min(clip_duration, max(relative_start, end_base + local_end - end_piece_start))
        item["start"] = round(relative_start, 3)
        item["end"] = round(relative_end, 3)
        item.pop("sourceStart", None)
        item.pop("sourceEnd", None)
        output.append(item)
    return output


def process(path: Path, source_dir: Path, output_dir: Path, timing_dir: Path,
            padding: float, force: bool, allowed_statuses: set[str]) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    number = int(data["n"])
    if data.get("status") not in allowed_statuses:
        return {"n": number, "status": "skipped", "reason": data.get("status")}
    destination = output_dir / f"{number:04d}.mp3"
    timing_path = timing_dir / f"n{number:04d}.json"
    pieces = build_pieces(data, padding)
    if force or not destination.exists() or destination.stat().st_size == 0:
        encode(source_dir, destination, pieces)
    duration = sum(piece["end"] - piece["start"] for piece in pieces)
    tokens = relative_tokens(data, pieces)
    timing = {
        "kind": "abudawud-clip-timing-v1", "collection": "abudawud",
        "n": number, "audio": destination.name, "duration": round(duration, 3),
        "padding": padding, "exactRatio": data["exactRatio"], "status": data["status"],
        "sourcePieces": pieces, "text": data["text"], "tokens": tokens,
    }
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"n": number, "status": "done", "duration": duration,
            "bytes": destination.stat().st_size, "pieces": len(pieces)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timings", type=Path, default=Path("qc/abudawud-asr/timings"))
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--relative-timings", type=Path, default=Path("qc/abudawud-clips/timings"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--padding", type=float, default=0.2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--numbers", help="comma-separated hadith numbers")
    parser.add_argument("--statuses", default="pass", help="comma-separated source statuses")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.relative_timings.mkdir(parents=True, exist_ok=True)
    paths = sorted(args.timings.glob("n*.json"))
    if args.numbers:
        selected = {int(value) for value in args.numbers.split(",")}
        paths = [path for path in paths if int(path.stem[1:]) in selected]
    if args.limit:
        paths = paths[:args.limit]
    results = []
    allowed_statuses = {value.strip() for value in args.statuses.split(",") if value.strip()}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process, path, args.source_dir, args.output_dir,
                               args.relative_timings, args.padding, args.force,
                               allowed_statuses) for path in paths]
        for completed, future in enumerate(as_completed(futures), 1):
            try:
                results.append(future.result())
            except Exception as error:
                results.append({"status": "error", "error": str(error)})
            if completed % 250 == 0:
                print(f"processed {completed}/{len(futures)}", flush=True)
    counts = {status: sum(r["status"] == status for r in results)
              for status in ("done", "skipped", "error")}
    report = {"requested": len(paths), "counts": counts, "padding": args.padding,
              "bytes": sum(r.get("bytes", 0) for r in results), "items": results}
    report_path = args.relative_timings.parent / "split-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("requested", "counts", "padding", "bytes")}, indent=2))


if __name__ == "__main__":
    main()


