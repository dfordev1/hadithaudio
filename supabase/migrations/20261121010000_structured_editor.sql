-- Structured drafts share the existing release pointers and rollback history.
alter table public.cms_versions alter column object_key drop not null;
alter table public.cms_versions add column document jsonb;
alter table public.cms_versions add constraint cms_version_has_one_body
  check ((object_key is not null) <> (document is not null));
create index cms_live_path_prefix on public.cms_live (path text_pattern_ops);

create function public.cms_stage_document(asset_path text, asset_document jsonb)
returns uuid language plpgsql security definer set search_path='' as $$
declare result uuid;
begin
  if auth.uid() is null or not exists (
    select 1 from public.cms_members where email=lower(auth.jwt()->>'email')
  ) then raise exception 'CMS editor required' using errcode='42501'; end if;
  if asset_path is null or asset_document is null or jsonb_typeof(asset_document)<>'object'
     or pg_column_size(asset_document)>1048576 then
    raise exception 'Invalid content document';
  end if;
  if asset_path ~ '^cms/library/[a-z0-9][a-z0-9_-]{0,63}[.]json$' then
    if asset_path is distinct from 'cms/library/' || (asset_document->>'slug') || '.json'
       or coalesce(length(btrim(asset_document->>'en')),0) not between 1 and 150
       or coalesce(length(btrim(asset_document->>'ar')),0) not between 1 and 150
       or jsonb_typeof(asset_document->'books') is distinct from 'array' then
      raise exception 'Invalid collection document';
    end if;
  elsif asset_path ~ '^cms/reports/[a-z0-9][a-z0-9_-]{0,63}/[1-9][0-9]{0,8}[a-z]?[.]json$' then
    if asset_path is distinct from 'cms/reports/' || (asset_document->>'slug') || '/' || (asset_document->>'n') || '.json'
       or coalesce(length(btrim(asset_document->>'ar')),0) not between 1 and 40000 then
      raise exception 'Invalid hadith document';
    end if;
  else raise exception 'Invalid structured content path';
  end if;
  insert into public.cms_versions(path,document,author)
    values(asset_path,asset_document,lower(auth.jwt()->>'email')) returning id into result;
  return result;
end $$;
revoke all on function public.cms_stage_document(text,jsonb) from public,anon,authenticated;
grant execute on function public.cms_stage_document(text,jsonb) to authenticated;

create function public.cms_collection_reports(collection_slug text, after_path text default '')
returns jsonb language sql stable set search_path='' as $$
  select coalesce(jsonb_agg(jsonb_build_array(path,n,ar,en,ur,book,audio) order by path),'[]'::jsonb)
  from (
    select l.path,v.document->>'n' as n,v.document->>'ar' as ar,v.document->>'en' as en,
      v.document->>'ur' as ur,v.document->>'book' as book,v.document ? 'audio' as audio
    from public.cms_live l join public.cms_versions v on v.id=l.version_id
    where collection_slug ~ '^[a-z0-9][a-z0-9_-]{0,63}$'
      and starts_with(l.path,'cms/reports/' || collection_slug || '/')
      and l.path > after_path and v.document is not null
    order by l.path limit 200
  ) reports;
$$;
revoke all on function public.cms_collection_reports(text,text) from public,anon,authenticated;
grant execute on function public.cms_collection_reports(text,text) to service_role;
