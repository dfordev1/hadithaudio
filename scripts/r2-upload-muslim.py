#!/usr/bin/env python3
"""Upload Sahih Muslim per-report audio and timing maps to Cloudflare R2."""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "qc" / "muslim-full"
ORIGINAL_AUDIO = BASE / "clips"
GENERATED_AUDIO = BASE / "generated-clips"
ORIGINAL_TIMINGS = BASE / "timings"
GENERATED_TIMINGS = BASE / "generated-timings"
PROGRESS = BASE / "r2-upload-progress.json"


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


def assets() -> list[tuple[Path, str, str]]:
    rows = []
    for number in range(1, 7564):
        original_timing = ORIGINAL_TIMINGS / f"m{number:04d}.json"
        generated_timing = GENERATED_TIMINGS / f"m{number:04d}.json"
        if generated_timing.exists():
            timing = generated_timing
            audio = GENERATED_AUDIO / f"{number:04d}.mp3"
        elif original_timing.exists():
            data = json.loads(original_timing.read_text(encoding="utf-8"))
            if not data.get("audio"):
                continue
            timing = original_timing
            audio = ORIGINAL_AUDIO / f"{number:04d}.mp3"
        else:
            continue
        if not audio.exists():
            raise RuntimeError(f"missing audio for Muslim {number}: {audio}")
        rows.append((audio, f"muslim/{number:04d}.mp3", "audio/mpeg"))
        rows.append((timing, f"muslim-timings/n{number:04d}.json", "application/json; charset=utf-8"))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    args = parser.parse_args()
    load_env()
    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    if not token or not account:
        raise SystemExit("Missing Cloudflare API configuration")
    rows = assets()
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
    if args.missing_only:
        remote_keys: set[str] = set()
        with httpx.Client(timeout=120) as client:
            for prefix in ("muslim/", "muslim-timings/"):
                cursor = None
                while True:
                    params = {"per_page": "1000", "prefix": prefix}
                    if cursor:
                        params["cursor"] = cursor
                    response = client.get(endpoint, params=params, headers={"Authorization": f"Bearer {token}"})
                    response.raise_for_status()
                    body = response.json()
                    if not body.get("success"):
                        raise RuntimeError(body.get("errors") or body)
                    remote_keys.update(item["key"] for item in body.get("result", []))
                    info = body.get("result_info") or {}
                    if not info.get("is_truncated"):
                        break
                    cursor = info.get("cursor")
        rows = [row for row in rows if row[1] not in remote_keys]
        print(f"missing remote objects: {len(rows)}")
    audio_count = sum(key.endswith(".mp3") for _, key, _ in rows)
    timing_count = sum(key.endswith(".json") for _, key, _ in rows)
    print(json.dumps({
        "objects": len(rows), "audio": audio_count, "timings": timing_count,
        "bytes": sum(path.stat().st_size for path, _, _ in rows),
    }, indent=2))
    if not args.missing_only and (audio_count != 7212 or timing_count != 7212):
        raise SystemExit("Expected exactly 7,212 audio/timing pairs")
    if args.dry_run:
        return 0
    def upload(row: tuple[Path, str, str]) -> str:
        path, key, content_type = row
        content = path.read_bytes()
        with httpx.Client(timeout=120) as client:
            for attempt in range(7):
                response = client.put(
                    f"{endpoint}/{key}",
                    content=content,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
                )
                if response.status_code != 429 and response.status_code < 500:
                    response.raise_for_status()
                    body = response.json()
                    if not body.get("success"):
                        raise RuntimeError(body.get("errors") or body)
                    return key
                if attempt == 6:
                    response.raise_for_status()
                time.sleep(min(30, 2 ** attempt))
        raise RuntimeError(f"upload failed: {key}")

    failed = []
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(upload, row): row for row in rows}
        for future in as_completed(futures):
            completed += 1
            try:
                future.result()
            except Exception as exc:
                failed.append(f"{futures[future][1]}: {exc}")
            if completed % 100 == 0 or completed == len(rows):
                payload = {
                    "completed": completed, "total": len(rows), "failed": len(failed),
                    "updated": time.time(),
                }
                PROGRESS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                print(f"uploaded {completed}/{len(rows)}; failed {len(failed)}", flush=True)
    if failed:
        print("\n".join(failed[:50]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


