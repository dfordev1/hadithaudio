#!/usr/bin/env python3
"""Re-PUT existing R2 objects with immutable cache metadata, preserving bytes and type."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE_CONTROL = "public, max-age=31536000, immutable"


def load_env(path: Path | None) -> None:
    for candidate in (path, ROOT / ".env.local", ROOT / ".env"):
        if not candidate or not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--cdn", default="https://cdn.hadith.to")
    parser.add_argument("--concurrency", type=int, default=24)
    parser.add_argument("--limit", type=int, default=0, help="refresh only the first N pending objects")
    parser.add_argument("--progress-file", type=Path, default=ROOT / "qc" / "r2-cache-metadata-progress.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_env(args.env_file)

    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    if not token or not account:
        raise SystemExit("Missing Cloudflare configuration")

    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
    auth = {"Authorization": f"Bearer {token}"}
    keys: list[str] = []
    cursor: str | None = None
    with httpx.Client(timeout=120) as client:
        while True:
            params = {"per_page": "1000"}
            if cursor:
                params["cursor"] = cursor
            response = client.get(endpoint, params=params, headers=auth)
            response.raise_for_status()
            body = response.json()
            keys.extend(item["key"] for item in body.get("result", []))
            info = body.get("result_info") or {}
            if not info.get("is_truncated"):
                break
            cursor = info.get("cursor")

    completed: set[str] = set()
    if args.progress_file.exists():
        completed.update(json.loads(args.progress_file.read_text(encoding="utf-8")).get("completed", []))
    pending = [key for key in keys if key not in completed]
    if args.limit:
        pending = pending[: args.limit]
    print(json.dumps({"objects": len(keys), "completed": len(completed), "pending": len(pending)}), flush=True)
    if args.dry_run:
        return 0

    args.progress_file.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    failures: list[tuple[str, str]] = []
    limits = httpx.Limits(max_connections=max(32, args.concurrency * 2), max_keepalive_connections=max(16, args.concurrency))
    transfer_client = httpx.Client(timeout=180, follow_redirects=True, limits=limits)

    def save() -> None:
        temporary = args.progress_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"completed": sorted(completed)}, separators=(",", ":")), encoding="utf-8")
        temporary.replace(args.progress_file)

    def refresh(key: str) -> str:
        source_url = f"{args.cdn.rstrip('/')}/{quote(key, safe='/')}"
        object_url = f"{endpoint}/{quote(key, safe='/')}"
        for attempt in range(7):
            try:
                source = transfer_client.get(source_url, headers={"Cache-Control": "no-cache"})
                source.raise_for_status()
                headers = {
                    **auth,
                    "Content-Type": source.headers.get("content-type", "application/octet-stream"),
                    "Cache-Control": CACHE_CONTROL,
                }
                for name in ("content-disposition", "content-language", "content-encoding"):
                    if source.headers.get(name):
                        headers[name.title()] = source.headers[name]
                uploaded = transfer_client.put(object_url, content=source.content, headers=headers)
                uploaded.raise_for_status()
                return key
            except Exception:
                if attempt == 6:
                    raise
                time.sleep(min(30, 2**attempt))
        return key

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(refresh, key): key for key in pending}
        for index, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                future.result()
                with lock:
                    completed.add(key)
            except Exception as exc:
                failures.append((key, str(exc)))
            if index % 100 == 0 or index == len(pending):
                with lock:
                    save()
                print(f"metadata: {index}/{len(pending)} failed={len(failures)}", flush=True)

    transfer_client.close()
    if failures:
        print(json.dumps({"failures": failures[:50]}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
