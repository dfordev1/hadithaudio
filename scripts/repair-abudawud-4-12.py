#!/usr/bin/env python3
"""Repair non-contiguous report 4 and the report 12/13 boundary."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "abudawud-asr" / "timings"


def write(number: int, data: dict) -> None:
    (TIMINGS / f"n{number:04d}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    report4 = json.loads((TIMINGS / "n0004.json").read_text(encoding="utf-8"))
    report4["audioSegments"] = [
        {"recording": 1, "source": "01_restored.flac", "start": 69.48, "end": 110.52},
    ]
    report4["end"] = 110.52
    repair4 = {
        57: (91.40, 91.96, "aligned_spoken_variant"),
        58: (92.04, 92.52, "aligned_spoken_variant"),
        59: (92.52, 93.08, "aligned_spoken_variant"),
        60: (93.32, 95.56, "aligned_spoken_variant"),
        61: (95.88, 96.36, "exact"),
        62: (96.52, 96.60, "exact"),
        63: (96.76, 96.84, "exact"),
        64: (97.08, 97.48, "exact"),
        65: (101.08, 101.56, "exact"),
        66: (101.96, 102.44, "exact"),
        67: (102.44, 102.84, "exact"),
        68: (102.92, 103.16, "exact"),
        69: (103.40, 104.84, "aligned_spoken_variant"),
        70: (105.00, 105.08, "exact"),
        71: (105.56, 106.04, "exact"),
        72: (106.04, 106.44, "recovered_from_waveform_gap"),
        73: (106.60, 106.68, "inferred_split_word"),
        74: (106.68, 106.92, "inferred_split_word"),
        75: (107.08, 107.56, "exact"),
        76: (109.08, 110.12, "exact"),
        77: (110.20, 110.52, "recovered_from_waveform_gap"),
    }
    for token in report4["tokens"]:
        if token["position"] in repair4:
            token["start"], token["end"], token["evidence"] = repair4[token["position"]]
            token["sourceStart"], token["sourceEnd"] = token["start"], token["end"]
    report4["boundaryRepair"] = "restored contiguous spoken variant; editorial summary words aligned to the corresponding fuller chain"
    write(4, report4)

    report12 = json.loads((TIMINGS / "n0012.json").read_text(encoding="utf-8"))
    report12["audioSegments"] = [
        {"recording": 1, "source": "01_restored.flac", "start": 255.32, "end": 273.64},
    ]
    report12["end"] = 273.64
    last = report12["tokens"][-1]
    last.update({
        "start": 273.08, "end": 273.70,
        "sourceStart": 273.08, "sourceEnd": 273.70,
        "evidence": "recovered_from_waveform_gap",
    })
    report12["boundaryRepair"] = "preserved final word from ASR-unrecognized waveform gap; trimmed before report 13 opening"
    write(12, report12)


if __name__ == "__main__":
    main()

