const MIME = {
  json:"application/json", mp3:"audio/mpeg", ogg:"audio/ogg", wav:"audio/wav",
  m4a:"audio/mp4", webp:"image/webp", png:"image/png", jpg:"image/jpeg",
};
const PATH = /^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*(?:\/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*)*\.(json|mp3|ogg|wav|m4a|webp|png|jpg)$/;
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const headers = { "Cache-Control":"no-store", "X-Content-Type-Options":"nosniff" };
const json = (data, status = 200) => Response.json(data, { status, headers });
const fail = (message, status) => json({ message }, status);
const validPath = value => typeof value === "string" && value.length <= 240 && PATH.test(value);
const typeFor = path => MIME[path.split(".").at(-1)];
let keyCache;

function decode(segment) {
  return Uint8Array.from(atob(segment.replaceAll("-", "+").replaceAll("_", "/")), char => char.charCodeAt(0));
}

function claims(segment) {
  return JSON.parse(new TextDecoder().decode(decode(segment)));
}

async function accessKeys(issuer) {
  if (keyCache?.issuer === issuer && keyCache.expires > Date.now()) return keyCache.keys;
  const response = await fetch(issuer + "/cdn-cgi/access/certs", { signal:AbortSignal.timeout(4000) });
  if (!response.ok) throw new Error("Access keys unavailable");
  const { keys } = await response.json();
  keyCache = { issuer, keys, expires:Date.now() + 300_000 };
  return keys;
}

async function memberFor(request, env) {
  const issuer = env.ACCESS_ISSUER?.replace(/\/$/, "");
  if (!issuer || !env.ACCESS_AUD || !/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/.test(issuer)) return null;
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token || token.length > 16384) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const [header, payload, signature] = parts;
    const { alg, kid } = claims(header);
    const { iss, aud, exp, nbf, email } = claims(payload);
    const now = Date.now() / 1000;
    if (alg !== "RS256" || typeof kid !== "string" || iss !== issuer || !Array.isArray(aud) ||
        !aud.includes(env.ACCESS_AUD) || !Number.isFinite(exp) || exp <= now ||
        (nbf !== undefined && (!Number.isFinite(nbf) || nbf > now)) || typeof email !== "string") return null;
    const keys = await accessKeys(issuer);
    const jwk = keys.find(key => key.kid === kid);
    if (!jwk) return null;
    const key = await crypto.subtle.importKey("jwk", jwk, { name:"RSASSA-PKCS1-v1_5", hash:"SHA-256" }, false, ["verify"]);
    if (!(await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, decode(signature), new TextEncoder().encode(header + "." + payload)))) return null;
    return env.DB.prepare("SELECT email, role FROM cms_members WHERE email=?").bind(email).first();
  } catch (error) {
    console.warn("CMS authentication failed", error.message);
    return null;
  }
}

async function asset(env, version, isPrivate) {
  if (!version) return fail("Asset unavailable", 404);
  const object = await env.MEDIA.get(version.object_key);
  if (!object) return fail("Asset unavailable", 404);
  return new Response(object.body, { headers:{
    ...headers,
    "Content-Type":typeFor(version.path),
    "Content-Length":String(object.size),
    "Cross-Origin-Resource-Policy":"same-origin",
    ...(isPrivate ? { "X-Robots-Tag":"noindex" } : {}),
  } });
}

async function publicApi(request, env, url) {
  if (request.method !== "GET") return fail("Method unavailable", 405);
  const view = url.searchParams.get("view");
  if (view === "manifest") {
    const row = await env.DB.prepare("SELECT json_group_object(path,version_id) AS manifest FROM cms_live").first();
    return json(JSON.parse(row.manifest));
  }
  const path = url.searchParams.get("path");
  const version = url.searchParams.get("version");
  if (view !== "asset" || !validPath(path) || !ID.test(version ?? "")) return fail("Asset unavailable", 404);
  const row = await env.DB.prepare(
    "SELECT v.path,v.object_key FROM cms_live l JOIN cms_versions v ON v.id=l.version_id WHERE l.path=? AND l.version_id=?"
  ).bind(path, version).first();
  return asset(env, row, false);
}

async function stage(request, env, member, path) {
  if (!validPath(path)) return fail("Invalid reader asset path", 400);
  const type = typeFor(path);
  const size = Number(request.headers.get("Content-Length"));
  const max = type === MIME.json ? 16 * 1024 * 1024 : 50 * 1024 * 1024;
  if (!Number.isSafeInteger(size) || size < 1 || size > max) return fail("Asset exceeds the upload limit or is empty", 413);
  if (request.headers.get("Content-Type") !== type) return fail("Asset type does not match its path", 415);
  let body = request.body;
  if (type === MIME.json) {
    body = await request.text();
    let value;
    try { value = JSON.parse(body); } catch { return fail("Invalid JSON document", 400); }
    if (value === null || typeof value !== "object") return fail("Expected a JSON object or array", 400);
    if (path === "cms/collections.json" && !Array.isArray(value)) return fail("Expected a collection array", 400);
  }
  const id = crypto.randomUUID();
  const key = "versions/" + id;
  await env.MEDIA.put(key, body, { httpMetadata:{ contentType:type } });
  try {
    await env.DB.prepare("INSERT INTO cms_versions(id,path,object_key,author) VALUES(?,?,?,?)")
      .bind(id, path, key, member.email).run();
  } catch (error) {
    await env.MEDIA.delete(key).catch(cleanup => console.error("CMS upload cleanup failed", cleanup.message));
    throw error;
  }
  return json(id, 201);
}

async function publish(request, env, member) {
  if (member.role !== "publisher") return fail("Publisher role required", 403);
  const size = Number(request.headers.get("Content-Length"));
  if (!Number.isSafeInteger(size) || size < 1 || size > 400_000) return fail("Release is too large", 413);
  let changes;
  try { changes = (await request.json()).release_changes; } catch { return fail("Invalid release data", 400); }
  const nullableId = value => value === null || (typeof value === "string" && ID.test(value));
  if (!Array.isArray(changes) || changes.length < 1 || changes.length > 1000 ||
      !changes.every(change => validPath(change?.path) && nullableId(change.expected) && nullableId(change.version)) ||
      new Set(changes.map(change => change.path)).size !== changes.length) return fail("Invalid release data", 400);
  try {
    const row = await env.DB.prepare("INSERT INTO cms_releases(actor,changes) VALUES(?,?) RETURNING id")
      .bind(member.email, JSON.stringify(changes)).first();
    return json(row.id, 201);
  } catch (error) {
    if (error.message.includes("release_conflict")) return fail("Live content changed. Refresh and select versions again.", 409);
    if (error.message.includes("publisher_required")) return fail("Publisher role required", 403);
    throw error;
  }
}

async function manage(request, env, url, member) {
  const action = url.pathname.slice("/admin/api/".length);
  const query = url.searchParams;
  if (request.method === "POST") {
    if (request.headers.get("Origin") !== url.origin) return fail("Same-origin request required", 403);
    if (action === "stage") return stage(request, env, member, query.get("path"));
    if (action === "publish") return publish(request, env, member);
  }
  if (request.method !== "GET") return fail("Method unavailable", 405);
  if (action === "session") return json(member);
  if (action === "releases") {
    const { results } = await env.DB.prepare(
      "SELECT id,published_at,changes FROM cms_releases ORDER BY id DESC LIMIT 30"
    ).all();
    return json(results.map(row => ({ ...row, changes:JSON.parse(row.changes) })));
  }
  if (action === "versions") {
    const id = query.get("id");
    if (id) {
      if (!ID.test(id)) return fail("Invalid version", 400);
      const row = await env.DB.prepare("SELECT id,path,created_at FROM cms_versions WHERE id=?").bind(id).first();
      return json(row ? [row] : []);
    }
    const limit = Math.min(100, Math.max(1, Number(query.get("limit")) || 100));
    const offset = Math.min(100_000, Math.max(0, Number(query.get("offset")) || 0));
    const filter = (query.get("filter") || "").slice(0, 240);
    const { results } = await env.DB.prepare(
      "SELECT id,path,created_at FROM cms_versions WHERE instr(lower(path),lower(?))>0 ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?"
    ).bind(filter, Math.trunc(limit), Math.trunc(offset)).all();
    return json(results);
  }
  if (action === "asset") {
    const id = query.get("id");
    if (!ID.test(id ?? "")) return fail("Invalid version", 400);
    return asset(env, await env.DB.prepare("SELECT path,object_key FROM cms_versions WHERE id=?").bind(id).first(), true);
  }
  return fail("Endpoint unavailable", 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/api/cms") return await publicApi(request, env, url);
      if (url.pathname === "/admin") return Response.redirect(new URL("/admin/", url), 302);
      if (!url.pathname.startsWith("/admin/")) return fail("Not found", 404);
      const member = await memberFor(request, env);
      if (!member) return fail("Hadith.to Studio access is required.", 403);
      if (url.pathname.startsWith("/admin/api/")) return await manage(request, env, url, member);
      const file = typeof STUDIO_FILES !== "undefined" && Object.hasOwn(STUDIO_FILES, url.pathname) && STUDIO_FILES[url.pathname];
      if (!file || request.method !== "GET") return fail("Not found", 404);
      return new Response(file.body, { headers:{
        ...headers, "Content-Type":file.type, "X-Frame-Options":"DENY", "X-Robots-Tag":"noindex",
        "Content-Security-Policy":"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'none'",
      } });
    } catch (error) {
      console.error("Hadith CMS request failed", error.message);
      return fail("The CMS could not complete this request.", 503);
    }
  },
};
