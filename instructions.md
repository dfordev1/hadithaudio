# Hadith Read-and-Listen — Build & Continuation Instructions

Handoff doc for continuing this project (e.g. in Cursor). Read this top to bottom
before touching anything. It covers what exists, where it lives, how the pieces
fit, what's left, and the exact commands + gotchas.

---

## 1. What this project is

A lightweight static site that presents hadith collections with:
- **Synced Arabic recitation** (TTS) with **word-level highlighting** (Forty collections only — timing sidecars exist; Muwatta is text/gloss-only until audio lands),
- **Word-by-word English + Urdu glosses** (a "HUSX gloss layer"; same schema for Forties + Muwatta),
- **Parallel Arabic/English**, cross-references that deep-link to sunnah.com,
- Reader settings (incl. Autoplay next + Repeat one, persisted), deep links, and a browsable Muwatta **in the same reader**.

It sits on top of **HUSX** — an evidence-first hadith interchange standard: a
stable-id corpus (witness → isnad → mention → token) with independent **sidecar
layers** (audio timing, translation, refs, sunnah-compat, clauses, glosses) that
address the same token ids without modifying the corpus.

## 2. Repos & deploy

| | |
|---|---|
| **Site (this repo)** | https://github.com/dfordev1/hadithaudio — static site, deployed by **Vercel** on push to `main` |
| **Live** | https://www.hadith.to (Vercel; `vercel.json` sets `outputDirectory: public`) |
| **HUSX data standard** | https://github.com/dfordev1/hadithusx — the corpus format, schema, validator, SDK. **The local `hadithusx/` folder is a clone with UNCOMMITTED work (see §7).** |
| **Prior art (Quran word-audio)** | https://github.com/dfordev1/qusx-audio — the sidecar/word-gloss pattern this follows |
| **Text data source** | `fawazahmed0/hadith-api` via jsDelivr CDN: `https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/<edition>.json` |
| **Profile site** (separate) | https://dfordev1.github.io/ — repo `dfordev1.github.io`; not part of this deploy |

Deploy = `git push origin main`. Vercel auto-builds. No build step (static).

## 3. Local layout (C:/Users/Dv/hadithaudio)

```
public/                         # the deployed site
  index.html                    # MAIN reader: Forties + Muwatta (unified); audio + WBW for Forties; text/gloss + book picker for Malik
  malik.html                    # redirects → ./#malik:N (legacy bookmarks)
  gloss.html / malik-sample.html/ tests.html / progress.html   # aux/QA pages
  recitation/<corpus>.NNN.mp3 + .json   # audio + per-token timing (Forty only so far)
  translation/<slug>.json       # English sentence-translation sidecar
  sunnah/<slug>.json            # sunnah.com identifier + cross-ref sidecar
  refs/nawawi.json              # cross-collection reference map (Nawawi pilot)
  gloss/<slug>-N.json           # word-by-word EN/UR gloss sidecar, one per hadith
  malik/book-N.json + index.json # Muwatta tokens grouped by book (for reader book picker)
hadithusx/                      # clone of the data-standard repo (see §7)
  data/<corpus>.json            # the husx corpus (witnesses, isnads, matn tokens)
  data/<corpus>.en.json / .refs.json / .sunnah.json / .clauses.json
  scripts/import-*.mjs build-*.mjs check-*.mjs validate.mjs convert-corpus.mjs
generate-recitation.mjs         # ElevenLabs TTS audio + timing (needs .env) — schema reference
omni-test.py                    # OmniVoice smoke test (language id arb, not ar)
OMNIVOICE-HANDOFF.md            # full friend handoff for local TTS + WhisperX alignment
pausal.mjs fix-clause.mjs       # audio: pausal (waqf) transform, clause splice-fix
check-glosses.mjs progress.mjs  # QA: gloss structural check, progress heatmap snapshot
.env                            # ELEVENLABS_API_KEY=...  (GITIGNORED — see §9)
```

## 4. Collection slugs / corpora

| slug | corpus (husx basename) | count | audio | glosses | reviewed |
|---|---|---|---|---|---|
| `nawawi40` | `nawawi-arbain` | 42 | ✅ | ✅ | ✅ |
| `qudsi40` | `qudsi-arbain` | 40 | ✅ | ✅ | ✅ |
| `shahwaliullah40` | `shahwaliullah-arbain` | 40 | ✅ | ✅ | ✅ |
| `malik` | `malik` (Muwatta) | 1829 | ❌ | **1829/1829** | ≈1537 (≈292 lack `review` block) |

`sunnah.com` numbering: **Bukhari** number == fawazahmed0 `hadithnumber`;
**Muslim** number == fawazahmed0 `arabicnumber` with the decimal as a letter
suffix (`1907.01` → `muslim:1907a`). Muwatta slug on sunnah.com is `malik`.

HUSX note: token ids are stable; gloss schema is shared Forties+Muwatta. Timing /
`public/recitation/*.json` is Forties-only until Muwatta audio exists.

## 5. The layers (all keyed to husx token ids; corpus never modified)

1. **recitation** — `public/recitation/<corpus>.NNN.{mp3,json}`. JSON = `{witness, duration, tokens:[{id,position,text,start,end}]}`.
2. **translation** — `public/translation/<slug>.json` (per-report English matn).
3. **refs / sunnah-compat** — `public/sunnah/<slug>.json` (primary `nawawi40:N` id + machine-suggested Bukhari/Muslim cross-refs with sunnah.com URLs).
4. **clauses** — `hadithusx/data/<corpus>.clauses.json` (waqf-bounded clause spans over tokens).
5. **gloss** — `public/gloss/<slug>-N.json`: `{husxGloss:"0.1", work, witness, languages:["en","ur"], reviewState:"machine-suggested", note, glosses:{"<token id>":{en,ur}}, review?:{checkedBy,method,tokensChecked,tokensChanged,changes[]}}`. **One gloss per matn token, keyed by exact token id.** Supplied/implied words in `[brackets]`.

## 6. WHAT'S LEFT (do these)

### 6a. Finish Muwatta scholarly reviews (optional / backlog)
- **All 1829 Muwatta hadith are glossed** (gap closed; do not reopen "28 unglossed").
- ≈292 still lack a scholarly `review` block. The reader barely uses reviews; this is polish, not blocking.
- Find gaps: `node check-glosses.mjs malik malik` (structural), and:
  `node -e "const c=require('./hadithusx/data/malik.json');const fs=require('fs');for(const w of c.witnesses){const n=w.structuredLocator.reportNumber;const f='public/gloss/malik-'+n+'.json';if(!fs.existsSync(f))console.log('nogloss',n);else if(!fs.readFileSync(f,'utf8').includes('\"review\"'))console.log('noreview',n);}"`
- Review remaining gaps using the workflow pattern in §8 if desired.

### 6b. Commit the hadithusx work (see §7) — still important
The data standard's substance is still largely uncommitted in the local `hadithusx/` clone. Commit + push there.

### 6c. (Optional) More books
Add any fawazahmed0 collection the same way. **Big canonical books** (Bukhari
`ara-bukhari` ~7563, Muslim `ara-muslim` ~7563) are 4–8× Muwatta — glossing them
is a very large multi-session run; do a book/kitab at a time. `eng-<x>` and
often `urd-<x>` editions exist as gloss anchors.

**ElevenLabs cost ballpark (if paying):** Muwatta matn alone ≈728k chars → ≈$36 Turbo / ≈364k list credits. Full Sittah+Muwatta on full-text editions upper ≈$550–$1000 Turbo; matn-only lower. Prefer **OmniVoice** (§6e) for free local generation at that scale.

### 6d. (Real quality) Authoritative audio
TTS **cannot** produce correct iʿrāb (case endings) or tajwīd — it's a labeled
*draft*. The real fix is **forced-aligning a real qārī's recitation** to the husx
tokens (same player, better source). This is the destination, not more TTS.

### 6e. OmniVoice local TTS path (preferred free path for new audio)

Full friend handoff: **`OMNIVOICE-HANDOFF.md`** at repo root — give that file to whoever runs local TTS + timestamps. That file has the full **QC / double-check** procedure (§7 there); the short version below is for anyone accepting a batch into this repo.

Short version:
- [OmniVoice](https://github.com/k2-fsa/OmniVoice) — free local TTS. Arabic language id is **`arb` (not `ar`)**; `ar` silently falls back to language-agnostic mode.
- No native character timestamps → use **WhisperX** (free, local) forced alignment against the exact diplomatic matn text.
- Output must match `public/recitation/*.json` token `start`/`end` schema (same shape as ElevenLabs pipeline).
- Hardware: **NVIDIA 12GB+ VRAM** recommended for serious runs; MacBook OK for a pilot only.
- Cost: software free. Vs ElevenLabs Sittah+Muwatta roughly **$550–$1000** Turbo.
- Time ballpark on a good GPU: Forties ≈1h, Muwatta ≈1 day, Sittah+Muwatta ≈1–3 weeks.
- **Order:** Forties → QC → Muwatta → big books.
- References already in-repo: `omni-test.py`, `generate-recitation.mjs` (JSON shape / ElevenLabs path), `qc-recitation-check.mjs` (structural QC).

#### QC / double-check before accepting a batch

Do not merge or ship a recitation drop until it passes this. Full checklist + reject criteria: **`OMNIVOICE-HANDOFF.md` §7**.

1. **Structural (every report)**
   - Matching pair: `public/recitation/<corpus>.NNN.mp3` + `.json` (same stem; stem matches husx corpus, e.g. `nawawi-arbain.001`).
   - `len(json.tokens) === len(witness.matn.tokens)`; each `id` / `text` matches husx.
   - `start` / `end` are finite numbers, `start < end`, times non-decreasing across the hadith.
   - `duration` ≈ last token `end` ≈ real mp3 length; duration roughly proportional to matn char count (not tiny silence, not absurdly long).

2. **Automated helper (optional — do not depend on it alone)**
   ```bash
   node qc-recitation-check.mjs                       # all Forties
   node qc-recitation-check.mjs nawawi-arbain
   node qc-recitation-check.mjs qudsi-arbain --hadith=1,3
   ```
   Writes `qc/recitation-check.json`. Needs `ffprobe` on PATH for mp3 duration checks. Exit code ≠ 0 means reject/fix those stems. Manual steps below still apply.

3. **Spot-listen (required)**
   - Drop files into `public/recitation/` (or use live if already wired).
   - Serve: `python -m http.server 8734 --directory public` → open http://localhost:8734/  
     or open https://audio.maltiquran.com
   - Pick 3–5 reports (short / medium / long). Tap mid-hadith words — seek must land on the spoken word, not drift.

4. **Content sanity**
   - Arabic is audible (not silence, hiss, or garbage).
   - Length feels proportional to matn length.

5. **Optional stronger check** — free local WhisperX/ASR transcript vs diplomatic (spot a few reports). Not required for handoff accept. Script also has `--stt` (ElevenLabs scribe; needs `.env`, costly) — skip unless chasing a specific suspect.

6. **Reject / fail the batch (or those stems) if**
   - Token count or id/text mismatch vs husx
   - Seek drift on mid-hadith taps
   - Empty / near-empty mp3, or duration wildly off vs text
   - Wrong collection stem (`malik.001` when you expected a Forty, etc.)

## 7. Committing the HUSX repo (IMPORTANT — currently unversioned)

`hadithusx/` is a clone of `dfordev1/hadithusx` with **all this session's data +
tooling uncommitted**: importers (`import-{nawawi-arbain,qudsi-arbain,shahwaliullah,malik}.mjs`),
sidecar builders (`build-*-{translation,refs,sunnah-compat}.mjs`, `build-clauses.mjs`),
checkers, and `data/*.json` for all 4 collections. Commit + push these to the
hadithusx repo so the standard's substance is versioned. Note: `npm test` in that
repo has a **pre-existing** failure (`staged candidates are tied to the exact
authority fixture`) unrelated to this work — verified identical on a clean clone.

## 8. How to add a NEW collection end-to-end (the recipe)

1. **Get text**: `curl -s "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/ara-<x>.json" -o ara-<x>.json` (+ `eng-<x>`, `urd-<x>` for gloss anchors). If a collection is only on sunnah.com (e.g. `shahwaliullah40`), scrape it via the browser (`.actualHadithContainer` → `.arabic_hadith_full` / `.english_hadith_full`) — note sunnah.com states **no text licence**.
2. **Import to husx**: adapt `hadithusx/scripts/import-nawawi-arbain.mjs` (simple/isnad-less) or `import-malik.mjs` (full isnads). Guarantee: matn is a **verbatim span**; tokens are the exact whitespace split; `node scripts/validate.mjs data/<corpus>.json` passes.
3. **Sidecars**: `build-<x>-translation.mjs`, `build-<x>-refs.mjs`, `build-<x>-sunnah-compat.mjs`, `build-clauses.mjs`. Publish to `public/translation/<slug>.json`, `public/sunnah/<slug>.json`.
4. **Audio (optional)**: prefer OmniVoice + WhisperX (§6e / `OMNIVOICE-HANDOFF.md`). ElevenLabs path: `node generate-recitation.mjs <corpus> --all` (needs `.env`; uses `pausal.mjs`, trailing-period, retry). Cost ≈ matn_chars × ~0.22 credits (real rate, ~half list) on Turbo.
5. **Glosses**: run the gloss+review workflow (below) → `public/gloss/<slug>-N.json`.
6. **Wire into `index.html`** `COLLECTIONS` (Muwatta already wired with `audio:false` + book picker; copy that pattern for other huge books), publish sidecars, `check-glosses.mjs`, commit, push.

### Gloss + review workflow pattern (proven)
The saved script is
`.claude/.../workflows/scripts/muwatta-slice-wf_*.js`. Pattern: `pipeline(batches,
glossStage, reviewStage)` — each batch (~28 hadith) is glossed by a
`general-purpose` agent, then flows straight into an independent reviewer agent.
Gloss agents **skip** files already valid; review agents **skip** files already
carrying a `review` block, so re-running resumes safely. Run **disjoint hadith
ranges as separate workflows** to parallelise (each caps ~16 concurrent).

## 9. GOTCHAS (learned the hard way — don't repeat)

- **`git add public/gloss/malik-*.json` fails silently** with "Argument list too long" (1800+ files). **Always `git add public/gloss/`** (the directory). Nearly lost 856 files to this.
- **Workflow `args` arrive as a STRING**, not an object. Parse defensively: `const A = typeof args==='string'?JSON.parse(args):args`.
- **`preload="none"` audio drops the first seek** → clicking a word plays from 0. Seek only after `loadedmetadata` if `readyState<1` (see `playFrom` in index.html).
- **Word-tap seek on local static servers**: many local HTTP servers lack `Range` support, so seeking into a remote URL fails. Reader uses **blob-backed audio** (`fetch` → `URL.createObjectURL`) so word taps seek correctly locally and on Vercel.
- **`urd-malik` (Urdu) source is unreliable** — empty/wrong/bundled entries; Urdu glosses are largely machine-composed, `machine-suggested`, need scholarly review. English anchors are clean.
- **TTS ceiling**: TTS ignores grammar → can produce wrong case endings; not tajwīd. OmniVoice: language id **`arb` (not `ar`)** for Standard Arabic. ElevenLabs honors diacritics (verified). Model: `eleven_turbo_v2_5` (0.5 cr/char, actual burn ~0.22); Multilingual v2 sounds better but 2×.
- **`.env` is gitignored and must stay so.** The ElevenLabs key was pasted in chat during development — **ROTATE IT** in the ElevenLabs dashboard and put the new one only in `.env`.
- **Huge agent runs hit the session usage limit.** Checkpoint (commit+push) often; resume after reset. Gloss/review agents are idempotent (skip-done), so resuming is safe.
- **CRLF warnings** on Windows git are harmless.
- **Full-isnad segmentation** (Muwatta) has known soft spots (anonymized narrators `عن الثقة`, cross-entry continuations, honorific bleed) — machine-suggested, no rijāl DB.

## 10. Quick commands

```bash
# serve locally
python -m http.server 8734 --directory public
# validate a corpus / check glosses / progress snapshot
cd hadithusx && node scripts/validate.mjs data/malik.json
node check-glosses.mjs malik malik
node progress.mjs   # writes public/progress.json for progress.html heatmap
# deploy
git add public/ && git commit -m "..." && git push
```

### Recitation double-check (structural QC)

Free local pass over Forties `{corpus}.NNN.mp3` + `.json` pairs — does **not** call
ElevenLabs unless you pass `--stt`. Catches missing/corrupt files, husx token /
diplomatic mismatches, bad/overlapping/gappy timestamps, and duration vs ffprobe.
Does **not** prove the spoken words are correct (that needs ASR: `--stt` or
`qc-detect.mjs` clause-level).

```bash
node qc-recitation-check.mjs                         # all Forties → qc/recitation-check.json
node qc-recitation-check.mjs nawawi-arbain
node qc-recitation-check.mjs qudsi-arbain --hadith=1,3
node qc-recitation-check.mjs --stt                   # optional; needs .env + costs STT
```

---
*Forties are fully glossed + reviewed + live with audio. Muwatta is fully glossed
(1829/1829), in the unified reader at https://audio.maltiquran.com (text/gloss +
book picker; `malik.html` redirects). Dock has Autoplay next + Repeat one. Open:
≈292 Muwatta reviews, uncommitted `hadithusx/` clone, and Muwatta/big-book audio
via OmniVoice (`OMNIVOICE-HANDOFF.md`) or eventual real-qārī alignment.*
