"use strict";

const $ = id => document.getElementById(id);
const mimeTypes = {
  json:"application/json", mp3:"audio/mpeg", ogg:"audio/ogg", wav:"audio/wav",
  m4a:"audio/mp4", webp:"image/webp", png:"image/png", jpg:"image/jpeg",
};
const assetPath = /^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*(?:\/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*)*\.(json|mp3|ogg|wav|m4a|webp|png|jpg)$/;
const pageSize = 100;
const date = value => new Date(value).toLocaleString();
let member;
let live = new Map();
let versions = [];
let selected = new Map();
let offset = 0;
let locked = false;
let preview = {};
let openDocument;
let reportIndex = -1;

function status(message, error = false) {
  $("status").textContent = message;
  $("status").toggleAttribute("data-error", error);
}

const backend = "https://mfwxdrxjmgetbmhlsqtt.supabase.co";
const apiKey = "sb_publishable_44R3cxkN9Z5THq9bvukL7A_cxhc6K0M";
let session;
let refreshSession;

async function send(path, { method="GET", body, type="application/json", auth=true } = {}) {
  if (auth && !session) throw new Error("Sign in to continue.");
  if (auth && session.expires_at <= Date.now()/1000 + 30) {
    refreshSession ??= send("/auth/v1/token?grant_type=refresh_token", {
      method:"POST", body:{refresh_token:session.refresh_token},auth:false,
    }).then(response => response.json()).then(value => { session=value; }).catch(error => {
      resetSession();
      throw error;
    }).finally(() => { refreshSession=null; });
    await refreshSession;
  }
  const response = await fetch(backend+path,{method,headers:{
    apikey:apiKey,...(auth ? {Authorization:"Bearer "+session.access_token} : {}),
    ...(body === undefined ? {} : {"Content-Type":type}),
  },...(body === undefined ? {} : {body:body instanceof Blob ? body : JSON.stringify(body)})});
  if (response.ok) return response;
  const error = await response.json().catch(() => ({}));
  throw new Error(error.message || error.msg || error.error_description || "Request failed ("+response.status+")");
}

async function objectKey(id) {
  const params = new URLSearchParams({select:"object_key",id:"eq."+id});
  const [row] = await send("/rest/v1/cms_versions?"+params).then(response => response.json());
  if (!row) throw new Error("Version unavailable.");
  return row.object_key.split("/").map(encodeURIComponent).join("/");
}

async function request(action, { method="GET", body, type="application/json", query={} } = {}) {
  if (action==="asset") return send("/storage/v1/object/authenticated/hadith-cms/"+await objectKey(query.id));
  if (action==="stage") {
    const key=session.user.id+"/"+crypto.randomUUID()+"/"+query.path.split("/").at(-1);
    await send("/storage/v1/object/hadith-cms/"+key,{method,type,body});
    try {
      return await send("/rest/v1/rpc/cms_stage",{method,body:{asset_path:query.path,uploaded_key:key}});
    } catch (error) {
      await send("/storage/v1/object/hadith-cms",{method:"DELETE",body:{prefixes:[key]}}).catch(() => {});
      throw error;
    }
  }
  if (action==="publish") return send("/rest/v1/rpc/cms_publish",{method,body});
  const params = action==="versions"
    ? {select:"id,path,created_at",order:"created_at.desc,id.desc",limit:query.limit,offset:query.offset,
       ...(query.filter ? {path:"ilike.*"+query.filter+"*"} : {})}
    : action==="releases" ? {select:"id,published_at,changes",order:"id.desc",limit:30} : {select:"email,role",limit:1};
  return send("/rest/v1/cms_"+(action==="session"?"members":action)+"?"+new URLSearchParams(params));
}

function data(action, options) {
  return request(action, options).then(response => response.json());
}

function run(action) {
  return async event => {
    event?.preventDefault();
    if (locked) return;
    locked = true;
    const buttons = Array.from(document.querySelectorAll("button"));
    buttons.forEach(button => { button.disabled = true; });
    try { await action(event); }
    catch (error) { status(error.message, true); }
    finally {
      locked = false;
      buttons.forEach(button => { button.disabled = false; });
    }
  };
}

function validatePath(path) {
  const match = path.match(assetPath);
  if (path.length > 240 || !match || path.split("/").some(segment => segment === "." || segment === "..")) {
    throw new Error("Enter a reader-relative path ending in JSON, MP3, OGG, WAV, M4A, WEBP, PNG, or JPG.");
  }
  return mimeTypes[match[1]];
}

function validateDocument(path, value) {
  if (value === null || typeof value !== "object") throw new Error("JSON content must contain an object or array.");
  if (path !== "cms/collections.json") return;
  const slugs = new Set();
  if (!Array.isArray(value) || value.some(item => {
    const slug = item?.slug;
    if (typeof slug !== "string" || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(slug) ||
        Object.hasOwn(Object.prototype, slug) || slugs.has(slug) ||
        typeof item.corpus !== "string" || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(item.corpus) ||
        ![item.en, item.ar].every(name => typeof name === "string" && name.trim() && name.length <= 150 && !/[<>&"\u0000-\u001f]/.test(name)) ||
        !Number.isSafeInteger(item.count) || item.count < 1) return true;
    slugs.add(slug);
    return false;
  })) throw new Error("Each catalog entry needs a unique slug, corpus, English and Arabic names, and a positive hadith count.");
}

async function stage(path, file) {
  const type = validatePath(path);
  if (type === mimeTypes.json) validateDocument(path, JSON.parse(await file.text()));
  const id = await data("stage", { method:"POST", query:{ path }, type, body:file });
  queue(path, id);
  return id;
}

function queue(path, version) {
  if ((live.get(path) ?? null) === version) selected.delete(path);
  else selected.set(path, { path, expected:live.get(path) ?? null, version });
  updatePublish();
}

function updatePublish() {
  $("publish").textContent = "Publish selected (" + selected.size + ")";
  $("publish").hidden = member?.role !== "publisher";
}

async function publish(changes) {
  if (!changes.length) throw new Error("Select a version to publish.");
  if (!window.confirm("Publish " + changes.length + " asset change(s) to Hadith.to?")) return;
  const id = await data("publish", { method:"POST", body:{ release_changes:changes } });
  selected.clear();
  await refresh();
  status("Published release #" + id + ".");
}

function action(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.onclick = run(handler);
  return button;
}

async function openAsset(path, versionId) {
  const type = validatePath(path);
  const response = versionId
    ? await request("asset", { query:{ id:versionId } })
    : await fetch("/" + path);
  if (!response.ok) throw new Error("No bundled content found at " + path);
  if (type === mimeTypes.json) {
    $("path").value = path;
    loadDocument(path, await response.json());
    $("document").focus();
    status("Opened " + path + ".");
    return;
  }
  const local = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = local;
  a.download = path.split("/").at(-1);
  a.click();
  setTimeout(() => URL.revokeObjectURL(local), 60_000);
  status("Downloaded " + path + " for preview.");
}

function loadDocument(path, value) {
  openDocument = { path, value };
  reportIndex = -1;
  $("report-tools").hidden = !Array.isArray(value?.hadith);
  $("whole-document").hidden = true;
  $("document-label").firstChild.nodeValue = "JSON content ";
  $("document").value = JSON.stringify(value, null, 2);
}

function activeReport() {
  if (reportIndex < 0 || !openDocument) return false;
  if ($("path").value.trim() !== openDocument.path) throw new Error("Reopen the new path before editing a hadith.");
  const report = JSON.parse($("document").value);
  if (!report || typeof report !== "object" || Array.isArray(report) ||
      String(report.n) !== String(openDocument.value.hadith[reportIndex].n)) {
    throw new Error("Keep the original hadith number when editing one report.");
  }
  openDocument.value.hadith[reportIndex] = report;
  return true;
}

$("open-report").onclick = run(() => {
  if (!openDocument || $("path").value.trim() !== openDocument.path) throw new Error("Open the book asset first.");
  if (!activeReport()) openDocument.value = JSON.parse($("document").value);
  const number = $("report-number").value.trim();
  const index = openDocument.value.hadith?.findIndex(report => String(report.n) === number) ?? -1;
  if (index < 0) throw new Error("Hadith " + number + " was not found in this book.");
  reportIndex = index;
  $("document-label").firstChild.nodeValue = "Hadith " + number + " JSON ";
  $("document").value = JSON.stringify(openDocument.value.hadith[index], null, 2);
  $("whole-document").hidden = false;
  $("document").focus();
});

$("whole-document").onclick = run(() => {
  if (activeReport()) loadDocument(openDocument.path, openDocument.value);
});

function renderVersions() {
  const container = $("versions");
  container.replaceChildren();
  const options = new Set(["cms/collections.json", "translation/en.json", "refs/nawawi.json", ...live.keys()]);
  for (const version of versions) {
    options.add(version.path);
    const published = live.get(version.path) === version.id;
    const queued = selected.get(version.path);
    const row = container.insertRow();
    row.insertCell().textContent = version.path;
    row.insertCell().textContent = date(version.created_at);
    row.insertCell().textContent = published ? "Live" : queued?.version === version.id ? "Selected" : "Saved";
    const cell = row.insertCell();
    cell.append(action(version.path.endsWith(".json") ? "Open" : "Download", () => openAsset(version.path, version.id)));
    if (member) {
      if (published && member.role === "publisher") {
        cell.append(action(queued?.version === null ? "Unselect reset" : "Queue reset", () => {
          if (queued?.version === null) selected.delete(version.path);
          else queue(version.path, null);
          renderVersions();
        }));
      } else if (!published) {
        cell.append(action(queued?.version === version.id ? "Unselect" : "Select", () => {
          if (queued?.version === version.id) selected.delete(version.path);
          else queue(version.path, version.id);
          renderVersions();
        }));
      }
    }
  }
  $("paths").replaceChildren(...Array.from(options, value => Object.assign(document.createElement("option"), { value })));
  updatePublish();
}

async function loadVersions(reset) {
  const filter = $("filter").value.trim();
  if (filter && !/^[a-z0-9./_-]+$/i.test(filter)) throw new Error("Filter with letters, numbers, dots, or slashes.");
  const start = reset ? 0 : offset;
  const next = await data("versions", { query:{ limit:pageSize, offset:start, filter } });
  versions = reset ? next : versions.concat(next);
  offset = start + next.length;
  $("more").hidden = next.length < pageSize;
  renderVersions();
}

async function refresh() {
  const [current, history] = await Promise.all([
    fetch(backend+"/functions/v1/hadith-cms?view=manifest").then(response => {
      if (!response.ok) throw new Error("Could not read live versions.");
      return response.json();
    }),
    data("releases"),
  ]);
  live = new Map(Object.entries(current));
  $("history").replaceChildren(...history.map(release => {
    const row = document.createElement("li");
    row.textContent = "#" + release.id + " · " + date(release.published_at) + " · " + release.changes.length + " asset(s)";
    if (member.role === "publisher") row.append(action("Revert release", () => publish(
      release.changes.map(change => ({ path:change.path, expected:change.version, version:change.expected }))
    )));
    return row;
  }));
  await loadVersions(true);
}

$("open").onclick = run(async () => {
  const path = $("path").value.trim();
  const id = selected.get(path)?.version ?? live.get(path);
  await openAsset(path, id);
});

$("catalog").onclick = run(async () => {
  const path = "cms/collections.json";
  const id = live.get(path);
  if (id) return openAsset(path, id);
  $("path").value = path;
  loadDocument(path, [{ slug:"new-collection", corpus:"new-collection", en:"Collection name", ar:"اسم المجموعة", count:1, books:true, audio:false }]);
  $("document").focus();
});

$("save").onclick = run(async () => {
  const path = $("path").value.trim();
  if (validatePath(path) !== mimeTypes.json) throw new Error("Use Asset imports for audio or images.");
  const text = activeReport() ? JSON.stringify(openDocument.value) : $("document").value;
  await stage(path, new Blob([text], { type:mimeTypes.json }));
  await loadVersions(true);
  status("Draft saved for " + path + ".");
});

$("single-import").onsubmit = run(async event => {
  const data = new FormData(event.currentTarget);
  const path = data.get("path").trim();
  const file = data.get("file");
  if (!file.size) throw new Error("Choose a nonempty file.");
  await stage(path, file);
  await loadVersions(true);
  status("Draft staged for " + path + ".");
});

$("bulk-import").onsubmit = run(async event => {
  const files = Array.from(event.currentTarget.elements.files.files);
  if (files.length > 1000) throw new Error("Choose up to 1,000 files per import folder.");
  const assets = files.map(file => ({ file, path:file.webkitRelativePath.split("/").slice(1).join("/") }));
  for (const { path, file } of assets) {
    if (!file.size) throw new Error("Empty asset: " + path);
    if (validatePath(path) === mimeTypes.json) validateDocument(path, JSON.parse(await file.text()));
  }
  let completed = 0;
  try {
    for (const { path, file } of assets) {
      status("Staging " + (completed + 1) + " of " + assets.length + " · " + path);
      await stage(path, file);
      completed++;
    }
  } catch (error) {
    throw new Error(completed + " file(s) staged before the import stopped. " + error.message);
  } finally {
    if (member) await loadVersions(true);
  }
  status("Staged " + completed + " files.");
});

function closePreview() {
  preview = {};
  $("preview-panel").hidden = true;
  $("preview-frame").removeAttribute("src");
}

async function showPreview() {
  const address = $("preview-address").value.trim();
  if (!/^[a-z0-9_-]+:[0-9]+[a-z]?$/i.test(address)) throw new Error("Enter a hadith address such as nawawi40:1.");
  if (!selected.size) throw new Error("Select at least one draft version to preview.");
  preview = Object.fromEntries(await Promise.all(Array.from(selected.values(), async change => {
    if (!change.version) return [change.path,null];
    const key = await objectKey(change.version);
    const result = await send("/storage/v1/object/sign/hadith-cms/"+key,{
      method:"POST",body:{expiresIn:900},
    }).then(response => response.json());
    if (!result.signedURL?.startsWith("/object/sign/")) throw new Error("Draft preview unavailable.");
    return [change.path,backend+"/storage/v1"+result.signedURL];
  })));
  $("preview-panel").hidden = false;
  $("preview-frame").src = "/?cms-preview=1&preview=" + crypto.randomUUID() + "#" + address;
  $("preview-panel").scrollIntoView({ behavior:"smooth" });
  status("Reader preview is ready.");
}

addEventListener("message", event => {
  const frame = $("preview-frame");
  if (!$("preview-panel").hidden && event.origin === location.origin &&
      event.source === frame.contentWindow && event.data?.type === "hadith-cms-preview-ready") {
    event.source.postMessage({ type:"hadith-cms-preview-assets", assets:preview }, location.origin);
  }
});
$("preview-selected").onclick = $("preview-load").onclick = run(showPreview);
$("preview-close").onclick = run(closePreview);
$("reload").onclick = run(refresh);
$("filter").onchange = run(() => loadVersions(true));
$("more").onclick = run(() => loadVersions(false));
$("publish").onclick = run(() => publish(Array.from(selected.values())));

function resetSession() {
  session=null;
  member=null;
  selected.clear();
  live.clear();
  versions=[];
  openDocument=null;
  reportIndex=-1;
  $("document").value="";
  $("path").value="";
  $("versions").replaceChildren();
  $("history").replaceChildren();
  closePreview();
  $("workspace").hidden=$("logout").hidden=true;
  $("login-panel").hidden=false;
}

$("login").onsubmit=run(async event => {
  const form=event.currentTarget;
  const details=new FormData(form);
  session=await send("/auth/v1/token?grant_type=password",{
    method:"POST",body:{email:details.get("email"),password:details.get("password")},auth:false,
  }).then(response => response.json());
  form.reset();
  try {
    [member]=await data("session");
    if (!member) throw new Error("This account is not a Studio member.");
    await refresh();
    $("identity").textContent=member.email+" · "+member.role;
    $("workspace").hidden=$("logout").hidden=false;
    $("login-panel").hidden=true;
    status("Signed in.");
  } catch (error) { resetSession(); throw error; }
});
$("logout").onclick=run(async () => {
  try { await send("/auth/v1/logout?scope=local",{method:"POST"}); }
  finally { resetSession(); }
  status("Signed out.");
});
status("Sign in to manage Hadith.to.");
