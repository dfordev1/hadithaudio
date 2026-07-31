#!/usr/bin/env python3
"""Build a reviewable word/name pool for full Bukhari isnad audio alignment.

The pool never fabricates narrator identities. It reuses existing Bukhari
glosses for exact normalized Arabic matches, supplies curated transmission
terms, and leaves unfamiliar proper names as Arabic-only review candidates.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "bukhari-asr-pilot" / "timings"
BOOKS = ROOT / "public" / "bukhari"
GLOSSES = ROOT / "public" / "gloss"
PUBLIC_OUT = ROOT / "public" / "bukhari-isnad-word-pool.json"
QC_OUT = ROOT / "qc" / "bukhari-isnad-name-candidates.json"
DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
PUNCT = re.compile(r"[^\u0621-\u063a\u0641-\u064a\u0671\u067e\u0686\u0698\u06a9\u06af\u06be\u06c0\u06cc]")
CHAIN_CUES = {"حدثنا", "حدثني", "اخبرنا", "اخبرني", "عن", "سمعت", "قال"}
CURATED = {
    "حدثنا": {"en": "narrated to us", "transliteration": "ḥaddathanā", "kind": "transmission"},
    "حدثني": {"en": "narrated to me", "transliteration": "ḥaddathanī", "kind": "transmission"},
    "اخبرنا": {"en": "informed us", "transliteration": "akhbaranā", "kind": "transmission"},
    "اخبرني": {"en": "informed me", "transliteration": "akhbaranī", "kind": "transmission"},
    "عن": {"en": "from", "transliteration": "ʿan", "kind": "transmission"},
    "سمعت": {"en": "I heard", "transliteration": "samiʿtu", "kind": "transmission"},
    "قال": {"en": "he said", "transliteration": "qāla", "kind": "transmission"},
    "وقال": {"en": "and he said", "transliteration": "wa-qāla", "kind": "transmission"},
    "انه": {"en": "that he", "transliteration": "annahu", "kind": "link"},
}


def norm(text: str) -> str:
    text = DIACRITICS.sub("", text or "")
    text = text.replace("ـ", "")
    text = PUNCT.sub("", text)
    return text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")


def existing_glosses() -> dict:
    token_text = {}
    for path in BOOKS.glob("book-*.json"):
        for hadith in json.loads(path.read_text(encoding="utf-8"))["hadith"]:
            token_text.update({t["id"]: t["text"] for t in hadith["tokens"]})
    choices = defaultdict(Counter)
    for path in GLOSSES.glob("bukhari-*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for token_id, gloss in data.get("glosses", {}).items():
            key = norm(token_text.get(token_id, ""))
            if key and gloss.get("en"):
                choices[key][json.dumps({k: gloss[k] for k in ("en", "ur", "transliteration") if gloss.get(k)}, ensure_ascii=False, sort_keys=True)] += 1
    return {key: json.loads(values.most_common(1)[0][0]) for key, values in choices.items()}


def main() -> None:
    known = existing_glosses()
    words, forms, reports, name_candidates = Counter(), defaultdict(Counter), defaultdict(set), Counter()
    rawis, rawi_reports = Counter(), defaultdict(set)
    # This field is the project's canonical, deliberately separated isnad.
    # It is the authoritative list for full narrator names; do not infer names
    # from arbitrary prose after "said" in the hadith body.
    for path in BOOKS.glob("book-*.json"):
        for hadith in json.loads(path.read_text(encoding="utf-8"))["hadith"]:
            for rawi in (hadith.get("isnad") or "").split("←"):
                rawi = rawi.strip()
                if rawi:
                    rawis[rawi] += 1
                    rawi_reports[rawi].add(str(hadith["n"]))
    for path in TIMINGS.glob("n*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        tokens = [t.get("text", "") for t in data.get("tokens", [])]
        clean = [norm(t) for t in tokens]
        for raw, key in zip(tokens, clean):
            if key:
                words[key] += 1; forms[key][raw] += 1; reports[key].add(data["n"])
        # Candidate full names are the words after a chain cue until punctuation/next cue.
        for i, key in enumerate(clean):
            if key not in CHAIN_CUES: continue
            part = []
            for raw, nxt in zip(tokens[i + 1:i + 7], clean[i + 1:i + 7]):
                if not nxt or nxt in CHAIN_CUES or re.search(r"[،.:]", raw): break
                part.append(raw)
            if part: name_candidates[" ".join(part)] += 1
    entries = {}
    for key, count in words.items():
        entry = {"count": count, "reports": len(reports[key]), "arabic": forms[key].most_common(1)[0][0]}
        entry.update(known.get(key, CURATED.get(key, {})))
        if "en" not in entry: entry["kind"] = "name-or-review"
        entries[key] = entry
    PUBLIC_OUT.write_text(json.dumps({"kind": "bukhari-isnad-word-pool", "reviewState": "machine-assisted; names require review", "words": entries}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    QC_OUT.write_text(json.dumps({
        "kind": "bukhari-rawi-name-pool",
        "note": "rawis are canonical full names from the Bukhari isnad field, sorted by number of reports. Heuristic candidates are retained only to help reconcile the fuller spoken diplomatic text.",
        "rawis": [{"arabic": name, "reports": count, "hadith": sorted(rawi_reports[name], key=lambda n: (int(re.match(r"\d+", n).group()), n))[:12]} for name, count in rawis.most_common()],
        "heuristicCandidates": [{"arabic": name, "count": count} for name, count in name_candidates.most_common()],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"words={len(entries)} rawis={len(rawis)} -> {PUBLIC_OUT.name}")


if __name__ == "__main__":
    main()
