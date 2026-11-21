(() => {
  "use strict";
  const model = window.HadithContent;
  const picker = $("library-collection");
  const details = $("library-details");
  const reportForm = $("library-report");
  const bookList = $("library-books");
  const current = new Map();
  let words = [];
  const featured = slug => model.bundled.find(item => item.slug === slug);
  const versionAt = path => selected.has(path) ? selected.get(path).version : live.get(path);
  async function read(path) {
    const id = versionAt(path);
    return id ? request("asset",{query:{id}}).then(response => response.json()) : null;
  }
  const readBaseline = path => send("/rest/v1/cms_baseline?"+new URLSearchParams({
    select:"document",path:"eq."+path,limit:1,
  })).then(result=>result.json()).then(rows=>rows[0]?.document || null);
  async function bundled(path, optional = false) {
    const id = versionAt(path);
    const response = id ? await request("asset",{query:{id}}) : await fetch("/"+path);
    if (!response.ok) {
      if (optional && response.status === 404) return null;
      throw new Error("Could not load "+path+".");
    }
    return response.json();
  }
  async function stageDocument(path, document) {
    const id = await send("/rest/v1/rpc/cms_stage_document",{
      method:"POST",body:{asset_path:path,asset_document:document},
    }).then(response => response.json());
    queue(path,id);
  }
  function controls(item) {
    details.reset();
    details.elements.slug.value = item?.slug || "";
    details.elements.slug.readOnly = Boolean(item);
    details.elements.en.value = item?.en || "";
    details.elements.ar.value = item?.ar || "";
    bookList.replaceChildren();
    (item?.books || []).forEach(addBook);
    reportForm.reset();
    reportForm.elements.book.replaceChildren(new Option("No book",""));
    for (const book of item?.books || []) reportForm.elements.book.add(new Option(book.title,String(book.number)));
    reportForm.hidden = !item;
    setWords([]);
  }
  function setWords(value) {
    words = value;
    $("library-timing").textContent = words.length ? words.length+" word timestamps loaded." : "";
  }
  function addBook(book = {}) {
    const row = $("library-book-template").content.firstElementChild.cloneNode(true);
    row.querySelector('[name="number"]').value = book.number ?? "";
    row.querySelector('[name="title"]').value = book.title || "";
    row.querySelector("[data-remove]").onclick = () => row.remove();
    bookList.append(row);
  }
  function fillPicker(slug = "") {
    picker.replaceChildren(new Option("New collection",""));
    for (const item of current.values()) picker.add(new Option(item.en,item.slug));
    picker.value = slug;
  }
  async function openCollection(slug) {
    let item = current.get(slug);
    if (item && featured(slug)?.books && !item.books.length && !versionAt(model.collectionPath(slug))) {
      const index = await bundled(slug+"/index.json").catch(() => null);
      if (index?.books) item = {...item,books:index.books.map(book => ({number:book.book,title:book.title||"Book "+book.book}))};
      current.set(slug,item);
    }
    controls(item);
  }
  window.hadithLibraryOpen = async () => {
    current.clear();
    for (const item of model.bundled) current.set(item.slug,{...item,books:[]});
    const baseline = await send("/rest/v1/cms_baseline?select=document&path=like.cms%2Flibrary%2F*&order=path").then(response=>response.json());
    for (const {document} of baseline) {
      const item = model.collection(document);
      current.set(item.slug,item);
    }
    const paths = new Set([...live.keys(),...selected.keys()]);
    await Promise.all(Array.from(paths).filter(path => /^cms\/library\/[a-z0-9_-]+[.]json$/.test(path)).map(async path => {
      const raw = await read(path);
      if (raw) { const item = model.collection(raw); current.set(item.slug,item); }
    }));
    fillPicker();
    controls(null);
  };
  window.hadithLibraryReset = () => { current.clear();fillPicker();controls(null); };
  picker.onchange = run(() => openCollection(picker.value));
  $("library-add-book").onclick = () => addBook();
  $("library-clear-timing").onclick = () => {reportForm.elements.timing.value="";setWords([]);};
  details.onsubmit = run(async event => {
    const data = new FormData(event.currentTarget);
    const item = model.collection({...Object.fromEntries(data),books:Array.from(bookList.children,row => ({
      number:row.querySelector('[name="number"]').value,title:row.querySelector('[name="title"]').value,
    }))});
    if (!picker.value && current.has(item.slug)) throw new Error("Select the existing collection before editing it.");
    await stageDocument(model.collectionPath(item.slug),item);
    current.set(item.slug,item);
    fillPicker(item.slug);
    controls(item);
    await loadVersions(true);
    status("Collection draft saved.");
  });

  async function legacyReport(slug,n) {
    const col = featured(slug);
    if (!col) return null;
    if (!col.books) {
      const rec = await bundled("recitation/"+col.corpus+"."+n.padStart(3,"0")+".json",true);
      if (!rec) return null;
      const [translations,refs] = await Promise.all([
        bundled("translation/"+slug+".json",true),bundled("sunnah/"+slug+".json",true),
      ]);
      const en = translations?.translations?.find(item => item.witness === rec.witness);
      const source = refs?.entries?.find(item => item.witness === rec.witness)?.sunnah?.url;
      const ar = rec.tokens.map(word => word.text).join(" ");
      return {slug,n,ar,en:en?.matn || en?.full || "",ur:"",source,
        audio:"https://cdn.hadith.to/recitation/"+col.corpus+"."+n.padStart(3,"0")+".mp3",
        words:rec.tokens.filter(word => Number.isFinite(word.start) && Number.isFinite(word.end) && word.end>word.start),
      };
    }
    const index = await bundled(slug+"/index.json",true);
    const book = index?.reportBook?.[n] ?? index?.books?.find(book => Number.parseInt(n,10)>=book.from && Number.parseInt(n,10)<=book.to)?.book;
    if (book == null) return null;
    const records = await bundled(slug+"/book-"+book+".json");
    const original = records.hadith?.find(item => String(item.n) === n);
    if (!original) return null;
    let translation = {};
    if (slug === "riyad" || slug === "musnad-ahmad") {
      const data = await bundled("translation/"+slug+".json",true);
      translation = data?.translations?.find(item => String(item.n) === n) || {};
    } else if (slug !== "darimi") {
      const load = async code => {
        const response = await fetch("https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/"+code+"-"+slug+"/"+n+".json");
        if (response.status === 404) return "";
        if (!response.ok) throw new Error("Could not load the existing translation.");
        const result = await response.json();
        return result.hadiths?.[0]?.text || "";
      };
      const [en,ur] = await Promise.all([load("eng"),load("urd")]);
      translation = {en,ur};
    }
    return {slug,n,book,ar:original.tokens.map(word => word.text).join(" "),en:translation.en||"",ur:translation.ur||"",
      reuseAudio:true,source:slug === "darimi" ? "" : "https://sunnah.com/"+slug+":"+n};
  }

  $("library-open-report").onclick = run(async () => {
    const slug = picker.value, n = reportForm.elements.n.value.trim().toLowerCase();
    if (!slug || !model.numberPattern.test(n)) throw new Error("Choose a collection and enter a hadith number.");
    const path = model.reportPath(slug,n);
    const record = await read(path) || await readBaseline(path) || await legacyReport(slug,n);
    for (const field of ["book","ar","en","ur","audio","source"]) reportForm.elements[field].value = record?.[field] ?? "";
    reportForm.elements.reuseAudio.checked = record?.reuseAudio === true;
    reportForm.elements.timing.value = "";
    setWords(record?.words || []);
    status(record ? "Hadith loaded." : "New hadith. Enter its Arabic text and translations.");
  });
  reportForm.onsubmit = run(async event => {
    const form = new FormData(event.currentTarget);
    const file = form.get("timing");
    let timing = words;
    if (file?.size) {
      const payload = JSON.parse(await file.text());
      timing = Array.isArray(payload) ? payload : payload.tokens;
      if (!Array.isArray(timing)) throw new Error("Word times must be an array or a tokens list.");
    }
    const item = model.report({...Object.fromEntries(form),slug:picker.value,words:timing,reuseAudio:reportForm.elements.reuseAudio.checked});
    if (item.book !== null && !current.get(item.slug)?.books.some(book => book.number === item.book)) throw new Error("Add the book to this collection first.");
    await stageDocument(model.reportPath(item.slug,item.n),item);
    setWords(item.words);
    $("preview-address").value=item.slug+":"+item.n;
    await loadVersions(true);
    status("Hadith draft saved.");
  });
  $("library-import").onsubmit = run(async event => {
    const file = new FormData(event.currentTarget).get("file");
    if (!file?.size || file.size > 40*1024*1024) throw new Error("Choose a JSON file up to 40 MiB.");
    const source = JSON.parse(await file.text());
    const collection = model.collection(source.collection);
    if (!Array.isArray(source.reports) || !source.reports.length || source.reports.length > 999) throw new Error("Import 1 to 999 hadith.");
    const ids = new Set();
    const records = source.reports.map(value => {
      const report = model.report({...value,slug:collection.slug});
      if (ids.has(report.n) || (report.book !== null && !collection.books.some(book => book.number === report.book))) {
        throw new Error("Duplicate hadith number or unknown book: "+report.n);
      }
      ids.add(report.n);
      return report;
    });
    let complete = 0;
    try {
      await stageDocument(model.collectionPath(collection.slug),collection);
      current.set(collection.slug,collection);
      fillPicker(collection.slug);
      controls(collection);
      for (const report of records) {
        status("Staging hadith "+(complete+1)+" of "+records.length+"…");
        await stageDocument(model.reportPath(report.slug,report.n),report);
        complete++;
      }
    } catch (error) { throw new Error(complete+" hadith staged. "+error.message); }
    finally { await loadVersions(true); }
    $("preview-address").value=collection.slug+":"+records[0].n;
    status("Collection and "+complete+" hadith staged.");
  });
})();
