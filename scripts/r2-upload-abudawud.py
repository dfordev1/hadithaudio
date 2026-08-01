#!/usr/bin/env python3
"""Resume-safe concurrent upload of Abu Dawood clips and timings to R2."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
AUDIO = Path(r"C:\Users\Dv\Downloads\Hadith\Abu-Dawud\clips-mp3")
TIMINGS = ROOT / "qc" / "abudawud-clips" / "timings"
PROGRESS = ROOT / "scripts" / "r2-upload-abudawud-progress.json"
_rate_lock = threading.Lock()
_next_request = 0.0


def limit_rate(requests_per_second: float) -> None:
    global _next_request
    with _rate_lock:
        now = time.monotonic()
        scheduled = max(now, _next_request)
        _next_request = scheduled + 1.0 / requests_per_second
    if scheduled > now:
        time.sleep(scheduled - now)


def load_env() -> None:
    path = ROOT / ".env.local"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def put(client: httpx.Client, account: str, token: str, bucket: str,
        key: str, path: Path, content_type: str, requests_per_second: float) -> None:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects/{key}"
    delay = 0.5
    for attempt in range(12):
        limit_rate(requests_per_second)
        response = client.put(url, content=path.read_bytes(), headers={
            "Authorization": f"Bearer {token}", "Content-Type": content_type,
        })
        if response.status_code == 429:
            time.sleep(delay)
            delay = min(delay * 1.7, 12)
            continue
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(str(body.get("errors") or body)[:300])
        return
    raise RuntimeError(f"rate limited after retries ({attempt + 1})")


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbers", help="comma-separated test subset")
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--rps", type=float, default=18.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timings-only", action="store_true")
    args = parser.parse_args()
    selected = {int(x) for x in args.numbers.split(",")} if args.numbers else set(range(1, 5275))

    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    if not token or not account:
        raise SystemExit("Missing Cloudflare API credentials")

    state = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {"uploaded": {}, "failed": {}}
    uploaded = state.setdefault("uploaded", {})
    failed = state.setdefault("failed", {})
    jobs = []
    for n in sorted(selected):
        if not args.timings_only:
            jobs.append((f"abudawud/{n:04d}.mp3", AUDIO / f"{n:04d}.mp3", "audio/mpeg"))
        jobs.append((f"abudawud-timings/n{n:04d}.json", TIMINGS / f"n{n:04d}.json", "application/json; charset=utf-8"))
    missing = [(key, str(path)) for key, path, _ in jobs if not path.exists()]
    if missing:
        raise SystemExit(f"Missing local inputs: {missing[:10]}")
    jobs = [job for job in jobs if args.force or job[0] not in uploaded]
    print(json.dumps({"selected_hadiths": len(selected), "pending_objects": len(jobs), "already_uploaded": len(uploaded)}))
    if not jobs:
        return 0

    limits = httpx.Limits(max_connections=args.concurrency + 4, max_keepalive_connections=args.concurrency + 4)
    client = httpx.Client(limits=limits, timeout=httpx.Timeout(180, connect=30))
    lock = threading.Lock()
    started = time.time()
    errors = 0

    def work(job):
        key, path, content_type = job
        put(client, account, token, bucket, key, path, content_type, args.rps)
        return key, path.stat().st_size

    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(work, job): job[0] for job in jobs}
            for index, future in enumerate(as_completed(futures), 1):
                key = futures[future]
                try:
                    done_key, size = future.result()
                    with lock:
                        uploaded[done_key] = {"size": size, "time": time.time()}
                        failed.pop(done_key, None)
                except Exception as exc:
                    errors += 1
                    failed[key] = str(exc)
                if index % 50 == 0 or index == len(jobs):
                    state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    PROGRESS.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
                    print(json.dumps({"done": index, "total": len(jobs), "errors": errors,
                                      "rate": round(index / max(time.time() - started, .001), 2)}))
    finally:
        client.close()
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())


