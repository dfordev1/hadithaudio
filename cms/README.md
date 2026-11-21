# Hadith.to Studio

The reader uses the public `hadith-cms` Edge Function for published assets. The function serves only versions currently listed in `cms_live`. The private bucket holds the asset bodies. Studio uses Supabase Auth and database membership for editorial access.

## Add a publisher

In the Supabase project, create the confirmed publisher account under Authentication, then insert its lowercase email with the publisher role into `public.cms_members`. Use the editor role for users who may stage drafts. Keep public signup disabled if the project only serves Studio accounts.

## Deploy

Apply the Supabase migration before deploying the `hadith-cms` function. The public function is deployed without gateway JWT enforcement and only exposes the live manifest and live asset bodies. Administrative operations require Supabase Auth and database authorization. The deployed project URL and browser-safe publishable key are in the reader and Studio scripts. Adjust them when deploying to another Supabase project.

Deploy the web files once to the existing reader host and visit `/admin/` to sign in. A published release updates reader content directly from Supabase. No Git commit or reader deployment is needed for subsequent content releases.

Stage JSON, audio, and other assets at their reader-relative paths, then preview and publish the selected versions. Publishers can restore earlier versions from release history or reset a published path to its bundled asset.

## Structured library editor

Open **Library** to edit collection titles and books, then load a hadith by its
existing number. New and edited hadith are stored as structured PostgreSQL
documents with their Arabic, English, Urdu, source link, audio, and word timing.
Publishing updates reader and search data from the same release. Existing public
hadith addresses continue to work during migration.

Use **Bulk import collection and hadith** to stage a collection and up to 999
reports for one release. An import file has a `collection` with `slug`, `en`,
`ar`, and `books` (number/title pairs), and `reports` with `n`, `ar` and
optional `book`, `en`, `ur`, `source`, `audio`, and `words`. Word timings
contain `text`, `start`, and `end` in seconds.

Generate a migration file for the existing Nawawi collection with:

```sh
node scripts/export-cms-collection.mjs nawawi40 > nawawi-import.json
```

Use Studio to preview the staged collection before publishing. Untouched
collections and reports continue to use the bundled content, so the migration
can proceed a collection or a release at a time. Apply the structured editor
database migration and deploy the updated public Edge Function before
deploying the updated Studio and reader.

## Existing corpus migration

`scripts/prepare-cms-baseline.mjs` exports the repository corpus as newline-delimited
records for the private `cms_baseline` table. It uses the deployment's pinned Darimi
catalog and pinned translation revision. Install the Darimi catalog with
`python scripts/install-darimi.py` before exporting all collections. Pass one or
more collection slugs for a partial export.

Studio loads migrated hadith by their original collection and number. A saved
edit follows the same draft, preview, publish and rollback workflow as a new
entry. Existing reader files and audio streams remain the public fallback until
a replacement is published. Shama’il track offsets and raw word anchors are
preserved in the baseline. Its original public audio reader continues to
interpret those track ranges.
