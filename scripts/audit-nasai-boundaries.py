#!/usr/bin/env python3
"""Create a focused review queue for adjacent Nasa'i report boundaries."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def timed_tokens(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        token for token in report.get("tokens") or []
        if isinstance(token.get("start"), (int, float)) and isinstance(token.get("end"), (int, float))
    ]


def token_view(token: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": token.get("id"),
        "text": token.get("text"),
        "start": token.get("start"),
        "end": token.get("end"),
        "status": token.get("status"),
        "similarity": token.get("similarity"),
        "audioStatus": token.get("audioStatus"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.package_dir / "manifest.json")
    overlaps: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    severity = Counter()

    for entry in manifest.get("recordings") or []:
        number = str(entry["recording"]).zfill(2)
        payload = load_json(args.package_dir / entry["resultFile"])
        reports = [report for report in payload.get("reports") or [] if report.get("readerHadithNumber") is not None]
        for previous, current in zip(reports, reports[1:]):
            previous_tokens = timed_tokens(previous)
            current_tokens = timed_tokens(current)
            if not previous_tokens or not current_tokens:
                continue
            previous_end = max(float(token["end"]) for token in previous_tokens)
            current_start = min(float(token["start"]) for token in current_tokens)
            delta = current_start - previous_end
            previous_id = str(previous["readerHadithNumber"])
            current_id = str(current["readerHadithNumber"])
            if delta < 0:
                seconds = round(-delta, 3)
                same_range = abs(float(previous.get("start")) - float(current.get("start"))) < 1e-6 and abs(float(previous.get("end")) - float(current.get("end"))) < 1e-6
                same_text = str(previous.get("fullText")) == str(current.get("fullText"))
                if same_range and same_text:
                    level = "shared_exact"
                elif seconds <= 0.16:
                    level = "frame_edge"
                elif seconds <= 0.4:
                    level = "small"
                elif seconds <= 0.8:
                    level = "medium"
                else:
                    level = "high"
                severity[level] += 1
                overlaps.append({
                    "recording": number,
                    "previous": previous_id,
                    "next": current_id,
                    "seconds": seconds,
                    "severity": level,
                    "sameRange": same_range,
                    "sameText": same_text,
                    "suggestedBoundary": round((previous_end + current_start) / 2, 3),
                    "previousCrossingTokens": [
                        token_view(token) for token in previous_tokens if float(token["end"]) > current_start
                    ],
                    "nextCrossingTokens": [
                        token_view(token) for token in current_tokens if float(token["start"]) < previous_end
                    ],
                })
            elif delta > 2:
                gaps.append({
                    "recording": number,
                    "previous": previous_id,
                    "next": current_id,
                    "seconds": round(delta, 3),
                })

    output = {
        "schema": "hadith/nasai-boundary-audit/v1",
        "summary": {
            "overlaps": len(overlaps),
            "sharedExact": severity["shared_exact"],
            "frameEdge": severity["frame_edge"],
            "small": severity["small"],
            "medium": severity["medium"],
            "high": severity["high"],
            "gapsOver2s": len(gaps),
        },
        "overlaps": sorted(overlaps, key=lambda item: item["seconds"], reverse=True),
        "gapsOver2s": sorted(gaps, key=lambda item: item["seconds"], reverse=True),
    }
    atomic_json(args.output, output)
    print(json.dumps(output["summary"], indent=2))
    print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
