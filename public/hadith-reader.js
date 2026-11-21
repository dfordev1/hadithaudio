const SITE_ORIGIN = "https://www.hadith.to";
const RECITATION_CDN = "https://cdn.hadith.to/recitation";
const REPORTS_API = "https://hadith-error-reports.quran-wbw.workers.dev";
function publicHadithUrl(slug, n){ return `${SITE_ORIGIN}/#${slug}:${n}`; }
function setPublicMetadata(title, slug=null, n=null){
  document.title = title;
  const url = slug && n ? publicHadithUrl(slug, n) : `${SITE_ORIGIN}/`;
  document.querySelector('link[rel="canonical"]')?.setAttribute("href", url);
  document.querySelector('meta[property="og:url"]')?.setAttribute("content", url);
  document.querySelector('meta[property="og:title"]')?.setAttribute("content", title);
}
window.va = window.va || function(){ (window.vaq = window.vaq || []).push(arguments); };
function trackSiteEvent(name, data={}){
  const safe = Object.fromEntries(Object.entries(data).filter(([, value]) =>
    typeof value === "string" || typeof value === "number" || typeof value === "boolean"
  ));
  window.va("event", { name, data:safe });
}
addEventListener("error", () => trackSiteEvent("reader_runtime_error", { source:"window" }));
addEventListener("unhandledrejection", () => trackSiteEvent("reader_runtime_error", { source:"promise" }));

function reportTimingUrl(slug, n){
  if (slug === "darimi") return `${SITE_ORIGIN}/darimi/book-${state.book}.json`;
  const col = bySlug[slug];
  if (col && !col.books) return `${SITE_ORIGIN}/recitation/${col.corpus}.${String(n).padStart(3,"0")}.json`;
  const stem = slug === "musnad-ahmad" ? `r${String(n).padStart(5,"0")}` : `n${String(n).padStart(4,"0")}`;
  return slug === "musnad-ahmad"
    ? `https://cdn.hadith.to/musnad-ahmad-timings/${stem}.json`
    : `https://cdn.hadith.to/${slug}-timings/${stem}.json`;
}
function openReportDialog(){
  setReaderToolsOpen(false);
  const col = bySlug[state.slug];
  if (!col || !state.n) return;
  const token = activeIdx >= 0 ? currentTokens[activeIdx] : null;
  document.getElementById("reportContext").textContent = `${col.en} · Hadith ${state.n}${token?.text ? ` · ${token.text} at ${fmt(audio.currentTime || 0)}` : ""}`;
  document.getElementById("reportMessage").textContent = "";
  document.getElementById("reportDialog").showModal();
}
document.getElementById("reportCancel").onclick = () => document.getElementById("reportDialog").close();
document.getElementById("reportForm").onsubmit = async (event) => {
  event.preventDefault();
  const message = document.getElementById("reportMessage");
  const submit = document.getElementById("reportSubmit");
  message.textContent = "Sending…"; submit.disabled = true;
  try {
    const tokenIndex = activeIdx >= 0 ? activeIdx : currentTokens.findIndex(t => isTimedToken(t) && (audio.currentTime || 0) >= t.start && (audio.currentTime || 0) <= t.end + .15);
    const token = tokenIndex >= 0 ? currentTokens[tokenIndex] : null;
    const context = tokenIndex >= 0 ? currentTokens.slice(Math.max(0,tokenIndex-3),tokenIndex+4).map(t => ({id:t.id||"",text:t.text||"",start:t.start,end:t.end})) : [];
    const response = await fetch(`${REPORTS_API}/v1/reports`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        collection:state.slug, hadithNumber:state.n, bookNumber:state.book || null,
        errorType:document.getElementById("reportType").value,
        severity:document.getElementById("reportSeverity").value,
        note:document.getElementById("reportNote").value,
        website:document.getElementById("reportWebsite").value,
        pageUrl:publicHadithUrl(state.slug,state.n),
        audioUrl:audioLogicalUrl || null,
        timingUrl:reportTimingUrl(state.slug,state.n),
        playbackTime:Number.isFinite(audio.currentTime) ? audio.currentTime : null,
        tokenId:token?.id || null, tokenText:token?.text || null,
        tokenStart:token?.start ?? null, tokenEnd:token?.end ?? null,
        context,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Could not send report");
    message.textContent = `Thank you. Report ${result.reportId.slice(0,8)} was received.`;
    document.getElementById("reportNote").value = "";
    trackSiteEvent("error_report_sent", { collection:state.slug, report:String(state.n), type:document.getElementById("reportType").value });
    setTimeout(() => document.getElementById("reportDialog").close(), 1600);
  } catch (error) { message.textContent = `${error.message}. Please try again.`; }
  finally { submit.disabled = false; }
};
function appendReportAction(parent){
  const area = document.createElement("div");
  area.className = "report-inline";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Report an error";
  button.onclick = openReportDialog;
  area.appendChild(button);
  parent.appendChild(area);
}
const htmlText = value => String(value).replace(/[&<>"']/g, char => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;",
})[char]);
const COLLECTIONS = window.HadithContent.bundled.map(item => ({...item}));
const catalogFields = item => item && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(item.slug) &&
  !Object.hasOwn(Object.prototype, item.slug) && typeof item.corpus === "string" &&
  /^[a-z0-9][a-z0-9_-]{0,63}$/.test(item.corpus) &&
  [item.en, item.ar].every(name => typeof name === "string" && name.trim() && name.length <= 150 && !/[<>&"\u0000-\u001f]/.test(name)) &&
  Number.isSafeInteger(item.count) && item.count > 0;
if (Array.isArray(window.hadithCmsCatalog)) {
  for (const item of window.hadithCmsCatalog.filter(catalogFields)) {
    const position = COLLECTIONS.findIndex(collection => collection.slug === item.slug);
    const collection = {
      slug:item.slug, corpus:item.corpus, ar:item.ar, en:item.en, count:item.count,
      books:item.books === true, audio:item.audio === true,
      synthetic:item.synthetic === "mixed" ? "mixed" : item.synthetic === true,
    };
    if (position < 0) COLLECTIONS.push(collection);
    else COLLECTIONS[position] = collection;
  }
}
function shelfAudioMeta(c){
  if (c.audio) return "read & listen";
  return "read";
}
for (const item of window.hadithManagedLibrary?.values() || []) {
  const existing = COLLECTIONS.find(col => col.slug === item.slug);
  if (existing) Object.assign(existing,{en:item.en,ar:item.ar});
  else {
    const numbers = window.hadithManagedNumbers(item.slug);
    if (numbers.length) COLLECTIONS.push({...item,count:numbers.length,audio:true,books:false,managed:true});
  }
}
const bySlug = Object.fromEntries(COLLECTIONS.map(c => [c.slug, c]));
const BUKHARI_BOOK_NAMES = {
  1:"Revelation",2:"Belief",3:"Knowledge",4:"Ablutions (Wudu')",5:"Bathing (Ghusl)",6:"Menstrual Periods",7:"Dry Ablution (Tayammum)",8:"Prayers (Salat)",9:"Times of Prayer",10:"Call to Prayer (Adhaan)",11:"Friday Prayer",12:"Fear Prayer",13:"The Two Festivals (Eids)",14:"Witr Prayer",15:"Prayer for Rain (Istisqaa)",16:"Eclipses",17:"Prostration during Qur'an Recital",18:"Shortening the Prayers",19:"Night Prayer (Tahajjud)",20:"Virtues of the Mosques of Makkah and Madinah",21:"Actions while Praying",22:"Forgetfulness in Prayer",23:"Funerals",24:"Zakat",25:"Hajj",26:"Umrah",27:"Pilgrims Prevented from Completing Hajj",28:"Hunting while on Pilgrimage",29:"Virtues of Madinah",30:"Fasting",31:"Night Prayer in Ramadan (Taraweeh)",32:"Virtues of the Night of Qadr",33:"Retreat in the Mosque (I'tikaf)",34:"Sales and Trade",35:"Advance Payment (Salam)",36:"Pre-emption (Shuf'a)",37:"Hiring",38:"Transfer of Debt (Hawala)",39:"Guarantees (Kafalah)",40:"Representation and Agency",41:"Agriculture",42:"Distribution of Water",43:"Loans and Bankruptcy",44:"Disputes",45:"Lost Property",46:"Oppressions",47:"Partnership",48:"Mortgaging",49:"Manumission of Slaves",50:"Contracts of Manumission",51:"Gifts",52:"Witnesses",53:"Peacemaking",54:"Conditions",55:"Wills and Testaments",56:"Striving in Allah's Cause (Jihad)",57:"One-fifth of Booty (Khumus)",58:"Jizyah and Treaties",59:"Beginning of Creation",60:"Prophets",61:"Virtues of the Prophet and Companions",62:"Companions of the Prophet",63:"Merits of the Ansar",64:"Military Expeditions",65:"Prophetic Commentary on the Qur'an",66:"Virtues of the Qur'an",67:"Marriage",68:"Divorce",69:"Supporting the Family",70:"Food and Meals",71:"Aqiqah",72:"Hunting and Slaughtering",73:"Eid Sacrifice",74:"Drinks",75:"Patients",76:"Medicine",77:"Dress",78:"Good Manners (Adab)",79:"Asking Permission",80:"Supplications",81:"Heart-Softening Narrations (Riqaq)",82:"Divine Will (Qadar)",83:"Oaths and Vows",84:"Expiation for Broken Oaths",85:"Inheritance",86:"Legal Punishments",87:"Blood Money",88:"Apostates",89:"Coercion",90:"Legal Stratagems",91:"Interpretation of Dreams",92:"Afflictions and the End of the World",93:"Judgments",94:"Wishes",95:"Accepting Reliable Reports",96:"Holding Fast to Qur'an and Sunnah",97:"Oneness of Allah (Tawheed)"
};
const BOOK_SECTION_NAMES = {
  bukhari: BUKHARI_BOOK_NAMES,
  muslim: {0:"Introduction",1:"The Book of Faith",2:"The Book of Purification",3:"The Book of Menstruation",4:"The Book of Prayers",5:"The Book of Mosques and Places of Prayer",6:"The Book of Prayer - Travellers",7:"The Book of Prayer - Friday",8:"The Book of Prayer - Two Eids",9:"The Book of Prayer - Rain",10:"The Book of Prayer - Eclipses",11:"The Book of Prayer - Funerals",12:"The Book of Zakat",13:"The Book of Fasting",14:"The Book of I'tikaf",15:"The Book of Pilgrimage",16:"The Book of Marriage",17:"The Book of Suckling",18:"The Book of Divorce",19:"The Book of Invoking Curses",20:"The Book of Emancipating Slaves",21:"The Book of Transactions",22:"The Book of Musaqah",23:"The Book of the Rules of Inheritance",24:"The Book of Gifts",25:"The Book of Wills",26:"The Book of Vows",27:"The Book of Oaths",28:"The Book of Oaths, Muharibin, Qasas (Retaliation), and Diyat (Blood Money)",29:"The Book of Legal Punishments",30:"The Book of Judicial Decisions",31:"The Book of Lost Property",32:"The Book of Jihad and Expeditions",33:"The Book on Government",34:"The Book of Hunting, Slaughter, and what may be Eaten",35:"The Book of Sacrifices",36:"The Book of Drinks",37:"The Book of Clothes and Adornment",38:"The Book of Manners and Etiquette",39:"The Book of Greetings",40:"The Book Concerning the Use of Correct Words",41:"The Book of Poetry",42:"The Book of Dreams",43:"The Book of Virtues",44:"The Book of the Merits of the Companions",45:"The Book of Virtue, Enjoining Good Manners, and Joining of the Ties of Kinship",46:"The Book of Destiny",47:"The Book of Knowledge",48:"The Book Pertaining to the Remembrance of Allah, Supplication, Repentance and Seeking Forgiveness",49:"The Book of Heart-Melting Traditions",50:"The Book of Repentance",51:"Characteristics of The Hypocrites And Rulings Concerning Them",52:"Characteristics of the Day of Judgment, Paradise, and Hell",53:"The Book of Paradise, its Description, its Bounties and its Inhabitants",54:"The Book of Tribulations and Portents of the Last Hour",55:"The Book of Zuhd and Softening of Hearts",56:"The Book of Commentary on the Qur'an"},
  abudawud: {1:"Purification (Kitab Al-Taharah)",2:"Prayer (Kitab Al-Salat)",3:"The Book Of The Prayer For Rain (Kitab al-Istisqa')",4:"Prayer (Kitab Al-Salat): Detailed Rules of Law about the Prayer during Journey",5:"Prayer (Kitab Al-Salat): Voluntary Prayers",6:"Prayer (Kitab Al-Salat): Detailed Injunctions about Ramadan",7:"Prayer (Kitab Al-Salat): Prostration while reciting the Qur'an",8:"Prayer (Kitab Al-Salat): Detailed Injunctions about Witr",9:"Zakat (Kitab Al-Zakat)",10:"The Book of Lost and Found Items",11:"The Rites of Hajj (Kitab Al-Manasik Wa'l-Hajj)",12:"Marriage (Kitab Al-Nikah)",13:"Divorce (Kitab Al-Talaq)",14:"Fasting (Kitab Al-Siyam)",15:"Jihad (Kitab Al-Jihad)",16:"Sacrifice (Kitab Al-Dahaya)",17:"Game (Kitab Al-Said)",18:"Wills (Kitab Al-Wasaya)",19:"Shares of Inheritance (Kitab Al-Fara'id)",20:"Tribute, Spoils, and Rulership (Kitab Al-Kharaj, Wal-Fai' Wal-Imarah)",21:"Funerals (Kitab Al-Jana'iz)",22:"Oaths and Vows (Kitab Al-Aiman Wa Al-Nudhur)",23:"Commercial Transactions (Kitab Al-Buyu)",24:"Wages (Kitab Al-Ijarah)",25:"The Office of the Judge (Kitab Al-Aqdiyah)",26:"Knowledge (Kitab Al-Ilm)",27:"Drinks (Kitab Al-Ashribah)",28:"Foods (Kitab Al-At'imah)",29:"Medicine (Kitab Al-Tibb)",30:"Divination and Omens (Kitab Al-Kahanah Wa Al-Tatayyur)",31:"The Book of Manumission of Slaves",32:"Dialects and Readings of the Qur'an (Kitab Al-Huruf Wa Al-Qira'at)",33:"Hot Baths (Kitab Al-Hammam)",34:"Clothing (Kitab Al-Libas)",35:"Combing the Hair (Kitab Al-Tarajjul)",36:"Signet-Rings (Kitab Al-Khatam)",37:"Trials and Fierce Battles (Kitab Al-Fitan Wa Al-Malahim)",38:"The Promised Deliverer (Kitab Al-Mahdi)",39:"Battles (Kitab Al-Malahim)",40:"Prescribed Punishments (Kitab Al-Hudud)",41:"Types of Blood-Wit (Kitab Al-Diyat)",42:"Model Behavior of the Prophet (Kitab Al-Sunnah)",43:"General Behavior (Kitab Al-Adab)"},
  nasai: {1:"The Book of Purification",2:"The Book of Water",3:"The Book of Menstruation and Istihadah",4:"The Book of Ghusl and Tayammum",5:"The Book of Salah",6:"The Book of the Times (of Prayer)",7:"The Book of the Adhan (The Call to Prayer)",8:"The Book of the Masjids",9:"The Book of the Qiblah",10:"The Book of Leading the Prayer (Al-Imamah)",11:"The Book of the Commencement of the Prayer",12:"The Book of The At-Tatbiq (Clasping One's Hands Together)",13:"The Book of Forgetfulness (In Prayer)",14:"The Book of Jumu'ah (Friday Prayer)",15:"The Book of Shortening the Prayer When Traveling",16:"The Book of Eclipses",17:"The Book of Praying for Rain (Al-Istisqa')",18:"The Book of the Fear Prayer",19:"The Book of the Prayer for the Two 'Eids",20:"The Book of Qiyam Al-Lail (The Night Prayer) and Voluntary Prayers During the Day",21:"The Book of Funerals",22:"The Book of Fasting",23:"The Book of Zakah",24:"The Book of Hajj",25:"The Book of Jihad",26:"The Book of Marriage",27:"The Book of Divorce",28:"The Book of Horses, Races and Shooting",29:"The Book of Endowments",30:"The Book of Wills",31:"The Book of Presents",32:"The Book of Gifts",33:"The Book of ar-Ruqba",34:"The Book of 'Umra",35:"The Book of Agriculture",36:"The Book of the Kind Treatment of Women",37:"The Book of Fighting [The Prohibition of Bloodshed]",38:"The Book of Distribution of Al-Fay'",39:"The Book of al-Bay'ah",40:"The Book of al-'Aqiqah",41:"The Book of al-Fara' and al-'Atirah",42:"The Book of Hunting and Slaughtering",43:"The Book of ad-Dahaya (Sacrifices)",44:"The Book of Financial Transactions",45:"The Book of Oaths (qasamah), Retaliation and Blood Money",46:"The Book of Cutting off the Hand of the Thief",47:"The Book Of Faith and its Signs",48:"The Book of Adornment",49:"The Book of the Etiquette of Judges",50:"The Book of Seeking Refuge with Allah",51:"The Book of Drinks"},
  tirmidhi: {1:"The Book on Purification",2:"The Book on Salat (Prayer)",3:"The Book on Al-Witr",4:"The Book on the Day of Friday",5:"The Book on the Two Eids",6:"The Book on Traveling",7:"The Book on Zakat",8:"The Book on Fasting",9:"The Book on Hajj",10:"The Book on Jana''iz (Funerals)",11:"The Book on Marriage",12:"The Book on Suckling",13:"The Book on Divorce and Li'an",14:"The Book on Business",15:"The Chapters On Judgements From The Messenger of Allah",16:"The Book on Blood Money",17:"The Book on Legal Punishments (Al-Hudud)",18:"The Book on Hunting",19:"The Book on Sacrifices",20:"The Book on Vows and Oaths",21:"The Book on Military Expeditions",22:"The Book on Virtues of Jihad",23:"The Book on Jihad",24:"The Book on Clothing",25:"The Book on Food",26:"The Book on Drinks",27:"Chapters on Righteousness And Maintaining Good Relations With Relatives",28:"Chapters on Medicine",29:"Chapters On Inheritance",30:"Chapters On Wasaya (Wills and Testament)",31:"Chapters On Wala' And Gifts",32:"Chapters On Al-Qadar",33:"Chapters On Al-Fitan",34:"Chapters On Dreams",35:"Chapters On Witnesses",36:"Chapters On Zuhd",37:"Chapters on the description of the Day of Judgement, Ar-Riqaq, and Al-Wara'",38:"Chapters on the description of Paradise",39:"The Book on the Description of Hellfire",40:"The Book on Faith",41:"Chapters on Knowledge",42:"Chapters on Seeking Permission",43:"Chapters on Manners",44:"Chapters on Parables",45:"Chapters on The Virtues of the Qur'an",46:"Chapters on Recitation",47:"Chapters on Tafsir",48:"Chapters on Supplication",49:"Chapters on Virtues"},
  ibnmajah: {0:"The Book of the Sunnah",1:"The Book of Purification and its Sunnah",2:"The Book of the Prayer",3:"The Book of the Adhan and the Sunnah Regarding It",4:"The Book On The Mosques And The Congregations",5:"Establishing the Prayer and the Sunnah Regarding Them",6:"Chapters Regarding Funerals",7:"Fasting",8:"The Chapters Regarding Zakat",9:"The Chapters on Marriage",10:"The Chapters on Divorce",11:"The Chapters on Expiation",12:"The Chapters on Business Transactions",13:"The Chapters on Rulings",14:"The Chapters on Gifts",15:"The Chapters on Charity",16:"The Chapters on Pawning",17:"The Chapters on Pre-emption",18:"The Chapters on Lost Property",19:"The Chapters on Manumission (of Slaves)",20:"The Chapters on Legal Punishments",21:"The Chapters on Blood Money",22:"The Chapters on Wills",23:"Chapters on Shares of Inheritance",24:"The Chapters on Jihad",25:"Chapters on Hajj Rituals",26:"Chapters on Sacrifices",27:"Chapters on Slaughtering",28:"Chapters on Hunting",29:"Chapters on Food",30:"Chapters on Drinks",31:"Chapters on Medicine",32:"Chapters on Dress",33:"Etiquette",34:"Supplication",35:"Interpretation of Dreams",36:"Tribulations",37:"Zuhd"},
  malik: {1:"The Times of Prayer",2:"Purity",3:"Prayer",4:"Forgetfulness in Prayer",5:"Jumu'a",6:"Prayer in Ramadan",7:"Tahajjud",8:"Prayer in Congregation",9:"Shortening the Prayer",10:"The Two 'Ids",11:"The Fear Prayer",12:"The Eclipse Prayer",13:"Asking for Rain",14:"The Qibla",15:"The Qur'an",16:"Burials",17:"Zakat",18:"Fasting",19:"I'tikaf in Ramadan",20:"Hajj",21:"Jihad",22:"Vows and Oaths",23:"Sacrificial Animals",24:"Slaughtering Animals",25:"Game",26:"The 'Aqiqa",27:"Fara'id",28:"Marriage",29:"Divorce",30:"Suckling",31:"Business Transactions",32:"Qirad",33:"Sharecropping",34:"Renting Land",35:"Pre-emption in Property",36:"Judgements",37:"Wills and Testaments",38:"Setting Free and Wala'",39:"The Mukatab",40:"The Mudabbar",41:"Hudud",42:"Drinks",43:"Blood-Money",44:"The Oath of Qasama",45:"Madina",46:"The Decree",47:"Good Character",48:"Dress",49:"The Description of the Prophet, may Allah Bless Him and Grant Him Peace",50:"The Evil Eye",51:"Hair",52:"Visions",53:"Greetings",54:"General Subjects",55:"The Oath of Allegiance",56:"Speech",57:"Jahannam",58:"Sadaqa",59:"Knowledge",60:"The Supplication of the Unjustly Wronged",61:"The Names of the Prophet, may Allah Bless Him and Grant Him Peace"},
};

// Musnad Ahmad's JSON files are 1,000-record transport chunks, not books.
// Its verified companion/group structure is carried in musnad-ahmad/index.json.
let musnadAhmadSections = [];
function musnadAhmadMeta(n){
  const sections = musnadAhmadSections;
  let low = 0, high = sections.length - 1, match = null;
  while (low <= high) {
    const mid = (low + high) >> 1;
    if (Number(sections[mid].from) <= Number(n)) { match = sections[mid]; low = mid + 1; }
    else high = mid - 1;
  }
  return match;
}
function musnadAhmadSection(n){
  return musnadAhmadMeta(n)?.sectionAr || "مسند أحمد";
}
function musnadAhmadReference(n){
  const meta = musnadAhmadMeta(n);
  if (!meta) return `مسند أحمد · ${n}`;
  const labels = [meta.groupAr, meta.sectionAr].filter(Boolean);
  if (labels.length === 2 && labels[0] === labels[1]) labels.shift();
  return `${labels.join(" · ")} · ${n}`;
}
function musnadPartSections(from, to){
  const firstMeta = musnadAhmadMeta(from);
  const lastMeta = musnadAhmadMeta(to);
  const first = firstMeta?.groupAr || firstMeta?.sectionAr || "مسند أحمد";
  const last = lastMeta?.groupAr || lastMeta?.sectionAr || "مسند أحمد";
  return first === last ? first : `${first} ← ${last}`;
}

function bookTitle(slug, book){
  if (slug === "darimi") return cache.bookIndex.darimi?.books.find(b => b.book === Number(book))?.title || "";
  if (book == null || book === "") return "";
  const map = BOOK_SECTION_NAMES[slug];
  if (!map) return "";
  return map[book] || map[String(book)] || "";
}
function bookLabel(slug, book){
  if (slug === "darimi") return bookTitle(slug, book);
  if (slug === "musnad-ahmad") return `Part ${book}`;
  const title = bookTitle(slug, book);
  return title ? `Book ${book} · ${title}` : `Book ${book}`;
}
// Bukhari recordings and their CTC forced-alignment maps live in public R2.
// A report remains readable without either asset while its alignment is pending.
const BUKHARI_R2 = "https://pub-4c1d62290e264660b4061d58417926be.r2.dev";
const bukhariTimingCache = {};
const bookTimingCache = {
  bukhari: bukhariTimingCache,
  abudawud: {},
  muslim: {},
  nasai: {},
  tirmidhi: {},
  ibnmajah: {},
  malik: {},
  riyad: {},
  "musnad-ahmad": {},
};
const syncedBookCollections = new Set(["bukhari", "abudawud", "muslim", "nasai", "tirmidhi", "ibnmajah", "malik", "riyad", "musnad-ahmad"]);
let bukhariIsnadPool;

async function getBukhariIsnadPool(){
  if (!bukhariIsnadPool) bukhariIsnadPool = jopt("bukhari-isnad-word-pool.json");
  return bukhariIsnadPool;
}

function normalizeArabicWord(text){
  return (text || "").replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06edـ]/g, "")
    .replace(/[^\u0621-\u063a\u0641-\u064a\u0671\u067e\u0686\u0698\u06a9\u06af\u06be\u06c0\u06cc]/g, "")
    .replace(/[أإآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه");
}

function alignOriginalGlosses(syncedTokens, originalTokens, gloss){
  const source = (originalTokens || [])
    .map((token, index) => ({ token, index, norm: normalizeArabicWord(token.text) }))
    .filter(item => item.norm);
  const target = (syncedTokens || [])
    .map((token, index) => ({ token, index, norm: normalizeArabicWord(token.text) }))
    .filter(item => item.norm);
  const rows = source.length + 1;
  const cols = target.length + 1;
  const score = Array.from({ length: rows }, () => new Uint16Array(cols));
  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      score[i][j] = source[i - 1].norm === target[j - 1].norm
        ? score[i - 1][j - 1] + 1
        : Math.max(score[i - 1][j], score[i][j - 1]);
    }
  }
  const mapped = {};
  const originalGlosses = gloss?.glosses || {};
  let i = source.length, j = target.length;
  while (i && j) {
    if (source[i - 1].norm === target[j - 1].norm) {
      const value = originalGlosses[source[i - 1].token.id];
      if (value) mapped[target[j - 1].token.id] = value;
      i--; j--;
    } else if (score[i - 1][j] >= score[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }
  return mapped;
}

function buildMeaningColumn(englishTranslation="", urduTranslation=""){
  const col = document.createElement("div"); col.className = "en-col meaning-col";
  const languages = document.createElement("div"); languages.className = "meaning-languages";
  const enSection = document.createElement("section"); enSection.className = "meaning-section";
  enSection.innerHTML = `<div class="col-label">English translation</div>`;
  const enDiv = document.createElement("div"); enDiv.className = "english";
  enDiv.lang = "en";
  enDiv.dir = "ltr";
  enDiv.textContent = englishTranslation || "Official English translation unavailable.";
  enSection.appendChild(enDiv);
  const urSection = document.createElement("section"); urSection.className = "meaning-section";
  urSection.innerHTML = `<div class="col-label" style="text-align:right">اردو ترجمہ</div>`;
  const urDiv = document.createElement("div"); urDiv.className = "urdu";
  urDiv.lang = "ur";
  urDiv.dir = "rtl";
  urDiv.textContent = urduTranslation || "سرکاری اردو ترجمہ دستیاب نہیں۔";
  urSection.appendChild(urDiv);
  languages.append(enSection, urSection); col.appendChild(languages);
  return col;
}

function honorificPartGloss(tokens, index){
  const forms = [
    {
      words:["صلي", "الله", "عليه", "وسلم"],
      glosses:[
        { en:"may Allah bless", transliteration:"ṣallā", pos:"V", features:{} },
        { en:"Allah", transliteration:"Allāh", pos:"PN", features:{} },
        { en:"upon him", transliteration:"ʿalayhi", pos:"P", features:{} },
        { en:"and grant him peace", transliteration:"wa-sallam", pos:"V", features:{} },
      ],
    },
    {
      words:["صلي", "الله", "عليه", "و", "سلم"],
      glosses:[
        { en:"may Allah bless", transliteration:"ṣallā", pos:"V", features:{} },
        { en:"Allah", transliteration:"Allāh", pos:"PN", features:{} },
        { en:"upon him", transliteration:"ʿalayhi", pos:"P", features:{} },
        { en:"and", transliteration:"wa", pos:"C", features:{} },
        { en:"grant him peace", transliteration:"sallam", pos:"V", features:{} },
      ],
    },
  ];
  for (const form of forms) {
    for (let start = Math.max(0, index - form.words.length + 1); start <= index; start++) {
      if (tokens.slice(start, start + form.words.length).map(t => normalizeArabicWord(t.text)).join(" ") === form.words.join(" ")) {
        return form.glosses[index - start];
      }
    }
  }
  return null;
  /* legacy source retained below for patch readability
  const words = ["صلي", "الله", "عليه", "وسلم"];
  const glosses = [
    { en:"may Allah bless", transliteration:"ṣallā", pos:"V", features:{} },
    { en:"Allah", transliteration:"Allāh", pos:"PN", features:{} },
    { en:"upon him", transliteration:"ʿalayhi", pos:"P", features:{} },
    { en:"and grant him peace", transliteration:"wa-sallam", pos:"V", features:{} },
  ];
  for (let start = Math.max(0, index - 3); start <= index; start++) {
    if (tokens.slice(start, start + 4).map(t => normalizeArabicWord(t.text)).join(" ") === words.join(" ")) {
      return glosses[index - start];
    }
  }
  return null; */
}

async function getBukhariTiming(n){
  if (!(n in bukhariTimingCache)) {
    const url = `${BUKHARI_R2}/bukhari-timings/n${String(n).padStart(4, "0")}.json`;
    bukhariTimingCache[n] = fetch(url)
      .then(r => r.ok ? r.json() : null)
      .then(data => Array.isArray(data?.tokens) && data.tokens.some(t => Number.isFinite(t.start) && Number.isFinite(t.end)) ? data : null)
      .catch(() => null)
      .then(data => {
        if (!data) delete bukhariTimingCache[n];
        return data;
      });
  }
  return bukhariTimingCache[n];
}

async function getBookTiming(slug, n){
  if (!syncedBookCollections.has(slug)) return null;
  if (slug === "musnad-ahmad") {
    const cache = bookTimingCache[slug];
    if (!(n in cache)) {
      const stem = `r${String(n).padStart(5, "0")}.json`;
      const local = location.hostname === "127.0.0.1" || location.hostname === "localhost";
      const url = local
        ? `../../musnad-ahmad-r2-staging-20260816-v1/timings/${stem}`
        : `https://cdn.hadith.to/musnad-ahmad-timings/${stem}`;
      cache[n] = fetch(url).then(r => r.ok ? r.json() : null).then(data =>
        Array.isArray(data?.tokens) && data.tokens.some(t => Number.isFinite(t.start) || Number.isFinite(t.displayStart)) ? data : null
      ).catch(() => null);
    }
    return cache[n];
  }
  const cache = bookTimingCache[slug];
  if (!(n in cache)) {
    if (slug === "muslim") {
      const localStem = `m${String(n).padStart(4, "0")}.json`;
      const remoteStem = `n${String(n).padStart(4, "0")}.json`;
      const local = location.hostname === "127.0.0.1" || location.hostname === "localhost";
      const urls = local
        ? [`../qc/muslim-full/timings/${localStem}`, `../qc/muslim-full/generated-timings/${localStem}`]
        : [`${BUKHARI_R2}/muslim-timings/${remoteStem}`];
      cache[n] = (async () => {
        for (const url of urls) {
          try {
            const response = await fetch(url);
            if (!response.ok) continue;
            const data = await response.json();
            if (Array.isArray(data?.tokens) && data.tokens.some(t => Number.isFinite(t.start) || Number.isFinite(t.displayStart))) {
              if (!data.audio && local) continue;
              return data;
            }
          } catch {}
        }
        return null;
      })();
    } else {
      const url = `${BUKHARI_R2}/${slug}-timings/n${String(n).padStart(4, "0")}.json`;
      cache[n] = fetch(url)
        .then(r => r.ok ? r.json() : null)
        .then(data => Array.isArray(data?.tokens) && data.tokens.some(t =>
          Number.isFinite(t.start) || Number.isFinite(t.displayStart)
        ) ? data : null)
        .catch(() => null)
        .then(data => {
          if (!data) delete cache[n];
          return data;
        });
    }
  }
  return cache[n];
}

function bookAudioUrl(slug, n, timing){
  if (slug === "darimi") return timing.audio;
  if (slug === "musnad-ahmad") {
    const file = timing?.audio || `r${String(n).padStart(5, "0")}.ogg`;
    const local = location.hostname === "127.0.0.1" || location.hostname === "localhost";
    return local
      ? `../../musnad-ahmad-r2-staging-20260816-v1/audio/${file}`
      : `https://cdn.hadith.to/musnad-ahmad/${file}`;
  }
  // Prefer sidecar audio filename (shared clips e.g. nasai 352/353 → 0352.mp3).
  const file = timing?.audio || `${String(n).padStart(4, "0")}.mp3`;
  if (slug !== "muslim") return `${BUKHARI_R2}/${slug}/${file}`;
  const local = location.hostname === "127.0.0.1" || location.hostname === "localhost";
  const generated = Boolean(timing?.synthetic);
  if (local) return generated
    ? `../qc/muslim-full/generated-clips/${file}`
    : `../qc/muslim-full/clips/${file}`;
  return `${BUKHARI_R2}/muslim/${file}`;
}

function effectiveTimingTokens(timing){
  return (timing?.tokens || []).map(token => ({
    ...token,
    start: Number.isFinite(token.displayStart) ? token.displayStart : token.start,
    end: Number.isFinite(token.displayEnd) ? token.displayEnd : token.end,
  }));
}

const store = {
  get:(k,d)=>{ try { return JSON.parse(localStorage.getItem("malti:"+k)) ?? d; } catch { return d; } },
  set:(k,v)=>{ try { localStorage.setItem("malti:"+k, JSON.stringify(v)); return true; } catch { return false; } },
};
const j = async (u) => (await fetch(u, { cache:"no-cache" })).json();
const jopt = async (u) => { try { return await j(u); } catch { return null; } };
const fmt = s => isNaN(s) ? "0:00" : `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,"0")}`;

/* ---------- settings ---------- */
/* Independent size axes — each control only writes its own CSS vars */
let enSz = store.get("ensz", 1.05);
let arSz = store.get("arsz", 2.1);
let urSz = store.get("ursz", 0.8);
let spSz = store.get("spsz", 18);
let arLine = store.get("arlh", 2.35);
let enLine = store.get("enlh", 1.75);
let urLine = store.get("urlh", 1.9);
let glossSz = store.get("glosssz", .85);
let wordPad = store.get("wordpad", 6);
let arFont = store.get("arfont", "scheherazade");
const AR_FONTS = {
  uthmani:'"KFGQPC Uthman Taha Naskh","Scheherazade New",Scheherazade,serif',
  scheherazade:'"Scheherazade New",Scheherazade,"Traditional Arabic",serif',
  amiri:'Amiri,"Times New Roman",serif',
  notoNaskh:'"Noto Naskh Arabic",serif',
  arefRuqaa:'"Aref Ruqaa",serif',
  reemKufi:'"Reem Kufi",sans-serif',
};
// migrate old "font" step if present once
(() => {
  const legacy = store.get("font", null);
  if (legacy != null && store.get("ensz", null) == null) {
    enSz = 1.15 + Number(legacy) * 0.08;
    store.set("ensz", enSz);
  }
})();
function applyFont(){
  const r = document.documentElement.style;
  r.setProperty("--en-size", enSz + "rem");
  r.setProperty("--en-gloss-size", glossSz + "rem");
  r.setProperty("--ar-size", arSz + "rem");
  r.setProperty("--ur-size", urSz + "rem");
  r.setProperty("--wbw-gap", spSz + "px");
  r.setProperty("--ar-lh", arLine);
  r.setProperty("--en-lh", enLine);
  r.setProperty("--ur-lh", urLine);
  r.setProperty("--word-pad", wordPad + "px");
  r.setProperty("--ar-font", AR_FONTS[arFont] || AR_FONTS.scheherazade);
  store.set("ensz", enSz); store.set("arsz", arSz); store.set("ursz", urSz); store.set("spsz", spSz);
  store.set("arlh", arLine); store.set("enlh", enLine); store.set("urlh", urLine); store.set("glosssz", glossSz); store.set("wordpad", wordPad); store.set("arfont", arFont);
  const controls = {
    arSize:[arSz, v => v + "rem"], arLine:[arLine, v => v.toFixed(2)], wordGap:[spSz, v => v + "px"],
    enSize:[enSz, v => v + "rem"], enLine:[enLine, v => v.toFixed(2)], urSize:[urSz, v => v + "rem"],
    urLine:[urLine, v => v.toFixed(2)], glossSize:[glossSz, v => v + "rem"], wordPad:[wordPad, v => v + "px"],
  };
  Object.entries(controls).forEach(([id, [value, label]]) => {
    const input = document.getElementById(id), output = document.getElementById(id + "Out");
    if (input) input.value = value;
    if (output) output.textContent = label(Number(value));
  });
  document.getElementById("arFont").value = arFont;
}
["arSize","arLine","wordGap","enSize","enLine","urSize","urLine","glossSize","wordPad"].forEach(id => document.getElementById(id).oninput = e => {
  const value = Number(e.target.value);
  if (id === "arSize") arSz = value;
  if (id === "arLine") arLine = value;
  if (id === "wordGap") spSz = value;
  if (id === "enSize") enSz = value;
  if (id === "enLine") enLine = value;
  if (id === "urSize") urSz = value;
  if (id === "urLine") urLine = value;
  if (id === "glossSize") glossSz = value;
  if (id === "wordPad") wordPad = value;
  applyFont();
});
document.getElementById("arFont").onchange = e => { arFont = e.target.value; applyFont(); };
document.getElementById("settingsReset").onclick = () => {
  enSz = 1.05; arSz = 2.1; urSz = .8; spSz = 18; arLine = 2.35; enLine = 1.75; urLine = 1.9; glossSz = .85; wordPad = 6; arFont = "scheherazade"; applyFont();
};
function applyTheme(t){
  document.documentElement.dataset.theme = t; store.set("theme", t);
  document.querySelectorAll(".theme [data-t]").forEach(b => {
    b.classList.toggle("on", b.dataset.t === t);
    b.setAttribute("aria-pressed", String(b.dataset.t === t));
  });
}
document.querySelectorAll(".theme [data-t]").forEach(b => b.onclick = () => applyTheme(b.dataset.t));
const gearBtn = document.getElementById("gear");
const settingsEl = document.getElementById("settings");
function setSettingsOpen(open){
  settingsEl.classList.toggle("open", open);
  gearBtn.classList.toggle("on", open);
  gearBtn.setAttribute("aria-expanded", open ? "true" : "false");
}
gearBtn.onclick = (e) => { e.stopPropagation(); setSettingsOpen(!settingsEl.classList.contains("open")); };
document.addEventListener("click", (e) => {
  if (!settingsEl.classList.contains("open")) return;
  if (settingsEl.contains(e.target) || gearBtn.contains(e.target)) return;
  setSettingsOpen(false);
});

const readerMoreBtn = document.getElementById("readerMoreBtn");
const readerToolsPanel = document.getElementById("readerToolsPanel");
function setReaderToolsOpen(open){
  readerToolsPanel.classList.toggle("open", open);
  readerMoreBtn.setAttribute("aria-expanded", open ? "true" : "false");
}
readerMoreBtn.onclick = (e) => {
  e.stopPropagation();
  if (settingsEl.classList.contains("open")) {
    setSettingsOpen(false);
    return;
  }
  setReaderToolsOpen(!readerToolsPanel.classList.contains("open"));
};
document.getElementById("rtWbw").onclick = () => {
  if (typeof readingMode !== "undefined" && readingMode === "receive") setReadingMode("study", true);
  document.getElementById("wbwBtn").click();
  syncReaderToolsUI();
};
document.getElementById("rtParallel").onclick = () => {
  if (typeof readingMode !== "undefined" && readingMode === "receive") setReadingMode("study", true);
  document.getElementById("parallelBtn").click();
  syncReaderToolsUI();
};
document.getElementById("rtAppearance").onclick = (e) => {
  e.stopPropagation();
  setReaderToolsOpen(false);
  setSettingsOpen(true);
};
function syncReaderToolsUI(){
  const wbwSub = { off:"Off", en:"English", ur:"Urdu", both:"EN + Urdu" };
  document.getElementById("rtWbw").classList.toggle("on", wbw !== "off");
  document.getElementById("rtWbwSub").textContent = wbwSub[wbw] || "Off";
  document.getElementById("rtParallel").classList.toggle("on", !single);
  document.getElementById("rtParallelSub").textContent = single ? "Hidden" : "Shown";
}
document.addEventListener("click", (e) => {
  if (readerToolsPanel.classList.contains("open") &&
      !readerToolsPanel.contains(e.target) && e.target !== readerMoreBtn) {
    setReaderToolsOpen(false);
  }
});

const dockMoreBtn = document.getElementById("dockMoreBtn");
const dockMorePanel = document.getElementById("dockMorePanel");
if (dockMoreBtn && dockMorePanel) {
  dockMoreBtn.onclick = (e) => {
    e.stopPropagation();
    if (settingsEl.classList.contains("open")) {
      setSettingsOpen(false);
      return;
    }
    const open = dockMorePanel.classList.toggle("open");
    dockMoreBtn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  document.addEventListener("click", (e) => {
    if (!dockMorePanel.classList.contains("open")) return;
    if (!dockMorePanel.contains(e.target) && e.target !== dockMoreBtn) {
      dockMorePanel.classList.remove("open");
      dockMoreBtn.setAttribute("aria-expanded", "false");
    }
  });
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  setSettingsOpen(false);
  setReaderToolsOpen(false);
  if (dockMorePanel) {
    dockMorePanel.classList.remove("open");
    dockMoreBtn.setAttribute("aria-expanded", "false");
  }
});

let single = store.get("single", false);
function applyParallel(){
  document.querySelectorAll(".parallel").forEach(p => p.classList.toggle("single", single));
  document.getElementById("parallelBtn").classList.toggle("on", !single);
  store.set("single", single);
  syncReaderToolsUI();
}
document.getElementById("parallelBtn").onclick = () => { single = !single; applyParallel(); };

const WBW = ["off","en","ur","both"];
const WBWLBL = { off:"Gloss", en:"EN", ur:"اردو", both:"EN·اردو" };
let wbw = "off";
let glossMode = "audio"; // "audio" | "study" — tied to readingMode
function wbwStoreKey(){ return glossMode === "study" ? "wbwStudy" : "wbwAudio"; }
function wbwDefault(){ return glossMode === "study" ? "en" : "off"; }
function applyWbw(persist=true){
  document.body.dataset.wbw = wbw;
  const b = document.getElementById("wbwBtn");
  b.textContent = WBWLBL[wbw];
  b.classList.toggle("on", wbw !== "off");
  if (persist) store.set(wbwStoreKey(), wbw);
  syncReaderToolsUI();
}
function setGlossMode(mode){
  glossMode = mode;
  wbw = store.get(wbwStoreKey(), wbwDefault());
  applyWbw(false);
}
document.getElementById("wbwBtn").onclick = () => {
  if (readingMode === "receive") setReadingMode("study", true);
  wbw = WBW[(WBW.indexOf(wbw)+1) % WBW.length];
  applyWbw(true);
};

/* Receive (default) ↔ Study — persist optional preference */
let readingMode = store.get("readingMode", "receive"); // "receive" | "study"
function applyReadingMode(persist=true){
  document.body.dataset.mode = readingMode;
  setGlossMode(readingMode === "study" ? "study" : "audio");
  const btn = document.getElementById("readingModeBtn");
  if (btn) {
    const isStudy = readingMode === "study";
    btn.textContent = isStudy ? "Reading" : "Study";
    btn.setAttribute("aria-pressed", isStudy ? "true" : "false");
    btn.title = isStudy ? "Return to listening mode" : "Show word gloss and translation";
  }
  if (persist) store.set("readingMode", readingMode);
  syncReaderToolsUI();
}
function setReadingMode(mode, persist=true){
  readingMode = mode === "study" ? "study" : "receive";
  applyReadingMode(persist);
}
document.getElementById("readingModeBtn").onclick = () => {
  setReadingMode(readingMode === "receive" ? "study" : "receive", true);
};

applyFont(); applyTheme(store.get("theme","light")); applyParallel();
applyReadingMode(false);
syncReaderToolsUI();

function shortCollectionName(col){
  return ({
    nawawi40: "Nawawi",
    qudsi40: "Qudsi",
    shahwaliullah40: "Shah Waliullah",
    malik: "Muwatta",
    bukhari: "Bukhari",
    muslim: "Muslim",
    abudawud: "Abu Dawud",
    tirmidhi: "Tirmidhi",
    nasai: "Nasa'i",
    ibnmajah: "Ibn Majah",
  })[col.slug] || col.en;
}
function rememberProgress(slug, n, book){
  store.set("resume", { slug, n, book: book || null, at: Date.now() });
}
function renderResume(){
  const box = document.getElementById("resume");
  const r = store.get("resume", null);
  if (!r || !bySlug[r.slug]) { box.style.display = "none"; box.innerHTML = ""; return; }
  const col = bySlug[r.slug];
  const label = r.slug === "musnad-ahmad"
    ? `${shortCollectionName(col)} · ${musnadAhmadSection(r.n)} · ${r.n}`
    : col.books && r.book
    ? `${shortCollectionName(col)} · ${bookLabel(col.slug, r.book)} · ${r.n}`
    : `${shortCollectionName(col)} · ${r.n}`;
  box.style.display = "block";
  box.innerHTML = `<a href="#${r.slug}:${htmlText(r.n)}"><div><div class="kicker">Continue reading</div><div class="title">${htmlText(label)}</div></div><div class="go">Resume →</div></a>`;
}

/* ---------- landing ---------- */
const cards = document.getElementById("cards");
for (const c of COLLECTIONS) {
  const a = document.createElement("a");
  a.href = `#${c.slug}:${c.managed ? window.hadithManagedNumbers(c.slug)[0] : 1}`;
  a.dataset.collection = c.slug;
  a.innerHTML = `
    <div>
      <div class="en">${c.en}</div>
      <div class="meta">${c.count.toLocaleString()} hadith · ${shelfAudioMeta(c)}</div>
    </div>
    <div class="side">
      <div class="ar" lang="ar" dir="rtl">${c.ar}</div>
    </div>`;
  cards.appendChild(a);
}
renderResume();
document.getElementById("home").onclick = () => { location.hash = ""; };

/* ---------- audio engine (one sticky player) ---------- */
const audio = new Audio(); audio.preload = "auto";
let activeSpans = [];
let activeIdx = -1;
let currentTokens = [];
const audioBlobUrls = new Map(); // remote path → object URL (reliable seeking)
let audioLogicalUrl = null;
let navEpoch = 0;
let currentNavToken = 0;
let audioSessionToken = 0;
let playRequestToken = 0;
const AUDIO_BLOB_CACHE_LIMIT = 8;
const playBtn = document.getElementById("playBtn");
const fill = document.getElementById("fill");
const timeEl = document.getElementById("timeEl");
const track = document.getElementById("track");
const dock = document.getElementById("dock");

function beginNavigation(){
  currentNavToken = ++navEpoch;
  audioSessionToken = currentNavToken;
  return currentNavToken;
}
function isCurrentNavigation(token){
  return token === currentNavToken;
}
function isTimedToken(token){
  return Number.isFinite(token?.start) && Number.isFinite(token?.end);
}
function refreshTrackA11y(){
  const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
  const current = Number.isFinite(audio.currentTime) && audio.currentTime >= 0 ? audio.currentTime : 0;
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", String(Math.max(duration, 0)));
  track.setAttribute("aria-valuenow", String(current));
  track.setAttribute("aria-valuetext", `${fmt(current)} / ${fmt(duration)}`);
}
function syncPlaybackStatus(){
  if (audioSessionToken !== currentNavToken) return;
  if (audio.duration) {
    fill.style.width = (Math.max(0, audio.currentTime) / audio.duration * 100) + "%";
    timeEl.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
  }
  refreshTrackA11y();
}
function clampTime(next){
  if (!Number.isFinite(next) || next < 0) return 0;
  if (Number.isFinite(audio.duration) && audio.duration > 0) return Math.min(audio.duration, next);
  return next;
}
function seekAudio(next){
  if (!audio.src) return;
  if (wordEnd !== null) {
    clearWordPlayback();
    armAudioEndedListener();
  }
  const time = clampTime(next);
  audio.currentTime = time;
  syncWordHighlight(time);
  refreshTrackA11y();
}
function cacheAudioBlobUrl(url, objectUrl){
  if (audioBlobUrls.has(url)) audioBlobUrls.delete(url);
  audioBlobUrls.set(url, objectUrl);
  while (audioBlobUrls.size > AUDIO_BLOB_CACHE_LIMIT) {
    const oldest = Array.from(audioBlobUrls.keys()).find(key => key !== audioLogicalUrl);
    if (oldest == null) break;
    const oldObjectUrl = audioBlobUrls.get(oldest);
    if (oldObjectUrl) {
      try { URL.revokeObjectURL(oldObjectUrl); } catch {}
    }
    audioBlobUrls.delete(oldest);
  }
}
function revokeAudioBlobUrl(url){
  const objectUrl = audioBlobUrls.get(url);
  if (!objectUrl) return;
  try { URL.revokeObjectURL(objectUrl); } catch {}
  audioBlobUrls.delete(url);
}

function setPlayingUI(playing){
  document.body.dataset.playing = playing ? "1" : "0";
  playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
  playBtn.innerHTML = playing
    ? `<svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/></svg>`
    : `<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>`;
}
playBtn.onclick = () => {
  ++playRequestToken;
  clearWordPlayback();
  armAudioEndedListener();
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
};
document.getElementById("skipBack").onclick = () => {
  if (!audio.src) return;
  seekAudio((audio.currentTime || 0) - 10);
};
document.getElementById("skipFwd").onclick = () => {
  if (!audio.src) return;
  seekAudio((audio.currentTime || 0) + 10);
};
/* Listen modes: independent toggles. If both on, Repeat one wins over Autoplay next. */
function listenFlag(key, fallback){
  const v = store.get(key, fallback);
  return typeof v === "boolean" ? v : fallback;
}
let autoplayNext = listenFlag("autoplay", true);
let repeatOne = listenFlag("repeat", false);
let wordOnly = listenFlag("wordOnly", false);
let wordEnd = null;
let wordPlaybackTimer;
let continuePlayAfterLoad = false;
let ignoreAudioEnded = false;
let endSilenceTimer = null;
const AUTOPLAY_GAP_MS = 1600; // ~1.5–2s stillness before next
const autoplayBtn = document.getElementById("autoplayBtn");
const repeatBtn = document.getElementById("repeatBtn");
const wordOnlyBtn = document.getElementById("wordOnlyBtn");
function clearWordPlayback(){
  clearInterval(wordPlaybackTimer);
  wordEnd = null;
}
function stopAtWordEnd(){
  if (wordEnd === null || audio.seeking || audio.currentTime < wordEnd) return;
  const end = wordEnd;
  clearWordPlayback();
  audio.pause();
  audio.currentTime = end;
  syncPlaybackStatus();
}
function clearEndSilence(){
  clearTimeout(endSilenceTimer);
  endSilenceTimer = null;
  delete document.body.dataset.silence;
}
function beginEndSilence(){
  clearEndSilence();
  document.body.dataset.silence = "1";
}
function finishEndSilence(){
  document.body.dataset.silence = "ready";
}
function syncListenModesUI(){
  if (!autoplayBtn || !repeatBtn) return;
  autoplayBtn.classList.toggle("on", autoplayNext);
  autoplayBtn.setAttribute("aria-pressed", autoplayNext ? "true" : "false");
  repeatBtn.classList.toggle("on", repeatOne);
  repeatBtn.setAttribute("aria-pressed", repeatOne ? "true" : "false");
  wordOnlyBtn.classList.toggle("on", wordOnly);
  wordOnlyBtn.setAttribute("aria-pressed", String(wordOnly));
}
syncListenModesUI();
if (autoplayBtn) autoplayBtn.onclick = () => {
  // Toggle only Autoplay — never touches Repeat / malti:repeat
  autoplayNext = !autoplayNext;
  store.set("autoplay", autoplayNext);
  syncListenModesUI();
};
if (repeatBtn) repeatBtn.onclick = () => {
  // Toggle only Repeat — never touches Autoplay / malti:autoplay
  repeatOne = !repeatOne;
  store.set("repeat", repeatOne);
  syncListenModesUI();
};
wordOnlyBtn.onclick = () => {
  wordOnly = !wordOnly;
  store.set("wordOnly", wordOnly);
  syncListenModesUI();
};

audio.addEventListener("play", () => {
  clearEndSilence();
  setPlayingUI(true);
});
audio.addEventListener("pause", () => {
  if (!audio.paused) return;
  clearWordPlayback();
  setPlayingUI(false);
});
audio.addEventListener("ended", () => {
  setPlayingUI(false);
  // Ignore emptied/reload/`src` reassignment ends — those were replaying as "Repeat"
  if (ignoreAudioEnded) return;
  if (audioSessionToken !== currentNavToken) return;
  // Precedence: explicit Repeat one loops; else Autoplay advances to a different hadith
  if (repeatOne === true) {
    ignoreAudioEnded = true;
    audio.currentTime = 0;
    syncWordHighlight(0);
    fill.style.width = "0%";
    const p = audio.play();
    Promise.resolve(p).catch(() => {}).finally(() => { ignoreAudioEnded = false; });
    return;
  }
  const endedSlug = state.slug;
  const endedN = state.n;
  const next = state.nav?.next ?? null;
  const nextDistinct = next != null && String(next) !== String(endedN);
  const alreadyAtNext = nextDistinct && location.hash === `#${endedSlug}:${next}`;
  const canAdvance = Boolean(
    endedSlug && bySlug[endedSlug]?.audio && nextDistinct && !alreadyAtNext
  );
  // Hold stillness on current hadith; no snappy UI change during the gap
  beginEndSilence();
  endSilenceTimer = setTimeout(() => {
    endSilenceTimer = null;
    // Drop stale timers if the reader already moved on
    if (state.slug !== endedSlug || String(state.n) !== String(endedN)) {
      finishEndSilence();
      return;
    }
    if (autoplayNext === true && canAdvance) {
      continuePlayAfterLoad = true;
      setHash(endedSlug, next);
      return;
    }
    finishEndSilence();
  }, AUTOPLAY_GAP_MS);
});
audio.addEventListener("loadedmetadata", () => {
  if (audioSessionToken !== currentNavToken) return;
  syncPlaybackStatus();
});
track.addEventListener("click", (e) => {
  const r = track.getBoundingClientRect();
  if (audio.duration) seekAudio((e.clientX - r.left) / r.width * audio.duration);
});
track.addEventListener("pointerdown", (e) => {
  if (!audio.src) return;
  const move = (evt) => {
    const r = track.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (evt.clientX - r.left) / r.width));
    seekAudio(ratio * (Number.isFinite(audio.duration) ? audio.duration : 0));
  };
  const up = (evt) => {
    track.releasePointerCapture?.(e.pointerId);
    track.removeEventListener("pointermove", move);
    track.removeEventListener("pointerup", up);
    track.removeEventListener("pointercancel", up);
    move(evt);
  };
  track.setPointerCapture?.(e.pointerId);
  track.addEventListener("pointermove", move);
  track.addEventListener("pointerup", up, { once:true });
  track.addEventListener("pointercancel", up, { once:true });
  move(e);
});
track.addEventListener("keydown", (e) => {
  if (!audio.src) return;
  const step = e.shiftKey ? 15 : 5;
  let next = audio.currentTime || 0;
  if (e.key === "ArrowLeft" || e.key === "ArrowDown" || e.key === "PageDown") next -= step;
  else if (e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "PageUp") next += step;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = Number.isFinite(audio.duration) ? audio.duration : next;
  else return;
  e.preventDefault();
  seekAudio(next);
});
document.querySelectorAll("#rates button").forEach(b => {
  b.onclick = () => {
    audio.playbackRate = Number(b.dataset.r);
    document.querySelectorAll("#rates button").forEach(x => x.classList.toggle("on", x === b));
  };
});
function syncWordHighlight(t = audio.currentTime){
  if (!currentTokens.length) return;
  let idx = -1;
  for (let i = 0; i < currentTokens.length; i++) {
    const token = currentTokens[i];
    if (!isTimedToken(token)) continue;
    if (t >= token.start) idx = i; else break;
  }
  activeIdx = idx;
  activeSpans.forEach((s, i) => {
    const token = currentTokens[i];
    s.classList.toggle("active", i === idx && isTimedToken(token) && t <= token.end + 0.15);
  });
  if (idx >= 0 && !audio.paused && activeSpans[idx]) {
    const r = activeSpans[idx].getBoundingClientRect();
    if (r.top < 140 || r.bottom > innerHeight - 120) activeSpans[idx].scrollIntoView({ block:"center", behavior:"smooth" });
  }
}
audio.addEventListener("timeupdate", () => {
  if (audioSessionToken !== currentNavToken) return;
  stopAtWordEnd();
  const t = audio.currentTime;
  syncPlaybackStatus();
  if (activeIdx >= 0 && currentTokens[activeIdx] &&
      isTimedToken(currentTokens[activeIdx]) &&
      t >= currentTokens[activeIdx].start &&
      t <= currentTokens[activeIdx].end + 0.15) return;
  syncWordHighlight(t);
});

/** Blob-backed src so word seeks work even when the host lacks Accept-Ranges (e.g. python -m http.server). */
async function prepareAudio(url, navToken = currentNavToken, direct = false){
  // Stay deaf to `ended` until the caller finishes seek/play setup.
  // Cached blob reassignment can restore an old end position and re-fire `ended`,
  // which Autoplay was treating as a finished track (looked like Repeat).
  ignoreAudioEnded = true;
  if (audioLogicalUrl === url && audio.src) {
    try { audio.currentTime = 0; } catch {}
    if (isCurrentNavigation(navToken)) syncPlaybackStatus();
    return;
  }
  audio.pause();
  const stream = direct ? url : window.hadithCmsStream?.(url);
  let obj = stream || audioBlobUrls.get(url);
  if (!obj) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`audio ${res.status}`);
    obj = URL.createObjectURL(await res.blob());
    cacheAudioBlobUrl(url, obj);
  } else if (!stream) {
    cacheAudioBlobUrl(url, obj);
  }
  if (!isCurrentNavigation(navToken)) return;
  audioLogicalUrl = url;
  audio.src = obj;
  try { audio.currentTime = 0; } catch {}
  if (audio.readyState >= 1) {
    if (isCurrentNavigation(navToken)) syncPlaybackStatus();
    return;
  }
  await new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timeout);
      audio.removeEventListener("loadedmetadata",onLoad);
      audio.removeEventListener("error",onError);
    };
    const onLoad = () => {
      cleanup();
      if (!isCurrentNavigation(navToken)) { resolve(); return; }
      try { audio.currentTime = 0; } catch {}
      resolve();
    };
    const onError = () => {
      cleanup();
      if (!isCurrentNavigation(navToken)) { resolve(); return; }
      reject(new Error("audio load failed"));
    };
    const timeout = setTimeout(onError,15000);
    audio.addEventListener("loadedmetadata", onLoad, { once:true });
    audio.addEventListener("error", onError, { once:true });
  });
}
function armAudioEndedListener(navToken = currentNavToken){
  if (isCurrentNavigation(navToken)) ignoreAudioEnded = false;
}
function playFrom(time, end){
  if (wordOnly && (!Number.isFinite(end) || end <= time)) return;
  clearWordPlayback();
  const requestToken = ++playRequestToken;
  const navToken = currentNavToken;
  const start = () => {
    if (requestToken !== playRequestToken || navToken !== currentNavToken) return;
    if (wordOnly && (!Number.isFinite(end) || end <= time)) return;
    if (wordOnly) {
      ignoreAudioEnded = true;
      wordEnd = clampTime(end);
      wordPlaybackTimer = setInterval(stopAtWordEnd, 20);
    } else {
      armAudioEndedListener(navToken);
    }
    audio.currentTime = time;
    syncWordHighlight(time);
    audio.play().catch(() => {
      if (requestToken === playRequestToken) clearWordPlayback();
    });
  };
  if (audio.readyState >= 1) start();
  else audio.addEventListener("loadedmetadata", start, { once:true });
}
function stopAudio(){
  clearWordPlayback();
  clearEndSilence();
  ignoreAudioEnded = true;
  audio.pause();
  try { audio.removeAttribute("src"); audio.load(); } catch {}
  audioLogicalUrl = null;
  fill.style.width = "0%";
  timeEl.textContent = "0:00 / 0:00";
  refreshTrackA11y();
  setPlayingUI(false);
  activeSpans = []; currentTokens = []; activeIdx = -1;
}

/* ---------- caches ---------- */
const cache = { trans:{}, sun:{}, bookIndex:{}, bookOf:{}, officialTranslation:{} };

async function ensureOfficialTranslations(slug, n){
  const key = `${slug}:${n}`;
  if (slug === "riyad") {
    if (!cache.officialTranslation.riyad) cache.officialTranslation.riyad = j("translation/riyad.json");
    const local = await cache.officialTranslation.riyad;
    const row = local.translations.find(item => Number(item.n) === Number(n));
    return { en:row?.en || "", ur:row?.ur || "" };
  }
  if (slug === "musnad-ahmad") {
    if (!cache.officialTranslation[slug]) cache.officialTranslation[slug] = jopt("translation/musnad-ahmad.json");
    const local = await cache.officialTranslation[slug];
    const row = local?.translations?.find(item => Number(item.n) === Number(n));
    return { en:row?.en || "", ur:row?.ur || "" };
  }
  if (!cache.officialTranslation[key]) {
    const edition = language => `https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/${language}-${slug}/${n}.json`;
    cache.officialTranslation[key] = Promise.all([
      jopt(edition("eng")),
      jopt(edition("urd")),
    ]).then(([en, ur]) => ({
      en: en?.hadiths?.find(h => Number(h.hadithnumber) === Number(n))?.text || "",
      ur: ur?.hadiths?.find(h => Number(h.hadithnumber) === Number(n))?.text || "",
    }));
  }
  return cache.officialTranslation[key];
}

async function ensureFortySidecars(slug){
  if (!cache.trans[slug]) cache.trans[slug] = await j(`translation/${slug}.json`);
  if (!cache.sun[slug]) cache.sun[slug] = await j(`sunnah/${slug}.json`);
  return { trans: cache.trans[slug], sun: cache.sun[slug] };
}
async function ensureBookIndex(slug){
  if (!cache.bookIndex[slug]) cache.bookIndex[slug] = await j(`${slug}/index.json`);
  if (slug === "musnad-ahmad") musnadAhmadSections = cache.bookIndex[slug].sections || [];
  return cache.bookIndex[slug];
}
async function ensureBookOf(slug, bk){
  if (!cache.bookOf[slug]) cache.bookOf[slug] = {};
  if (!cache.bookOf[slug][bk]) cache.bookOf[slug][bk] = await j(`${slug}/book-${bk}.json`);
  return cache.bookOf[slug][bk];
}
function bookForReport(idx, n){
  const bk = idx.reportBook && idx.reportBook[n];
  if (bk != null) return idx.books.find(b => b.book === bk) || null;
  // n not found exactly (gap in numbering, or bad deep link): approximate
  // by nearest book range. Only a fallback -- ranges are not authoritative
  // when book numbering interleaves (see build-book-index.mjs).
  const base = parseInt(n, 10);
  return idx.books.find(b => base >= b.from && base <= b.to) || null;
}
function reportsInBook(bookData){
  return bookData.hadith.map(h => h.n);
}
function neighborReport(list, n, dir){
  const i = list.indexOf(n);
  if (i < 0) return null;
  return list[i + dir] ?? null;
}

/* ---------- state ---------- */
let state = { slug:null, n:null, book:null, seq:[], nav:{ prev:null, next:null } };

function setHash(slug, n){
  const next = `#${slug}:${n}`;
  if (location.hash !== next) location.hash = next;
  else route();
}

function fillCollectionJump(){
  const sel = document.getElementById("collJump");
  sel.innerHTML = COLLECTIONS.map(c => `<option value="${c.slug}">${c.en}</option>`).join("");
  sel.value = state.slug;
  sel.onchange = () => {
    const col = bySlug[sel.value];
    if (col.books) setHash(col.slug, 1);
    else setHash(col.slug, 1);
  };
}

async function fillBookJump(navToken = currentNavToken){
  const sel = document.getElementById("bookJump");
  const col = bySlug[state.slug];
  if (!col.books) { sel.classList.add("hidden"); return true; }
  const idx = await ensureBookIndex(col.slug);
  if (!isCurrentNavigation(navToken)) return false;
  sel.classList.remove("hidden");
  sel.innerHTML = idx.books.map(b => {
    if (col.slug === "musnad-ahmad") {
      return `<option value="${htmlText(b.book)}">Part ${htmlText(b.book)} · ${htmlText(musnadPartSections(b.from, b.to))} · ${htmlText(b.count)}</option>`;
    }
    if (col.slug === "darimi") {
      const option = new Option([b.section === b.title ? "" : b.section, b.title, b.count].filter(Boolean).join(" · "), b.book);
      option.setAttribute("value", b.book);
      return option.outerHTML;
    }
    const title = b.title || bookTitle(col.slug, b.book);
    return `<option value="${htmlText(b.book)}">Book ${htmlText(b.book)}${title ? ` · ${htmlText(title)}` : ""} · ${htmlText(b.count)}</option>`;
  }).join("");
  sel.value = String(state.book);
  sel.onchange = async () => {
    const bk = Number(sel.value);
    const data = await ensureBookOf(col.slug, bk);
    const first = data.hadith[0]?.n || 1;
    setHash(col.slug, first);
  };
  return true;
}

function fillHadithJump(){
  const sel = document.getElementById("hadithJump");
  sel.innerHTML = state.seq.map(n => `<option value="${htmlText(n)}">Hadith ${htmlText(n)}</option>`).join("");
  sel.value = String(state.n);
  sel.onchange = () => setHash(state.slug, bySlug[state.slug].books || bySlug[state.slug].managed || /[a-z]$/.test(sel.value) ? sel.value : Number(sel.value));
}

function updateLocSummary(){
  const col = bySlug[state.slug];
  if (!col) return;
  const short = shortCollectionName(col);
  const bookBit = col.slug === "musnad-ahmad"
    ? ` · ${musnadAhmadSection(state.n)}`
    : col.books && state.book
    ? ` · ${bookTitle(col.slug, state.book) || `Bk ${state.book}`}`
    : "";
  const el = document.getElementById("locSummary");
  el.textContent = `${short}${bookBit} · ${state.n} ▾`;
  el.setAttribute("aria-expanded", document.getElementById("locator").classList.contains("expanded") ? "true" : "false");
}

function setLocatorExpanded(open){
  const loc = document.getElementById("locator");
  loc.classList.toggle("expanded", open);
  loc.classList.toggle("compact", !open);
  updateLocSummary();
}
document.getElementById("locSummary").onclick = () => {
  const loc = document.getElementById("locator");
  setLocatorExpanded(!loc.classList.contains("expanded"));
};

function updateNavEdges(){
  const prev = state.nav?.prev ?? null;
  const next = state.nav?.next ?? null;
  document.getElementById("prevBtn").disabled = prev == null;
  document.getElementById("nextBtn").disabled = next == null;
  updateLocSummary();
}
document.getElementById("prevBtn").onclick = () => {
  const n = state.nav?.prev ?? null;
  if (n != null) setHash(state.slug, n);
};
document.getElementById("nextBtn").onclick = () => {
  if (document.body.dataset.silence === "1") return;
  const n = state.nav?.next ?? null;
  if (n != null) setHash(state.slug, n);
};
addEventListener("keydown", e => {
  if (document.getElementById("reader").classList.contains("hidden")) return;
  if (e.defaultPrevented || e.target.closest("input,textarea,select,button,a,[role=slider],[role=button],[contenteditable=true],dialog")) return;
  if (settingsEl.classList.contains("open") || readerToolsPanel.classList.contains("open") || dockMorePanel.classList.contains("open")) return;
  if (document.body.dataset.silence === "1" && e.key === "ArrowRight") return;
  if (e.key === "ArrowLeft") document.getElementById("prevBtn").click();
  if (e.key === "ArrowRight") document.getElementById("nextBtn").click();
  if (e.key === " " && !document.getElementById("dock").classList.contains("hidden")) {
    e.preventDefault(); playBtn.click();
  }
});

function renderRefs(rb, entry, en){
  const row = (label, ref, url, conf) => {
    const div = document.createElement("div");
    div.className = "refrow" + (conf === "low" ? " low" : "");
    div.innerHTML = `<span class="lbl">${label}</span>`;
    let reference;
    try { reference = new URL(url); } catch { return; }
    if (reference.protocol !== "https:" && reference.protocol !== "http:") return;
    const a = document.createElement("a"); a.href = reference.href; a.target = "_blank"; a.rel = "noopener"; a.textContent = ref;
    div.appendChild(a);
    if (conf) { const b = document.createElement("span"); b.className = "badge"; b.textContent = conf; div.appendChild(b); }
    rb.appendChild(div);
  };
  if (entry) {
    row("Reference", entry.sunnah.reference, entry.sunnah.url, null);
    if (en && en.takhrij && en.takhrij.length) {
      const t = document.createElement("div"); t.className = "refrow";
      t.innerHTML = `<span class="lbl">Grade</span><span style="font-style:italic;color:var(--muted)">${htmlText(en.takhrij.join(" · "))}</span>`;
      rb.appendChild(t);
    }
    for (const r of entry.crossReferences || []) row("Also in", r.sunnahRef, r.url, r.confidence);
  }
}

async function resolveBookNeighbors(slug, n, idx, currentBookNumber, currentBookData){
  const books = idx?.books || [];
  const bookPos = books.findIndex(b => Number(b.book) === Number(currentBookNumber));
  const hadithNumbers = (currentBookData?.hadith || []).map(h => h.n);
  const i = hadithNumbers.findIndex(value => String(value) === String(n));
  let prev = i > 0 ? hadithNumbers[i - 1] : null;
  let next = i >= 0 && i < hadithNumbers.length - 1 ? hadithNumbers[i + 1] : null;
  for (let pos = bookPos - 1; prev == null && pos >= 0; pos--) {
    const data = await ensureBookOf(slug, books[pos].book);
    const list = data?.hadith || [];
    if (list.length) prev = list[list.length - 1].n;
  }
  for (let pos = bookPos + 1; next == null && pos < books.length; pos++) {
    const data = await ensureBookOf(slug, books[pos].book);
    const list = data?.hadith || [];
    if (list.length) next = list[0].n;
  }
  return { prev, next };
}

// Kunya / patronymic markers: أبو X, أم X, ابن/بن X, بنت X (+ و- "and" prefix).
// Detected by bare (diacritic/punct-stripped) form; merged with a FOLLOWING
// proper-noun token into one name cell ("Abu Bakr", "Ibn Umar", "Umm Salamah").
const NAME_BARE = (s) => s.replace(/[ً-ْٰـۖ-ۭ]/gu, "").replace(/[،,.:;"'{}»«‎‏]/gu, "").trim();
const KUNYA = {
  "أبو":"Abu","أبا":"Abu","أبي":"Abu","أم":"Umm","ابن":"Ibn","بن":"Ibn","بنت":"Bint",
  "وأبو":"and Abu","وأبا":"and Abu","وأبي":"and Abu","وأم":"and Umm","وابن":"and Ibn","وبن":"and Ibn","وبنت":"and Bint",
};
const KUNYA_UR = {
  "أبو":"ابو","أبا":"ابو","أبي":"ابو","أم":"ام","ابن":"ابن","بن":"ابن","بنت":"بنت",
  "وأبو":"اور ابو","وأبا":"اور ابو","وأبي":"اور ابو","وأم":"اور ام","وابن":"اور ابن","وبن":"اور ابن","وبنت":"اور بنت",
};
const stripKunyaPrefix = (en) =>
  (en || "")
    .replace(/^((and )?(Abu|Abi|Aba|Umm|Ibn|Bin|Bint)\s+)+/i, "")   // drop leading kunya word(s)
    .replace(/\s*\((name|proper name|proper noun|tribal nisba|tribal\/nisba name)\)\s*$/i, ""); // drop noise suffix

function buildArabic(tokens, gloss, clickable){
  const arDiv = document.createElement("div"); arDiv.className = "arabic";
  arDiv.lang = "ar";
  arDiv.dir = "rtl";
  const G = gloss && gloss.glosses ? gloss.glosses : {};
  const spans = []; // index-aligned with tokens (merged runs share one span across their token slots)
  const isHonorific = (t) => (G[t.id] || {}).pos === "HONORIFIC";
  for (let i = 0; i < tokens.length; ) {
    let run = 1;
    let g = G[tokens[i].id] || {};
    let text;
    // 1) Honorific formula run (صلى الله عليه وسلم) -> one cell, one meaning.
    if (isHonorific(tokens[i])) {
      while (i + run < tokens.length && isHonorific(tokens[i + run])) run++;
      text = tokens.slice(i, i + run).map(t => t.text).join(" ");
    } else {
      // 2) Kunya / patronymic: [marker][proper noun] -> one name cell.
      const mk = KUNYA[NAME_BARE(tokens[i].text)];
      const nextG = i + 1 < tokens.length ? (G[tokens[i + 1].id] || {}) : null;
      if (mk && nextG && nextG.pos === "PN") {
        run = 2;
        const nameEn = stripKunyaPrefix(nextG.en);
        text = tokens[i].text + " " + tokens[i + 1].text;
        g = {
          en: mk + " " + nameEn,
          ur: (KUNYA_UR[NAME_BARE(tokens[i].text)] || "") + " " + (nextG.ur || ""),
          transliteration: [(G[tokens[i].id] || {}).transliteration, nextG.transliteration].filter(Boolean).join(" "),
          root: null, lemma: text, pos: "PN", features: {},
        };
      } else {
        text = tokens[i].text; // plain single token
      }
    }
    const first = tokens[i];
    const s = document.createElement("span"); s.className = "w" + (run > 1 ? " w-unit" : "");
    s.innerHTML = `<span class="t"></span><span class="g-en"></span><span class="g-ur"></span>`;
    if (first.estimated) s.title = "Approximate word timing";
    s.querySelector(".t").textContent = text;
    s.querySelector(".g-en").textContent = g.en || "";
    s.querySelector(".g-ur").textContent = g.ur || "";
    if (clickable && Number.isFinite(first.start)) {
      const last = tokens[i + run - 1];
      s.onclick = () => playFrom(first.start, last.end);
    }
    attachLongPressGrammar(s, text, g);
    arDiv.append(s, document.createTextNode(" "));
    for (let k = 0; k < run; k++) spans.push(s); // keep index alignment for audio highlight
    i += run;
  }
  return { arDiv, spans };
}

/* ---------- grammar popover (long-press) ---------- */
const POS_LABELS = {
  V:"verb", N:"noun", PN:"proper noun", ADJ:"adjective", ADV:"adverb",
  PREP:"preposition", ADP:"preposition", PART:"particle", PRON:"pronoun",
  DEM:"demonstrative", SUB:"subordinator", CONJ:"conjunction", DET:"determiner",
  NUM:"numeral", INTJ:"interjection", REL:"relative", HONORIFIC:"honorific formula",
  PUNCT:"punctuation", X:"unknown",
};
function grammarPopEl(){
  let el = document.getElementById("gramPop");
  if (!el) {
    el = document.createElement("div"); el.id = "gramPop";
    document.body.appendChild(el);
    addEventListener("scroll", hideGrammar, true);
    addEventListener("resize", hideGrammar);
    document.addEventListener("pointerdown", (e) => {
      if (el.classList.contains("show") && !el.contains(e.target) && !e.target.closest(".w.gram-open")) hideGrammar();
    });
  }
  return el;
}
let gramSpan = null;
function hideGrammar(){
  const el = document.getElementById("gramPop");
  if (el) el.classList.remove("show");
  if (gramSpan) { gramSpan.classList.remove("gram-open"); gramSpan = null; }
}
function showGrammar(span, text, g){
  const el = grammarPopEl();
  const has = g && (g.root || g.lemma || g.pos || (g.features && Object.keys(g.features).length) || g.transliteration);
  const rows = [];
  if (g && g.transliteration) {} // shown as subtitle
  if (g && g.pos) rows.push(["part of speech", `<span class="gp-v">${POS_LABELS[g.pos] || g.pos}</span>`]);
  if (g && g.root) rows.push(["root", `<span class="gp-v root">${g.root}</span>`]);
  if (g && g.lemma) rows.push(["lemma", `<span class="gp-v root">${g.lemma}</span>`]);
  const feats = g && g.features ? Object.entries(g.features).filter(([k,v]) => v != null && v !== "" && v !== false) : [];
  if (feats.length) rows.push(["features", `<span class="gp-feats">${feats.map(([k,v]) => `<span>${v === true ? k : String(v)}</span>`).join("")}</span>`]);
  el.innerHTML =
    `<div class="gp-ar">${text}</div>` +
    (g && g.transliteration ? `<div class="gp-tr">${g.transliteration}</div>` : "") +
    (has ? rows.map(([k,v]) => `<div class="gp-row"><span class="gp-k">${k}</span>${v}</div>`).join("")
         : `<div class="gp-hint">No grammar data for this word yet.</div>`);
  // position near the span
  el.style.left = "0px"; el.style.top = "0px"; el.classList.add("show");
  const r = span.getBoundingClientRect(); const pr = el.getBoundingClientRect();
  let left = r.left + r.width/2 - pr.width/2;
  left = Math.max(8, Math.min(left, innerWidth - pr.width - 8));
  let top = r.bottom + 8;
  if (top + pr.height > innerHeight - 8) top = r.top - pr.height - 8;
  el.style.left = left + "px"; el.style.top = Math.max(8, top) + "px";
  if (gramSpan) gramSpan.classList.remove("gram-open");
  gramSpan = span; span.classList.add("gram-open");
}
function attachLongPressGrammar(span, text, g){
  let timer = null, sx = 0, sy = 0, fired = false;
  const start = (e) => {
    fired = false;
    const p = e.touches ? e.touches[0] : e;
    sx = p.clientX; sy = p.clientY;
    timer = setTimeout(() => { fired = true; showGrammar(span, text, g); }, 420);
  };
  const move = (e) => {
    const p = e.touches ? e.touches[0] : e;
    if (Math.abs(p.clientX - sx) > 10 || Math.abs(p.clientY - sy) > 10) { clearTimeout(timer); }
  };
  const end = () => clearTimeout(timer);
  span.addEventListener("pointerdown", start);
  span.addEventListener("pointermove", move);
  span.addEventListener("pointerup", end);
  span.addEventListener("pointercancel", end);
  // suppress the audio-seek click if a long-press just fired
  span.addEventListener("click", (e) => { if (fired) { e.stopImmediatePropagation(); e.preventDefault(); fired = false; } }, true);
  span.addEventListener("contextmenu", (e) => e.preventDefault());
}

const VIEW_FADE_MS = 450;
const STAGE_FADE_MS = 420;

function prefersReducedMotion(){
  return matchMedia("(prefers-reduced-motion: reduce)").matches;
}
function motionWait(ms){
  return prefersReducedMotion() ? Promise.resolve() : new Promise(r => setTimeout(r, ms));
}
async function fadeStageOut(){
  const stage = document.getElementById("stage");
  if (prefersReducedMotion()) return;
  if (!stage.querySelector(".stage-head, .parallel, .refblock")) return;
  stage.classList.add("is-fading");
  await motionWait(STAGE_FADE_MS);
}
function revealStage(){
  const stage = document.getElementById("stage");
  stage.classList.remove("is-fading");
  dispatchEvent(new Event("hadith:rendered"));
  if (prefersReducedMotion()) return;
  stage.classList.add("is-fading");
  requestAnimationFrame(() => requestAnimationFrame(() => stage.classList.remove("is-fading")));
}
async function enterReaderView(){
  const landing = document.getElementById("landing");
  const reader = document.getElementById("reader");
  document.body.dataset.view = "reader";
  landing.classList.remove("hidden");
  landing.classList.add("is-leaving");
  reader.classList.remove("hidden");
  if (prefersReducedMotion()) {
    landing.classList.add("hidden");
    landing.classList.remove("is-leaving");
    reader.classList.add("is-in");
    return;
  }
  await motionWait(VIEW_FADE_MS);
  landing.classList.add("hidden");
  landing.classList.remove("is-leaving");
  requestAnimationFrame(() => reader.classList.add("is-in"));
}
async function leaveReaderView(){
  const landing = document.getElementById("landing");
  const reader = document.getElementById("reader");
  reader.classList.remove("is-in");
  dock.classList.remove("is-in");
  if (prefersReducedMotion()) {
    reader.classList.add("hidden");
    landing.classList.remove("hidden");
    landing.classList.remove("is-leaving");
    return;
  }
  await motionWait(VIEW_FADE_MS);
  reader.classList.add("hidden");
  landing.classList.remove("hidden");
  landing.classList.remove("is-leaving");
}

function showDock(){
  dock.classList.remove("hidden");
  requestAnimationFrame(() => {
    requestAnimationFrame(() => dock.classList.add("is-in"));
  });
}
function hideDock(){
  dock.classList.remove("is-in");
  dock.classList.add("hidden");
}

async function openForty(col, n, navToken = currentNavToken){
  stopAudio();
  await fadeStageOut();
  const stage = document.getElementById("stage");
  stage.classList.remove("is-fading");
  stage.innerHTML = `<div class="status" role="status" aria-live="polite">Loading hadith…</div>`;
  const pad = String(n).padStart(3, "0");
  const [{ trans, sun }, rec, gloss] = await Promise.all([
    ensureFortySidecars(col.slug),
    j(`recitation/${col.corpus}.${pad}.json`),
    jopt(`gloss/${col.slug}-${n}.json`),
  ]);
  if (!isCurrentNavigation(navToken)) return false;
  const en = trans.translations.find(t => t.witness === rec.witness);
  const entry = sun.entries.find(e => e.witness === rec.witness);

  state = { slug: col.slug, n, book: null, seq: Array.from({ length: col.count }, (_, i) => i + 1), nav:{ prev:n > 1 ? n - 1 : null, next:n < col.count ? n + 1 : null } };
  applyReadingMode(false);
  rememberProgress(col.slug, n, null);
  fillCollectionJump();
  if (!(await fillBookJump(navToken))) return false;
  fillHadithJump();
  updateNavEdges();
  if (matchMedia("(max-width:680px)").matches) setLocatorExpanded(false);

  showDock();
  let audioAvailable = true;
  try {
    const audioVersion = encodeURIComponent(`${rec.qusxAudio || "recitation"}-${rec.duration || "0"}`);
    await prepareAudio(`${RECITATION_CDN}/${col.corpus}.${pad}.mp3?v=${audioVersion}`, navToken);
  } catch {
    if (!isCurrentNavigation(navToken)) return false;
    audioAvailable = false;
    hideDock();
    trackSiteEvent("audio_unavailable", { collection:col.slug, report:String(n) });
  }
  if (!isCurrentNavigation(navToken)) return false;
  currentTokens = rec.tokens;
  const shouldContinue = continuePlayAfterLoad;
  continuePlayAfterLoad = false;
  if (!shouldContinue || !audioAvailable) armAudioEndedListener(navToken);

  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="stage-head"><div class="collection">${col.en}</div><div class="ref">${n}</div></div>`;
  if (!audioAvailable) {
    const notice = document.createElement("div");
    notice.className = "availability warn";
    notice.textContent = "Audio is temporarily unavailable. The Arabic text and meanings remain readable.";
    wrap.appendChild(notice);
  }
  const par = document.createElement("div");
  par.className = "parallel" + (single ? " single" : "");
  const enCol = buildMeaningColumn(en ? en.matn : "", "");
  const arCol = document.createElement("div"); arCol.className = "ar-col";
  arCol.innerHTML = `<div class="col-label" style="text-align:right">العربية</div>`;
  const { arDiv, spans } = buildArabic(rec.tokens, gloss, true);
  activeSpans = spans;
  arCol.appendChild(arDiv);
  par.append(enCol, arCol);
  wrap.appendChild(par);

  const rb = document.createElement("div"); rb.className = "refblock";
  renderRefs(rb, entry, en);
  const copy = document.createElement("button"); copy.className = "copy"; copy.textContent = "Copy link";
  copy.onclick = async () => {
    const url = publicHadithUrl(col.slug, n);
    try { await navigator.clipboard.writeText(url); copy.textContent = "Copied"; setTimeout(() => copy.textContent = "Copy link", 1200); }
    catch { prompt("Copy link:", url); }
  };
  rb.appendChild(copy);
  wrap.appendChild(rb);
  appendReportAction(wrap);

  if (!isCurrentNavigation(navToken)) return false;
  if (!isCurrentNavigation(navToken)) return false;
  stage.innerHTML = ""; stage.appendChild(wrap);
  revealStage();
  applyParallel();
  setPublicMetadata(`${col.en} ${n} — hadith.to`, col.slug, n);
  scrollTo(0, 0);
  if (shouldContinue && audioAvailable) {
    audio.currentTime = 0;
    syncWordHighlight(0);
    const p = audio.play();
    Promise.resolve(p).catch(() => {}).finally(() => armAudioEndedListener(navToken));
  }
}

async function openBookHadith(slug, n, navToken = currentNavToken){
  stopAudio();
  await fadeStageOut();
  hideDock();
  const stage = document.getElementById("stage");
  stage.classList.remove("is-fading");
  stage.innerHTML = `<div class="status" role="status" aria-live="polite">Loading hadith…</div>`;

  const idx = await ensureBookIndex(slug);
  let bookMeta = bookForReport(idx, n);
  if (!bookMeta) {
    // Gaps in numbering: snap to nearest existing report in index range
    const base = parseInt(n, 10);
    bookMeta = idx.books.find(b => base < b.from) || idx.books[idx.books.length - 1];
    const data0 = await ensureBookOf(slug, bookMeta.book);
    n = data0.hadith[0].n;
  }
  const bookData = await ensureBookOf(slug, bookMeta.book);
  let h = bookData.hadith.find(x => String(x.n) === String(n));
  if (!h) { h = bookData.hadith[0]; n = h.n; }
  n = h.n;

  const [gloss, timing, officialTranslation] = await Promise.all([
    slug === "darimi" ? null : jopt(`gloss/${slug}-${n}.json`),
    slug === "darimi" ? (h.clip ? { audio:`darimi/clips/${h.clip}.mp3`, tokens:h.tokens } : null) : getBookTiming(slug, n),
    slug === "darimi" ? {} : ensureOfficialTranslations(slug, n),
  ]);
  if (!isCurrentNavigation(navToken)) return false;
  const isnadPool = timing && slug === "bukhari" ? await getBukhariIsnadPool() : null;
  const hasSyncedAudio = Boolean(timing);
  let audioAvailable = hasSyncedAudio;
  const shouldContinue = continuePlayAfterLoad;
  continuePlayAfterLoad = false;
  state = { slug, n, book: bookMeta.book, seq: reportsInBook(bookData), nav:{ prev:null, next:null } };
  applyReadingMode(false);
  rememberProgress(slug, n, bookMeta.book);
  fillCollectionJump();
  if (!(await fillBookJump(navToken))) return false;
  state.nav = await resolveBookNeighbors(slug, n, idx, bookMeta.book, bookData);
  if (!isCurrentNavigation(navToken)) return false;
  fillHadithJump();
  updateNavEdges();
  if (matchMedia("(max-width:680px)").matches) setLocatorExpanded(false);

  if (hasSyncedAudio) showDock();
  else hideDock();
  if (hasSyncedAudio) {
    try {
      await prepareAudio(bookAudioUrl(slug, n, timing), navToken);
    } catch {
      audioAvailable = false;
      hideDock();
      trackSiteEvent("audio_unavailable", { collection:slug, report:String(n) });
    }
    if (!isCurrentNavigation(navToken)) return false;
    currentTokens = effectiveTimingTokens(timing);
  }
  // Arm ended-listener now when we will not auto-continue; continue path arms after play().
  if (!shouldContinue || !hasSyncedAudio || !audioAvailable) armAudioEndedListener(navToken);

  const col = bySlug[slug];
  const wrap = document.createElement("div");
  const reference = slug === "musnad-ahmad"
    ? musnadAhmadReference(n)
    : state.book ? `${bookLabel(slug, state.book)} · ${n}` : n;
  wrap.innerHTML = `
    <div class="stage-head"><div class="collection">${col.en}</div><div class="ref">${htmlText(reference)}</div></div>`;
  if (!audioAvailable && hasSyncedAudio) {
    const notice = document.createElement("div");
    notice.className = "availability warn";
    notice.textContent = "Audio is temporarily unavailable. The aligned Arabic text and translations remain readable.";
    wrap.appendChild(notice);
  } else if (!hasSyncedAudio) {
    const notice = document.createElement("div");
    notice.className = "availability";
    notice.textContent = "Audio and word timestamps are not available for this report yet.";
    wrap.appendChild(notice);
  }
  if (timing?.synthetic) {
    const notice = document.createElement("div");
    notice.className = "availability warn";
    notice.textContent = timing.disclosure || "Generated recitation; this report is omitted from the supplied original audiobook.";
    wrap.appendChild(notice);
  }
  // One continuous Arabic token stream only — never a separate arrow-isnad strip.
  const par = document.createElement("div");
  par.className = "parallel single"; // Muwatta has no sentence translation sidecar
  const arCol = document.createElement("div"); arCol.className = "ar-col";
  arCol.innerHTML = `<div class="col-label" style="text-align:right">العربية</div>`;
  const tokens = hasSyncedAudio
    ? effectiveTimingTokens(timing).map((t, i) => ({
        id: t.id || `uh:token:${slug}.${String(n).padStart(4, "0")}:asr:${String(i + 1).padStart(4, "0")}`,
        text: t.text,
        start: t.start,
        end: t.end,
        estimated: t.estimated,
        gloss: t.gloss || null,
      }))
    : h.tokens.map(t => ({ id:t.id, text:t.text.replace(/[،:]/g, "") }));
  const alignedGlosses = hasSyncedAudio ? alignOriginalGlosses(tokens, h.tokens, gloss) : {};
  const syncedGloss = hasSyncedAudio ? {
    ...(gloss || {}),
    glosses: {
      ...((gloss && gloss.glosses) || {}),
      ...alignedGlosses,
      ...Object.fromEntries(tokens.map((t, i) => {
        const pool = t.gloss || honorificPartGloss(tokens, i) || isnadPool?.words?.[normalizeArabicWord(t.text)];
        return pool?.en ? [t.id, pool] : [t.id, null];
      }).filter(([, value]) => value)),
    },
  } : gloss;
  const { arDiv, spans } = buildArabic(tokens, syncedGloss, hasSyncedAudio);
  if (hasSyncedAudio) activeSpans = spans;
  arCol.appendChild(arDiv);
  const meaningCol = buildMeaningColumn(officialTranslation.en, officialTranslation.ur);
  par.className = "parallel" + (single ? " single" : "");
  par.append(meaningCol, arCol);
  wrap.appendChild(par);

  const rb = document.createElement("div"); rb.className = "refblock";
  const row = document.createElement("div"); row.className = "refrow";
  row.innerHTML = `<span class="lbl">Reference</span>`;
  const a = document.createElement("a");
  a.href = slug === "darimi" ? publicHadithUrl(slug, n) : `https://sunnah.com/${slug}:${n}`; a.target = "_blank"; a.rel = "noopener";
  a.textContent = `${slug}:${n}`;
  row.appendChild(a); rb.appendChild(row);
  if (!gloss) {
    const pend = document.createElement("div"); pend.className = "refrow";
    pend.innerHTML = `<span class="lbl">Gloss</span><span style="color:var(--faint);font-style:italic">pending</span>`;
    rb.appendChild(pend);
  }
  const copy = document.createElement("button"); copy.className = "copy"; copy.textContent = "Copy link";
  copy.onclick = async () => {
    const url = publicHadithUrl(slug, n);
    try { await navigator.clipboard.writeText(url); copy.textContent = "Copied"; setTimeout(() => copy.textContent = "Copy link", 1200); }
    catch { prompt("Copy link:", url); }
  };
  if (slug === "darimi") {
    const source = document.createElement("div");
    source.className = "refrow";
    source.innerHTML = '<span class="lbl">Audio source</span><a href="https://rawy.net/library" target="_blank" rel="noopener">Rawy Library · مكتبة الراوي</a>';
    rb.appendChild(source);
  }
  rb.appendChild(copy);
  wrap.appendChild(rb);
  appendReportAction(wrap);

  stage.innerHTML = ""; stage.appendChild(wrap);
  revealStage();
  if (shouldContinue && hasSyncedAudio && audioAvailable) {
    audio.currentTime = 0;
    syncWordHighlight(0);
    const p = audio.play();
    Promise.resolve(p).catch(() => {}).finally(() => armAudioEndedListener(navToken));
  }
  setPublicMetadata(`${shortCollectionName(col)} ${n} — hadith.to`, slug, n);
  scrollTo(0, 0);
}

async function openManagedHadith(col, record, navToken) {
  const {slug,n} = record;
  stopAudio();
  hideDock();
  await fadeStageOut();
  if (!isCurrentNavigation(navToken)) return;
  const index = col.books ? await ensureBookIndex(slug).catch(() => null) : null;
  const bookMeta = index ? bookForReport(index,n) : null;
  const bookData = bookMeta ? await ensureBookOf(slug,bookMeta.book).catch(() => null) : null;
  if (!isCurrentNavigation(navToken)) return;
  const managed = window.hadithManagedNumbers(slug);
  const inCurrentBook = bookData ? reportsInBook(bookData) : [];
  const bundled = col.managed || col.books ? inCurrentBook : Array.from({length:col.count},(_,i) => String(i+1));
  const seq = [...new Set([...bundled.map(String),...managed,n])].sort((a,b) => a.localeCompare(b,undefined,{numeric:true}));
  const position = seq.indexOf(n);
  state = {slug,n,book:record.book ?? bookMeta?.book ?? null,seq,
    nav:{prev:seq[position-1] ?? null,next:seq[position+1] ?? null}};
  if (bookData && bookMeta) {
    const neighbors = await resolveBookNeighbors(slug,n,index,bookMeta.book,bookData);
    if (!isCurrentNavigation(navToken)) return;
    if (state.nav.prev === null) state.nav.prev = neighbors.prev;
    if (state.nav.next === null) state.nav.next = neighbors.next;
  }
  rememberProgress(slug,n,state.book);
  fillCollectionJump();
  const jump = document.getElementById("bookJump");
  if (bookMeta) {
    if (!(await fillBookJump(navToken))) return;
  } else if (col.managed && window.hadithManagedLibrary.get(slug)?.books.length) {
    const books = window.hadithManagedLibrary.get(slug).books;
    const entries = await window.hadithManagedSearch(slug).catch(() => new Map());
    if (!isCurrentNavigation(navToken)) return;
    const firstReports = new Map();
    for (const number of managed) {
      const book = entries.get(number)?.[4];
      if (book && !firstReports.has(book)) firstReports.set(book,number);
    }
    jump.replaceChildren(new Option("Choose book",""),...books.filter(book => firstReports.has(book.number))
      .map(book => new Option(book.title,String(book.number))));
    jump.value = String(record.book || "");
    jump.classList.toggle("hidden",firstReports.size === 0);
    jump.onchange = () => { if (jump.value) setHash(slug,firstReports.get(Number(jump.value))); };
  } else jump.classList.add("hidden");
  fillHadithJump();
  updateNavEdges();
  applyReadingMode(false);

  let audioUrl = record.audio;
  let timing = record.words;
  if (!audioUrl && record.reuseAudio && col.books) {
    const h = bookData?.hadith.find(item => String(item.n) === n);
    const legacyTiming = slug === "darimi" && h?.clip ? {audio:"darimi/clips/"+h.clip+".mp3",tokens:h.tokens} : await getBookTiming(slug,n);
    if (!isCurrentNavigation(navToken)) return;
    if (legacyTiming) {
      audioUrl = bookAudioUrl(slug,n,legacyTiming);
      timing = effectiveTimingTokens(legacyTiming);
    }
  }
  const textWords = record.ar.split(/\s+/);
  const canSync = audioUrl && timing.length > 0 &&
    (record.reuseAudio && !record.audio || normalizeArabicWord(timing.map(word => word.text).join(" ")) === normalizeArabicWord(record.ar));
  const tokens = (canSync ? timing : textWords.map(text => ({text})))
    .map((word,i) => ({...word,id:"cms:"+slug+":"+n+":"+i}));
  const wrap = document.createElement("div");
  const title = document.createElement("div");
  title.className = "stage-head";
  const collection = document.createElement("div");
  collection.className = "collection";
  collection.textContent = col.en;
  const ref = document.createElement("div");
  ref.className = "ref";
  const book = window.hadithManagedLibrary.get(slug)?.books.find(item => item.number === record.book);
  ref.textContent = book ? book.title + " · " + n : n;
  title.append(collection,ref);
  wrap.append(title);
  const parallel = document.createElement("div");
  parallel.className = "parallel" + (single ? " single" : "");
  const arabic = document.createElement("div");
  arabic.className = "ar-col";
  const {arDiv,spans} = buildArabic(tokens,null,Boolean(canSync));
  arabic.append(arDiv);
  parallel.append(buildMeaningColumn(record.en,record.ur),arabic);
  wrap.append(parallel);
  const references = document.createElement("div");
  references.className = "refblock";
  if (record.source) {
    const link = document.createElement("a");
    link.href = record.source;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Source";
    references.append(link);
  }
  wrap.append(references);
  appendReportAction(wrap);
  const stage = document.getElementById("stage");
  stage.replaceChildren(wrap);
  currentTokens = canSync ? tokens : [];
  activeSpans = canSync ? spans : [];
  revealStage();
  applyParallel();
  setPublicMetadata(col.en+" "+n+" — hadith.to",slug,n);
  scrollTo(0,0);
  const continueAudio = continuePlayAfterLoad;
  continuePlayAfterLoad = false;
  if (audioUrl) {
    showDock();
    try {
      await prepareAudio(audioUrl,navToken,Boolean(record.audio?.startsWith("https:")));
      if (!isCurrentNavigation(navToken)) return;
      armAudioEndedListener(navToken);
      if (continueAudio) await audio.play().catch(() => {});
    } catch {
      if (!isCurrentNavigation(navToken)) return;
      hideDock();
      const notice = document.createElement("p");
      notice.className = "availability warn";
      notice.textContent = "Recitation is temporarily unavailable.";
      wrap.append(notice);
    }
  }
}

async function openHadith(slug, n, navToken = currentNavToken){
  const col = bySlug[slug]; if (!col) return showLanding(navToken);
  if (document.body.dataset.view === "landing") await enterReaderView();
  else {
    document.body.dataset.view = "reader";
    document.getElementById("landing").classList.add("hidden");
    document.getElementById("reader").classList.remove("hidden");
    document.getElementById("reader").classList.add("is-in");
  }
  syncReaderToolsUI();
  try {
    const number = String(n || 1).toLowerCase();
    const managed = await window.hadithManagedReport?.(slug,number).catch(() => null);
    if (!isCurrentNavigation(navToken)) return;
    if (managed) return await openManagedHadith(col,window.HadithContent.report(managed),navToken);
    if (col.managed) {
      const first = window.hadithManagedNumbers(slug)[0];
      if (first && !n) return setHash(slug,first);
      throw new Error("Hadith not found");
    }
    if (col.books) await openBookHadith(slug, String(n || 1).toLowerCase(), navToken);
    else {
      n = Number(n) || 1;
      if (n < 1) n = 1;
      if (n > col.count) n = col.count;
      await openForty(col, n, navToken);
    }
  } catch (err) {
    document.getElementById("stage").innerHTML = `<div class="status" aria-live="assertive">Couldn’t load this hadith. Check your connection and try again.</div>`;
    trackSiteEvent("hadith_load_error", { collection:slug, report:String(n || 1) });
    console.error(err);
  }
}

async function showLanding(navToken = currentNavToken){
  stopAudio();
  state = { slug:null, n:null, book:null, seq:[], nav:{ prev:null, next:null } };
  document.body.dataset.view = "landing";
  setReaderToolsOpen(false);
  setSettingsOpen(false);
  await leaveReaderView();
  hideDock();
  setPublicMetadata(window.hadithCmsHomeTitle || "Read, Listen & Study Hadith");
  renderResume();
  scrollTo(0, 0);
  dispatchEvent(new Event("hadith:landing"));
}

function route(){
  const navToken = beginNavigation();
  const m = location.hash.match(/^#([a-z0-9_-]+)(?::(\d+[a-z]?))?/i);
  if (m && bySlug[m[1]]) openHadith(m[1], m[2] || 1, navToken);
  else showLanding(navToken);
}
// Legacy /h/:collection/:id SEO URLs redirect here as ?c=&n= — fold into hash.
(function adoptLegacyHadithQuery(){
  const q = new URLSearchParams(location.search);
  const c = q.get("c");
  const n = q.get("n");
  if (!c || !n || !/^[a-z0-9]+$/i.test(c) || !/^\d+[a-z]?$/i.test(n)) return;
  history.replaceState(null, "", `/#${c}:${n}`);
})();
addEventListener("hashchange", route);
route();
