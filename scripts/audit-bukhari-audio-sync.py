#!/usr/bin/env python3
"""Audit Bukhari word timing maps for structural and alignment risks."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "bukhari-asr-pilot" / "timings"
OUTPUT = ROOT / "qc" / "bukhari-audio-sync-audit.json"


def inspect(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    tokens = data.get("tokens") or []
    duration = data.get("duration")
    issues: list[str] = []
    overlap_count = 0
    if not tokens:
        issues.append("empty-tokens")
    if [token.get("position") for token in tokens] != list(range(1, len(tokens) + 1)):
        issues.append("token-position-sequence")
    for index, token in enumerate(tokens):
        start, end = token.get("start"), token.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start < 0 or end <= start:
            issues.append("invalid-range")
            continue
        if isinstance(duration, (int, float)) and end > duration + 0.1:
            issues.append("past-audio-end")
        if index and start < float(tokens[index - 1]["end"]) - 0.005:
            overlap_count += 1
    if overlap_count:
        issues.append("overlapping-highlights")
    coverage = data.get("fa_coverage")
    cer = data.get("cer")
    wer = data.get("wer")
    structural = {"empty-tokens", "token-position-sequence", "invalid-range", "past-audio-end", "overlapping-highlights"}
    if structural.intersection(issues):
        classification = "definite-failure"
    elif isinstance(coverage, (int, float)) and coverage < 0.9:
        classification = "alignment-review"
    elif ((isinstance(cer, (int, float)) and cer > 0.25) or
          (isinstance(wer, (int, float)) and wer > 0.5)):
        classification = "text-review"
    else:
        classification = "clean-structural"
    return {
        "n": data.get("n"), "classification": classification, "issues": sorted(set(issues)),
        "tokens": len(tokens), "overlaps": overlap_count, "duration": duration,
        "faCoverage": coverage, "cer": cer, "wer": wer,
    }


def main() -> None:
    items = [inspect(path) for path in sorted(TIMINGS.glob("n*.json"))]
    summary = Counter(item["classification"] for item in items)
    payload = {
        "kind": "bukhari-audio-sync-audit-v1",
        "summary": {"hadiths": len(items), **dict(summary)},
        "items": items,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()


