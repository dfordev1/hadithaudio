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

// First arg is the collection key (husx corpus basename); the rest are report
// numbers or --all.
//   node generate-recitation.mjs qudsi-arbain --all
//   node generate-recitation.mjs nawawi-arbain 1 2 3
const args = process.argv.slice(2);
const COLLECTION = args[0];
const KNOWN = new Set(["nawawi-arbain", "qudsi-arbain", "shahwaliullah-arbain"]);
if (!COLLECTION || !KNOWN.has(COLLECTION)) {
  console.error(`usage: node generate-recitation.mjs <${[...KNOWN].join("|")}> <report numbers | --all>`);
  process.exit(1);
}
const rest = args.slice(1);
const corpus = JSON.parse(readFileSync(`hadithusx/data/${COLLECTION}.json`, "utf8"));
const wanted = rest.includes("--all")
  ? corpus.witnesses.map((w) => w.structuredLocator.reportNumber)
  : rest.map(Number).filter((n) => Number.isInteger(n));

if (!wanted.length) {
  console.error("no report numbers given (pass numbers or --all)");
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
  const stem = `${COLLECTION}.${String(n).padStart(3, "0")}`;
  if (existsSync(`${OUT}/${stem}.mp3`) && existsSync(`${OUT}/${stem}.json`)) {
    console.log(`${stem}: already generated, skipped`);
    continue;
  }

  const text = witness.matn.diplomatic;
  // A trailing full stop gives the model a clean sentence-close (verified by the
  // qusx-audio A/B tests: trailing "." helps, leading "." hurts). This is a
  // generation-only tweak — the stored husx matn and its tokens are untouched;
  // the period sits after the last token, so the timestamp mapping still lines up.
  const sendText = /[.!?؟۔]$/u.test(text) ? text : text + ".";
  // Retry transient network failures (connect timeouts) so one blip doesn't kill
  // a long batch. A non-ok HTTP status still stops the run (real API error).
  let res;
  for (let attempt = 1; ; attempt++) {
    try {
      res = await fetch(
        `https://api.elevenlabs.io/v1/text-to-speech/${VOICE}/with-timestamps?output_format=mp3_44100_128`,
        {
          method: "POST",
          headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
          body: JSON.stringify({
            text: sendText,
            model_id: MODEL,
            voice_settings: { stability: 0.6, similarity_boost: 0.8, speed: 0.9 }
          })
        }
      );
      break;
    } catch (err) {
      if (attempt >= 4) { console.error(`${stem}: network failed after ${attempt} tries: ${err.message}`); process.exit(1); }
      console.error(`${stem}: network blip (attempt ${attempt}), retrying…`);
      await new Promise((r) => setTimeout(r, 2000 * attempt));
    }
  }
  if (!res.ok) {
    console.error(`${stem}: API ${res.status} ${(await res.text()).slice(0, 200)}`);
    break;                       // stop rather than burn credits on a broken run
  }
  const data = await res.json();
  const { characters, character_start_times_seconds: starts, character_end_times_seconds: ends } = data.alignment;

  // If ElevenLabs altered the text, character offsets no longer address our
  // tokens. Compare against what we sent (matn + trailing "."). Token spans are
  // found within `text`, which is a prefix of sendText, so their offsets are
  // identical in both — the appended period only adds one trailing char we ignore.
  const returned = characters.join("");
  if (returned !== sendText) {
    console.error(`${stem}: MISMATCH - model returned ${returned.length} chars, sent ${sendText.length}; skipping mapping`);
    writeFileSync(`${OUT}/${stem}.mismatch.txt`, `sent:\n${sendText}\n\nreturned:\n${returned}\n`);
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
