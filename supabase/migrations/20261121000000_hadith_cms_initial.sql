create table public.cms_members(email text primary key check(email=lower(email)), role text not null check(role in ('editor','publisher')));
create table public.cms_versions(id uuid primary key default gen_random_uuid(), path text not null check(length(path)<=240 and path ~ '^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*(/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*)*[.](json|mp3|wav|ogg|m4a|webp|png|jpg)$'), object_key text unique not null, author text not null, created_at timestamptz not null default now());
create index cms_versions_latest on public.cms_versions(created_at desc,id desc);
create table public.cms_live(path text primary key, version_id uuid not null references public.cms_versions(id));
create table public.cms_releases(id bigint generated always as identity primary key, actor text not null, published_at timestamptz not null default now(), changes jsonb not null);

alter table public.cms_members enable row level security;
alter table public.cms_versions enable row level security;
alter table public.cms_live enable row level security;
alter table public.cms_releases enable row level security;
revoke all on public.cms_members,public.cms_versions,public.cms_live,public.cms_releases from anon,authenticated;
grant select on public.cms_members,public.cms_versions,public.cms_live,public.cms_releases to authenticated,service_role;
create policy cms_member_self on public.cms_members for select to authenticated using (email=lower((select auth.jwt())->>'email') and (select auth.uid()) is not null);
create policy cms_version_read on public.cms_versions for select to authenticated using (exists(select 1 from public.cms_members));
create policy cms_release_read on public.cms_releases for select to authenticated using (exists(select 1 from public.cms_members));
create policy cms_live_read on public.cms_live for select to authenticated using (exists(select 1 from public.cms_members));

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values ('hadith-cms','hadith-cms',false,52428800,array['application/json','audio/mpeg','audio/ogg','audio/wav','audio/mp4','image/webp','image/png','image/jpeg']);
create policy cms_upload on storage.objects for insert to authenticated with check (bucket_id='hadith-cms' and (storage.foldername(name))[1]=(select auth.uid())::text and exists(select 1 from public.cms_members));
create policy cms_preview on storage.objects for select to authenticated using (bucket_id='hadith-cms' and exists(select 1 from public.cms_members));
create policy cms_cancel_upload on storage.objects for delete to authenticated using (bucket_id='hadith-cms' and (storage.foldername(name))[1]=(select auth.uid())::text and exists(select 1 from public.cms_members) and not exists(select 1 from public.cms_versions v where v.object_key=name));

create function public.cms_stage(asset_path text, uploaded_key text) returns uuid language plpgsql security definer set search_path='' as $$
declare new_id uuid;
begin
  if not exists(select 1 from public.cms_members where email=lower(auth.jwt()->>'email')) or auth.uid() is null or split_part(uploaded_key,'/',1) is distinct from auth.uid()::text then raise exception 'CMS editor required' using errcode='42501'; end if;
  perform 1 from storage.objects where bucket_id='hadith-cms' and name=uploaded_key and metadata->>'mimetype'=case substring(asset_path from '[.]([a-z]+)$') when 'json' then 'application/json' when 'mp3' then 'audio/mpeg' when 'wav' then 'audio/wav' when 'ogg' then 'audio/ogg' when 'm4a' then 'audio/mp4' when 'webp' then 'image/webp' when 'png' then 'image/png' when 'jpg' then 'image/jpeg' end for update;
  if not found then raise exception 'Upload unavailable or type mismatch'; end if;
  insert into public.cms_versions(path,object_key,author) values (asset_path,uploaded_key,lower(auth.jwt()->>'email')) returning id into new_id;
  return new_id;
end $$;

create function public.cms_publish(release_changes jsonb) returns bigint language plpgsql security definer set search_path='' as $$
declare c record; old_id uuid; release_id bigint;
begin
  if auth.uid() is null or not exists(select 1 from public.cms_members where email=lower(auth.jwt()->>'email') and role='publisher') then raise exception 'Publisher required' using errcode='42501'; end if;
  if jsonb_typeof(release_changes) is distinct from 'array' then raise exception 'Expected an array of release changes'; end if;
  if jsonb_array_length(release_changes) not between 1 and 1000 or (select count(distinct x->>'path') from jsonb_array_elements(release_changes) x)<>jsonb_array_length(release_changes) then raise exception 'Expected 1–1,000 unique asset paths'; end if;
  perform pg_advisory_xact_lock(3735218);
  for c in select * from jsonb_to_recordset(release_changes) as changes(path text,expected uuid,version uuid) loop
    select version_id into old_id from public.cms_live where path=c.path;
    if old_id is distinct from c.expected or old_id is not distinct from c.version then raise exception 'Live version conflict for %',c.path using errcode='40001'; end if;
    if c.version is null then delete from public.cms_live where path=c.path;
    elsif exists(select 1 from public.cms_versions where path=c.path and id=c.version) then
      insert into public.cms_live(path,version_id) values(c.path,c.version) on conflict(path) do update set version_id=excluded.version_id;
    else raise exception 'Version does not match %',c.path;
    end if;
  end loop;
  insert into public.cms_releases(actor,changes) values(lower(auth.jwt()->>'email'),release_changes) returning id into release_id;
  return release_id;
end $$;
create function public.cms_manifest() returns jsonb language sql stable set search_path='' as $$
  select coalesce(jsonb_object_agg(path,version_id),'{}'::jsonb) from public.cms_live;
$$;
revoke all on function public.cms_stage(text,text),public.cms_publish(jsonb),public.cms_manifest() from public,anon,authenticated;
grant execute on function public.cms_stage(text,text),public.cms_publish(jsonb) to authenticated;
grant execute on function public.cms_manifest() to service_role;