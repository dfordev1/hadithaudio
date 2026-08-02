from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "public" / "translations-pinned" / "manifest.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def fetch_raw(repo: str, commit: str, source_path: str, timeout: int) -> bytes:
    source_path = source_path.lstrip("/")
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{source_path}"
    request = urllib.request.Request(url, headers={"User-Agent": "CodexPinnedTranslations/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def validate_payload(name: str, payload: dict, expected_count: int) -> None:
    hadiths = payload.get("hadiths")
    if not isinstance(hadiths, list):
        raise ValueError(f"{name}: missing hadiths list")
    if len(hadiths) != expected_count:
        raise ValueError(f"{name}: expected {expected_count} hadiths, found {len(hadiths)}")


def normalize_commit(commit: str) -> str:
    commit = commit.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"invalid pinned commit: {commit!r}")
    return commit


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache pinned hadith-api translation payloads with count/hash validation.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to public/translations-pinned/manifest.json")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Override the cache directory from the manifest")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds")
    parser.add_argument("--verify-only", action="store_true", help="Validate payloads without writing the cache")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = read_json(manifest_path)

    upstream = manifest.get("upstream") or {}
    repo = upstream.get("repo") or os.environ.get("HADITH_API_REPO", "fawazahmed0/hadith-api")
    commit = normalize_commit(upstream.get("commit") or os.environ.get("HADITH_API_COMMIT", ""))

    cache_cfg = manifest.get("cache") or {}
    cache_dir = args.cache_dir or Path(os.environ.get("TRANSLATIONS_PINNED_CACHE_DIR") or cache_cfg.get("directory") or "public/translations-pinned/cache")
    if not cache_dir.is_absolute():
        cache_dir = (ROOT / cache_dir).resolve()

    editions = manifest.get("editions")
    if not isinstance(editions, list) or not editions:
        raise SystemExit("manifest.editions must be a non-empty list")

    summary = {
        "manifest": str(manifest_path),
        "repo": repo,
        "commit": commit,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "entries": [],
    }

    for entry in editions:
        if not isinstance(entry, dict):
            raise SystemExit("manifest.editions entries must be objects")
        name = entry.get("name") or entry.get("edition") or entry.get("output")
        if not name:
            raise SystemExit("each edition entry needs name/edition/output")
        source_path = entry.get("sourcePath")
        expected_count = entry.get("expectedHadithCount")
        expected_sha256 = entry.get("sha256")
        output_name = entry.get("output") or f"{name}.json"

        if not source_path:
            raise SystemExit(f"{name}: missing sourcePath")
        if not isinstance(expected_count, int) or expected_count <= 0:
            raise SystemExit(f"{name}: expectedHadithCount must be a positive integer")
        if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256)):
            raise SystemExit(f"{name}: sha256 must be a 64-character hex digest when present")

        raw = fetch_raw(repo, commit, source_path, args.timeout)
        payload = json.loads(raw)
        validate_payload(str(name), payload, expected_count)

        actual_sha256 = sha256_bytes(raw)
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise SystemExit(f"{name}: sha256 mismatch for pinned raw payload")

        if not args.verify_only:
            cache_dir.mkdir(parents=True, exist_ok=True)
            output_path = cache_dir / output_name
            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            tmp_path.write_bytes(raw)
            tmp_path.replace(output_path)
        else:
            output_path = cache_dir / output_name

        summary["entries"].append(
            {
                "name": name,
                "sourcePath": source_path,
                "output": str(output_path),
                "hadithCount": expected_count,
                "sha256": actual_sha256,
                "bytes": len(raw),
            }
        )

    if not args.verify_only:
        write_json(cache_dir / "index.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
