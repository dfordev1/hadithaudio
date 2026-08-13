#!/usr/bin/env python3
"""Upload forty-hadith recitation MP3s to Cloudflare R2 (cdn.hadith.to/recitation/).

Credentials come from .env.local; never printed. Missing-only and resumable.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
RECITATION_DIR = ROOT / "public" / "recitation"
DEFAULT_CDN = "https://cdn.hadith.to"
PREFIX = "recitation"


def load_env(explicit: Path | None) -> None:
    candidates = [explicit] if explicit else [ROOT / ".env.local", ROOT / ".env"]
    for path in candidates:
        if path is None or not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def list_r2_keys(client: httpx.Client, account: str, bucket: str, token: str) -> set[str]:
    present: set[str] = set()
    cursor = None
    base = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
    while True:
        params: dict[str, str] = {"per_page": "1000", "prefix": f"{PREFIX}/"}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(base, params=params, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(body.get("errors") or body)
        for obj in body.get("result", []):
            if obj["key"].endswith(".mp3"):
                present.add(obj["key"])
        info = body.get("result_info") or {}
        if info.get("is_truncated") and info.get("cursor"):
            cursor = info["cursor"]
        else:
            return present


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--corpus", help="Limit files to this corpus prefix, e.g. nawawi-arbain")
    args = parser.parse_args()
    load_env(args.env_file)

    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    cdn = os.environ.get("R2_PUBLIC_BASE", DEFAULT_CDN).rstrip("/")
    if not token or not account:
        raise SystemExit("Missing CF_API_TOKEN and/or CF_ACCOUNT_ID")

    pattern = f"{args.corpus}.*.mp3" if args.corpus else "*.mp3"
    local_files = sorted(RECITATION_DIR.glob(pattern))
    if not local_files:
        raise SystemExit(f"No MP3 files in {RECITATION_DIR}")

    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
    progress_path = RECITATION_DIR / "r2-upload-progress.json"

    with httpx.Client(timeout=120) as client:
        print("listing R2 recitation objects ...", flush=True)
        remote = list_r2_keys(client, account, bucket, token)

    local_keys = {f"{PREFIX}/{path.name}" for path in local_files}
    to_upload = sorted(local_keys if args.replace else local_keys - remote)
    print(f"local mp3: {len(local_files)}  remote: {len(remote)}  to upload: {len(to_upload)}")

    if args.verify_only:
        sample = sorted(local_keys)
        random.shuffle(sample)
        sample = sample[: min(8, len(sample))]
    elif args.dry_run:
        print("dry-run; sample keys:", to_upload[:5])
        return 0
    else:
        def upload(key: str) -> str:
            path = RECITATION_DIR / key.split("/", 1)[1]
            payload = path.read_bytes()
            with httpx.Client(timeout=120) as client:
                for attempt in range(6):
                    resp = client.put(
                        f"{endpoint}/{key}",
                        content=payload,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "audio/mpeg",
                            "Cache-Control": "public, max-age=31536000, immutable",
                        },
                    )
                    if resp.status_code != 429 and resp.status_code < 500:
                        resp.raise_for_status()
                        body = resp.json()
                        if not body.get("success"):
                            raise RuntimeError(body.get("errors") or body)
                        return key
                    time.sleep(min(30, 2 ** attempt))
            return key

        failed: list[str] = []
        uploaded: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
            futures = {pool.submit(upload, key): key for key in to_upload}
            for index, future in enumerate(as_completed(futures), 1):
                key = futures[future]
                try:
                    uploaded.append(future.result())
                except Exception as exc:
                    failed.append(f"{key}: {exc}")
                if index % 20 == 0 or index == len(to_upload):
                    print(f"uploaded {index}/{len(to_upload)}", flush=True)
        if failed:
            print("FAILED:\n" + "\n".join(failed[:20]))
            return 1
        sample = uploaded[:: max(1, len(uploaded) // 8)][:8] if uploaded else []

    bad: list[str] = []
    with httpx.Client(timeout=60) as client:
        keys = sample if sample else sorted(local_keys)[:8]
        for key in keys:
            url = f"{cdn}/{key}"
            resp = client.head(url)
            if resp.status_code != 200:
                bad.append(f"{url} -> {resp.status_code}")
    if bad:
        print("CDN verify failed:\n" + "\n".join(bad))
        return 1

    payload: dict[str, Any] = {
        "schema": "hadith/recitation-r2-upload/v1",
        "prefix": PREFIX,
        "localCount": len(local_files),
        "remoteBefore": len(remote),
        "uploaded": len(to_upload) if not args.verify_only else 0,
        "verifiedSample": keys,
    }
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CDN verify OK ({len(keys)} samples). manifest: {progress_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
