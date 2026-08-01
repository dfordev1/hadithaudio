#!/usr/bin/env python3
"""Rebuild Abu Dawood 4 from the actual spoken words, without inherited timing."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qc" / "abudawud-asr" / "timings" / "n0004.json"

# Corrected transcript of the acoustic word stream. The recording places the
# complete report 5 between report 4's main narration and its closing Wuhaib
# variant, so report 4 deliberately uses two source pieces.
SPOKEN = [
    ("Ø­ÙŽØ¯ÙŽÙ‘Ø«ÙŽÙ†ÙŽØ§", 69.48, 70.04), ("Ù…ÙØ³ÙŽØ¯ÙŽÙ‘Ø¯Ù", 70.12, 70.76),
    ("Ø¨Ù’Ù†Ù", 70.76, 70.84), ("Ù…ÙØ³ÙŽØ±Ù’Ù‡ÙŽØ¯Ù", 71.00, 71.64),
    ("Ø­ÙŽØ¯ÙŽÙ‘Ø«ÙŽÙ†ÙŽØ§", 71.80, 72.36), ("Ø­ÙŽÙ…ÙŽÙ‘Ø§Ø¯Ù", 72.44, 72.84),
    ("Ø¨Ù’Ù†Ù", 73.00, 73.08), ("Ø²ÙŽÙŠÙ’Ø¯Ù", 73.24, 73.56),
    ("ÙˆÙŽØ¹ÙŽØ¨Ù’Ø¯Ù", 73.72, 74.12), ("Ø§Ù„Ù’ÙˆÙŽØ§Ø±ÙØ«Ù", 74.28, 74.76),
    ("Ø¹ÙŽÙ†Ù’", 74.92, 75.00), ("Ø¹ÙŽØ¨Ù’Ø¯Ù", 75.16, 75.24),
    ("Ø§Ù„Ù’Ø¹ÙŽØ²ÙÙŠØ²Ù", 75.48, 75.80), ("Ø¨Ù’Ù†Ù", 75.88, 75.96),
    ("ØµÙÙ‡ÙŽÙŠÙ’Ø¨Ù", 76.20, 76.60), ("Ø¹ÙŽÙ†Ù’", 76.84, 76.92),
    ("Ø£ÙŽÙ†ÙŽØ³Ù", 77.00, 77.32), ("Ø¨Ù’Ù†Ù", 77.40, 77.48),
    ("Ù…ÙŽØ§Ù„ÙÙƒÙ", 77.72, 78.04), ("Ù‚ÙŽØ§Ù„ÙŽ", 78.20, 78.28),
    ("ÙƒÙŽØ§Ù†ÙŽ", 78.76, 78.84), ("Ø±ÙŽØ³ÙÙˆÙ„Ù", 79.24, 79.32),
    ("Ø§Ù„Ù„ÙŽÙ‘Ù‡Ù", 79.56, 79.64), ("ØµÙ„Ù‰", 79.88, 79.96),
    ("Ø§Ù„Ù„Ù‡", 80.36, 80.44), ("Ø¹Ù„ÙŠÙ‡", 80.60, 80.68),
    ("ÙˆØ³Ù„Ù…", 80.92, 81.00), ("Ø¥ÙØ°ÙŽØ§", 81.72, 81.80),
    ("Ø¯ÙŽØ®ÙŽÙ„ÙŽ", 82.04, 82.28), ("Ø§Ù„Ù’Ø®ÙŽÙ„Ø§ÙŽØ¡ÙŽ", 82.52, 83.00),
    ("Ù‚ÙŽØ§Ù„ÙŽ", 83.24, 83.32), ("Ø¹ÙŽÙ†Ù’", 83.56, 83.64),
    ("Ø­ÙŽÙ…ÙŽÙ‘Ø§Ø¯Ù", 83.72, 84.20), ("Ù‚ÙŽØ§Ù„ÙŽ", 84.52, 84.60),
    ("Ø§Ù„Ù„ÙŽÙ‘Ù‡ÙÙ…ÙŽÙ‘", 85.24, 85.72), ("Ø¥ÙÙ†ÙÙ‘ÙŠ", 85.72, 86.12),
    ("Ø£ÙŽØ¹ÙÙˆØ°Ù", 86.20, 86.68), ("Ø¨ÙÙƒÙŽ", 86.68, 86.92),
    ("ÙˆÙŽÙ‚ÙŽØ§Ù„ÙŽ", 87.16, 87.24), ("Ø¹ÙŽÙ†Ù’", 87.64, 87.72),
    ("Ø¹ÙŽØ¨Ù’Ø¯Ù", 87.80, 88.12), ("Ø§Ù„Ù’ÙˆÙŽØ§Ø±ÙØ«Ù", 88.12, 88.60),
    ("Ù‚ÙŽØ§Ù„ÙŽ", 88.76, 88.84), ("Ø£ÙŽØ¹ÙÙˆØ°Ù", 88.92, 89.40),
    ("Ø¨ÙØ§Ù„Ù„ÙŽÙ‘Ù‡Ù", 89.40, 89.64), ("Ù…ÙÙ†ÙŽ", 90.04, 90.16),
    ("Ø§Ù„Ù’Ø®ÙØ¨ÙØ«Ù", 90.16, 90.60), ("ÙˆÙŽØ§Ù„Ù’Ø®ÙŽØ¨ÙŽØ§Ø¦ÙØ«Ù", 90.68, 91.24),
    ("ÙˆÙŽÙ‚ÙŽØ§Ù„ÙŽ", 106.60, 106.92), ("ÙˆÙÙ‡ÙŽÙŠÙ’Ø¨ÙŒ", 107.08, 107.56),
    ("Ø¹ÙŽÙ†Ù’", 107.96, 108.04), ("Ø¹ÙŽØ¨Ù’Ø¯Ù", 108.20, 108.28),
    ("Ø§Ù„Ù’Ø¹ÙŽØ²ÙÙŠØ²Ù", 108.52, 108.92), ("ÙÙŽÙ„Ù’ÙŠÙŽØªÙŽØ¹ÙŽÙˆÙŽÙ‘Ø°Ù’", 109.08, 110.12),
    ("Ø¨ÙØ§Ù„Ù„ÙŽÙ‘Ù‡Ù", 110.20, 110.52),
]

INLINE_GLOSSES = {
    1: {"en": "he narrated to us", "ur": "ÛÙ… Ø³Û’ Ø¨ÛŒØ§Ù† Ú©ÛŒØ§"},
    2: {"en": "Musaddad", "ur": "Ù…Ø³Ø¯Ø¯"},
    3: {"en": "son of", "ur": "Ø¨Ù† / Ø¨ÛŒÙ¹Ø§"},
    4: {"en": "Musarhad", "ur": "Ù…Ø³Ø±ÛØ¯"},
    5: {"en": "he narrated to us", "ur": "ÛÙ… Ø³Û’ Ø¨ÛŒØ§Ù† Ú©ÛŒØ§"},
    6: {"en": "Hammad", "ur": "Ø­Ù…Ø§Ø¯"},
    7: {"en": "son of", "ur": "Ø¨Ù† / Ø¨ÛŒÙ¹Ø§"},
    8: {"en": "Zayd", "ur": "Ø²ÛŒØ¯"},
    49: {"en": "and he said", "ur": "Ø§ÙˆØ± Ø§Ø³ Ù†Û’ Ú©ÛØ§"},
    50: {"en": "Wuhayb", "ur": "ÙˆÛÛŒØ¨"},
}


def main() -> None:
    previous = 0.0
    for text, start, end in SPOKEN:
        if start < previous or end <= start:
            raise ValueError(f"non-monotonic timing at {text}: {start}-{end}")
        previous = end

    old = json.loads(SOURCE.read_text(encoding="utf-8"))
    rebuilt = {
        key: value for key, value in old.items()
        if key not in {"tokens", "text", "start", "end", "audioSegments", "boundaryRepair"}
    }
    rebuilt.update({
        "text": " ".join(text for text, _, _ in SPOKEN),
        "start": 69.48,
        "end": 110.52,
        "audioSegments": [
            {"recording": 1, "source": "01_restored.flac", "start": 69.48, "end": 91.24},
            {"recording": 1, "source": "01_restored.flac", "start": 106.60, "end": 110.52},
        ],
        "boundaryRepair": (
            "rebuilt from spoken transcript; report 5 interval excluded; "
            "closing Wuhaib variant retained as second source piece"
        ),
        "tokens": [
            ({
                "position": index,
                "text": text,
                "recording": 1,
                "start": start,
                "end": end,
                "sourceStart": start,
                "sourceEnd": end,
                "evidence": "manual_acoustic_rebuild",
            } | ({"gloss": INLINE_GLOSSES[index]} if index in INLINE_GLOSSES else {}))
            for index, (text, start, end) in enumerate(SPOKEN, 1)
        ],
    })
    SOURCE.write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "tokens": len(SPOKEN),
        "sourcePieces": len(rebuilt["audioSegments"]),
        "sourceAudioSeconds": round((91.24 - 69.48) + (110.52 - 106.60), 2),
    }, indent=2))


if __name__ == "__main__":
    main()

