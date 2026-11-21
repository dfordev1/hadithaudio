// Write an existing collection in Studio's structured import format.
import { readFile } from "node:fs/promises";
import process from "node:process";

globalThis.window = {};
await import("../public/cms-content.js");
const model = window.HadithContent;
const [slug, range] = process.argv.slice(2);
const original = model.bundled.find(item => item.slug === slug);
if (!original || (range && !/^\d+-\d+$/.test(range))) {
  throw new Error("Usage: node scripts/export-cms-collection.mjs <collection-slug> [start-end]");
}
const root = new URL("../public/",import.meta.url);
const read = path => readFile(new URL(path,root),"utf8").then(JSON.parse);
const optional = path => read(path).catch(error => {
  if (error.code !== "ENOENT") throw error;
  return null;
});
const [start,end] = range ? range.split("-").map(Number) : [1,999];
const inRange = n => Number.parseInt(n,10)>=start && Number.parseInt(n,10)<=end;
const catalog = { ...original, books:[] };
const reports = [];
const translations = await optional("translation/"+slug+".json");

if (original.books) {
  const index = await read(slug+"/index.json");
  catalog.books = index.books.map(book => ({number:book.book,title:book.title||"Book "+book.book}));
  const localized = new Map((translations?.translations||[]).map(item => [String(item.n),item]));
  const loaded = new Set();
  for (const book of index.books.filter(book => book.to>=start && book.from<=end)) {
    const data = await read(slug+"/book-"+book.book+".json");
    for (const item of data.hadith) {
      const n = String(item.n);
      if (!inRange(n) || loaded.has(n)) continue;
      if (!localized.has(n) && original.slug !== "darimi") {
        throw new Error("This collection's translations are loaded externally. Use Studio to load and migrate individual entries without losing their translations.");
      }
      loaded.add(n);
      const meanings = localized.get(n) || {};
      reports.push(model.report({slug,n,book:book.book,ar:item.tokens.map(token => token.text).join(" "),
        en:meanings.en,ur:meanings.ur,reuseAudio:true,source:slug==="darimi"?"":"https://sunnah.com/"+slug+":"+n}));
    }
  }
} else {
  const sources = await optional("sunnah/"+slug+".json");
  const localized = new Map((translations?.translations||[]).map(item => [item.witness,item]));
  const references = new Map((sources?.entries||[]).map(item => [item.witness,item.sunnah?.url]));
  for (let number=start;number<=Math.min(original.count,end);number++) {
    const filename = original.corpus+"."+String(number).padStart(3,"0");
    const recitation = await read("recitation/"+filename+".json");
    const en = localized.get(recitation.witness);
    reports.push(model.report({slug,n:number,ar:recitation.tokens.map(token => token.text).join(" "),
      en:en?.matn||en?.full,source:references.get(recitation.witness),
      audio:"https://cdn.hadith.to/recitation/"+filename+".mp3",
      words:recitation.tokens.filter(word => Number.isFinite(word.start) && Number.isFinite(word.end) && word.end>word.start)}));
  }
}
if (!reports.length || reports.length>999) throw new Error("The range must contain between 1 and 999 hadith.");
process.stdout.write(JSON.stringify({collection:model.collection(catalog),reports},null,2)+"\n");
