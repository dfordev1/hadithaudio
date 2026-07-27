// Generate hadith audio + character timestamps via ElevenLabs.
// Usage: node generate.mjs <model_id> <out_name>
import { readFileSync, writeFileSync, mkdirSync } from 'fs';

const apiKey = readFileSync('.env', 'utf8').match(/ELEVENLABS_API_KEY=(\S+)/)[1];
const VOICE_ID = 'xvhpbk8otnNHtT3fjCpr'; // Omar – Premium Arabic Voice

const [modelId = 'eleven_turbo_v2_5', outName = 'sample'] = process.argv.slice(2);

const hadith = JSON.parse(readFileSync('hadith.json', 'utf8'));

const res = await fetch(
  `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/with-timestamps?output_format=mp3_44100_128`,
  {
    method: 'POST',
    headers: { 'xi-api-key': apiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: hadith.arabic,
      model_id: modelId,
      voice_settings: { stability: 0.6, similarity_boost: 0.8, speed: 0.9 },
    }),
  }
);
if (!res.ok) {
  console.error('API error', res.status, await res.text());
  process.exit(1);
}
const data = await res.json();

mkdirSync('public/audio', { recursive: true });
writeFileSync(`public/audio/${outName}.mp3`, Buffer.from(data.audio_base64, 'base64'));

// Collapse character timings into word timings for the player.
const { characters, character_start_times_seconds: starts, character_end_times_seconds: ends } = data.alignment;
const words = [];
let cur = null;
characters.forEach((ch, i) => {
  if (/\s/.test(ch)) { if (cur) { words.push(cur); cur = null; } return; }
  if (!cur) cur = { text: ch, start: starts[i], end: ends[i] };
  else { cur.text += ch; cur.end = ends[i]; }
});
if (cur) words.push(cur);

writeFileSync(`public/audio/${outName}.json`, JSON.stringify({ ...hadith, model: modelId, words }, null, 2));
console.log(`OK: ${words.length} words, ${ends[ends.length - 1].toFixed(1)}s -> public/audio/${outName}.mp3/.json`);
