(() => {
  "use strict";
  const bundled = [
  { slug:"bukhari", corpus:"bukhari", ar:"صحيح البخاري", en:"Sahih al-Bukhari", count:7580, audio:true, books:true },
  { slug:"muslim", corpus:"muslim", ar:"صحيح مسلم", en:"Sahih Muslim", count:7360, audio:true, books:true },
  { slug:"al-ilmam", corpus:"al-ilmam", ar:"الإلمام بأحاديث الأحكام", en:"Al-Ilmam bi-Ahadith al-Ahkam", count:1629, audio:true, books:true, synthetic:false, audioSource:"https://rawy.net/book/12105" },
  { slug:"abudawud", corpus:"abudawud", ar:"سنن أبي داود", en:"Sunan Abi Dawud", count:5274, audio:true, books:true },
  { slug:"tirmidhi", corpus:"tirmidhi", ar:"جامع الترمذي", en:"Jami at-Tirmidhi", count:3924, audio:true, books:true },
  { slug:"nasai", corpus:"nasai", ar:"سنن النسائي", en:"Sunan an-Nasa'i", count:5679, audio:true, books:true },
  { slug:"ibnmajah", corpus:"ibnmajah", ar:"سنن ابن ماجه", en:"Sunan Ibn Majah", count:4338, audio:true, books:true },
  { slug:"malik", corpus:"malik", ar:"موطأ مالك", en:"Muwatta Malik", count:1829, audio:true, books:true },
  { slug:"darimi", corpus:"darimi", ar:"سنن الدارمي", en:"Sunan al-Darimi", count:3535, audio:true, books:true },
  { slug:"riyad", corpus:"riyad-as-salihin", ar:"رياض الصالحين", en:"Riyad as-Salihin", count:1896, audio:true, books:true, synthetic:"mixed" },
  { slug:"musnad-ahmad", corpus:"musnad-ahmad", ar:"مسند أحمد", en:"Musnad Ahmad", count:27648, audio:true, books:true, synthetic:false },
  { slug:"nawawi40", corpus:"nawawi-arbain", ar:"الأربعون النووية", en:"An-Nawawi's Forty Hadith", count:42, audio:true, synthetic:false },
  { slug:"qudsi40", corpus:"qudsi-arbain", ar:"الأربعون القدسية", en:"The Forty Hadith Qudsi", count:40, audio:true, synthetic:true },
  { slug:"shahwaliullah40", corpus:"shahwaliullah-arbain", ar:"أربعون شاه ولي الله الدهلوي", en:"Forty Hadith of Shah Waliullah Dehlawi", count:40, audio:true, synthetic:true },
];;
  const slugPattern = /^[a-z0-9][a-z0-9_-]{0,63}$/;
  const numberPattern = /^[1-9][0-9]{0,8}[a-z]?$/;
  const safeNames = /[<>&"\u0000-\u001f]/;
  const string = (value, max) => typeof value === "string" ? value.trim().slice(0,max) : "";
  const positive = value => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;

  function https(value) {
    if (!value) return "";
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password) throw new Error("Use a public HTTPS URL.");
    return url.href;
  }

  function collection(value) {
    const slug = string(value?.slug,65), en = string(value?.en,150), ar = string(value?.ar,150);
    if (!slugPattern.test(slug) || Object.hasOwn(Object.prototype,slug) ||
        !en || !ar || safeNames.test(en) || safeNames.test(ar)) throw new Error("Enter a valid collection address and both titles.");
    if (!Array.isArray(value.books)) throw new Error("Books must be a list.");
    const seen = new Set();
    const books = value.books.map(book => {
      const number = positive(book.number);
      const title = string(book.title,150);
      if (!number || !title || seen.has(number)) throw new Error("Each book needs a unique positive number and title.");
      seen.add(number);
      return {number,title};
    }).sort((a,b) => a.number-b.number);
    return {slug,en,ar,books};
  }

  function report(value) {
    const slug = string(value?.slug,65), n = string(String(value?.n ?? ""),10);
    const ar = string(value?.ar,40000);
    const book = value.book === "" || value.book == null ? null : positive(value.book);
    if (!slugPattern.test(slug) || Object.hasOwn(Object.prototype,slug) || !numberPattern.test(n) || !ar ||
        (value.book && !book)) throw new Error("Enter a valid collection, hadith number, Arabic text, and book number if applicable.");
    const words = Array.isArray(value.words) ? value.words : [];
    let previous = 0;
    const timing = words.map(word => {
      const text = string(word?.text,300);
      const start = word?.start, end = word?.end;
      if (!text || !Number.isFinite(start) || !Number.isFinite(end) || start < previous || end <= start) {
        throw new Error("Word timestamps must have text and increasing start and end times.");
      }
      previous = start;
      return {text,start,end};
    });
    const audio = typeof value.audio === "string" && /^\/recitation\/[a-zA-Z0-9_.-]+[.](?:mp3|m4a|ogg|wav)$/.test(value.audio)
      ? value.audio : https(value.audio);
    if (timing.length && !audio) throw new Error("Add a recitation URL to use word timestamps.");
    return {slug,n,book,ar,en:string(value.en,40000),ur:string(value.ur,40000),
      ...(audio ? {audio} : {}), reuseAudio:value.reuseAudio === true, words:timing, source:https(value.source)};
  }
  const collectionPath = slug => "cms/library/"+slug+".json";
  const reportPath = (slug,n) => "cms/reports/"+slug+"/"+n+".json";
  window.HadithContent = {bundled,collection,report,collectionPath,reportPath,slugPattern,numberPattern};
})();
