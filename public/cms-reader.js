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
    window.fetch = fetchWithOverrides;
    await script("/hadith-reader.js");
    await script("/reader-ui.js?v=arabic-search-snippets");
    await script("/arabic-word-library.js?v=2");
  }
  bootstrap().catch(error => console.error("Hadith reader could not start:", error));
})();
