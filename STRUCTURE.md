# Repository and data-flow structure

## Reader

- `public/index.html` is the single static reader application.
- `public/<collection>/index.json` maps books and report IDs.
- `public/<collection>/book-<n>.json` stores display tokens and isnād metadata.
- `public/gloss-compact/` stores deduplicated gloss pools and report token references.
- Official English/Urdu translations load from the repository-pinned hadith-api revision with local fill data as a fallback.

## Audio delivery

Production audio and timing JSON live in Cloudflare R2 behind `https://cdn.hadith.to`.

Collection convention:

```text
<slug>/<report>.mp3
<slug>-timings/n<report>.json
```

The timing sidecar controls the actual audio filename, allowing an intentionally shared clip (Nasāʾī 352/353) without duplicating audio.

Local Nasāʾī output is ignored by Git:

```text
qc/nasai-app-ready-full/
  clips/
  timings/
  qa/
  manifest.json
  progress.json
```

Large audio and generated timing assets must never be committed to Git.

## Nasāʾī pipeline

```text
reviewed ZIP + 12 original MP3s + canonical Arabic
        ↓
validate-nasai-app-ready.py
        ↓
app-ready validation JSON
        ↓
import-nasai-app-ready.py ──→ public/nasai/book-*.json (full isnād + matn)
        ↓
build-nasai-app-ready-clips.py
        ↓
per-report MP3 + timing JSON + resumable progress/manifest
        ↓
remap-nasai-timing-ids.py  (align timing IDs to reader/gloss IDs)
        ↓
verify-nasai-clips.py
        ↓
missing-only r2-upload-nasai.py
        ↓
main reader production QA
```

The reviewed ZIP is immutable. Three replacement-character repairs are applied as a separate, auditable presentation layer from `qc/nasai-canonical-repairs.json`.

## Boundary policy

- Non-overlapping adjacent reports retain their reviewed acoustic timestamps.
- Identical text with identical acoustic ranges may share audio.
- A non-shared edge overlap is partitioned inside the overlapping edge-token interval using canonical order. Raw values and repair metadata remain in the sidecar.
- No absent word receives a fabricated timestamp.

## Local testing

Serve the parent directory so both tracked reader files and ignored QC assets resolve:

```powershell
python -m http.server 8770 --directory C:\Users\Dv
```

Open:

```text
http://127.0.0.1:8770/hadithaudio-site-release/public/index.html#nasai:1
http://127.0.0.1:8770/hadithaudio-site-release/tools/control-panel/nasai.html
```

## Release flow

1. Validate canonical data and generated pairs.
2. Run corpus-encoding and repository-size checks.
3. Upload MP3s and timing JSON with immutable caching and low concurrency.
4. Verify representative CDN objects, including variants and text-only cases.
5. Run desktop/mobile interaction tests.
6. Commit only source code, compact reader data, tests, and documentation.
7. Push a ready branch/PR, merge, and verify `https://www.hadith.to`.

