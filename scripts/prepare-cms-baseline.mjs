import { readFile } from "node:fs/promises";
import { once } from "node:events";
import process from "node:process";

globalThis.window = {};
await import("../public/cms-content.js");
const model = window.HadithContent;
const root = new URL("../public/",import.meta.url);
const json = async path => JSON.parse(await readFile(new URL(path,root),"utf8"));
const optional = path => json(path).catch(error => {
  if (error.code === "ENOENT") return null;
  throw error;
});
const {upstream} = await json("translations-pinned/manifest.json");
const upstreamCollections = new Set(["bukhari","muslim","abudawud","tirmidhi","nasai","ibnmajah","malik"]);
const sha = upstream.commit;
const cdn = `https://cdn.jsdelivr.net/gh/${upstream.repo}@${sha}/editions/`;
async function edition(slug, language) {
  const result = await fetch(cdn+language+"-"+slug+".min.json",{signal:AbortSignal.timeout(45000)});
  if (result.status === 404 && slug === "malik") return new Map();
  if (!result.ok) throw new Error("Translation unavailable: "+language+"-"+slug+" ("+result.status+")");
  const data = await result.json();
  return new Map(data.hadiths.map(row => [String(row.hadithnumber),row.text]));
}
async function write(path,document) {
  if (!process.stdout.write(JSON.stringify({path,document})+"\n")) await once(process.stdout,"drain");
}
const slugs = new Set(process.argv.slice(2));
const collectionList = [...model.bundled,{slug:"shamail",en:"Al-Shama’il al-Muhammadiyyah",ar:"الشمائل المحمدية",books:true}];
const drafts = collectionList.filter(col => !slugs.size || slugs.has(col.slug));
if (!drafts.length || [...slugs].some(slug => !drafts.some(col => col.slug===slug))) throw new Error("Unknown collection.");
const output = [];
for (const col of drafts) {
  const {slug} = col;
  const reports = new Map();
  let books = [];
  const local = await optional("translation/"+slug+".json");
  if (slug === "shamail") {
    const chapters = new Map();
    for (const entry of await json("shamail/shamail-hadiths.json")) {
      const n = String(entry.number);
      if (!chapters.has(entry.chapter)) chapters.set(entry.chapter,chapters.size+1);
      const value={slug,n,book:chapters.get(entry.chapter),ar:entry.words.map(word=>word.text).join(" ")};
      reports.set(n,{...(value.ar.trim()?model.report(value):{...value,missingArabic:true}),
        originalAudio:entry.audio,originalWords:entry.words});
    }
    books = Array.from(chapters,([title,number])=>({number,title}));
  } else if (col.books) {
    const index = await json(slug+"/index.json");
    books = index.books.map(book=>({number:book.book,title:book.title||"Book "+book.book}));
    const [en,ur] = upstreamCollections.has(slug) ? await Promise.all([edition(slug,"eng"),edition(slug,"urd")]) : [new Map(),new Map()];
    const translated = new Map((local?.translations||[]).map(row=>[String(row.n),row]));
    for (const book of index.books) {
      const data = await json(slug+"/book-"+book.book+".json");
      for (const entry of data.hadith) {
        const n = String(entry.n);
        if (reports.has(n) && index.reportBook?.[n] !== book.book) continue;
        const text = entry.tokens.map(word=>word.text).join(" ");
        const row = translated.get(n);
        const fields = {slug,n,book:book.book,ar:text,en:row?.en||en.get(n)||"",
          ur:row?.ur||ur.get(n)||"",source:slug==="darimi"?"":"https://sunnah.com/"+slug+":"+n,reuseAudio:col.audio};
        const report = text.trim() ? model.report(fields) : {...fields,words:[],missingArabic:true};
        reports.set(n,{...report,corpusPath:slug+"/book-"+book.book+".json"});
      }
    }
  } else {
    const references = await optional("sunnah/"+slug+".json");
    const byWitness = new Map((local?.translations||[]).map(row=>[row.witness,row]));
    const sources = new Map((references?.entries||[]).map(row=>[row.witness,row]));
    for (let i=1;i<=col.count;i++) {
      const n=String(i), file=col.corpus+"."+n.padStart(3,"0"), corpusPath="recitation/"+file+".json";
      const rec=await json(corpusPath), translation=byWitness.get(rec.witness), ref=sources.get(rec.witness);
      reports.set(n,{...model.report({slug,n,ar:rec.tokens.map(word=>word.text).join(" "),en:translation?.matn||translation?.full,
        source:ref?.sunnah?.url,audio:"https://cdn.hadith.to/recitation/"+file+".mp3",
        words:rec.tokens.filter(word=>Number.isFinite(word.start)&&Number.isFinite(word.end)&&word.end>word.start)}),corpusPath,
        ...(ref ? {references:ref} : {})});
    }
  }
  const catalog=model.collection({...col,books});
  await write(model.collectionPath(slug),catalog);
  for (const report of reports.values()) await write(model.reportPath(slug,report.n),report);
  const stats={slug,reports:reports.size,books:books.length,
    english:[...reports.values()].filter(row=>row.en).length,urdu:[...reports.values()].filter(row=>row.ur).length};
  output.push(stats);
  process.stderr.write(JSON.stringify(stats)+"\n");
}
