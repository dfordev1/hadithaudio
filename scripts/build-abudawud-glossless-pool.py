#!/usr/bin/env python3
"""Pool Abu Dawood audio-synced words that fail to inherit an existing gloss.

This mirrors the reader's normalized LCS mapping, then groups the remaining
timing-token occurrences by normalized Arabic. Existing corpus glosses are
reported as reusable candidates so only genuinely novel/ambiguous forms need
new translation work.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOK_DIR = ROOT / "public" / "abudawud"
GLOSS_DIR = ROOT / "public" / "gloss"
TIMING_DIR = ROOT / "qc" / "abudawud-clips" / "timings"
OUT = ROOT / "qc" / "abudawud-synced-glossless-word-pool.json"


def norm(text: str) -> str:
    text = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    text = text.translate(str.maketrans("Ø¥Ø£Ø¢Ù±Ù‰Ø¤Ø¦", "Ø§Ø§Ø§Ø§ÙŠÙˆÙŠ"))
    return re.sub(r"[^\u0621-\u063a\u0641-\u064a]", "", text)


def stable(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def lcs_mapped_ids(source: list[dict], target: list[dict], glosses: dict) -> set[int]:
    """Return target indexes receiving a gloss, matching public/index.html."""
    left = [(i, norm(token["text"])) for i, token in enumerate(source)]
    left = [(i, value) for i, value in left if value]
    right = [(i, norm(token["text"])) for i, token in enumerate(target)]
    right = [(i, value) for i, value in right if value]
    rows, cols = len(left) + 1, len(right) + 1
    score = [[0] * cols for _ in range(rows)]
    for i in range(1, rows):
        for j in range(1, cols):
            score[i][j] = (
                score[i - 1][j - 1] + 1
                if left[i - 1][1] == right[j - 1][1]
                else max(score[i - 1][j], score[i][j - 1])
            )
    mapped: set[int] = set()
    i, j = len(left), len(right)
    while i and j:
        if left[i - 1][1] == right[j - 1][1]:
            source_token = source[left[i - 1][0]]
            value = glosses.get(source_token["id"], {})
            if value.get("en") and value.get("ur"):
                mapped.add(right[j - 1][0])
            i -= 1
            j -= 1
        elif score[i - 1][j] >= score[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return mapped


def main() -> None:
    reports: dict[int, dict] = {}
    known: dict[str, Counter[str]] = defaultdict(Counter)
    for book_path in BOOK_DIR.glob("book-*.json"):
        book = json.loads(book_path.read_text(encoding="utf-8"))
        for report in book["hadith"]:
            number = int(report["n"])
            gloss_path = GLOSS_DIR / f"abudawud-{number}.json"
            glosses = (
                json.loads(gloss_path.read_text(encoding="utf-8")).get("glosses", {})
                if gloss_path.exists() else {}
            )
            reports[number] = {"tokens": report["tokens"], "glosses": glosses}
            for token in report["tokens"]:
                key = norm(token["text"])
                value = glosses.get(token["id"], {})
                if key and value.get("en") and value.get("ur"):
                    known[key][stable(value)] += 1

    pool: dict[str, dict] = {}
    isnad_prefix_occurrences = 0
    reports_without_body_match = 0
    timing_files = sorted(TIMING_DIR.glob("n*.json"))
    for timing_path in timing_files:
        number = int(timing_path.stem[1:])
        report = reports.get(number)
        if not report:
            continue
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        target = timing.get("tokens", [])
        mapped = lcs_mapped_ids(report["tokens"], target, report["glosses"])
        if not mapped:
            reports_without_body_match += 1
            continue
        body_start = min(mapped)
        for index, token in enumerate(target):
            key = norm(token.get("text", ""))
            if not key or index in mapped:
                continue
            if index < body_start:
                isnad_prefix_occurrences += 1
                continue
            entry = pool.setdefault(key, {
                "forms": Counter(), "hadiths": set(), "occurrences": 0, "examples": []
            })
            entry["forms"][token["text"]] += 1
            entry["hadiths"].add(number)
            entry["occurrences"] += 1
            if len(entry["examples"]) < 5:
                lo, hi = max(0, index - 3), min(len(target), index + 4)
                entry["examples"].append({
                    "hadith": number,
                    "tokenIndex": index,
                    "context": " ".join(item["text"] for item in target[lo:hi]),
                })

    words = []
    reusable_occurrences = 0
    novel_occurrences = 0
    for key, raw in sorted(pool.items(), key=lambda item: (-item[1]["occurrences"], item[0])):
        choices = known.get(key, Counter())
        candidate_source_count = sum(choices.values())
        candidate_variant_count = len(choices)
        alternatives = [
            {"count": count, "gloss": json.loads(value)}
            for value, count in choices.most_common(3)
        ]
        candidate = alternatives[0]["gloss"] if alternatives else None
        candidate_confidence = (
            alternatives[0]["count"] / candidate_source_count
            if alternatives and candidate_source_count else 0
        )
        safe_reuse = bool(candidate) and (
            candidate_variant_count == 1
            or (alternatives[0]["count"] >= 3 and candidate_confidence >= 0.9)
        )
        if candidate:
            reusable_occurrences += raw["occurrences"]
        else:
            novel_occurrences += raw["occurrences"]
        words.append({
            "normalized": key,
            "form": raw["forms"].most_common(1)[0][0],
            "occurrences": raw["occurrences"],
            "hadithCount": len(raw["hadiths"]),
            "variants": [{"text": text, "count": count} for text, count in raw["forms"].most_common()],
            "resolution": (
                "safe-reuse" if safe_reuse
                else "review-reuse" if candidate
                else "needs-new-gloss"
            ),
            "candidateSourceCount": candidate_source_count,
            "candidateVariantCount": candidate_variant_count,
            "candidateConfidence": round(candidate_confidence, 4),
            "candidate": candidate,
            "candidateAlternatives": alternatives,
            "examples": raw["examples"],
        })

    payload = {
        "kind": "abudawud-synced-glossless-word-pool",
        "method": "normalized LCS identical to the live reader; grouped after alignment",
        "scope": "Unmatched audio tokens from the first canonical report-body match onward; preceding isnad tokens excluded.",
        "summary": {
            "timedHadiths": len(timing_files),
            "reportsWithoutBodyMatch": reports_without_body_match,
            "isnadPrefixOccurrencesExcluded": isnad_prefix_occurrences,
            "glosslessOccurrences": sum(item["occurrences"] for item in words),
            "uniqueNormalizedWords": len(words),
            "safeReuseUniqueWords": sum(item["resolution"] == "safe-reuse" for item in words),
            "safeReuseOccurrences": sum(item["occurrences"] for item in words if item["resolution"] == "safe-reuse"),
            "reviewReuseUniqueWords": sum(item["resolution"] == "review-reuse" for item in words),
            "reviewReuseOccurrences": sum(item["occurrences"] for item in words if item["resolution"] == "review-reuse"),
            "reusableUniqueWords": sum(item["candidate"] is not None for item in words),
            "reusableOccurrences": reusable_occurrences,
            "novelUniqueWords": sum(item["resolution"] == "needs-new-gloss" for item in words),
            "novelOccurrences": novel_occurrences,
        },
        "words": words,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(OUT)


if __name__ == "__main__":
    main()

