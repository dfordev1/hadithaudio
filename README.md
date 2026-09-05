# Hadith.to — Hadith collections, read & listen

A lightweight static reader for the Forty Hadith of an-Nawawi: synced Arabic
recitation with word-level highlighting, English translation side by side, and
cross-references that deep-link to sunnah.com.

No client framework — a static HTML reader with a small CSS and JavaScript UI layer
over static JSON and audio. Deployed through Vercel at **www.hadith.to**.

## What's here

| path | |
|---|---|
| `public/index.html` | reader, collection loading, and audio playback |
| `public/reader-ui.css` | responsive sacred reading theme |
| `public/reader-ui.js` | library tabs, saved passages, search, and focused reading |
| `public/fonts/` | bundled Source Serif 4 and Scheherazade New, with SIL OFL licences |
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

## Website UI

The collection library uses a stone palette, bronze accents, Source Serif 4, and
Scheherazade New. Light, sepia, and dark themes share the same responsive layout.
Reading mode keeps Arabic central; Show meaning reveals the selected English or
Urdu translation. Study retains the existing word gloss and parallel controls.

Saved passages and appearance preferences stay on the device. Recent passages
and phrase search cover passages opened during the current session; exact hadith
number lookup uses the selected collection's existing data. Focus, copy, and
previous/next controls operate on the current real passage. The corpus, source
references, recitation URLs, and audio timing pipeline are unchanged.

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
3. In the project's **Domains**, use `www.hadith.to` as the primary domain and
   redirect the apex `hadith.to` domain to it.
   If the domain's DNS lives at the registrar instead, use the DNS values shown
   by Vercel for `www` and the apex redirect.

## Licence

Code: MIT. Hadith text derives from public datasets; see the data repo for
source provenance. Verify before relying on any text or grade for religious use.
