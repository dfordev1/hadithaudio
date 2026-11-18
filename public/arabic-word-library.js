(() => {
  const catalogUrl = "https://cdn.jsdelivr.net/gh/playorbitt/arabic-word-reader@main/library.json";
  const list = document.getElementById("arabicWordLibraryList");
  if (!list) return;
  const esc = value => String(value ?? "").replace(/[&<>\\"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\":"&quot;","'":"&#39;"}[c]));
  const fallback = message => { list.innerHTML = '<p class="search-status">' + esc(message) + '</p>'; };
  const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("catalog timeout")), 7000));
  Promise.race([fetch(catalogUrl + "?v=1", { cache: "no-store", mode: "cors" }), timeout])
    .then(response => { if (!response.ok) throw new Error("catalog unavailable"); return response.json(); })
    .then(catalog => {
      const books = Array.isArray(catalog.books) ? catalog.books : [];
      if (!books.length) return fallback("The synchronized book catalog is being prepared.");
      list.innerHTML = books.map(book => {
        const title = esc(book.titleArabic || book.title || book.id);
        const en = esc(book.titleEnglish || book.subtitle || "Arabic word-synchronized book");
        const sync = book.sync === "word" ? "word-level sync" : book.sync === "sentence" ? "sentence sync" : "text only";
        const href = book.readerUrl || book.text || "#";
        return '<a href="' + esc(href) + '" target="_blank" rel="noopener" class="library-book"><div><div class="ar">' + title + '</div><div class="en">' + en + '</div><div class="meta">' + esc(sync) + (book.chapters ? " · chapters" : "") + '</div></div><div class="side">Open ↗</div></a>';
      }).join("");
    })
    .catch(() => fallback("The synchronized-book catalog could not be loaded. Please try again shortly."));
})();
