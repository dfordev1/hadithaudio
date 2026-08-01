#!/usr/bin/env python3
"""Generate clearly labelled synthetic audio for Muslim reports absent from the recording."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qc" / "muslim-full" / "timings"
OUTPUT = ROOT / "qc" / "muslim-full" / "generated-clips"
TIMING = ROOT / "qc" / "muslim-full" / "generated-timings"
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
TEMPO = 0.90


def load_env() -> None:
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def generate(number: int, key: str) -> dict:
    original = json.loads((SOURCE / f"m{number:04d}.json").read_text(encoding="utf-8"))
    if original.get("audio"):
        raise RuntimeError(f"Muslim {number} already has original audio")
    pieces: list[str] = []
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for token in original["tokens"]:
        if pieces:
            pieces.append(" ")
            cursor += 1
        value = token["text"]
        start = cursor
        pieces.append(value)
        cursor += len(value)
        ranges.append((start, cursor))
    text = "".join(pieces)
    body = json.dumps({
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.86,
            "similarity_boost": 0.72,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"
        "?output_format=mp3_22050_32",
        data=body,
        method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    audio_path = OUTPUT / f"{number:04d}.mp3"
    raw_path = OUTPUT / f"{number:04d}.raw.mp3"
    raw_path.write_bytes(base64.b64decode(result["audio_base64"]))
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_path),
        "-filter:a", f"atempo={TEMPO}", "-c:a", "libmp3lame", "-b:a", "32k", str(audio_path),
    ], check=True)
    raw_path.unlink()
    # Raw alignment indexes correspond exactly to the submitted Arabic text.
    # Normalized alignment may expand or contract Arabic characters.
    alignment = result["alignment"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(audio_path),
    ], text=True))
    tokens = []
    for source_token, (start_index, end_index) in zip(original["tokens"], ranges):
        valid = [
            index for index in range(start_index, min(end_index, len(starts)))
            if text[index].strip()
        ]
        start = (starts[valid[0]] if valid else (ends[start_index - 1] if start_index else 0.0)) / TEMPO
        end = (ends[valid[-1]] if valid else start * TEMPO) / TEMPO
        tokens.append({
            "id": source_token["id"],
            "position": source_token["position"],
            "text": source_token["text"],
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "timingEvidence": "elevenlabs_character_alignment",
        })
    payload = {
        "kind": "muslim-synthetic-supplement-v1",
        "collection": "muslim",
        "n": number,
        "audio": audio_path.name,
        "duration": round(duration, 3),
        "status": "synthetic_audio_not_in_original_recording",
        "synthetic": True,
        "provider": "ElevenLabs",
        "model": "eleven_multilingual_v2",
        "voiceId": VOICE_ID,
        "tempo": TEMPO,
        "disclosure": "Generated recitation; this report is not present in the original recording.",
        "tokens": tokens,
    }
    TIMING.mkdir(parents=True, exist_ok=True)
    (TIMING / f"m{number:04d}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "n": number,
        "duration": round(duration, 3),
        "tokens": len(tokens),
        "bounds": all(0 <= token["start"] <= token["end"] <= duration + 0.1 for token in tokens),
        "audio": str(audio_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbers", default="2075")
    args = parser.parse_args()
    load_env()
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not configured")
    results = [generate(int(value), key) for value in args.numbers.split(",") if value.strip()]
    key = ""
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()


