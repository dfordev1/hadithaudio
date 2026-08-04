#!/usr/bin/env python3
"""Upload Bukhari ASR timing maps to Cloudflare R2, reconciled against the reader.

The reader gates audio playback on the timing sidecar, not the MP3:
`hasSyncedAudio = Boolean(timing)`. So a report whose MP3 is in R2 but whose
timing JSON is not still shows "Text only". This uploader closes that gap
safely:

  1. List existing bukhari-timings/ keys already in R2.
  2. Read the current Bukhari reader report IDs (public/bukhari/book-*.json).
  3. Upload only local numeric timings that (a) correspond to a current numeric
     reader report and (b) are absent from R2.
  4. Skip obsolete local numeric timings with no matching reader report.
  5. 4 workers with exponential backoff on 429/5xx.
  6. Verify each uploaded object (re-GET; structural check), plus a sample.
  7. Write a manifest of alphanumeric reports (e.g. 690b, 1390c) that this
     uploader deliberately does NOT touch -- they need per-report analysis.

Keys: bukhari-timings/nNNNN.json. Idempotent: reruns skip what already exists
remotely (use --replace to force re-PUT).

Run from the worktree that actually holds qc/bukhari-asr-pilot/timings (the
dirty primary worktree), e.g.:

    python scripts/r2-upload-bukhari-timings.py --dry-run
    python scripts/r2-upload-bukhari-timings.py --concurrency 4
    python scripts/r2-upload-bukhari-timings.py --verify-only
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "qc" / "bukhari-asr-pilot" / "timings"
BOOKS = ROOT / "public" / "bukhari"
MANIFEST = ROOT / "qc" / "bukhari-timing-upload-manifest.json"


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


def usable(data: dict) -> bool:
    return bool(data.get("tokens")) and any(
        isinstance(t.get("start"), (int, float))
        and isinstance(t.get("end"), (int, float))
        and t["end"] > t["start"]
        for t in data["tokens"]
    )


def reader_report_ids() -> tuple[set[str], list[str]]:
    numeric: set[str] = set()
    alpha: list[str] = []
    for path in glob.glob(str(BOOKS / "book-*.json")):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for hadith in data["hadith"]:
            rid = str(hadith["n"])
            if rid.isdigit():
                numeric.add(str(int(rid)))
            else:
                alpha.append(rid)
    return numeric, sorted(alpha)


def list_r2_timings(client: httpx.Client, account: str, bucket: str, token: str) -> set[str]:
    present: set[str] = set()
    cursor = None
    base = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
            f"/r2/buckets/{bucket}/objects")
    while True:
        params = {"per_page": "1000", "prefix": "bukhari-timings/"}
        if cursor:
            params["cursor"] = cursor
        for attempt in range(7):
            resp = client.get(base, params=params,
                              headers={"Authorization": f"Bearer {token}"})
            if resp.status_code != 429 and resp.status_code < 500:
                break
            time.sleep(min(30, 2 ** attempt))
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(body.get("errors") or body)
        for obj in body.get("result", []):
            m = re.match(r"bukhari-timings/n(\d+)\.json$", obj["key"])
            if m:
                present.add(str(int(m.group(1))))
        info = body.get("result_info") or {}
        if info.get("is_truncated") and info.get("cursor"):
            cursor = info["cursor"]
        else:
            return present


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true",
                        help="re-PUT even if the key already exists in R2")
    parser.add_argument("--verify-only", action="store_true",
                        help="skip upload; only reconcile and write the manifest")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    load_env()
    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    bucket = os.environ.get("R2_BUCKET", "hadithaudio")
    if not token or not account:
        raise SystemExit("Missing CF_API_TOKEN and/or CF_ACCOUNT_ID")
    if not TIMINGS.is_dir():
        raise SystemExit(f"Local timings not found: {TIMINGS}\n"
                         "Run from the worktree that holds qc/bukhari-asr-pilot/timings")

    numeric_reports, alpha_reports = reader_report_ids()
    endpoint = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
                f"/r2/buckets/{bucket}/objects")

    with httpx.Client(timeout=90) as client:
        print("listing existing R2 timings ...", flush=True)
        r2 = list_r2_timings(client, account, bucket, token)
    print(f"reader numeric reports : {len(numeric_reports)}")
    print(f"reader alphanumeric    : {len(alpha_reports)}")
    print(f"already in R2 (numeric): {len(r2 & numeric_reports)}")

    local: dict[str, Path] = {}
    for path in TIMINGS.glob("n*.json"):
        m = re.match(r"n(\d+)\.json$", path.name)
        if m:
            local[str(int(m.group(1)))] = path

    obsolete = sorted(set(local) - numeric_reports, key=int)
    no_local = sorted(numeric_reports - set(local), key=int)

    candidates = sorted(
        (numeric_reports & set(local)) - (set() if args.replace else r2),
        key=int,
    )

    to_upload: list[tuple[str, Path]] = []
    unusable: list[str] = []
    for rid in candidates:
        try:
            data = json.loads(local[rid].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unusable.append(rid)
            continue
        if usable(data):
            to_upload.append((rid, local[rid]))
        else:
            unusable.append(rid)

    if args.limit:
        to_upload = to_upload[: args.limit]

    print(f"obsolete local (skipped): {len(obsolete)} {obsolete}")
    print(f"numeric reports w/o local timing: {len(no_local)} {no_local[:20]}")
    print(f"unusable local (skipped): {len(unusable)} {unusable[:20]}")
    print(f">> to upload: {len(to_upload)}")

    manifest = {
        "schema": "hadith/bukhari-timing-upload/v1",
        "reader_numeric_reports": len(numeric_reports),
        "already_in_r2": sorted(r2 & numeric_reports, key=int),
        "uploaded_target": [rid for rid, _ in to_upload],
        "obsolete_local_skipped": obsolete,
        "numeric_reports_without_local_timing": no_local,
        "unusable_local_skipped": unusable,
        "alphanumeric_exceptions": alpha_reports,
        "alphanumeric_note": (
            "These reader reports have non-numeric locators (b/c suffixes). "
            "They are NOT handled here. Each must be classified: distinct "
            "recording needing its own alignment; duplicate/alternate sharing "
            "the base report's audio; or a report embedded in adjacent audio "
            "needing a separate timing slice. Never blind-copy base timings."
        ),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest written: {MANIFEST}")

    if args.verify_only or args.dry_run:
        return 0

    def upload(item: tuple[str, Path]) -> str:
        rid, path = item
        key = f"bukhari-timings/n{int(rid):04d}.json"
        payload = path.read_bytes()
        with httpx.Client(timeout=90) as client:
            for attempt in range(6):
                resp = client.put(
                    f"{endpoint}/{key}",
                    content=payload,
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json; charset=utf-8"},
                )
                if resp.status_code != 429 and resp.status_code < 500:
                    resp.raise_for_status()
                    body = resp.json()
                    if not body.get("success"):
                        raise RuntimeError(body.get("errors") or body)
                    return key
                if attempt == 5:
                    resp.raise_for_status()
                time.sleep(min(30, 2 ** attempt))
        return key

    failed: list[str] = []
    uploaded: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(upload, it): it[0] for it in to_upload}
        for i, future in enumerate(as_completed(futures), 1):
            rid = futures[future]
            try:
                uploaded.append(future.result())
            except Exception as exc:
                failed.append(f"n{rid}: {exc}")
            if i % 100 == 0 or i == len(to_upload):
                print(f"uploaded {i}/{len(to_upload)}", flush=True)

    if failed:
        print(f"FAILED {len(failed)}:\n" + "\n".join(failed[:20]))
        return 1

    sample = uploaded[:: max(1, len(uploaded) // 25)][:25] if uploaded else []
    print(f"verifying {len(sample)} uploaded objects ...")
    bad = []
    with httpx.Client(timeout=60) as client:
        for key in sample:
            resp = client.get(f"{endpoint}/{key}",
                              headers={"Authorization": f"Bearer {token}"})
            try:
                data = resp.json()
            except ValueError:
                bad.append(key)
                continue
            if not usable(data):
                bad.append(key)
    if bad:
        print(f"VERIFY FAILED for: {bad}")
        return 1
    print(f"verified OK ({len(sample)} sampled). uploaded {len(uploaded)} objects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
