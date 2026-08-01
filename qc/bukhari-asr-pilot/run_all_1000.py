#!/usr/bin/env python3
"""Batch Bukhari ASR + CTC FA (resume-safe, sharded).

Usage:
  python run_all_1000.py --start 1 --end 250 --worker 0
  python run_all_1000.py --start 1001 --end 1250 --worker 0 --tag 1001-2000 --zip PATH
  python run_all_1000.py --merge --tag 1001-2000
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from asr_align import (
    MODEL,
    PILOT,
    TOKENS,
    AlignEngine,
    cer,
    ensure_audio,
    fetch_hadith_text,
    force_align_text,
    load_audio_16k,
    wer,
)

TIMINGS = PILOT / "timings"
FAILURES = PILOT / "batch-1000-failures.json"  # shared (watch_progress)
MAX_N = 7563

BATCH_TAG = "1000"
PROGRESS_MERGED = PILOT / "batch-1000-progress.json"
SUMMARY = PILOT / "batch-1000-summary.json"
ZIP_CANDIDATES: list[Path] | None = None


def configure_batch(tag: str) -> None:
    global BATCH_TAG, PROGRESS_MERGED, SUMMARY
    BATCH_TAG = tag
    PROGRESS_MERGED = PILOT / f"batch-{tag}-progress.json"
    SUMMARY = PILOT / f"batch-{tag}-summary.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def progress_path(worker: int) -> Path:
    return PILOT / f"batch-{BATCH_TAG}-progress-w{worker}.json"


def timing_valid(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    tokens = data.get("tokens") or []
    if not tokens:
        return False
    if not any((t.get("end") or 0) > 0 for t in tokens):
        return False
    cov = data.get("fa_coverage")
    if cov is None:
        last = tokens[-1].get("end") or 0
        dur = data.get("duration") or 0
        cov = (last / dur) if dur else 0
    return float(cov) > 0.5


def fetch_text_retry(n: int) -> dict:
    try:
        return fetch_hadith_text(n)
    except Exception as e1:
        time.sleep(1.5)
        try:
            return fetch_hadith_text(n)
        except Exception as e2:
            raise RuntimeError(f"text CDN failed after retry: {e1!s} | {e2!s}") from e2


def _atomic_write_json(path: Path, payload: str) -> bool:
    """Write JSON via unique tmp + replace. Windows-safe against watcher locks.

    Retries PermissionError a few times; on persistent lock, logs and returns False
    so workers keep processing instead of dying.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        last_err: Exception | None = None
        for attempt in range(8):
            try:
                tmp.replace(path)
                return True
            except PermissionError as e:
                last_err = e
                time.sleep(0.05 * (attempt + 1))
            except OSError as e:
                # WinError 5 sometimes surfaces as OSError; also sharing violations
                if getattr(e, "winerror", None) not in (5, 32) and e.errno not in (
                    13,
                    11,
                ):
                    raise
                last_err = e
                time.sleep(0.05 * (attempt + 1))
        print(
            f"[progress] replace skipped for {path.name}: {last_err!r}",
            flush=True,
        )
        return False
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def append_failure(n: int, error: str, worker: int) -> None:
    FAILURES.parent.mkdir(parents=True, exist_ok=True)
    failures: list = []
    if FAILURES.exists():
        try:
            failures = json.loads(FAILURES.read_text(encoding="utf-8"))
            if not isinstance(failures, list):
                failures = []
        except Exception:
            failures = []
    failures = [f for f in failures if f.get("n") != n]
    failures.append({"n": n, "error": error, "worker": worker, "at": utc_now()})
    _atomic_write_json(FAILURES, json.dumps(failures, ensure_ascii=False, indent=2))


def write_worker_progress(worker: int, state: dict) -> None:
    path = progress_path(worker)
    _atomic_write_json(path, json.dumps(state, ensure_ascii=False, indent=2))


def cer_stats(cers: list[float]) -> dict:
    if not cers:
        return {"count": 0, "p50": None, "p90": None, "mean": None, "min": None, "max": None}
    xs = sorted(cers)
    def pct(p: float) -> float:
        if len(xs) == 1:
            return xs[0]
        i = (len(xs) - 1) * p
        lo = int(i)
        hi = min(lo + 1, len(xs) - 1)
        frac = i - lo
        return round(xs[lo] * (1 - frac) + xs[hi] * frac, 4)
    return {
        "count": len(xs),
        "p50": pct(0.5),
        "p90": pct(0.9),
        "mean": round(statistics.mean(xs), 4),
        "min": round(xs[0], 4),
        "max": round(xs[-1], 4),
    }


def process_one(engine: AlignEngine, n: int) -> dict:
    print(f"\n=== Hadith {n} ===", flush=True)
    audio = ensure_audio(n, zip_candidates=ZIP_CANDIDATES)
    text = fetch_text_retry(n)
    full = text["fullText"]
    print(f"audio={audio.name}  chars={len(full)} words={len(full.split())}", flush=True)

    samples, sr = load_audio_16k(audio)
    duration = len(samples) / sr
    print(f"duration={duration:.2f}s", flush=True)

    decode = engine.free_decode(samples, sr)
    hyp = decode["hypothesis"]
    alignment_text = full.strip()
    fallback_reason = None
    if not alignment_text and hyp.strip():
        alignment_text = hyp.strip()
        fallback_reason = "empty canonical Arabic; aligned ASR hypothesis"

    c = round(cer(full, hyp), 4) if full.strip() else None
    w = round(wer(full, hyp), 4) if full.strip() else None
    print(f"decode {decode['elapsed_s']}s  CER={c} WER={w}", flush=True)

    fa_tokens, fa_note = force_align_text(engine, samples, alignment_text, sr)
    fa_worked = len(fa_tokens) > 0 and any(t.get("end", 0) > 0 for t in fa_tokens)
    last_end = fa_tokens[-1]["end"] if fa_tokens else 0.0
    coverage = round(last_end / duration, 4) if duration > 0 else 0.0
    if (not fa_worked or coverage <= 0.5) and hyp.strip() and alignment_text != hyp.strip():
        retry_tokens, retry_note = force_align_text(engine, samples, hyp.strip(), sr)
        retry_last_end = retry_tokens[-1]["end"] if retry_tokens else 0.0
        retry_coverage = round(retry_last_end / duration, 4) if duration > 0 else 0.0
        if retry_tokens and retry_coverage > coverage:
            fa_tokens = retry_tokens
            fa_note = f"{retry_note}; fallback after canonical FA failure"
            fa_worked = any(t.get("end", 0) > 0 for t in fa_tokens)
            last_end = retry_last_end
            coverage = retry_coverage
            alignment_text = hyp.strip()
            fallback_reason = "canonical FA failed; aligned ASR hypothesis"
    print(fa_note, flush=True)
    print(f"FA coverage={coverage}", flush=True)

    timing = {
        "kind": "bukhari-asr-demo",
        "collection": "bukhari",
        "n": n,
        "audio": f"{n:04d}.mp3",
        "duration": round(duration, 3),
        "diplomatic": alignment_text,
        "canonical_diplomatic": full if fallback_reason else None,
        "english": text.get("english") or "",
        "tokens": fa_tokens,
        "source": "ctc_fa" if fa_worked else "none",
        "token_scheme": "whitespace-demo",
        "cer": c,
        "wer": w,
        "fa_coverage": coverage,
        "fa_note": fa_note,
        "text_source": text.get("source"),
        "alignment_fallback": fallback_reason,
    }

    TIMINGS.mkdir(parents=True, exist_ok=True)
    out = TIMINGS / f"n{n:04d}.json"
    payload = json.dumps(timing, ensure_ascii=False, indent=2)
    if not _atomic_write_json(out, payload):
        # Last resort direct write if replace was locked
        out.write_text(payload, encoding="utf-8")
    print(f"wrote {out.name}", flush=True)

    return {
        "n": n,
        "ok": bool(fa_worked and coverage > 0.5),
        "skipped": False,
        "duration_s": round(duration, 3),
        "cer": c,
        "wer": w,
        "fa_words": len(fa_tokens),
        "fa_coverage": coverage,
        "decode_s": decode["elapsed_s"],
        "error": None if fa_worked else fa_note,
    }


def merge_progress() -> dict:
    workers = []
    seen = set()
    paths = []
    for pat in (f"batch-{BATCH_TAG}-progress-w*.json", "batch-*-progress-w*.json"):
        for p in sorted(PILOT.glob(pat)):
            if p.name in seen:
                continue
            seen.add(p.name)
            paths.append(p)
    for p in paths:
        try:
            workers.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            workers.append({"file": p.name, "error": str(e)})

    timing_files = sorted(TIMINGS.glob("n*.json")) if TIMINGS.exists() else []
    ok_ns: list[int] = []
    cers: list[float] = []
    coverages: list[float] = []
    for tf in timing_files:
        if not timing_valid(tf):
            continue
        try:
            d = json.loads(tf.read_text(encoding="utf-8"))
            n = int(d.get("n") or tf.stem[1:])
            ok_ns.append(n)
            if d.get("cer") is not None:
                cers.append(float(d["cer"]))
            if d.get("fa_coverage") is not None:
                coverages.append(float(d["fa_coverage"]))
        except Exception:
            continue

    failures = []
    if FAILURES.exists():
        try:
            failures = json.loads(FAILURES.read_text(encoding="utf-8"))
        except Exception:
            failures = []

    fail_ns = sorted({int(f["n"]) for f in failures if "n" in f})
    # Drop failures that later succeeded
    fail_ns = [n for n in fail_ns if n not in set(ok_ns)]
    failures = [f for f in failures if f.get("n") in set(fail_ns)]
    FAILURES.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")

    last_ns = [w.get("last_n") for w in workers if isinstance(w, dict) and w.get("last_n") is not None]
    merged = {
        "updated_at": utc_now(),
        "workers": workers,
        "ok_count": len(ok_ns),
        "fail_count": len(fail_ns),
        "timing_files": len(timing_files),
        "valid_timings": len(ok_ns),
        "last_n_max": max(last_ns) if last_ns else None,
        "cer": cer_stats(cers),
        "coverage": cer_stats(coverages),
        "failed_ns": fail_ns,
        "range_tag": BATCH_TAG,
        "missing_ns": [
            n for n in range(1, (max(ok_ns) if ok_ns else 0) + 1)
            if n not in set(ok_ns)
        ] if ok_ns else [],
    }
    PROGRESS_MERGED.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        **merged,
        "engine": "Quran FastConformer (sherpa-onnx + onnxruntime CTC FA)",
        "model": MODEL.name,
        "range": BATCH_TAG,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def run_range(
    start: int,
    end: int,
    worker: int,
    *,
    only: list[int] | None = None,
    num_threads: int = 1,
    max_chunk_s: float | None = None,
    clear_between: bool = False,
) -> int:
    assert MODEL.exists(), MODEL
    assert TOKENS.exists(), TOKENS

    try:
        import kaldi_native_fbank  # noqa: F401
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "kaldi-native-fbank"])

    engine = AlignEngine(num_threads=num_threads, max_chunk_s=max_chunk_s)
    t_start = time.perf_counter()
    ok = 0
    fail = 0
    skipped = 0
    cers: list[float] = []
    last_n = None
    processed = 0

    if only:
        ns = [n for n in only if start <= n <= end] if start and end else list(only)
        ns = sorted(set(ns))
    else:
        ns = list(range(start, end + 1))

    state = {
        "worker": worker,
        "start": start if not only else (ns[0] if ns else start),
        "end": end if not only else (ns[-1] if ns else end),
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "last_n": None,
        "ok": 0,
        "fail": 0,
        "skipped": 0,
        "processed": 0,
        "cer": cer_stats([]),
        "status": "running",
        "wall_s": 0,
    }
    write_worker_progress(worker, state)

    for idx, n in enumerate(ns):
        last_n = n
        out = TIMINGS / f"n{n:04d}.json"
        if out.exists() and timing_valid(out):
            skipped += 1
            try:
                d = json.loads(out.read_text(encoding="utf-8"))
                if d.get("cer") is not None:
                    cers.append(float(d["cer"]))
                ok += 1  # count as success already present
            except Exception:
                pass
            print(f"SKIP n={n} (valid timing exists)", flush=True)
        else:
            try:
                r = process_one(engine, n)
                processed += 1
                if r.get("ok"):
                    ok += 1
                    if r.get("cer") is not None:
                        cers.append(float(r["cer"]))
                else:
                    fail += 1
                    append_failure(n, r.get("error") or "FA failed", worker)
            except MemoryError as e:
                # Retry once with smaller chunks + cleared sessions
                print(f"MemoryError n={n}; clearing sessions and retrying with chunk=60s", flush=True)
                engine.clear_sessions()
                engine.max_chunk_s = min(float(getattr(engine, "max_chunk_s", 120.0) or 120.0), 60.0)
                try:
                    import gc

                    gc.collect()
                except Exception:
                    pass
                try:
                    r = process_one(engine, n)
                    processed += 1
                    if r.get("ok"):
                        ok += 1
                        if r.get("cer") is not None:
                            cers.append(float(r["cer"]))
                    else:
                        fail += 1
                        append_failure(n, r.get("error") or "FA failed", worker)
                except Exception as e2:
                    processed += 1
                    fail += 1
                    err = f"{type(e2).__name__}: {e2} (after MemoryError: {e})"
                    print(f"FAIL n={n}: {err}", flush=True)
                    traceback.print_exc()
                    append_failure(n, err, worker)
            except Exception as e:
                processed += 1
                fail += 1
                err = f"{type(e).__name__}: {e}"
                print(f"FAIL n={n}: {err}", flush=True)
                traceback.print_exc()
                append_failure(n, err, worker)

            if clear_between:
                engine.clear_sessions()

        state.update(
            {
                "updated_at": utc_now(),
                "last_n": last_n,
                "ok": ok,
                "fail": fail,
                "skipped": skipped,
                "processed": processed,
                "cer": cer_stats(cers),
                "wall_s": round(time.perf_counter() - t_start, 1),
                "status": "running",
            }
        )
        write_worker_progress(worker, state)

        # Periodic merged summary every 50 hadiths in this shard
        if (idx + 1) % 50 == 0 or n == ns[-1]:
            try:
                merge_progress()
                print(f"[w{worker}] merged progress at n={n}", flush=True)
            except Exception as e:
                print(f"[w{worker}] merge warning: {e}", flush=True)

    state["status"] = "done"
    state["finished_at"] = utc_now()
    state["wall_s"] = round(time.perf_counter() - t_start, 1)
    write_worker_progress(worker, state)
    merge_progress()
    print(
        f"\n[w{worker}] DONE start={start} end={end} ok={ok} fail={fail} "
        f"skipped={skipped} wall={state['wall_s']}s",
        flush=True,
    )
    return 0 if fail == 0 else 1


def main() -> int:
    global ZIP_CANDIDATES
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=1000)
    ap.add_argument("--worker", type=int, default=0)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument(
        "--only",
        type=str,
        default="",
        help="comma-separated hadith numbers to process (ignores contiguous range fill)",
    )
    ap.add_argument("--num-threads", type=int, default=1, help="ONNX/Sherpa threads (default 1)")
    ap.add_argument(
        "--max-chunk-s",
        type=float,
        default=0.0,
        help="FA/decode chunk seconds (0 = engine default)",
    )
    ap.add_argument(
        "--clear-between",
        action="store_true",
        help="drop ONNX/Sherpa sessions after each hadith (lower peak RAM)",
    )
    ap.add_argument(
        "--tag",
        type=str,
        default="",
        help="progress file tag (pass 1001-2000 for shard runs)",
    )
    ap.add_argument(
        "--zip",
        type=str,
        default="",
        help="optional mp3 zip path (prepended to auto candidates)",
    )
    args = ap.parse_args()

    tag = args.tag.strip()
    if not tag:
        if args.start == 1 and args.end == 1000:
            tag = "1000"
        else:
            tag = f"{args.start}-{args.end}"
    configure_batch(tag)

    if args.zip:
        from asr_align import default_zip_candidates

        zp = Path(args.zip)
        mid = (args.start + args.end) // 2
        ZIP_CANDIDATES = [zp] + [c for c in default_zip_candidates(mid) if c.resolve() != zp.resolve()]

    if args.merge:
        m = merge_progress()
        print(json.dumps({k: m[k] for k in ("ok_count", "fail_count", "cer", "coverage", "missing_ns") if k in m}, indent=2))
        print(f"missing count: {len(m.get('missing_ns') or [])}")
        return 0

    only: list[int] | None = None
    if args.only.strip():
        only = []
        for part in args.only.split(","):
            part = part.strip()
            if not part:
                continue
            only.append(int(part))
        if not only:
            print("Empty --only list", file=sys.stderr)
            return 2
        args.start = min(only)
        args.end = max(only)

    if args.start < 1 or args.end > MAX_N or args.start > args.end:
        print(f"Invalid range (1..{MAX_N})", file=sys.stderr)
        return 2
    max_chunk = float(args.max_chunk_s) if args.max_chunk_s and args.max_chunk_s > 0 else None
    return run_range(
        args.start,
        args.end,
        args.worker,
        only=only,
        num_threads=args.num_threads,
        max_chunk_s=max_chunk,
        clear_between=bool(args.clear_between),
    )


if __name__ == "__main__":
    raise SystemExit(main())
