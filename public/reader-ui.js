/* Presentation and local reading tools. Corpus/audio playback remain in index.html. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const icons = {
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    bookmark:'<path d="M6 3h12v18l-6-4-6 4z"/>',
    copy:'<rect x="8" y="8" width="12" height="12" rx="1"/><path d="M15 4H4v11"/>',
    focus:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  };
  const svg = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]}</svg>`;
  const button = (label, action, icon) => {
    const b = document.createElement("button"); b.type = "button"; b.className = "iconbtn";
    b.setAttribute("aria-label", label); b.title = label; b.innerHTML = svg(icon); b.onclick = action; return b;
  };
  const refKey = ref => `${ref.slug}:${ref.n}`;
  const validRef = ref => ref && typeof ref.slug === "string" && Object.hasOwn(bySlug, ref.slug) && /^\d+[a-z]?$/i.test(String(ref.n));
  const rawSaved = store.get("savedHadith", []);
  let saved = Array.isArray(rawSaved) ? rawSaved.filter(validRef).map(r => ({slug:r.slug, n:String(r.n)})) : [];
  const opened = new Map();
  let recent = [];
  let searchEpoch = 0;
  let toastTimer;
  let focusReturn = null;
  const six = new Set(["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah"]);
  const normalize = text => String(text).normalize("NFKC").toLowerCase().replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]/g, "").replace(/[أإآٱ]/g, "ا").trim();
  function announce(message) {
    const toast = $("uiToast"); toast.textContent = message; toast.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.hidden = true; }, 2400);
  }
  function toggleSaved(ref) {
    if (!validRef(ref)) return;
    const key = refKey(ref), exists = saved.some(r => refKey(r) === key);
    saved = exists ? saved.filter(r => refKey(r) !== key) : [{slug:ref.slug,n:String(ref.n)}, ...saved];
    const persisted = store.set("savedHadith", saved);
    announce(exists ? "Removed from saved passages" : persisted === false ? "Saved for this session; device storage is unavailable." : "Passage saved on this device");
    renderSaved(); syncSaveButtons();
  }
  function syncSaveButtons() {
    const active = validRef(state) && saved.some(r => refKey(r) === refKey(state));
    document.querySelectorAll("[data-save-current]").forEach(b => {
      b.setAttribute("aria-pressed", String(active)); b.title = active ? "Unsave passage" : "Save passage";
      b.setAttribute("aria-label", b.title);
      const path = b.querySelector("path"); if (path) path.setAttribute("fill", active ? "currentColor" : "none");
    });
    $("savedCount").textContent = saved.length ? String(saved.length) : "";
  }
  function renderRefList(target, refs, isSaved) {
    target.replaceChildren();
    if (!refs.length) {
      const empty = document.createElement("div"); empty.className = "empty-shelf";
      const title = document.createElement("h2"); title.textContent = isSaved ? "No saved passages yet" : "No recent passages";
      const p = document.createElement("p"); p.textContent = isSaved ? "Save a passage while reading to return to it here." : "Passages you open will appear here during this session.";
      const a = document.createElement("a"); a.href = "#bukhari:1"; a.textContent = "Open the reader";
      empty.append(title, p, a); target.append(empty); return;
    }
    refs.forEach(ref => {
      const row = document.createElement("div"); row.className = "saved-row";
      const link = document.createElement("a"); link.href = `#${refKey(ref)}`;
      const title = document.createElement("strong"); title.textContent = bySlug[ref.slug].en;
      const meta = document.createElement("small"); meta.textContent = `Hadith ${ref.n}`;
      link.append(title, meta); row.append(link);
      if (isSaved) row.append(button("Unsave passage", () => toggleSaved(ref), "bookmark"));
      target.append(row);
    });
  }
  function renderSaved() { renderRefList($("savedPanel"), saved, true); syncSaveButtons(); }
  function homePanel() {
    const panel = ({"#saved":"saved", "#recent":"recent", "#search":"search"})[location.hash] || "collections";
    document.body.dataset.homePanel = panel;
    const panels = {collections:"cards",saved:"savedPanel",recent:"recentPanel",search:"searchPanel"};
    Object.entries(panels).forEach(([key,id]) => { $(id).hidden = key !== panel; });
    $("shelfFilters").hidden = panel !== "collections";
    document.querySelectorAll("[data-home-tab]").forEach(b => {
      const active = b.dataset.homeTab === panel; b.setAttribute("aria-selected", String(active)); b.tabIndex = active ? 0 : -1;
    });
    if(panel === "saved") renderSaved();
    if(panel === "recent") renderRefList($("recentPanel"), recent, false);
    if(panel === "search") { renderSearch(); requestAnimationFrame(() => $("searchInput").focus()); }
  }
  document.querySelectorAll("[data-home-tab]").forEach(b => {
    b.onclick = () => { location.hash = b.dataset.homeTab === "collections" ? "" : b.dataset.homeTab; };
    b.onkeydown = e => {
      const tabs = [...document.querySelectorAll("[data-home-tab]")]; let index = tabs.indexOf(b);
      if(e.key === "ArrowRight") index = (index + 1) % tabs.length;
      else if(e.key === "ArrowLeft") index = (index + tabs.length - 1) % tabs.length;
      else if(e.key === "Home") index = 0; else if(e.key === "End") index = tabs.length - 1; else return;
      e.preventDefault(); tabs[index].click(); tabs[index].focus();
    };
  });
  document.querySelectorAll("[data-shelf-filter]").forEach(b => { b.onclick = () => {
    const filter = b.dataset.shelfFilter;
    document.querySelectorAll("[data-shelf-filter]").forEach(item => item.setAttribute("aria-pressed", String(item === b)));
    [...$("cards").children].forEach(a => {
      const c = bySlug[a.dataset.collection];
      a.hidden = filter === "six" ? !six.has(c.slug) : filter === "forty" ? !!c.books : filter === "other" ? six.has(c.slug) || !c.books : false;
    });
  }; });
  $("openSearch").innerHTML = svg("search"); $("openSaved").innerHTML = svg("bookmark");
  $("openSearch").onclick = () => { location.hash = "search"; };
  $("openSaved").onclick = () => { location.hash = "saved"; };
  $("rtSaved").onclick = () => { setReaderToolsOpen(false); location.hash = "saved"; };
  $("skipToContent").onclick = e => {
    e.preventDefault();
    const content = document.body.dataset.view === "reader" ? $("stage") : $("landing");
    content.focus(); content.scrollIntoView({block:"start"});
  };

  function closeFocus(restoreFocus = true) {
    if (document.body.dataset.focus !== "true") return;
    document.body.dataset.focus = "false"; $("focusExit").hidden = true;
    $("stage").removeAttribute("role"); $("stage").removeAttribute("aria-modal"); $("stage").removeAttribute("aria-label");
    $("prevBtn").inert = false; $("nextBtn").inert = false;
    if (restoreFocus) focusReturn?.focus(); focusReturn = null;
  }
  function openFocus() {
    if (!$("stage").querySelector(".arabic")) return;
    focusReturn = $("readerToolsPanel").contains(document.activeElement) ? $("readerMoreBtn") : document.activeElement;
    setReaderToolsOpen(false); setSettingsOpen(false);
    document.body.dataset.focus = "true"; $("focusExit").hidden = false;
    $("prevBtn").inert = true; $("nextBtn").inert = true;
    $("stage").setAttribute("role", "region"); $("stage").setAttribute("aria-label", "Focused reading");
    $("focusExit").focus();
  }
  $("focusExit").onclick = closeFocus; $("rtFocus").onclick = openFocus;
  async function copyPassage() {
    const ar = [...$("stage").querySelectorAll(".arabic .t")].map(x => x.textContent).join(" ");
    const lang = document.body.dataset.meaningLanguage || "en";
    const meanings = [...$("stage").querySelectorAll(lang === "ur" ? ".urdu" : lang === "both" ? ".english,.urdu" : ".english")].map(x => x.textContent);
    try { await navigator.clipboard.writeText([ar,...meanings,`${bySlug[state.slug].en} · ${state.n}`,publicHadithUrl(state.slug,state.n)].join("\n\n")); announce("Passage copied"); }
    catch { announce("Copy is unavailable. Select the passage text to copy it."); }
  }
  function decorateReader() {
    if (!validRef(state) || !$("stage").querySelector(".arabic")) return;
    const ref = {slug:state.slug,n:String(state.n)}, key = refKey(ref);
    recent = [ref, ...recent.filter(r => refKey(r) !== key)].slice(0,50);
    const record = { ...ref, arabic:[...$("stage").querySelectorAll(".arabic .t")].map(x => x.textContent).join(" "),
      english:$("stage").querySelector(".english")?.textContent || "", urdu:$("stage").querySelector(".urdu")?.textContent || "" };
    opened.set(key, record);
    if ($("stage").querySelector(".reading-actions")) { syncSaveButtons(); return; }
    document.body.dataset.showMeaning = "false";
    const actions = document.createElement("div"); actions.className = "reading-actions";
    const meaning = document.createElement("button"); meaning.type = "button"; meaning.className = "show-meaning"; meaning.textContent = "Show meaning"; meaning.setAttribute("aria-expanded","false");
    meaning.disabled = !$("stage").querySelector(".meaning-section");
    if (meaning.disabled) meaning.textContent = "Translation unavailable";
    meaning.onclick = () => {
      const shown = document.body.dataset.showMeaning !== "true"; document.body.dataset.showMeaning = String(shown);
      meaning.textContent = shown ? "Hide meaning" : "Show meaning"; meaning.setAttribute("aria-expanded",String(shown));
    };
    const language = document.createElement("select"); language.className = "meaning-language"; language.setAttribute("aria-label","Translation language");
    language.innerHTML = '<option value="en">English</option><option value="ur">اردو</option><option value="both">English + اردو</option>';
    language.value = document.body.dataset.meaningLanguage;
    language.disabled = meaning.disabled;
    language.onchange = () => { document.body.dataset.meaningLanguage = language.value; store.set("meaningLanguage",language.value); };
    const grow = document.createElement("span"); grow.className = "grow";
    const save = button("Save passage", () => toggleSaved(ref), "bookmark"); save.dataset.saveCurrent = "";
    actions.append(meaning,language,grow,save,button("Copy passage",copyPassage,"copy"),button("Focused reader",openFocus,"focus"));
    const anchor = $("stage").querySelector(".refblock"); anchor.after(actions);
    const nav = document.createElement("nav"); nav.className = "mobile-page-nav"; nav.setAttribute("aria-label","Hadith navigation");
    const previous = document.createElement("button"); previous.type = "button"; previous.textContent = "‹ Previous"; previous.disabled = state.nav?.prev == null; previous.onclick = () => $("prevBtn").click();
    const next = document.createElement("button"); next.type = "button"; next.textContent = "Next ›"; next.disabled = state.nav?.next == null; next.onclick = () => $("nextBtn").click();
    nav.append(previous,next); actions.after(nav); syncSaveButtons();
  }

  const searchCollection = $("searchCollection");
  COLLECTIONS.forEach(c => { const option = document.createElement("option"); option.value = c.slug; option.textContent = c.en; searchCollection.append(option); });
  function appendSearchRecord(record) {
    const link = document.createElement("a"); link.className = "search-result"; link.href = `#${refKey(record)}`;
    const reference = document.createElement("strong"); reference.textContent = `${bySlug[record.slug].en} · Hadith ${record.n}`;
    const arabic = document.createElement("p"); arabic.className = "ar"; arabic.lang = "ar"; arabic.dir = "rtl"; arabic.textContent = record.arabic.split(/\s+/).slice(0,24).join(" ");
    const meaning = document.createElement("p"); meaning.className = "en"; meaning.textContent = record.english.slice(0,240);
    link.append(reference,arabic,meaning); $("searchResults").append(link);
  }
  function renderSearch() {
    ++searchEpoch; $("openNumber").disabled = false;
    const query = normalize($("searchInput").value), slug = searchCollection.value;
    const exact = /^\d+[a-z]?$/i.test(query); $("openNumber").hidden = !exact;
    $("searchResults").replaceChildren();
    const results = [...opened.values()].filter(r => r.slug === slug && (!query || (exact ? String(r.n).toLowerCase() === query : normalize([r.arabic,r.english,r.urdu,r.n].join(" ")).includes(query))));
    results.forEach(appendSearchRecord);
    $("searchStatus").textContent = exact ? `Open hadith ${query} in ${bySlug[slug].en}.` : results.length ? `${results.length} matching ${results.length === 1 ? "passage" : "passages"}` : query ? "No matches in the passages opened this session. Use an exact hadith number to search the collection." : "Passages opened this session will appear here.";
  }
  $("searchInput").oninput = renderSearch; searchCollection.onchange = renderSearch;
  $("clearSearch").onclick = () => { $("searchInput").value = ""; renderSearch(); $("searchInput").focus(); };
  $("searchForm").onsubmit = async e => {
    e.preventDefault(); const n = $("searchInput").value.trim().toLowerCase(), slug = searchCollection.value;
    if(!/^\d+[a-z]?$/i.test(n)) { renderSearch(); return; }
    const epoch = ++searchEpoch; $("openNumber").disabled = true; $("searchStatus").textContent = "Finding hadith…";
    try {
      const col = bySlug[slug]; let found;
      if(col.books) {
        const idx = await ensureBookIndex(slug), book = bookForReport(idx,n);
        if(book) { const data = await ensureBookOf(slug,book.book); found = data.hadith.find(h => String(h.n).toLowerCase() === n)?.n; }
      } else if(/^\d+$/.test(n) && Number(n) >= 1 && Number(n) <= col.count) found = Number(n);
      if(epoch !== searchEpoch || location.hash !== "#search") return;
      if(found === undefined) { $("searchStatus").textContent = "That exact hadith number was not found in this collection."; return; }
      setHash(slug,found);
    } catch { if(epoch === searchEpoch) $("searchStatus").textContent = "Could not load the collection. Check your connection and try again."; }
    finally { if(epoch === searchEpoch) $("openNumber").disabled = false; }
  };
  addEventListener("hashchange", () => { ++searchEpoch; closeFocus(false); homePanel(); });
  addEventListener("hadith:landing", () => { if(location.hash === "#search") $("searchInput").focus(); });
  addEventListener("hadith:rendered", decorateReader);
  addEventListener("keydown", e => {
    if(e.key === "Escape") closeFocus();
    if(e.key === "/" && !e.metaKey && !e.ctrlKey && !e.target.closest("input,textarea,select,button,[contenteditable=true],dialog")) { e.preventDefault(); location.hash = "search"; }
  });
  const language = store.get("meaningLanguage","en"); document.body.dataset.meaningLanguage = ["en","ur","both"].includes(language) ? language : "en";
  homePanel(); renderSaved(); decorateReader();
})();
