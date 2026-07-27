// Generates recitation audio for husx witnesses and maps ElevenLabs character
// timestamps onto husx matn token ids.
//
//   node generate-recitation.mjs 1 2 3          # specific report numbers
//   node generate-recitation.mjs --all
//
// Output per report, under public/recitation/:
//   nawawi-arbain.NNN.mp3
//   nawawi-arbain.NNN.json    { witness, audio, tokens: [{id, text, start, end}] }
//
// Safe to re-run: a report whose .mp3 and .json already exist is skipped, so
// nothing is paid for twice.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";

const API_KEY = readFileSync(".env", "utf8").match(/ELEVENLABS_API_KEY=(\S+)/)[1];
const VOICE = "xvhpbk8otnNHtT3fjCpr";        // Omar - Premium Arabic Voice
const MODEL = "eleven_turbo_v2_5";           // 0.5 credits/char
const OUT = "public/recitation";

const corpus = JSON.parse(readFileSync("hadithusx/data/nawawi-arbain.json", "utf8"));
const args = process.argv.slice(2);
const wanted = args.includes("--all")
  ? corpus.witnesses.map((w) => w.structuredLocator.reportNumber)
  : args.map(Number).filter((n) => Number.isInteger(n));

if (!wanted.length) {
  console.error("usage: node generate-recitation.mjs <report numbers> | --all");
  process.exit(1);
}
mkdirSync(OUT, { recursive: true });

// Token char spans within the diplomatic text. The husx semantic validator
// already guarantees tokens are exactly the whitespace split of diplomatic,
// so spans can be walked without re-tokenizing.
function tokenSpans(diplomatic, tokens) {
  const spans = [];
  let cursor = 0;
  for (const token of tokens) {
    const at = diplomatic.indexOf(token.text, cursor);
    if (at < 0) throw new Error(`token ${token.id} not found at/after ${cursor}`);
    spans.push({ ...token, start: at, end: at + token.text.length });
    cursor = at + token.text.length;
  }
  return spans;
}

let spent = 0;
for (const n of wanted) {
  const witness = corpus.witnesses.find((w) => w.structuredLocator.reportNumber === n);
  if (!witness) { console.error(`report ${n}: no such witness`); continue; }
  const stem = `nawawi-arbain.${String(n).padStart(3, "0")}`;
  if (existsSync(`${OUT}/${stem}.mp3`) && existsSync(`${OUT}/${stem}.json`)) {
    console.log(`${stem}: already generated, skipped`);
    continue;
  }

  const text = witness.matn.diplomatic;
  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${VOICE}/with-timestamps?output_format=mp3_44100_128`,
    {
      method: "POST",
      headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        model_id: MODEL,
        voice_settings: { stability: 0.6, similarity_boost: 0.8, speed: 0.9 }
      })
    }
  );
  if (!res.ok) {
    console.error(`${stem}: API ${res.status} ${(await res.text()).slice(0, 200)}`);
    break;                       // stop rather than burn credits on a broken run
  }
  const data = await res.json();
  const { characters, character_start_times_seconds: starts, character_end_times_seconds: ends } = data.alignment;

  // If ElevenLabs altered the text, character offsets no longer address our
  // tokens. Refuse to write a mapping that would be silently wrong.
  const returned = characters.join("");
  if (returned !== text) {
    console.error(`${stem}: MISMATCH - model returned ${returned.length} chars, sent ${text.length}; skipping mapping`);
    writeFileSync(`${OUT}/${stem}.mismatch.txt`, `sent:\n${text}\n\nreturned:\n${returned}\n`);
    continue;
  }

  const tokens = tokenSpans(text, witness.matn.tokens).map((t) => ({
    id: t.id,
    position: t.position,
    text: t.text,
    start: starts[t.start],
    end: ends[t.end - 1]
  }));

  writeFileSync(`${OUT}/${stem}.mp3`, Buffer.from(data.audio_base64, "base64"));
  writeFileSync(`${OUT}/${stem}.json`, `${JSON.stringify({
    qusxAudio: "0.1-recitation-draft",
    kind: "recitation",
    language: "ar",
    witness: witness.id,
    locator: witness.locator,
    model: MODEL,
    voice: VOICE,
    audio: `${stem}.mp3`,
    duration: ends[ends.length - 1],
    diplomatic: text,
    tokens
  }, null, 2)}\n`);

  spent += text.length;
  console.log(`${stem}: ${tokens.length} tokens, ${ends[ends.length - 1].toFixed(1)}s, ${text.length} chars`);
}
console.log(`\nsent ${spent} characters (~${Math.round(spent * 0.5)} credits on ${MODEL})`);
