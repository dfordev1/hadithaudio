customElements.define("bukhari-urdu", class extends HTMLElement {
  connectedCallback() {
    this.innerHTML = '<details><summary>Listen in Urdu</summary><div aria-live="polite"></div></details>';
    const details = this.firstElementChild;
    details.ontoggle = async () => {
      if (!details.open) return this.sound?.pause();
      if (this.loaded) return;
      this.loaded = true;
      const box = details.lastElementChild;
      try {
        const load = async name => {
          const response = await fetch("bukhari/urdu/" + name + ".json");
          if (!response.ok) throw Error();
          return response.json();
        };
        const [index, book] = await Promise.all([load("index"), load("book-" + this.dataset.book)]);
        if (!this.isConnected) return;
        const row = book.hadith[this.dataset.report];
        if (!row || !(row.e > row.s && row.s >= 0)) {
          box.textContent = "No Urdu audio for this hadith.";
          return;
        }
        const sound = this.sound = new Audio(new URL(row.f, index.audioBase));
        sound.preload = "none";
        const button = document.createElement("button");
        button.textContent = "Play Urdu";
        const words = document.createElement("p");
        words.lang = "ur";
        words.dir = "rtl";
        words.className = "urdu";
        const play = time => {
          audio.pause();
          sound.currentTime = time;
          sound.play().catch(() => { if (this.isConnected) button.textContent = "Retry Urdu audio"; });
        };
        button.onclick = () => sound.paused
          ? play(sound.currentTime >= row.s && sound.currentTime < row.e - 0.08 ? sound.currentTime : row.s)
          : sound.pause();
        const timed = [];
        for (const [word,start,end] of row.w) {
          const el = document.createElement("span");
          el.textContent = word;
          if (Number.isFinite(start) && end > start && start >= row.s && start < row.e) {
            el.tabIndex = 0;
            el.setAttribute("role","button");
            el.style.cursor = "pointer";
            el.onclick = () => play(start);
            el.onkeydown = event => {
              if (event.key === "Enter" || event.key === " ") { event.preventDefault(); play(start); }
            };
            timed.push({el,start,end});
          } else el.style.opacity = "0.7";
          words.append(el," ");
        }
        let active;
        const tick = () => {
          if (sound.currentTime >= row.e - 0.08) { sound.pause(); sound.currentTime = row.s; }
          const next = timed.find(t => sound.currentTime >= t.start && sound.currentTime < t.end);
          if (active !== next) {
            if (active) active.el.style.backgroundColor = "";
            if (next) next.el.style.backgroundColor = "Highlight";
            active = next;
          }
        };
        this.stopUrdu = () => sound.pause();
        audio.addEventListener("play",this.stopUrdu);
        sound.onplay = () => { button.textContent = "Pause Urdu"; this.timer = setInterval(tick,30); };
        sound.onpause = () => { clearInterval(this.timer); button.textContent = "Play Urdu"; };
        const credit = document.createElement("small");
        credit.textContent = [row.tags?.includes("text-from-recording") && "Urdu text from the recording", index.credits.audio, index.credits.text].filter(Boolean).join(" · ");
        box.replaceChildren(button,words,credit);
      } catch {
        box.textContent = "Could not load Urdu audio. Close and reopen to retry.";
        this.loaded = false;
      }
    };
  }

  disconnectedCallback() {
    this.sound?.pause();
    clearInterval(this.timer);
    if (this.stopUrdu) audio.removeEventListener("play",this.stopUrdu);
    this.loaded = false;
  }
});
