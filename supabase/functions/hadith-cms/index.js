const pathPattern = /^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*(?:\/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*)*\.(?:json|mp3|wav|ogg|m4a|webp|png|jpg)$/;
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const types = {json:"application/json",mp3:"audio/mpeg",wav:"audio/wav",ogg:"audio/ogg",m4a:"audio/mp4",webp:"image/webp",png:"image/png",jpg:"image/jpeg"};
const headers = {"Access-Control-Allow-Origin":"*","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"};
Deno.serve(async request => {
  const reply = (value, status = 200) => Response.json(value, {headers,status});
  if (request.method !== "GET") return reply({error:"Method unavailable"},405);
  const {searchParams} = new URL(request.url);
  const view = searchParams.get("view");
  const root = Deno.env.get("SUPABASE_URL");
  const service = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const auth = {apikey:service,Authorization:"Bearer "+service};
  try {
    if (view === "manifest") {
      const response = await fetch(root+"/rest/v1/rpc/cms_manifest", {headers:auth});
      if (!response.ok) throw new Error("Manifest query failed");
      return reply(await response.json());
    }
    if (view === "reports") {
      const slug = searchParams.get("slug") || "";
      const after = searchParams.get("after") || "";
      if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(slug) || after.length > 240) return reply({error:"Invalid collection"},400);
      const response = await fetch(root+"/rest/v1/rpc/cms_collection_reports",{
        method:"POST",headers:{...auth,"Content-Type":"application/json"},
        body:JSON.stringify({collection_slug:slug,after_path:after}),
      });
      if (!response.ok) throw new Error("Report query failed");
      return reply(await response.json());
    }
    const path = searchParams.get("path") || "";
    const version = searchParams.get("version") || "";
    if (view!=="asset" || path.length>240 || !pathPattern.test(path) || !uuid.test(version)) return reply({error:"Asset unavailable"},404);
    const query = new URLSearchParams({select:"cms_versions!inner(object_key,document)",path:"eq."+path,version_id:"eq."+version});
    const lookup = await fetch(root+"/rest/v1/cms_live?"+query,{headers:auth});
    if (!lookup.ok) throw new Error("Asset query failed");
    const [row] = await lookup.json();
    if (!row) return reply({error:"Asset unavailable"},404);
    if (row.cms_versions.document !== null) return reply(row.cms_versions.document);
    const key = row.cms_versions.object_key.split("/").map(encodeURIComponent).join("/");
    const body = await fetch(root+"/storage/v1/object/authenticated/hadith-cms/"+key,{headers:auth});
    if (!body.ok) return reply({error:"Asset unavailable"},body.status===404?404:503);
    return new Response(body.body,{headers:{...headers,"Content-Type":types[path.split(".").at(-1)]}});
  } catch (error) {
    console.error(error.message);
    return reply({error:"CMS unavailable"},503);
  }
});