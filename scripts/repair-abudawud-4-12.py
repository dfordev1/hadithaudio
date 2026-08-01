#!/usr/bin/env python3
"""Repair the report 12/13 boundary.

Report 4 is intentionally rebuilt from scratch by rebuild-abudawud-4.py.
"""

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

