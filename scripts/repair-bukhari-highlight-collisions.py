#!/usr/bin/env python3
"""Make overlapping Bukhari word-highlight intervals sequential."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "bukhari-asr-pilot" / "timings"
AUDIT = ROOT / "qc" / "bukhari-audio-sync-audit.json"
REPORT = ROOT / "qc" / "bukhari-highlight-collision-repair.json"


def weight(text: str) -> int:
    return max(1, len(re.sub(r"[^\u0621-\u063a\u0641-\u064a]", "", text)))


def collision_runs(tokens: list[dict]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for index in range(1, len(tokens)):
        collides = float(tokens[index]["start"]) < float(tokens[index - 1]["end"]) - 0.005
        if collides and start is None:
            start = index - 1
        if start is not None and (not collides or index == len(tokens) - 1):
            end = index if collides and index == len(tokens) - 1 else index - 1
            runs.append((start, end))
            start = None
    return runs


def repair(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    tokens = data.get("tokens") or []
    changes = []
    for first, last in collision_runs(tokens):
        group = tokens[first:last + 1]
        original_start = min(float(token["start"]) for token in group)
        original_end = max(float(token["end"]) for token in group)
        left_limit = float(tokens[first - 1]["end"]) if first else original_start
        right_limit = float(tokens[last + 1]["start"]) if last + 1 < len(tokens) else original_end
        start = max(left_limit, original_start)
        end = min(right_limit, original_end)
        if end <= start:
            start, end = left_limit, right_limit
        weights = [weight(token.get("text", "")) for token in group]
        total = sum(weights)
        cursor = start
        repaired = []
        for offset, (token, token_weight) in enumerate(zip(group, weights)):
            token_end = end if offset == len(group) - 1 else cursor + (end - start) * token_weight / total
            old = [float(token["start"]), float(token["end"])]
            token["start"] = round(cursor, 3)
            token["end"] = round(max(cursor + 0.001, token_end), 3)
            repaired.append({"position": token.get("position"), "old": old,
                             "new": [token["start"], token["end"]]})
            cursor = token_end
        changes.append({"firstIndex": first, "lastIndex": last,
                        "window": [round(start, 3), round(end, 3)], "tokens": repaired})
    remaining = collision_runs(tokens)
    if remaining:
        raise RuntimeError(f"collision repair incomplete for {path.stem}: {remaining}")
    if changes:
        data["highlightCollisionRepair"] = {
            "method": "sequential character-weighted interpolation between acoustic anchors",
            "runs": len(changes),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"n": int(data["n"]), "runs": len(changes),
            "tokensChanged": sum(len(change["tokens"]) for change in changes), "changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbers", help="comma-separated hadith numbers")
    args = parser.parse_args()
    if args.numbers:
        numbers = [int(value) for value in args.numbers.split(",") if value.strip()]
    else:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        numbers = [item["n"] for item in audit["items"]
                   if "overlapping-highlights" in item["issues"]]
    results = [repair(TIMINGS / f"n{number:04d}.json") for number in numbers]
    payload = {
        "kind": "bukhari-highlight-collision-repair-v1", "results": results,
        "summary": {"reports": len(results), "runs": sum(item["runs"] for item in results),
                    "tokensChanged": sum(item["tokensChanged"] for item in results)},
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print("numbers", ",".join(str(number) for number in numbers))


if __name__ == "__main__":
    main()


