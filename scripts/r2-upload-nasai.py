#!/usr/bin/env python3
"""Reconcile, upload, and verify Nasa'i audio/timing assets in Cloudflare R2.

The default release command is missing-only and resumable. Credentials are read
from an explicitly supplied env file or the repository's local env files and
are never printed. Generated assets remain outside Git.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "qc" / "nasai-app-ready-full"
EXPECTED_AUDIO = 5672
EXPECTED_TIMINGS = 5673
EXPECTED_OBJECTS = EXPECTED_AUDIO + EXPECTED_TIMINGS
DEFAULT_CDN = "https://cdn.hadith.to"


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


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.025 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def report_stem(locator: str) -> str:
    return locator.zfill(4) if locator.isdigit() else locator


def parse_reports(value: str | None) -> set[str] | None:
    if not value:
        return None
    result: set[str] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item and all(part.isdigit() for part in item.split("-", 1)):
            low, high = (int(part) for part in item.split("-", 1))
            result.update(str(number) for number in range(low, high + 1))
        else:
            result.add(item)
    return result


def assets(base: Path, reports: set[str] | None = None) -> list[tuple[Path, str, str]]:
    timings_dir = base / "timings"
    clips_dir = base / "clips"
    rows: list[tuple[Path, str, str]] = []
    audio_rows: dict[str, tuple[Path, str, str]] = {}
    for timing_path in sorted(timings_dir.glob("n*.json")):
        data = json.loads(timing_path.read_text(encoding="utf-8"))
        locator = str(data.get("n"))
        if reports is not None and locator not in reports:
            continue
        if data.get("collection") != "nasai" or data.get("synthetic") is not False:
            raise RuntimeError(f"unsafe timing disclosure in {timing_path}")
        audio_name = str(data.get("audio") or "")
        audio_path = clips_dir / audio_name
        if not audio_path.exists() or audio_path.stat().st_size <= 1024:
            raise RuntimeError(f"missing/invalid audio for Nasa'i {locator}: {audio_path}")
        audio_key = f"nasai/{audio_name}"
        audio_rows[audio_key] = (audio_path, audio_key, "audio/mpeg")
        rows.append((timing_path, f"nasai-timings/{timing_path.name}", "application/json; charset=utf-8"))
    return sorted(audio_rows.values(), key=lambda row: row[1]) + sorted(rows, key=lambda row: row[1])


def request_with_backoff(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(8):
        response = client.request(method, url, **kwargs)
        if response.status_code != 429 and response.status_code < 500:
            return response
        retry_after = response.headers.get("retry-after")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else min(45.0, 2 ** attempt)
        time.sleep(delay + random.random() * 0.25)
    assert response is not None
    return response


def list_remote(client: httpx.Client, endpoint: str, token: str, prefix: str) -> set[str]:
    keys: set[str] = set()
    cursor: str | None = None
    while True:
        params = {"per_page": "1000", "prefix": prefix}
        if cursor:
            params["cursor"] = cursor
        response = request_with_backoff(
            client, "GET", endpoint, params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(body.get("errors") or body)
        keys.update(str(item["key"]) for item in body.get("result") or [])
        info = body.get("result_info") or {}
        if info.get("is_truncated") and info.get("cursor"):
            cursor = str(info["cursor"])
        else:
            return keys


def verify_public(keys: list[str], cdn: str, concurrency: int) -> list[str]:
    failures: list[str] = []

    def head(key: str) -> None:
        url = f"{cdn.rstrip('/')}/{quote(key, safe='/')}"
        with httpx.Client(timeout=45, follow_redirects=True) as client:
            response = request_with_backoff(client, "HEAD", url, headers={"Accept-Encoding": "identity"})
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            content_type = response.headers.get("content-type", "").lower()
            expected = "audio" if key.endswith(".mp3") else "json"
            if expected not in content_type and "octet-stream" not in content_type:
                raise RuntimeError(f"unexpected Content-Type {content_type!r}")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(head, key): key for key in keys}
        for completed, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                future.result()
            except Exception as exc:
                failures.append(f"{key}: {exc}")
            if completed % 500 == 0 or completed == len(futures):
                print(f"public HEAD {completed}/{len(futures)}; failures={len(failures)}", flush=True)
    return failures


def representative_keys(all_keys: set[str]) -> list[str]:
    wanted = [
        "nasai/0001.mp3", "nasai-timings/n0001.json",
        "nasai/0352.mp3", "nasai-timings/n0352.json", "nasai-timings/n0353.json",
        "nasai/1944.mp3", "nasai-timings/n1944.json",
        "nasai/4805.mp3", "nasai-timings/n4805.json",
        "nasai/5758.mp3", "nasai-timings/n5758.json",
    ]
    present = [key for key in wanted if key in all_keys]
    remaining = sorted(all_keys - set(present))
    if remaining:
        stride = max(1, len(remaining) // 20)
        present.extend(remaining[::stride][:20])
    return present


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--verify-public", choices=("none", "sample", "all"), default="sample")
    parser.add_argument("--cdn", default=DEFAULT_CDN)
    parser.add_argument("--reports", help="comma-separated report IDs/ranges")
    args = parser.parse_args()

    selected_reports = parse_reports(args.reports)
    rows = assets(args.base, selected_reports)
    local_keys = {key for _, key, _ in rows}
    audio_count = sum(key.endswith(".mp3") for key in local_keys)
    timing_count = sum(key.endswith(".json") for key in local_keys)
    inventory = {
        "objects": len(rows),
        "audio": audio_count,
        "timings": timing_count,
        "bytes": sum(path.stat().st_size for path, _, _ in rows),
    }
    print(json.dumps(inventory, indent=2))
    if selected_reports is None and (audio_count != EXPECTED_AUDIO or timing_count != EXPECTED_TIMINGS):
        raise SystemExit(
            f"expected {EXPECTED_AUDIO} audio + {EXPECTED_TIMINGS} timings; "
            f"found {audio_count} + {timing_count}"
        )
    if args.dry_run and not (args.missing_only or args.verify_only):
        return 0

    load_env(args.env_file)
    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    if not token or not account:
        raise SystemExit("Missing Cloudflare API configuration (values are never printed)")
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
    with httpx.Client(timeout=120) as client:
        print("listing current Nasa'i objects in R2 ...", flush=True)
        remote = list_remote(client, endpoint, token, "nasai/")
        remote |= list_remote(client, endpoint, token, "nasai-timings/")
    present = local_keys & remote
    missing = local_keys - remote
    extra = remote - local_keys if selected_reports is None else set()
    print(json.dumps({
        "present": len(present), "missing": len(missing), "extraUnderPrefixes": len(extra)
    }, indent=2))

    if args.verify_only:
        if missing:
            print(f"remote missing {len(missing)} object(s); first={sorted(missing)[:20]}")
            return 1
        mode_keys = sorted(local_keys) if args.verify_public == "all" else representative_keys(local_keys)
        if args.verify_public != "none":
            failures = verify_public(mode_keys, args.cdn, max(2, args.concurrency))
            if failures:
                print("\n".join(failures[:50]))
                return 1
        print(f"verified {len(local_keys)} listed objects; public checks={len(mode_keys) if args.verify_public != 'none' else 0}")
        return 0

    upload_rows = rows
    if args.missing_only and not args.replace:
        upload_rows = [row for row in rows if row[1] in missing]
    elif not args.replace:
        already = len(present)
        if already:
            raise SystemExit(f"{already} objects already exist; use --missing-only or --replace")
    print(f">> upload queue: {len(upload_rows)}")
    if args.dry_run:
        return 0

    progress_path = args.base / "r2-upload-progress.json"
    failed: list[dict[str, str]] = []
    uploaded: list[str] = []

    def upload(row: tuple[Path, str, str]) -> str:
        path, key, content_type = row
        with httpx.Client(timeout=180) as client:
            response = request_with_backoff(
                client, "PUT", f"{endpoint}/{key}", content=path.read_bytes(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type,
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(body.get("errors") or body)
        return key

    atomic_json(progress_path, {
        "phase": "nasai_r2_upload", "status": "running", "completed": 0,
        "total": len(upload_rows), "failed": [], "started": time.time(),
    })
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(upload, row): row for row in upload_rows}
        for completed, future in enumerate(as_completed(futures), 1):
            key = futures[future][1]
            try:
                uploaded.append(future.result())
            except Exception as exc:
                failed.append({"key": key, "error": str(exc)})
            if completed % 100 == 0 or completed == len(futures):
                atomic_json(progress_path, {
                    "phase": "nasai_r2_upload",
                    "status": "running",
                    "completed": completed,
                    "total": len(upload_rows),
                    "failed": failed,
                    "updated": time.time(),
                })
                print(f"uploaded {completed}/{len(upload_rows)}; failures={len(failed)}", flush=True)
    if failed:
        atomic_json(progress_path, {
            "phase": "nasai_r2_upload", "status": "complete_with_failures",
            "completed": len(upload_rows), "total": len(upload_rows), "failed": failed,
            "updated": time.time(),
        })
        print("\n".join(f"{item['key']}: {item['error']}" for item in failed[:50]))
        return 1

    with httpx.Client(timeout=120) as client:
        remote_after = list_remote(client, endpoint, token, "nasai/")
        remote_after |= list_remote(client, endpoint, token, "nasai-timings/")
    missing_after = local_keys - remote_after
    if missing_after:
        print(f"post-upload reconciliation missing {len(missing_after)}: {sorted(missing_after)[:20]}")
        return 1
    check_keys = sorted(local_keys) if args.verify_public == "all" else representative_keys(local_keys)
    public_failures = [] if args.verify_public == "none" else verify_public(
        check_keys, args.cdn, max(2, args.concurrency)
    )
    status = "complete" if not public_failures else "public_verify_failed"
    atomic_json(progress_path, {
        "phase": "nasai_r2_upload", "status": status,
        "completed": len(upload_rows), "total": len(upload_rows), "failed": public_failures,
        "remoteObjects": len(local_keys & remote_after), "updated": time.time(),
    })
    if public_failures:
        print("\n".join(public_failures[:50]))
        return 1
    print(f"R2 complete: {len(local_keys & remote_after)}/{len(local_keys)} expected objects present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
