# Hadith.to Studio

The reader uses the public `hadith-cms` Edge Function for published assets. The function serves only versions currently listed in `cms_live`. The private bucket holds the asset bodies. Studio uses Supabase Auth and database membership for editorial access.

## Add a publisher

In the Supabase project, create the confirmed publisher account under Authentication, then insert its lowercase email with the publisher role into `public.cms_members`. Use the editor role for users who may stage drafts. Keep public signup disabled if the project only serves Studio accounts.

## Deploy

Apply the Supabase migration before deploying the `hadith-cms` function. The public function is deployed without gateway JWT enforcement and only exposes the live manifest and live asset bodies. Administrative operations require Supabase Auth and database authorization. The deployed project URL and browser-safe publishable key are in the reader and Studio scripts. Adjust them when deploying to another Supabase project.

Deploy the web files once to the existing reader host and visit `/admin/` to sign in. A published release updates reader content directly from Supabase. No Git commit or reader deployment is needed for subsequent content releases.

Stage JSON, audio, and other assets at their reader-relative paths, then preview and publish the selected versions. Publishers can restore earlier versions from release history or reset a published path to its bundled asset.
