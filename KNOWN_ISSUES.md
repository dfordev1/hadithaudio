# Known issues

## R2 upload in progress

- Severity: operational
- Evidence: `qc/nasai-app-ready-full/qa/r2-upload.log`
- State: local corpus is complete and verifier-clean; Cloudflare R2 had 0 Nasāʾī objects at upload start (11,345 missing).
- Action: resume with the exact command in `MEMORY.md` / `PROGRESS.json` if interrupted. Never mark synthetic audio as original.

## Six text-bearing reports are fully untimed

- Severity: content availability
- Reports: 17, 434b, 731, 1343, 2827, 2927
- Evidence: `qc/nasai-app-ready-full/qa/app-ready-validation.json`
- State: retained as full Arabic text, honestly shown without audio. The source package classifies the words as audio variants and supplies no independent times.
- Action: review real source recordings first; synthetic replacement is a final-phase fallback only and must be disclosed.

## Empty upstream rows

- Severity: upstream data gap
- Reports: 125, 1368, 1369, 1372, 3857–3938
- State: 86 report objects contain no Arabic lexical token and have no reader mapping. They are excluded; neighbouring text is never assigned.

## Source-manifest count warning

- Severity: low
- Recording 01 contains 502 report objects while its embedded validation summary says 500.
- State: all actual report IDs and token IDs are unique, content hashes pass, and canonical Arabic matches. The local validation report records the discrepancy.

## Boundary listening pass pending

- Severity: QA
- State: 50 non-shared edge overlaps are deterministically partitioned and recorded; representative and outlier listening tests remain required after R2 publication.
- Evidence: `qc/nasai-app-ready-full/qa/boundary-audit.json`

## Downloads path for app-ready ZIP

- Severity: low / environment
- The handoff path `C:\Users\Dv\Downloads\nasai-sunan-an-nasai-complete-app-ready.zip` was missing; the package is available at `C:\Users\Dv\hadithaudio\nasai-sunan-an-nasai-complete-app-ready.zip` and already extracted to `qc/nasai-app-ready-20260804`.
- Action: prefer the extracted staging copy; do not re-extract over verified assets casually.

## Excluded Claude drop

- Severity: policy
- `C:\Users\Dv\Downloads\Nasai 0` and the legacy `scripts/build-nasai-clips.py` path that pointed at it must not be used. App-ready package + `build-nasai-app-ready-clips.py` are authoritative.
