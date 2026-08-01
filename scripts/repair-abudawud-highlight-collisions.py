#!/usr/bin/env python3
"""Sequentially interpolate overlapping Abu Dawood word-highlight intervals."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "abudawud-asr" / "timings"
AUDIT = ROOT / "qc" / "abudawud-audio-sync-audit.json"
REPORT = ROOT / "qc" / "abudawud-highlight-collision-repair.json"


def weight(text: str) -> int:
    return max(1, len(re.sub(r"[^\u0621-\u063a\u0641-\u064a]", "", text)))


def collision_runs(tokens: list[dict]) -> list[tuple[int, int]]:
    runs = []
    start = None
    for i in range(1, len(tokens)):
        same_recording = tokens[i].get("recording") == tokens[i - 1].get("recording")
        collides = same_recording and float(tokens[i]["start"]) < float(tokens[i - 1]["end"]) - 0.005
        if collides and start is None:
            start = i - 1
        if start is not None and (not collides or i == len(tokens) - 1):
            end = i if collides and i == len(tokens) - 1 else i - 1
            runs.append((start, end))
            start = None
    return runs


def repair(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    tokens = data.get("tokens", [])
    before = collision_runs(tokens)
    changes = []
    for first, last in before:
        group = tokens[first:last + 1]
        recording = group[0].get("recording")
        original_start = min(float(t["start"]) for t in group)
        original_end = max(float(t["end"]) for t in group)
        left_limit = (
            float(tokens[first - 1]["end"])
            if first and tokens[first - 1].get("recording") == recording else original_start
        )
        right_limit = (
            float(tokens[last + 1]["start"])
            if last + 1 < len(tokens) and tokens[last + 1].get("recording") == recording else original_end
        )
        desired = max(original_end - original_start, 0.12 * len(group))
        available = max(0.0, right_limit - left_limit)
        duration = min(desired, available) if available else original_end - original_start
        extra = max(0.0, duration - (original_end - original_start))
        left_room = max(0.0, original_start - left_limit)
        start = original_start - min(left_room, extra / 2)
        end = min(right_limit, start + duration)
        start = max(left_limit, end - duration)
        weights = [weight(t.get("text", "")) for t in group]
        total = sum(weights)
        cursor = start
        repaired = []
        for offset, (token, token_weight) in enumerate(zip(group, weights)):
            token_end = end if offset == len(group) - 1 else cursor + (end - start) * token_weight / total
            old = [float(token["start"]), float(token["end"])]
            token["start"] = round(cursor, 3)
            token["end"] = round(max(cursor, token_end), 3)
            token["sourceStart"] = token["start"]
            token["sourceEnd"] = token["end"]
            token["evidence"] = "interpolated_collision_repair"
            repaired.append({"position": token.get("position"), "text": token.get("text"),
                             "old": old, "new": [token["start"], token["end"]]})
            cursor = token_end
        changes.append({"firstIndex": first, "lastIndex": last, "recording": recording,
                        "window": [round(start, 3), round(end, 3)], "tokens": repaired})
    after = collision_runs(tokens)
    if after:
        raise RuntimeError(f"collision repair incomplete for {path.stem}: {after}")
    if changes:
        data["highlightCollisionRepair"] = {
            "method": "sequential character-weighted interpolation between acoustic anchors",
            "runs": len(changes),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"n": int(data["n"]), "runs": len(changes),
            "tokensChanged": sum(len(x["tokens"]) for x in changes), "changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbers", help="comma-separated report numbers")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if args.numbers:
        numbers = [int(x) for x in args.numbers.split(",")]
    else:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        numbers = [x["n"] for x in audit["items"] if x["classification"] == "definite-failure"][:args.limit]
    results = [repair(TIMINGS / f"n{number:04d}.json") for number in numbers]
    payload = {"kind": "abudawud-highlight-collision-repair-v1", "results": results,
               "summary": {"reports": len(results), "runs": sum(x["runs"] for x in results),
                           "tokensChanged": sum(x["tokensChanged"] for x in results)}}
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print("numbers", numbers)


if __name__ == "__main__":
    main()


