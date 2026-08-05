# Hadith.to operational memory

## Purpose

Hadith.to is a mobile-first Arabic hadith reader with official English/Urdu translations, word glosses, and word-synchronised recitation. The current priority is production-quality Sunan an-Nasāʾī audio.

**Site lightening (Aug 2026):** boot fonts trimmed to Source Sans 3 + Scheherazade; Arabic alternates and Nastaliq load on demand. Glosses fetch per-report `gloss-lazy/` slices first (~few KiB) with compact pool fallback. Forty MP3s on `cdn.hadith.to/recitation/`. Isnād word pools load only when study WBW is active.

## Authoritative Nasāʾī inputs

- Reviewed alignment archive: `C:\Users\Dv\Downloads\nasai-sunan-an-nasai-complete-app-ready.zip` (also mirrored at repo root / extracted under `C:\Users\Dv\hadithaudio\qc\nasai-app-ready-20260804`)
- Extracted immutable staging copy: `C:\Users\Dv\hadithaudio\qc\nasai-app-ready-20260804`
- Original recordings: `C:\Users\Dv\Downloads\Nasai\01.mp3` through `12.mp3` (junction → `C:\Users\Dv\hadithaudio\Nasai`)
- Canonical Arabic used for validation: `C:\Users\Dv\hadithaudio\qc\nasai-source\ara-nasai.json`
- Reader data: `public/nasai/index.json` and `public/nasai/book-*.json`
- Active engineering worktree: `C:\Users\Dv\hadithaudio-site-release` on branch `agent/nasai-audio-integration`
- The directory `C:\Users\Dv\Downloads\Nasai 0` is explicitly excluded by the user. Do not inspect, import, merge, move, delete, or cite it.

## Verified corpus facts

- 12/12 source recordings open successfully; MP3, mono, 16 kHz, 32 kbps.
- 5,765 unique source report objects.
- 5,679 text-bearing reader reports.
- 86 source rows are empty: 125, 1368, 1369, 1372, and 3857–3938. They are excluded rather than assigned neighbouring text.
- 334,948 canonical lexical tokens.
- 333,569 timestamped lexical tokens (99.588294%).
- 1,379 explicitly untimed/fused/variant lexical tokens.
- 359,712 unique source token IDs.
- Zero source hash failures, canonical mismatches, invalid intervals, token-order reversals, or duplicate token IDs.
- Six text-bearing reports have no independently timed lexical token: 17, 434b, 731, 1343, 2827, 2927. They remain text-only.
- Reports 352 and 353 contain identical canonical text and identical acoustic times. They intentionally share one clip.
- 50 non-shared adjacent report overlaps are edge-token CTC conflicts. The clip builder partitions each conflicting interval at a canonical-order midpoint constrained inside both crossing tokens and records the raw overlap and chosen boundary in timing metadata.
- The source manifest understates recording 01 by two report objects (500 declared, 502 present). Content hashes and IDs still validate.

## Disk state (2026-08-05)

- Unique clips: **5672 / 5672** under `qc/nasai-app-ready-full/clips/`
- Timing sidecars: **5673** under `qc/nasai-app-ready-full/timings/` (352/353 share audio)
- Publication verifier: **0 errors** (`qc/nasai-app-ready-full/qa/clip-verification.json`, `--quick` after ID remap)
- Full MP3 probe earlier: 5672/5672 probed, 0 probe failures
- Force-rebuilt short clip **2037**; expanded zero-width highlight on **5634**
- Timing token IDs remapped 1:1 to reader IDs via `scripts/remap-nasai-timing-ids.py` (gloss compatibility)
- R2: **11345 / 11345** objects present (audio 5672 + timings 5673); failures=0; sample public HEAD 31/31 OK on `https://cdn.hadith.to` (also verified via `R2_PUBLIC_BASE`). Logs: `qc/nasai-app-ready-full/qa/r2-upload.log`, `r2-upload-resume.log`, `r2-upload-final.log`

## Completed in this branch

- Added repeatable structural validator: `scripts/validate-nasai-app-ready.py`.
- Added full-isnād/full-matn reader importer: `scripts/import-nasai-app-ready.py`.
- Replaced Nasāʾī matn-only reader tokens with full canonical tokens while retaining legacy matn IDs for gloss compatibility.
- Repaired three inherited U+FFFD defects with provenance in `qc/nasai-canonical-repairs.json`.
- Added resumable clip/timing builder: `scripts/build-nasai-app-ready-clips.py`.
- Added boundary audit: `scripts/audit-nasai-boundaries.py`.
- Added verifier: `scripts/verify-nasai-clips.py`.
- Added R2 uploader: `scripts/r2-upload-nasai.py` (rejects synthetic mislabeled as original).
- Added timing↔reader ID remapper: `scripts/remap-nasai-timing-ids.py`.
- Added local progress/control page: `tools/control-panel/nasai.html`.
- Enabled Nasāʾī timing/audio loading in the main reader.
- Fixed the untimed-word notice so punctuation/null editorial markers are not counted as words.
- Live pilot tested reports 1 and 2: load, full Arabic, official translations, playback, seek, active-word update, and Next navigation all passed.
- Full clip build finished; publication verifier clean; R2 upload completed 11345/11345 with sample CDN verify.

## Local URLs

- Reader: `http://127.0.0.1:8770/hadithaudio-site-release/public/index.html#nasai:1`
- Control panel: `http://127.0.0.1:8770/hadithaudio-site-release/tools/control-panel/nasai.html`
- CDN sample audio: `https://cdn.hadith.to/nasai/0001.mp3`
- CDN sample timing: `https://cdn.hadith.to/nasai-timings/n0001.json`
- Serve with: `python -m http.server 8770 --bind 127.0.0.1` from `C:\Users\Dv`

## Exact next command

```powershell
cd C:\Users\Dv\hadithaudio-site-release
# R2 upload complete. Next: boundary listening pass + production reader QA
python scripts\verify-nasai-clips.py --workers 8 --output qc\nasai-app-ready-full\qa\clip-verification.json
```

## Core commands

```powershell
python scripts\validate-nasai-app-ready.py --package-dir C:\Users\Dv\hadithaudio\qc\nasai-app-ready-20260804 --audio-dir C:\Users\Dv\Downloads\Nasai --canonical-json C:\Users\Dv\hadithaudio\qc\nasai-source\ara-nasai.json --reader-dir public\nasai --output qc\nasai-app-ready-full\qa\app-ready-validation.json

python scripts\import-nasai-app-ready.py --package-dir C:\Users\Dv\hadithaudio\qc\nasai-app-ready-20260804 --reader-dir public\nasai --report qc\nasai-app-ready-full\qa\reader-import.json --write

python scripts\build-nasai-app-ready-clips.py --package-dir C:\Users\Dv\hadithaudio\qc\nasai-app-ready-20260804 --audio-dir C:\Users\Dv\Downloads\Nasai --output-dir qc\nasai-app-ready-full --workers 4

python scripts\remap-nasai-timing-ids.py

python scripts\verify-nasai-clips.py --quick --output qc\nasai-app-ready-full\qa\clip-verification.json

python scripts\audit-nasai-boundaries.py --package-dir C:\Users\Dv\hadithaudio\qc\nasai-app-ready-20260804 --output qc\nasai-app-ready-full\qa\boundary-audit.json

python scripts\r2-upload-nasai.py --missing-only --concurrency 6 --verify-public sample --env-file .env.local
```

## Current next action

R2 upload is complete (11345/11345, 0 failures, sample CDN HEADs OK). Do a short listening pass on the 50 boundary repairs and production-reader QA. Do **not** start ElevenLabs / cross-collection work. Do **not** use Nasai 0.
## Boundary listening QA (2026-08-05)

- Report: `qc/nasai-app-ready-full/qa/boundary-listening-report.md` (script: `scripts/run-boundary-listening-qa.py`).
- Mechanical checks on 50 midpoint repairs: **50/50 OK**; **18/50** need no mandatory re-listen (overlap <0.4s).
- Human re-listen queue: **27** pairs remaining; **5/5** priority high-overlap pairs **human_ok / listened-pass** (2026-08-05, user listened: OK).
- 352/353 share `0352.mp3`; text-only six have no timing sidecars (no false aligned-audio sidecars).

