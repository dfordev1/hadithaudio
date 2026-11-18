(() => {
  const base = 'https://raw.githubusercontent.com/playorbitt/arabic-word-reader/main/';
  const id = new URLSearchParams(location.search).get('book');
  const audio = document.getElementById('audio');
  const title = document.getElementById('title');
  const status = document.getElementById('status');
  const book = document.getElementById('book');
  const timed = [];
  let active;
  async function json(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  }
  function appendWords(container, words) {
    for (const word of words) {
      const seekable = Number.isFinite(word.start) && Number.isFinite(word.end) && word.end > word.start;
      const element = document.createElement(seekable ? 'button' : 'span');
      element.textContent = word.text;
      if (seekable) {
        element.type = 'button';
        element.className = 'word';
        element.dataset.start = word.start;
        timed.push({ start: word.start, end: word.end, element });
      }
      container.append(element, ' ');
    }
  }
  function paragraph(words) {
    const row = document.createElement('p');
    appendWords(row, words);
    book.append(row);
  }
  function render(data) {
    if (Array.isArray(data)) {
      let start = 0;
      for (let end = 1; end <= data.length; end++) {
        if (end === data.length || (end - start >= 55 && /[.!؟:]$/.test(data[end - 1].text)) || end - start >= 95) {
          paragraph(data.slice(start, end));
          start = end;
        }
      }
    } else {
      for (const part of data.parts) {
        const heading = document.createElement('h2');
        heading.textContent = part.title;
        book.append(heading);
        for (const row of part.rows) if (row.kind !== 'chapter') paragraph(row.words);
      }
    }
    timed.sort((a, b) => a.start - b.start);
  }
  function highlight() {
    const time = audio.currentTime;
    let low = 0, high = timed.length;
    while (low < high) {
      const middle = (low + high) >>> 1;
      if (timed[middle].start <= time) low = middle + 1;
      else high = middle;
    }
    const entry = timed[low - 1];
    const next = entry && time < entry.end ? entry.element : undefined;
    if (active === next) return;
    active?.classList.remove('active');
    active = next;
    active?.classList.add('active');
  }
  audio.addEventListener('timeupdate', highlight);
  audio.addEventListener('seeked', highlight);
  audio.addEventListener('error', () => { status.textContent = 'تعذّر تحميل التسجيل الصوتي.'; });
  book.addEventListener('click', event => {
    const word = event.target.closest('button.word');
    if (!word) return;
    audio.currentTime = Number(word.dataset.start);
    audio.play().catch(() => {});
  });
  async function load() {
    const catalog = await json(base + 'library.json');
    const entry = catalog.books.find(item => item.id === id);
    if (!entry) throw new Error('Unknown book');
    title.textContent = entry.titleArabic;
    document.title = entry.titleArabic + ' | Hadith.to';
    const data = await json(base + 'timings/' + encodeURIComponent(id) + '.json');
    render(data);
    status.textContent = '';
    audio.src = entry.audio;
  }
  load().catch(() => { status.textContent = 'تعذّر تحميل الكتاب. حاول تحديث الصفحة.'; });
})();
