(() => {
  const api = "https://mfwxdrxjmgetbmhlsqtt.supabase.co/functions/v1/hadith-cms?";
  const nativeFetch = window.fetch.bind(window);
  let assets = {};
  let preview = {};
  let streams = {};
  async function previewAssets() {
    if (!new URLSearchParams(location.search).has("cms-preview") || parent === window) return {};
    return new Promise(resolve => {
      const timer = setTimeout(() => finish({}), 3000);
      function finish(value) {
        clearTimeout(timer);
        removeEventListener("message", receive);
        resolve(value);
      }
      function receive(event) {
        if (event.origin === location.origin && event.source === parent && event.data?.type === "hadith-cms-preview-assets") {
          finish(event.data.assets ?? {});
        }
      }
      addEventListener("message", receive);
      parent.postMessage({ type:"hadith-cms-preview-ready" }, location.origin);
    });
  }
  function assetUrl(input) {
    const url = new URL(input, location.href);
    const managed = url.origin === location.origin ||
      ["www.hadith.to", "cdn.hadith.to"].includes(url.hostname);
    const path = url.pathname.slice(1);
    if (!managed) return input;
    if (Object.hasOwn(preview, path)) return preview[path] || input;
    if (!Object.hasOwn(assets, path)) return input;
    return api + new URLSearchParams({ view: "asset", path, version: assets[path] });
  }
  const managedPaths = () => [...new Set([...Object.keys(assets),...Object.keys(preview)])]
    .filter(path => !Object.hasOwn(preview,path) || preview[path]);

  async function readDocument(path) {
    const input = "/" + path;
    const url = assetUrl(input);
    if (url === input) return null;
    const response = await fetchWithOverrides(input,{signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("Published document could not load.");
    return response.json();
  }

  window.hadithManagedReport = (slug,n) => readDocument("cms/reports/"+slug+"/"+n+".json");
  window.hadithManagedNumbers = slug => managedPaths().filter(path => path.startsWith("cms/reports/"+slug+"/"))
    .map(path => path.split("/").at(-1).slice(0,-5)).sort((a,b) => a.localeCompare(b,undefined,{numeric:true}));
  async function readReportIndex(slug) {
    const records = new Map();
    if (!window.hadithManagedNumbers(slug).length) return records;
    let after = "";
    for (;;) {
      const response = await nativeFetch(api+new URLSearchParams({view:"reports",slug,after}),{signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error("Published search data is unavailable.");
      const rows = await response.json();
      if (!Array.isArray(rows)) throw new Error("Invalid published search data.");
      for (const [path,n,ar,en,ur,book] of rows) if (!Object.hasOwn(preview,path)) records.set(String(n),[String(n),ar||"",en||"",ur||"",Number(book)||null]);
      if (rows.length < 200) break;
      after = rows.at(-1)[0];
    }
    const prefix = "cms/reports/"+slug+"/";
    for (const [path,url] of Object.entries(preview)) {
      if (!url || !path.startsWith(prefix)) continue;
      const draft = await readDocument(path);
      records.set(String(draft.n),[String(draft.n),draft.ar||"",draft.en||"",draft.ur||"",draft.book||null]);
    }
    return records;
  }

  const indexCache = new Map();
  window.hadithManagedSearch = slug => {
    if (!indexCache.has(slug)) indexCache.set(slug,readReportIndex(slug).catch(error => {
      indexCache.delete(slug);
      throw error;
    }));
    return indexCache.get(slug);
  };

  async function loadLibrary() {
    window.hadithManagedLibrary = new Map();
    const paths = managedPaths().filter(path => /^cms\/library\/[a-z0-9_-]+[.]json$/.test(path));
    await Promise.all(paths.map(async path => {
      try {
        const item = window.HadithContent.collection(await readDocument(path));
        if (window.HadithContent.collectionPath(item.slug) === path) window.hadithManagedLibrary.set(item.slug,item);
      } catch (error) { console.warn("Collection could not load:",error.message); }
    }));
  }

  function script(src) {
    return new Promise((resolve, reject) => {
      const element = document.createElement("script");
      element.src = src;
      element.onload = resolve;
      element.onerror = reject;
      document.head.append(element);
    });
  }
  window.hadithCmsStream = input => {
    const url = new URL(input, location.href);
    if (url.origin !== location.origin && !["www.hadith.to","cdn.hadith.to"].includes(url.hostname)) return null;
    const path = url.pathname.slice(1);
    if (!Object.hasOwn(streams,path)) return null;
    try {
      const stream = new URL(streams[path]);
      return stream.protocol==="https:" && !stream.username && !stream.password ? stream.href : null;
    } catch { return null; }
  };
  window.hadithCmsCatalog = [];
  window.hadithCmsHasAsset = input => assetUrl(input) !== input;
  async function readManifest() {
    const response = await nativeFetch(api + "view=manifest", { signal:AbortSignal.timeout(2500) });
    if (response.ok) assets = await response.json();
  }

  async function fetchWithOverrides(input, options) {
    if (typeof input !== "string" && !(input instanceof URL)) return nativeFetch(input, options);
    const override = assetUrl(input);
    const response = await nativeFetch(override, options);
    if (response.status !== 404 || typeof override !== "string" || !override.startsWith(api)) return response;
    // A tab can outlive a release. Recheck the live map before retrying a retired version.
    await readManifest().catch(() => {});
    const current = assetUrl(input);
    return current === override ? response : nativeFetch(current, options);
  }

  async function loadSite() {
    const path = "/cms/site.json";
    const url = assetUrl(path);
    if (url === path) return;
    const response = await nativeFetch(url,{signal:AbortSignal.timeout(2500)});
    if (!response.ok) return;
    const site = await response.json();
    if (!site || typeof site !== "object") return;
    const clean = (value,max) => typeof value === "string" ? value.trim().slice(0,max) : "";
    const heading = clean(site.heading,120);
    const intro = clean(site.intro,2000);
    const title = clean(site.title,120);
    const description = clean(site.description,300);
    const pages = (Array.isArray(site.pages) ? site.pages : []).filter(page => page &&
      typeof page.slug === "string" && page.slug.length<=64 && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(page.slug) &&
      clean(page.title,120) && clean(page.body,24000));
    const links = document.getElementById("site-navigation");
    const query = new URLSearchParams(location.search);
    if (query.has("cms-preview")) {
      query.delete("page");
    } else {
      for (const key of Array.from(query.keys())) query.delete(key);
    }
    function pageUrl(slug) {
      const params = new URLSearchParams(query);
      if (slug) params.set("page",slug);
      return "/"+(params.size ? "?"+params : "");
    }
    for (const page of pages.filter(item => item.nav === true)) {
      const link = document.createElement("a");
      link.href=pageUrl(page.slug);
      link.textContent=clean(page.title,120);
      links.append(link);
    }
    links.hidden=!links.childElementCount;
    for (const [id,value] of [["site-heading",heading],["site-intro",intro]]) {
      const element=document.getElementById(id);
      element.textContent=value;
      element.hidden=!value;
    }
    const requested=new URLSearchParams(location.search).get("page");
    const page=pages.find(item => item.slug===requested);
    const metadata=(name,value) => {
      if (!value) return;
      document.querySelector('meta[name="'+name+'"]')?.setAttribute("content",value);
      document.querySelector('meta[property="og:'+name+'"]')?.setAttribute("content",value);
    };
    if (description) metadata("description",description);
    if (page) {
      document.getElementById("landing").hidden=true;
      const content=document.getElementById("site-page");
      document.getElementById("site-page-home").href=pageUrl();
      document.getElementById("site-page-title").textContent=clean(page.title,120);
      document.getElementById("site-page-body").textContent=clean(page.body,24000);
      document.getElementById("skipToContent").href="#site-page";
      content.hidden=false;
      document.title=clean(page.title,120)+" | Hadith.to";
      metadata("title",document.title);
      metadata("description",clean(page.body,160));
      const canonical = new URL("https://www.hadith.to/");
      canonical.searchParams.set("page",page.slug);
      document.querySelector('link[rel="canonical"]')?.setAttribute("href",canonical.href);
      return true;
    }
    window.hadithCmsHomeTitle=title;
    return false;
  }

  async function bootstrap() {
    preview = await previewAssets();
    try {
      await readManifest();
      const streamMap = assetUrl("/cms/streams.json");
      if (streamMap !== "/cms/streams.json") {
        try {
          const response = await nativeFetch(streamMap,{signal:AbortSignal.timeout(2500)});
          if (response.ok) {
            const value = await response.json();
            if (value && typeof value === "object" && !Array.isArray(value)) streams = value;
          }
        } catch (error) { console.warn("Hadith stream map could not load:",error.message); }
      }
      if (assetUrl("/cms/collections.json") !== "/cms/collections.json") {
        const catalog = await nativeFetch(assetUrl("/cms/collections.json"), { signal: AbortSignal.timeout(2500) });
        if (catalog.ok) window.hadithCmsCatalog = await catalog.json();
      }
    } catch (error) {
      console.warn("Hadith CMS could not load:", error.message);
    }
    if (await loadSite().catch(error => {
      console.warn("Hadith website content could not load:", error.message);
      return false;
    })) return;
    await script("/cms-content.js");
    await loadLibrary();
    window.fetch = fetchWithOverrides;
    await script("/hadith-reader.js");
    await script("/reader-ui.js?v=arabic-search-snippets");
    await script("/arabic-word-library.js?v=2");
  }
  bootstrap().catch(error => console.error("Hadith reader could not start:", error));
})();
