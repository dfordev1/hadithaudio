# Hadith.to Studio

Studio publishes reader content directly from Cloudflare. D1 tracks memberships,
immutable versions, releases and the live version of each path. The private R2
bucket stores draft and published asset bodies. The reader checks the CMS for
published replacements and also uses the site's existing corpus and media.

## Deploy once

1. Create a dedicated D1 database and private R2 bucket. Apply
   [0001_initial.sql](migrations/0001_initial.sql) to the database.
2. Create a Cloudflare Access self-hosted application protecting
   `www.hadith.to/admin` and its descendants. Configure the team's supported
   identity provider or One-Time PIN and allow the approved editorial accounts.
3. Insert the first publisher into D1 using a parameterized query with their
   approved login email. The role must be `publisher` or `editor`.
   `INSERT INTO cms_members(email,role) VALUES (?, 'publisher')`.
4. From the repository root run
   `node scripts/build-cms-worker.mjs > /tmp/hadith-cms-worker.mjs`.
   Deploy that ES module as a Cloudflare Worker. Bind the database as `DB`
   and the bucket as `MEDIA`. Set `ACCESS_ISSUER` to the exact Access team
   origin and `ACCESS_AUD` to the self-hosted application's audience tag.
5. Attach Worker routes `www.hadith.to/admin*` and `www.hadith.to/api/cms*`
   on the proxied Cloudflare zone. The current reader origin can stay in place.
   Deploy the reader changes through its existing pipeline once.
6. Verify that an unauthenticated visit to `/admin/` prompts for Access login,
   a publisher can stage and preview a draft, and the public reader picks up the
   asset only after publication. Check that a release can be reverted.

A login with the Access app's audience and a valid signature is required for every
admin request. Studio also checks D1 membership on each request. Adding and
removing members is an infrastructure action in D1 and Access.

## Publish content

- Open `/admin/` and sign in. Use a path relative to the reader root, such as
  `bukhari/book-1.json` or `recitation/nawawi-arbain.001.mp3`.
- Open bundled or published JSON to edit it, or import files using the exact paths
  that the reader requests. A folder import preserves directory layout inside
  the selected folder. Drafts are saved independently and can be selected later.
- Import a collection by staging its index and book files or recitation JSON
  files. Include translations, source references, timings, recordings and search
  sidecars as appropriate for the collection. Use `cms/collections.json` for
  catalog entries. Each entry has `slug`, `corpus`, `ar`, `en`, and `count`.
  Set `books` for collections with an index and numbered book files, and
  `audio` for collections with recitation. The catalog can add entries or edit
  existing entries by slug.
- Select the versions that belong together, then preview them at a hadith address
  in the embedded reader. A publisher can commit all selected paths in one
  release. Changes to Arabic text, alignment, and audio can ship together.
- Revert a release from history if its affected assets are still at the same
  versions. For one asset, select a previous version or queue a reset to the
  bundled file.

Bulk staging accepts up to 1,000 files at a time and each release accepts up to
1,000 unique paths. JSON uploads are capped at 16 MiB, media at 50 MiB per file.
New Arabic search data uses `search-data/<slug>.json` in the same format as the
generated search data. Build code, data-processing scripts, and new reader
behaviors use the software deployment pipeline.
