(() => {
  const base = 'https://raw.githubusercontent.com/playorbitt/arabic-word-reader/main/';
  const id = new URLSearchParams(location.search).get('book');
  const audio = document.getElementById('audio');
  const title = document.getElementById('title');
  const status = document.getElementById('status');
  const book = document.getElementById('book');
  const timed = [];
  const chapters = document.getElementById('chapters');
  const follow = document.getElementById('follow');
  const theme = document.getElementById('theme');
  const aqidahParts = [["المقدمة وتوحيد الله",298],["النبوة والقرآن ورؤية الله",326],["الإسراء والمعراج والشفاعة",63],["الميثاق والقضاء والقدر",361],["الإيمان وأهل القبلة والكبائر",321],["العبادة والجماعة وولاة الأمور",141],["الموت والبعث والآخرة",306],["الصحابة والسلف والأولياء",213],["أشراط الساعة والخاتمة",141]];
  try { theme.value = JSON.parse(localStorage.getItem('malti:theme')) || 'light'; } catch {}
  if (!theme.value) theme.value = 'light';
  document.documentElement.dataset.theme = theme.value;
  theme.addEventListener('change', () => {
    document.documentElement.dataset.theme = theme.value;
    try { localStorage.setItem('malti:theme', JSON.stringify(theme.value)); } catch {}
  });
  chapters.addEventListener('change', () => {
    document.getElementById(chapters.value)?.scrollIntoView({ block: 'start' });
  });
  function chapter(label) {
    const heading = document.createElement('h2');
    heading.className = 'book-chapter';
    heading.id = 'chapter-' + (chapters.options.length + 1);
    heading.textContent = label;
    chapters.add(new Option(label, heading.id));
    book.append(heading);
  }
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
  function prose(words) {
    let start = 0;
    for (let end = 1; end <= words.length; end++) {
      if (end === words.length || (end - start >= 55 && /[.!؟:]$/.test(words[end - 1].text)) || end - start >= 95) {
        paragraph(words.slice(start, end));
        start = end;
      }
    }
  }
  function render(data) {
    if (Array.isArray(data)) {
      let offset = 0;
      for (const [label, count] of aqidahParts) {
        chapter(label);
        prose(data.slice(offset, offset + count));
        offset += count;
      }
      if (offset < data.length) prose(data.slice(offset));
    } else {
      for (const part of data.parts) {
        chapter(part.title);
        for (const row of part.rows) if (row.kind !== 'chapter') paragraph(row.words);
      }
    }
    chapters.disabled = !chapters.options.length;
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
    if (active && follow.checked && !audio.paused) {
      const bounds = active.getBoundingClientRect();
      const top = document.querySelector('.book-header').getBoundingClientRect().bottom;
      const bottom = document.querySelector('.book-dock').getBoundingClientRect().top;
      if (bounds.top < top || bounds.bottom > bottom) active.scrollIntoView({ block: 'center' });
    }
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
