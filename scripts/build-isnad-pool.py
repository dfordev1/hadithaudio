#!/usr/bin/env python3
"""Build a reviewable isnad word/name pool for a synced collection.

Muslim, Abu Dawud, and Ibn Majah display the full spoken chain (from the timing
sidecars) but — unlike Bukhari/Malik/Tirmidhi — have no isnad word-pool, so
narrator names and transmission connectors in the chain render ungloss­ed.

This mirrors scripts/build-bukhari-isnad-pool.py, adapted to the compact gloss
store (the per-report public/gloss/ tree it used is gone). It never fabricates
narrator identities: it reuses an existing gloss when the same normalized
surface form is glossed anywhere in the collection, supplies curated
transmission terms, and leaves unfamiliar proper names as Arabic-only review
candidates (no invented English/Urdu).

Reads timings from the primary (dirty) worktree's qc/ and glosses from the
release worktree's gloss-compact. Run with explicit paths, e.g.:

    python scripts/build-isnad-pool.py \
        --slug muslim \
        --timings C:/Users/Dv/hadithaudio/qc/muslim-full/timings \
        --glob 'm*.json'
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
PUNCT = re.compile(r"[^\u0621-\u063a\u0641-\u064a\u0671\u067e\u0686\u0698\u06a9\u06af\u06be\u06c0\u06cc]")

CURATED = {
    "حدثنا": {"en": "he narrated to us", "transliteration": "ḥaddathanā", "kind": "transmission"},
    "حدثني": {"en": "he narrated to me", "transliteration": "ḥaddathanī", "kind": "transmission"},
    "اخبرنا": {"en": "he informed us", "transliteration": "akhbaranā", "kind": "transmission"},
    "اخبرني": {"en": "he informed me", "transliteration": "akhbaranī", "kind": "transmission"},
    "انبانا": {"en": "he announced to us", "transliteration": "anbaʾanā", "kind": "transmission"},
    "عن": {"en": "from", "transliteration": "ʿan", "kind": "transmission"},
    "سمعت": {"en": "I heard", "transliteration": "samiʿtu", "kind": "transmission"},
    "قال": {"en": "he said", "transliteration": "qāla", "kind": "transmission"},
    "قالت": {"en": "she said", "transliteration": "qālat", "kind": "transmission"},
    "وقال": {"en": "and he said", "transliteration": "wa-qāla", "kind": "transmission"},
    "انه": {"en": "that he", "transliteration": "annahu", "kind": "link"},
    "انها": {"en": "that she", "transliteration": "annahā", "kind": "link"},
    "يقول": {"en": "he says", "transliteration": "yaqūlu", "kind": "transmission"},
}


def norm(text: str) -> str:
    text = DIACRITICS.sub("", text or "")
    text = text.replace("ـ", "")
    text = PUNCT.sub("", text)
    return (text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                .replace("ى", "ي").replace("ة", "ه"))


def known_glosses(slug: str) -> dict:
    """norm(surface) -> {en, ur, transliteration} reused from the compact store."""
    bundle = json.load(gzip.open(os.path.join(ROOT, "public", "gloss-compact",
                                              f"{slug}-bundle.json.gz"), mode="rt", encoding="utf-8"))
    pool = json.load(gzip.open(os.path.join(ROOT, "public", "gloss-compact",
                                            f"{slug}-pool.json.gz"), mode="rt", encoding="utf-8"))
    values = {e["id"]: e["value"] for e in pool["entries"]}
    # token id -> surface text, from book jsons
    token_text = {}
    for path in glob.glob(os.path.join(ROOT, "public", slug, "book-*.json")):
        for h in json.load(open(path, encoding="utf-8"))["hadith"]:
            for t in h["tokens"]:
                token_text[t["id"]] = t["text"]
    choices = defaultdict(Counter)
    for rep in bundle["reports"]:
        for tid, pid in rep["tokenRefs"]:
            v = values.get(pid)
            key = norm(token_text.get(tid, ""))
            if key and v and v.get("en"):
                slim = {k: v[k] for k in ("en", "ur", "transliteration") if v.get(k)}
                choices[key][json.dumps(slim, ensure_ascii=False, sort_keys=True)] += 1
    return {k: json.loads(c.most_common(1)[0][0]) for k, c in choices.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--timings", required=True, help="dir of timing sidecars")
    ap.add_argument("--glob", default="n*.json", help="filename glob within --timings")
    args = ap.parse_args()

    known = known_glosses(args.slug)
    surface = {}          # norm -> representative diacritized surface
    count = Counter()     # norm -> occurrences
    reports = defaultdict(set)

    files = glob.glob(os.path.join(args.timings, args.glob))
    for path in files:
        data = json.load(open(path, encoding="utf-8"))
        rep = str(data.get("n", os.path.basename(path)))
        for tok in data.get("tokens", []):
            key = norm(tok["text"])
            if not key:
                continue
            count[key] += 1
            reports[key].add(rep)
            surface.setdefault(key, tok["text"])

    words = {}
    stats = Counter()
    for key, n in count.items():
        entry = {"count": n, "reports": len(reports[key]), "arabic": surface[key]}
        if key in CURATED:
            entry.update({k: v for k, v in CURATED[key].items() if k != "kind"})
            entry["kind"] = CURATED[key]["kind"]
            stats["curated"] += 1
        elif key in known:
            entry.update(known[key])
            entry["kind"] = "reused-gloss"
            stats["reused"] += 1
        else:
            entry["kind"] = "review-name"   # Arabic-only; no invented meaning
            stats["review"] += 1
        words[key] = entry

    out = {
        "kind": f"{args.slug}-isnad-word-pool",
        "reviewState": "machine-assisted; names require review",
        "source": "timing sidecars + reused compact glosses; curated transmission terms",
        "words": words,
    }
    out_path = os.path.join(ROOT, "public", f"{args.slug}-isnad-word-pool.json")
    # minified to match the existing Bukhari/Malik/Tirmidhi pools and the repo budget
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))

    total = len(words)
    covered = stats["curated"] + stats["reused"]
    print(f"{args.slug}: {len(files)} timings -> {total} unique words")
    print(f"  curated transmission : {stats['curated']}")
    print(f"  reused gloss         : {stats['reused']}")
    print(f"  review-name (no en)  : {stats['review']}")
    print(f"  glossed coverage     : {covered}/{total} ({100*covered//total}%)")
    print(f"  wrote {out_path}")


if __name__ == "__main__":
    main()
