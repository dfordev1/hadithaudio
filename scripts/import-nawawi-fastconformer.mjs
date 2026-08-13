import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const repo = String.raw`C:\Users\Dv\hadithaudio\_hadithto-source-20260809`;
const source = String.raw`C:\Users\Dv\hadithaudio\nawawi42-fastconformer`;
const out = join(repo, "public", "recitation");

for (let number = 1; number <= 42; number++) {
  const nn = String(number).padStart(2, "0");
  const nnn = String(number).padStart(3, "0");
  const report = JSON.parse(
    readFileSync(join(source, "reports", `${nn}.json`), "utf8"),
  );
  const tokens = report.tokens.map((token, index) => ({
    id: `uh:token:nawawi-arbain.${nnn}:${String(index + 1).padStart(4, "0")}`,
    position: index + 1,
    text: token.text,
    start: token.start,
    end: token.end,
  }));
  const payload = {
    qusxAudio: "0.2-fastconformer-full-recitation",
    kind: "recitation",
    language: "ar",
    witness: `uh:witness:nawawi-arbain.${nnn}`,
    locator: `hadith ${number}`,
    model: "tilawa-fastconformer-ctc",
    audio: `nawawi-arbain.${nnn}.mp3`,
    duration: report.audioDurationSeconds,
    audioStart: report.audioStart,
    diplomatic: tokens.map((token) => token.text).join(" "),
    tokens,
  };
  writeFileSync(
    join(out, `nawawi-arbain.${nnn}.json`),
    `${JSON.stringify(payload, null, 2)}\n`,
    "utf8",
  );
  copyFileSync(
    join(source, "audio", `${nn}.mp3`),
    join(out, `nawawi-arbain.${nnn}.mp3`),
  );
}

console.log("Imported 42 Nawawi full-recitation timing reports and MP3 files.");
