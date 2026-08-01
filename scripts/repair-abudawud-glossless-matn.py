#!/usr/bin/env python3
"""Fill the three Abu Dawood matn gloss gaps caused by damaged source glyphs."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOSS_DIR = ROOT / "public" / "gloss"
FIXES = {
    615: {
        "uh:token:abudawud.0615:0015": {
            "en": "on his right side",
            "ur": "Ø§Ø³ Ú©ÛŒ Ø¯Ø§Ø¦ÛŒÚº Ø¬Ø§Ù†Ø¨",
            "transliteration": "yamÄ«nihi",
            "root": "ÙŠ Ù… Ù†",
            "lemma": "ÙŠÙŽÙ…ÙÙŠÙ†",
            "pos": "N",
            "features": {"case": "GEN", "state": "CONSTRUCT"},
            "note": "Source glyph corruption repaired from context: Ø¹ÙŽÙ†Ù’ ÙŠÙŽÙ…ÙÙŠÙ†ÙÙ‡Ù.",
        }
    },
    741: {
        "uh:token:abudawud.0741:0061": {
            "en": "son of",
            "ur": "Ø¨ÛŒÙ¹Ø§ / Ø§Ø¨Ù†",
            "transliteration": "ibni",
            "root": "Ø¨ Ù† Ùˆ",
            "lemma": "Ø§ÙØ¨Ù’Ù†",
            "pos": "N",
            "features": {"case": "GEN", "state": "CONSTRUCT"},
            "note": "Source glyph corruption repaired as Ø§Ø¨Ù’Ù†Ù.",
        }
    },
    3014: {
        "uh:token:abudawud.3014:0065": {
            "en": "befalls him",
            "ur": "Ø§Ø³ Ù¾Ø± Ù¾ÛŒØ´ Ø¢ØªØ§ ÛÛ’",
            "transliteration": "yanzilu bihi",
            "root": "Ù† Ø² Ù„",
            "lemma": "Ù†ÙŽØ²ÙŽÙ„ÙŽ",
            "pos": "V",
            "features": {"aspect": "IMPF", "person": "3", "gender": "MASC", "number": "SING"},
            "note": "Source glyph corruption repaired from context: ÙˆÙŽÙ…ÙŽØ§ ÙŠÙŽÙ†Ù’Ø²ÙÙ„Ù Ø¨ÙÙ‡Ù.",
        }
    },
}


def main() -> None:
    for number, additions in FIXES.items():
        path = GLOSS_DIR / f"abudawud-{number}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("glosses", {}).update(additions)
        payload["matnGapRepair"] = {
            "method": "manual contextual repair of corrupted Arabic source glyphs",
            "tokens": list(additions),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(number, len(additions))


if __name__ == "__main__":
    main()

