-- Original corpus records are available to Studio without flooding the live manifest.
create table public.cms_baseline (
  path text primary key check (
    path ~ '^cms/(library/[a-z0-9_-]+|reports/[a-z0-9_-]+/[0-9]+[a-z]?)[.]json$'
  ),
  document jsonb not null check (jsonb_typeof(document)='object'),
  imported_at timestamptz not null default now()
);
alter table public.cms_baseline enable row level security;
revoke all on public.cms_baseline from anon,authenticated;
grant select on public.cms_baseline to authenticated;
create policy cms_baseline_read on public.cms_baseline for select to authenticated
  using (exists(select 1 from public.cms_members));
