# audio.maltiquran.com — An-Nawawi's Forty Hadith, read & listen

A lightweight static reader for the Forty Hadith of an-Nawawi: synced Arabic
recitation with word-level highlighting, English translation side by side, and
cross-references that deep-link to sunnah.com.

No framework, no build step — a single `public/index.html` over static JSON and
audio. Deployed to GitHub Pages at **audio.maltiquran.com**.

## What's here

| path | |
|---|---|
| `public/index.html` | the whole app (one file, no dependencies) |
| `public/recitation/` | 42 hadith: `.mp3` recitation + `.json` word-timing map |
| `public/translation/en.json` | English sidecar, aligned per report |
| `public/refs/nawawi.json` | cross-collection reference map (Bukhari, Muslim) |
| `public/sunnah/nawawi.json` | sunnah.com-compatible identifiers + deep links |
| `generate-recitation.mjs` | regenerates audio + timing from the husx corpus |

The underlying corpus, and the scripts that build these sidecars, live in the
data repo (`hadithusx`), kept separate on purpose: text and interpretation are
versioned there, presentation here.

## Features

- **Word-synced recitation** — the active word highlights and the page follows
  the audio (ElevenLabs alignment timestamps); click any word to seek.
- **Parallel Arabic / English**, in sunnah.com's own font cascade
  (KFGQPC → Scheherazade New, SIL OFL).
- **Deep links** — `#nawawi40:13` addresses one hadith, shareable.
- **Reader settings** — text size, light / sepia / dark, saved locally.
- **sunnah.com cross-references** with their published numbering.

## Provenance & attribution

Recitation is **synthesised** (ElevenLabs) — no human reciter read these; it is
not a substitute for recitation from a qārī. Layout conventions follow bible.com
and sunnah.com for familiarity; all code, styling and audio here are original.
Cross-references are **machine-suggested** and carry sunnah.com's own numbering.

## Deploy (Vercel)

Static site, no build step. `vercel.json` sets the output directory to `public/`.

1. Push this repo to GitHub.
2. In Vercel: **Add New → Project → import this repo**. Framework preset
   **Other**, Build Command empty, Output Directory `public` (already in
   `vercel.json`).
3. In the project's **Domains**, add `audio.maltiquran.com`. Because
   `maltiquran.com` is already on Vercel, the DNS record is created for you.
   If the domain's DNS lives at the registrar instead, add a CNAME:
   `audio` → `cname.vercel-dns.com`.

## Licence

Code: MIT. Hadith text derives from public datasets; see the data repo for
source provenance. Verify before relying on any text or grade for religious use.
