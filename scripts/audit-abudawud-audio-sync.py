#!/usr/bin/env python3
"""Rank structural and alignment risks across every Abu Dawood audio clip."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "qc" / "abudawud-asr" / "timings"
CLIP_DIR = ROOT / "qc" / "abudawud-clips" / "timings"
BOOK_DIR = ROOT / "public" / "abudawud"
OUT = ROOT / "qc" / "abudawud-audio-sync-audit.json"


def norm(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = text.translate(str.maketrans("Ø¥Ø£Ø¢Ù±Ù‰Ø¤Ø¦", "Ø§Ø§Ø§Ø§ÙŠÙˆÙŠ"))
    return re.sub(r"[^\u0621-\u063a\u0641-\u064a]", "", text)


def lcs_count(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for a in left:
        current = [0]
        for j, b in enumerate(right, 1):
            current.append(previous[j - 1] + 1 if a == b else max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def report_intervals(data: dict) -> list[dict]:
    explicit = data.get("audioSegments") or []
    if explicit:
        return [
            {"recording": int(x["recording"]), "start": float(x["start"]), "end": float(x["end"])}
            for x in explicit
        ]
    grouped: dict[int, list[dict]] = defaultdict(list)
    for token in data.get("tokens", []):
        if token.get("recording") is not None:
            grouped[int(token["recording"])].append(token)
    return [
        {"recording": recording, "start": min(float(t["start"]) for t in tokens),
         "end": max(float(t["end"]) for t in tokens)}
        for recording, tokens in grouped.items()
    ]


def main() -> None:
    canonical = {}
    for path in BOOK_DIR.glob("book-*.json"):
        for report in json.loads(path.read_text(encoding="utf-8"))["hadith"]:
            canonical[int(report["n"])] = [norm(t["text"]) for t in report["tokens"] if norm(t["text"])]

    source = {}
    interval_rows = []
    for path in sorted(SOURCE_DIR.glob("n*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        number = int(data["n"])
        source[number] = data
        for interval in report_intervals(data):
            interval_rows.append({"n": number, **interval})

    cross_overlaps: dict[int, list[dict]] = defaultdict(list)
    by_recording: dict[int, list[dict]] = defaultdict(list)
    for row in interval_rows:
        by_recording[row["recording"]].append(row)
    for recording, rows in by_recording.items():
        rows.sort(key=lambda x: (x["start"], x["end"]))
        active = []
        for row in rows:
            active = [x for x in active if x["end"] > row["start"]]
            for other in active:
                if other["n"] == row["n"]:
                    continue
                overlap = min(other["end"], row["end"]) - max(other["start"], row["start"])
                if overlap >= 0.20:
                    detail = {"other": other["n"], "recording": recording, "seconds": round(overlap, 3),
                              "selfFraction": round(overlap / (row["end"] - row["start"]), 3),
                              "otherFraction": round(overlap / (other["end"] - other["start"]), 3)}
                    reverse = {"other": row["n"], "recording": recording, "seconds": round(overlap, 3),
                               "selfFraction": detail["otherFraction"], "otherFraction": detail["selfFraction"]}
                    cross_overlaps[row["n"]].append(detail)
                    cross_overlaps[other["n"]].append(reverse)
            active.append(row)

    items = []
    for number, data in sorted(source.items()):
        clip_path = CLIP_DIR / f"n{number:04d}.json"
        clip = json.loads(clip_path.read_text(encoding="utf-8")) if clip_path.exists() else None
        tokens = (clip or data).get("tokens", [])
        durations = [float(t["end"]) - float(t["start"]) for t in tokens]
        nonpositive = sum(value <= 0 for value in durations)
        overlaps = sum(float(tokens[i]["start"]) < float(tokens[i - 1]["end"]) - 0.005 for i in range(1, len(tokens)))
        interval_counts = Counter((round(float(t["start"]), 3), round(float(t["end"]), 3)) for t in tokens)
        shared_intervals = sum(count - 1 for count in interval_counts.values() if count > 1)
        short = sum(0 < value < 0.075 for value in durations)
        long = sum(value > 2.0 for value in durations)
        gaps = [
            round(float(tokens[i]["start"]) - float(tokens[i - 1]["end"]), 3)
            for i in range(1, len(tokens))
            if float(tokens[i]["start"]) - float(tokens[i - 1]["end"]) > 1.5
        ]
        spoken = [norm(t.get("text", "")) for t in tokens if norm(t.get("text", ""))]
        expected = canonical.get(number, [])
        matched = lcs_count(expected, spoken) if expected and spoken else 0
        canonical_coverage = matched / len(expected) if expected else 1.0
        exact_ratio = float(data.get("exactRatio", 0) or 0)
        clip_drop = max(0, len(data.get("tokens", [])) - len(tokens)) if clip else len(data.get("tokens", []))
        overlap_details = sorted(cross_overlaps.get(number, []), key=lambda x: -x["seconds"])
        nested_overlaps = [
            x for x in overlap_details
            if x["seconds"] >= 3 and (x["selfFraction"] >= 0.8 or x["otherFraction"] >= 0.8)
        ]
        known_variant = "rebuilt from spoken transcript" in data.get("boundaryRepair", "")

        definite = []
        if nonpositive: definite.append(f"{nonpositive} non-positive token intervals")
        if overlaps: definite.append(f"{overlaps} overlapping highlight intervals")
        if shared_intervals: definite.append(f"{shared_intervals} tokens share another token's full interval")
        if clip_drop: definite.append(f"{clip_drop} source tokens missing from built clip")
        boundary = []
        if nested_overlaps: boundary.append(f"source substantially contains/is contained by {len(nested_overlaps)} report interval(s)")
        likely = []
        if canonical_coverage < 0.80: likely.append(f"canonical spoken coverage {canonical_coverage:.1%}")
        if exact_ratio < 0.50: likely.append(f"acoustic exact ratio {exact_ratio:.1%}")
        if long: likely.append(f"{long} token intervals exceed 2 seconds")
        if gaps: likely.append(f"{len(gaps)} unexplained clip gaps exceed 1.5 seconds")
        if tokens and short / len(tokens) > 0.25: likely.append(f"{short / len(tokens):.1%} of tokens are under 75ms")
        if overlap_details and not nested_overlaps:
            likely.append(f"source touches/overlaps {len(overlap_details)} neighboring report interval(s)")

        score = (
            100 * bool(nonpositive or overlaps or clip_drop)
            + 80 * bool(nested_overlaps)
            + min(40, shared_intervals * 4)
            + max(0, (0.85 - canonical_coverage) * 100)
            + max(0, (0.60 - exact_ratio) * 50)
            + min(20, long * 2 + len(gaps) * 3)
        )
        classification = (
            "known-spoken-variant" if known_variant and not definite
            else "definite-failure" if definite
            else "boundary-review" if boundary
            else "listening-review" if likely
            else "clean-structural"
        )
        items.append({
            "n": number, "classification": classification, "score": round(score, 2),
            "tokens": len(tokens), "exactRatio": round(exact_ratio, 4),
            "canonicalSpokenCoverage": round(canonical_coverage, 4),
            "sourcePieces": len(report_intervals(data)), "definiteSignals": definite,
            "boundarySignals": boundary,
            "reviewSignals": likely, "crossReportOverlaps": overlap_details[:10],
            "metrics": {"nonpositive": nonpositive, "overlaps": overlaps,
                        "sharedIntervals": shared_intervals, "shortUnder75ms": short,
                        "longOver2s": long, "gapsOver1_5s": gaps[:10], "clipTokenDrop": clip_drop},
        })

    items.sort(key=lambda x: (-x["score"], x["n"]))
    counts = Counter(item["classification"] for item in items)
    payload = {
        "kind": "abudawud-audio-sync-audit-v1",
        "limitations": "Structural and transcript-risk audit; subtle pronunciation errors still require listening.",
        "summary": {"hadiths": len(items), **dict(counts)},
        "items": items,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print("top definite:", [x["n"] for x in items if x["classification"] == "definite-failure"][:30])
    print("top listening review:", [x["n"] for x in items if x["classification"] == "listening-review"][:30])
    print(OUT)


if __name__ == "__main__":
    main()

