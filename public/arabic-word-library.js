(() => {
  const catalogUrl = "https://raw.githubusercontent.com/playorbitt/arabic-word-reader/main/library.json";
  const list = document.getElementById("arabicWordLibraryList");
  if (!list) return;
  const esc = value => String(value ?? "").replace(/[&<>\\"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\":"&quot;","'":"&#39;"}[c]));
  const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("catalog timeout")), 7000));
  Promise.race([fetch(catalogUrl + "?v=1", { cache: "no-store", mode: "cors" }), timeout])
    .then(response => { if (!response.ok) throw new Error("catalog unavailable"); return response.json(); })
    .then(catalog => {
      const books = Array.isArray(catalog.books) ? catalog.books : [];
      if (!books.length) return;
      list.innerHTML = books.map(book => {
        const title = esc(book.titleArabic || book.title || book.id);
        const en = esc(book.titleEnglish || book.subtitle || "Arabic word-synchronized book");
        const sync = book.sync === "word" ? "word-level sync" : book.sync === "sentence" ? "sentence sync" : "text only";
        const href = "/arabic-book.html?book=" + encodeURIComponent(book.id);
        return '<a href="' + esc(href) + '" class="library-book"><div><div class="en">' + en + '</div><div class="meta">Arabic text · ' + esc(sync) + (book.chapters ? " · chapters" : "") + '</div></div><div class="side"><div class="ar" lang="ar" dir="rtl">' + title + '</div></div></a>';
      }).join("");
    })
    .catch(() => { /* Keep the books already rendered by the page. */ });
})();
