#!/usr/bin/env python3
"""Watch Bukhari ASR batch timings and write a compact live progress manifest.

Scans qc/bukhari-asr-pilot/timings/ + worker progress + failures every ~2s,
writes public/bukhari-asr-progress-data.json (no tokens — small payload).

Usage:
  python watch_progress.py
  python watch_progress.py --once
  python watch_progress.py --interval 2
  python watch_progress.py --sync-demo   # also mirror playable assets into public/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PILOT = Path(__file__).resolve().parent
REPO = PILOT.parent.parent
TIMINGS = PILOT / "timings"
FAILURES = PILOT / "batch-1000-failures.json"
OUT = REPO / "public" / "bukhari-asr-progress-data.json"
DEFAULT_TOTAL = 2000  # covers 1-1000 + 1001-2000; bumps with worker ends
TOTAL = DEFAULT_TOTAL

# Fast extract: avoid loading huge token arrays
_RE_N = re.compile(r'"n"\s*:\s*(\d+)')
_RE_DUR = re.compile(r'"duration"\s*:\s*([0-9.]+)')
_RE_CER = re.compile(r'"cer"\s*:\s*([0-9.]+|null)')
_RE_COV = re.compile(r'"fa_coverage"\s*:\s*([0-9.]+|null)')


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def load_env_local() -> None:
    """Populate env vars from .env.local when running the watcher directly."""
    p = REPO / ".env.local"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


def env_base(*names: str) -> str:
    for name in names:
        v = (os.environ.get(name) or "").strip().rstrip("/")
        if v:
            return v
    return ""


def public_urls(n: int) -> dict[str, str | None]:
    r2_base = env_base("R2_PUBLIC_BASE")
    timing_base = env_base("TIMINGS_PUBLIC_BASE", "ASR_TIMINGS_PUBLIC_BASE")
    audio_url = f"{r2_base}/bukhari/{n:04d}.mp3" if r2_base else None
    timing_url = (
        f"{timing_base}/n{n:04d}.json"
        if timing_base
        else f"tests/bukhari-demo/n{n:04d}.json"
    )
    demo_url = f"bukhari-asr-demo.html?n={n}"
    return {
        "audio_url": audio_url,
        "timing_url": timing_url,
        "demo_url": demo_url,
    }


def extract_timing_meta(path: Path) -> dict | None:
    """Read head+tail only — skip the tokens array body."""
    try:
        with path.open("rb") as f:
            head = f.read(1200).decode("utf-8", errors="ignore")
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 800))
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return None

    blob = head + "\n" + tail
    m_n = _RE_N.search(blob)
    if not m_n:
        # fall back to filename nNNNN
        stem = path.stem
        if stem.startswith("n") and stem[1:].isdigit():
            n = int(stem[1:])
        else:
            return None
    else:
        n = int(m_n.group(1))

    def num(rx: re.Pattern[str]) -> float | None:
        m = rx.search(blob)
        if not m or m.group(1) == "null":
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    duration = num(_RE_DUR)
    cer = num(_RE_CER)
    coverage = num(_RE_COV)

    # Validity: presence of timing file + coverage > 0.5 (same spirit as batch)
    ok = True
    if coverage is not None and coverage <= 0.5:
        ok = False

    return {
        "n": n,
        "cer": round(cer, 4) if cer is not None else None,
        "coverage": round(coverage, 4) if coverage is not None else None,
        "duration": round(duration, 3) if duration is not None else None,
        "ok": ok,
    }


def load_failures() -> list[dict]:
    if not FAILURES.exists():
        return []
    try:
        data = json.loads(FAILURES.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        out = []
        for f in data:
            if not isinstance(f, dict) or "n" not in f:
                continue
            out.append(
                {
                    "n": int(f["n"]),
                    "error": str(f.get("error") or "failed")[:200],
                }
            )
        return out
    except Exception:
        return []


def load_workers() -> list[dict]:
    workers = []
    seen = set()
    for p in sorted(PILOT.glob("batch-*-progress-w*.json")):
        if p.name in seen:
            continue
        seen.add(p.name)
        try:
            w = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(w, dict):
                continue
            # Derive batch tag from filename batch-{tag}-progress-wN.json
            tag = None
            name = p.name
            if name.startswith("batch-") and "-progress-w" in name:
                tag = name[len("batch-"): name.index("-progress-w")]
            workers.append(
                {
                    "worker": w.get("worker"),
                    "batch": tag,
                    "start": w.get("start"),
                    "end": w.get("end"),
                    "last_n": w.get("last_n"),
                    "ok": w.get("ok"),
                    "fail": w.get("fail"),
                    "status": w.get("status"),
                    "started_at": w.get("started_at"),
                    "updated_at": w.get("updated_at"),
                    "wall_s": w.get("wall_s"),
                    "cer": w.get("cer"),
                }
            )
        except Exception:
            continue
    return workers


def resolve_total(workers: list[dict], done: list[dict], fail: list[dict]) -> int:
    total = TOTAL
    for w in workers:
        end = w.get("end")
        if isinstance(end, int) and end > total:
            total = end
    for d in done:
        n = d.get("n")
        if isinstance(n, int) and n > total:
            total = n
    for f in fail:
        n = f.get("n")
        if isinstance(n, int) and n > total:
            total = n
    return total


class Cache:
    def __init__(self) -> None:
        self.by_path: dict[str, tuple[float, int, dict]] = {}  # path -> (mtime, size, meta)

    def get(self, path: Path) -> dict | None:
        try:
            st = path.stat()
        except OSError:
            self.by_path.pop(str(path), None)
            return None
        key = str(path)
        prev = self.by_path.get(key)
        if prev and prev[0] == st.st_mtime and prev[1] == st.st_size:
            return prev[2]
        meta = extract_timing_meta(path)
        if meta is None:
            self.by_path.pop(key, None)
            return None
        self.by_path[key] = (st.st_mtime, st.st_size, meta)
        return meta

    def prune(self, alive: set[str]) -> None:
        dead = [k for k in self.by_path if k not in alive]
        for k in dead:
            del self.by_path[k]


CACHE = Cache()


def build_manifest() -> dict:
    done: list[dict] = []
    weak: list[dict] = []  # timing present but coverage too low
    alive: set[str] = set()

    if TIMINGS.exists():
        for path in TIMINGS.glob("n*.json"):
            if path.name.endswith(".tmp") or ".tmp" in path.suffixes:
                continue
            alive.add(str(path))
            meta = CACHE.get(path)
            if not meta:
                continue
            entry = {
                "n": meta["n"],
                "cer": meta["cer"],
                "coverage": meta["coverage"],
                "duration": meta["duration"],
            }
            if meta["ok"]:
                done.append(entry)
            else:
                weak.append(entry)

    CACHE.prune(alive)

    done.sort(key=lambda x: x["n"])
    done_ns = {d["n"] for d in done}

    for d in done:
        d.update(public_urls(d["n"]))

    failures_raw = load_failures()
    fail = [f for f in failures_raw if f["n"] not in done_ns]
    # weak coverage counts as fail for heatmap
    for w in weak:
        if w["n"] not in done_ns and not any(f["n"] == w["n"] for f in fail):
            fail.append(
                {
                    "n": w["n"],
                    "error": f"low coverage ({w.get('coverage')})",
                    "cer": w.get("cer"),
                    "coverage": w.get("coverage"),
                    "duration": w.get("duration"),
                }
            )
    fail.sort(key=lambda x: x["n"])
    fail_ns = {f["n"] for f in fail}

    workers = load_workers()
    total = resolve_total(workers, done, fail)
    active: list[int] = []
    for w in workers:
        if w.get("status") != "running":
            continue
        last = w.get("last_n")
        start = w.get("start") or 1
        end = w.get("end") or total
        if last is None:
            cand = start
        else:
            cand = int(last) + 1
        if start <= cand <= end and cand not in done_ns and cand not in fail_ns:
            active.append(cand)

    started_ts = [parse_iso(w.get("started_at")) for w in workers]
    started_ts = [t for t in started_ts if t is not None]
    earliest = min(started_ts) if started_ts else None
    now = time.time()
    done_count = len(done)
    fail_count = len(fail)
    pending = max(0, total - done_count - fail_count)
    elapsed = (now - earliest) if earliest else None

    eta_s = None
    rate = None
    if elapsed and elapsed > 5 and done_count > 0:
        rate = done_count / elapsed  # items/sec
        remaining = pending
        if rate > 0 and remaining > 0:
            eta_s = round(remaining / rate)

    sample_n = done[0]["n"] if done else 1
    sample = public_urls(sample_n)

    return {
        "updated": utc_now(),
        "total": total,
        "done_count": done_count,
        "fail_count": fail_count,
        "pending_count": pending,
        "active": active,
        "pct": round(100.0 * done_count / total, 2) if total else 0.0,
        "elapsed_s": round(elapsed, 1) if elapsed is not None else None,
        "rate_per_min": round(rate * 60, 2) if rate else None,
        "eta_s": eta_s,
        "public_base": env_base("R2_PUBLIC_BASE") or None,
        "timing_base": env_base("TIMINGS_PUBLIC_BASE", "ASR_TIMINGS_PUBLIC_BASE") or None,
        "sample_url": sample["audio_url"],
        "done": done,
        "fail": fail,
        "workers": workers,
    }


def write_manifest(manifest: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    tmp = OUT.with_name(f"{OUT.stem}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        for attempt in range(8):
            try:
                tmp.replace(OUT)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
            except OSError as e:
                if getattr(e, "winerror", None) not in (5, 32):
                    raise
                time.sleep(0.05 * (attempt + 1))
        # Fall back: leave previous manifest if locked
        print(f"[watch] replace skipped for {OUT.name} (locked)", flush=True)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def once() -> dict:
    m = build_manifest()
    write_manifest(m)
    return m


def maybe_sync_demo() -> str:
    """Mirror done timings+mp3 into public/tests/bukhari-demo/. Returns short status."""
    try:
        from sync_demo_assets import sync_all

        s = sync_all()
        return f"demo={s['viewable']}(+{s['synced']})"
    except Exception as e:
        return f"demo-err={type(e).__name__}:{e}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_env_local()
    ap = argparse.ArgumentParser(description="Live Bukhari ASR progress manifest writer")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between scans")
    ap.add_argument("--once", action="store_true", help="write once and exit")
    ap.add_argument(
        "--total",
        type=int,
        default=DEFAULT_TOTAL,
        help=f"heatmap total / pending baseline (default {DEFAULT_TOTAL})",
    )
    ap.add_argument(
        "--sync-demo",
        action="store_true",
        help="also sync playable mp3+timing JSON into public/tests/bukhari-demo/",
    )
    args = ap.parse_args()
    global TOTAL
    TOTAL = max(1, int(args.total))

    if args.once:
        m = once()
        extra = ""
        if args.sync_demo:
            extra = " " + maybe_sync_demo()
        print(
            f"wrote {OUT} done={m['done_count']} fail={m['fail_count']} "
            f"pending={m['pending_count']} bytes={OUT.stat().st_size}{extra}",
            flush=True,
        )
        return 0

    print(
        f"watching {TIMINGS} → {OUT} every {args.interval}s"
        + (" (+demo sync)" if args.sync_demo else ""),
        flush=True,
    )
    while True:
        t0 = time.perf_counter()
        try:
            m = once()
            demo_bit = ""
            if args.sync_demo:
                demo_bit = " " + maybe_sync_demo()
            dt = time.perf_counter() - t0
            print(
                f"[{m['updated']}] done={m['done_count']} fail={m['fail_count']} "
                f"pending={m['pending_count']} active={m['active']} "
                f"scan={dt:.2f}s size={OUT.stat().st_size}B{demo_bit}",
                flush=True,
            )
        except Exception as e:
            print(f"watch error: {type(e).__name__}: {e}", flush=True)
        time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
