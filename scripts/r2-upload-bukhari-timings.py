#!/usr/bin/env python3
"""Upload completed Bukhari ASR timing maps to Cloudflare R2.

Keys: bukhari-timings/nNNNN.json
Only maps containing usable word timestamps are uploaded. The operation is
idempotent: rerunning replaces a map when a better alignment is generated.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "bukhari-asr-pilot" / "timings"


def load_env() -> None:
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def usable(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("tokens")) and any(
            isinstance(t.get("start"), (int, float)) and isinstance(t.get("end"), (int, float)) and t["end"] > t["start"]
            for t in data["tokens"]
        )
    except (OSError, ValueError, TypeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    load_env()
    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    if not token or not account:
        raise SystemExit("Missing CF_API_TOKEN and/or CF_ACCOUNT_ID")
    paths = [p for p in sorted(TIMINGS.glob("n*.json")) if usable(p)]
    if args.limit:
        paths = paths[: args.limit]
    print(f"usable timing maps: {len(paths)}")
    if args.dry_run:
        return 0
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"

    def upload(path: Path) -> str:
        key = f"bukhari-timings/{path.name}"
        with httpx.Client(timeout=60) as client:
            for attempt in range(6):
                response = client.put(
                    f"{endpoint}/{key}",
                    content=path.read_bytes(),
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                )
                if response.status_code != 429 and response.status_code < 500:
                    response.raise_for_status()
                    body = response.json()
                    if not body.get("success"):
                        raise RuntimeError(body.get("errors") or body)
                    break
                if attempt == 5:
                    response.raise_for_status()
                time.sleep(min(30, 2 ** attempt))
        return key

    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(upload, p): p for p in paths}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as exc:
                failed.append(f"{futures[future].name}: {exc}")
            if i % 100 == 0 or i == len(paths):
                print(f"uploaded {i}/{len(paths)}", flush=True)
    if failed:
        print("failed:\n" + "\n".join(failed[:20]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
