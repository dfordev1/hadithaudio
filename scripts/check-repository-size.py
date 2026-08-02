#!/usr/bin/env python3
"""Enforce repository and deployment budgets that prevent data regressions."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-public-mib", type=float, default=340)
    parser.add_argument("--max-public-files", type=int, default=37_000)
    parser.add_argument("--max-file-mib", type=float, default=8)
    args = parser.parse_args()

    files = [path for path in tracked_files() if path.is_file()]
    public = [path for path in files if path.is_relative_to(ROOT / "public")]
    legacy = [path for path in public if path.is_relative_to(ROOT / "public" / "gloss")]
    oversized = [(path, path.stat().st_size) for path in files if path.stat().st_size > args.max_file_mib * MIB]
    public_bytes = sum(path.stat().st_size for path in public)

    failures: list[str] = []
    if legacy:
        failures.append(f"legacy public/gloss contains {len(legacy)} tracked files")
    if len(public) > args.max_public_files:
        failures.append(f"public file count {len(public):,} exceeds {args.max_public_files:,}")
    if public_bytes > args.max_public_mib * MIB:
        failures.append(f"public size {public_bytes / MIB:.1f} MiB exceeds {args.max_public_mib:.1f} MiB")
    if oversized:
        examples = ", ".join(
            f"{path.relative_to(ROOT).as_posix()} ({size / MIB:.1f} MiB)"
            for path, size in sorted(oversized, key=lambda item: item[1], reverse=True)[:10]
        )
        failures.append(f"tracked files exceed {args.max_file_mib:.1f} MiB: {examples}")

    print(
        f"repository budget: public={public_bytes / MIB:.1f} MiB, "
        f"public_files={len(public):,}, tracked_files={len(files):,}, "
        f"largest={max((path.stat().st_size for path in files), default=0) / MIB:.1f} MiB"
    )
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1
    print("repository budget: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
