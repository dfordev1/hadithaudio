#!/usr/bin/env python3
"""Build full-isnad+matn Muwatta reader data, clips, and timing maps."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "qc" / "muwatta-full"
ALIGNMENTS = BASE / "alignment"
SOURCE_AUDIO = Path(r"C:\Users\Dv\Downloads\Muwatta_201504")
CLIPS = BASE / "clips"
TIMINGS = BASE / "timings"


def norm(text: str) -> str:
    text = re.sub(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06edـ]", "", text or "")
    text = re.sub(r"[^\u0621-\u063a\u0641-\u064a\u0671]", "", text)
    return text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")


def source_audio(recording: str) -> Path:
    found = sorted(SOURCE_AUDIO.glob(f"{recording}*.mp3"))
    if len(found) != 1:
        raise RuntimeError(f"recording {recording}: expected one MP3, found {len(found)}")
    return found[0]


def report_paths() -> list[Path]:
    return sorted(ALIGNMENTS.glob("*/reports/*.json"), key=lambda p: int(p.stem))


def allocate(tokens: list[dict], duration: float) -> int:
    """Add a monotonic display timeline while preserving acoustic timestamps."""
    changed = 0
    index = 0
    while index < len(tokens):
        if tokens[index].get("start") is not None:
            index += 1
            continue
        first = index
        while index + 1 < len(tokens) and tokens[index + 1].get("start") is None:
            index += 1
        last = index
        left = next((i for i in range(first - 1, -1, -1) if tokens[i].get("end") is not None), None)
        right = next((i for i in range(last + 1, len(tokens)) if tokens[i].get("start") is not None), None)
        start = float(tokens[left]["end"]) if left is not None else 0.0
        end = float(tokens[right]["start"]) if right is not None else duration
        if end <= start:
            start = float(tokens[left]["start"]) if left is not None else 0.0
            end = float(tokens[right]["end"]) if right is not None else duration
        if end > start:
            group = tokens[first:last + 1]
            weights = [max(1, len(norm(item["text"]))) for item in group]
            total = sum(weights)
            cursor = start
            for offset, (item, weight) in enumerate(zip(group, weights)):
                item_end = end if offset == len(group) - 1 else cursor + (end - start) * weight / total
                item["displayStart"] = round(cursor, 4)
                item["displayEnd"] = round(item_end, 4)
                item["timingEvidence"] = "derived_between_acoustic_constraints"
                cursor = item_end
                changed += 1
        index += 1
    return changed


def convert(path: Path, make_clip: bool) -> dict:
    source = json.loads(path.read_text(encoding="utf-8"))
    number = int(source["report"]["hadithNumber"])
    recording = str(source["recording"]).zfill(3)
    clip_start, clip_end = source.get("start"), source.get("end")
    if clip_start is None or clip_end is None:
        return {"n": number, "status": "synthetic_required", "coverage": source.get("coverage")}
    clip_start = max(0.0, float(clip_start) - 0.18)
    source_duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(source_audio(recording)),
    ], text=True).strip())
    clip_end = min(source_duration, float(clip_end) + 0.28)
    duration = clip_end - clip_start
    tokens = []
    for position, token in enumerate(source["tokens"], 1):
        start, end = token.get("start"), token.get("end")
        tokens.append({
            "id": f"uh:token:malik.{number:04d}:{position:04d}", "position": position,
            "text": token["text"],
            "start": round(float(start) - clip_start, 4) if start is not None else None,
            "end": round(float(end) - clip_start, 4) if end is not None else None,
            "asrText": token.get("asrText"), "similarity": token.get("similarity"),
            "status": token.get("status"),
        })
    derived = allocate(tokens, duration)
    CLIPS.mkdir(parents=True, exist_ok=True)
    TIMINGS.mkdir(parents=True, exist_ok=True)
    audio_name = f"{number:04d}.mp3"
    payload = {
        "kind": "muwatta-full-word-stream-v1", "collection": "malik", "n": number,
        "audio": audio_name, "duration": round(duration, 4), "recording": recording,
        "sourceStart": clip_start, "sourceEnd": clip_end,
        "coverage": source.get("coverage"), "meanSimilarity": source.get("meanSimilarity"),
        "status": source.get("status"), "derivedDisplayTokens": derived,
        "disclosure": "Derived display timings are constrained by neighbouring acoustic matches.",
        "tokens": tokens,
    }
    (TIMINGS / f"n{number:04d}.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    destination = CLIPS / audio_name
    if make_clip and (not destination.exists() or destination.stat().st_size == 0):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{clip_start:.4f}", "-i", str(source_audio(recording)),
            "-t", f"{duration:.4f}", "-map_metadata", "-1", "-ac", "1", "-ar", "24000",
            "-c:a", "libmp3lame", "-b:a", "32k", str(destination),
        ], check=True)
    return {"n": number, "status": "original", "duration": duration, "tokens": len(tokens), "derived": derived}


def merge_reader() -> dict:
    source_by_number = {}
    for path in report_paths():
        data = json.loads(path.read_text(encoding="utf-8"))
        source_by_number[int(data["report"]["hadithNumber"])] = data

    pool: dict[str, Counter] = defaultdict(Counter)
    for path in (ROOT / "public" / "gloss").glob("malik-*.json"):
        number = int(path.stem.split("-")[1])
        book = json.loads((ROOT / "public" / "malik" / f"book-{source_by_number[number]['report']['reference']['book']}.json").read_text(encoding="utf-8"))
        report = next((row for row in book["hadith"] if int(row["n"]) == number), None)
        if not report:
            continue
        gloss = json.loads(path.read_text(encoding="utf-8"))
        for token in report.get("tokens", []):
            value = gloss.get("glosses", {}).get(token["id"])
            if value and norm(token["text"]):
                pool[norm(token["text"])][json.dumps(value, ensure_ascii=False, sort_keys=True)] += 1

    changed = glossed = 0
    for book_path in sorted((ROOT / "public" / "malik").glob("book-*.json")):
        book = json.loads(book_path.read_text(encoding="utf-8"))
        for report in book["hadith"]:
            number = int(report["n"])
            source = source_by_number[number]
            new_tokens, new_glosses = [], {}
            for position, token in enumerate(source["tokens"], 1):
                token_id = f"uh:token:malik.{number:04d}:{position:04d}"
                new_tokens.append({"id": token_id, "text": token["text"]})
                candidates = pool.get(norm(token["text"]))
                if candidates:
                    new_glosses[token_id] = json.loads(candidates.most_common(1)[0][0]); glossed += 1
            report["tokens"] = new_tokens
            report["isnad"] = ""
            report["fullWordStream"] = True
            gloss_path = ROOT / "public" / "gloss" / f"malik-{number}.json"
            existing = json.loads(gloss_path.read_text(encoding="utf-8"))
            existing["glosses"] = new_glosses
            existing["note"] = "Full canonical isnad and matn word stream; pooled machine glosses."
            gloss_path.write_text(json.dumps(existing, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            changed += 1
        book_path.write_text(json.dumps(book, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"reports": changed, "pooledGlosses": glossed, "poolWords": len(pool)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--merge-reader", action="store_true")
    parser.add_argument("--numbers")
    args = parser.parse_args()
    wanted = {int(v) for v in args.numbers.split(",")} if args.numbers else None
    paths = [p for p in report_paths() if wanted is None or int(p.stem) in wanted]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda p: convert(p, args.clips), paths))
    summary = {
        "reports": len(results), "original": sum(r["status"] == "original" for r in results),
        "syntheticRequired": sum(r["status"] == "synthetic_required" for r in results),
        "derivedDisplayTokens": sum(r.get("derived", 0) for r in results),
    }
    if args.merge_reader:
        summary["reader"] = merge_reader()
    (BASE / "release-manifest.json").write_text(json.dumps({"summary": summary, "items": results}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
