#!/usr/bin/env node
/**
 * List objects in the hadithaudio R2 bucket (optional prefix).
 * Loads CF_API_TOKEN / CF_ACCOUNT_ID from env or .env.local (never commit tokens).
 *
 * Usage:
 *   node scripts/r2-list-hadithaudio.mjs
 *   node scripts/r2-list-hadithaudio.mjs bukhari/
 *   node scripts/r2-list-hadithaudio.mjs --prefix bukhari/ --limit 50
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

function loadEnvLocal() {
  const p = path.join(root, ".env.local");
  if (!fs.existsSync(p)) return;
  for (const line of fs.readFileSync(p, "utf8").split(/\r?\n/)) {
    const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!m) continue;
    if (!process.env[m[1]]) process.env[m[1]] = m[2];
  }
}

loadEnvLocal();

const token = process.env.CF_API_TOKEN || process.env.CLOUDFLARE_API_TOKEN;
const accountId = process.env.CF_ACCOUNT_ID || process.env.CLOUDFLARE_ACCOUNT_ID;
const bucket = process.env.R2_BUCKET || "hadithaudio";

if (!token || !accountId) {
  console.error("Missing CF_API_TOKEN / CF_ACCOUNT_ID (set env or .env.local)");
  process.exit(1);
}

const args = process.argv.slice(2);
let prefix = "";
let limit = Infinity;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--prefix") prefix = args[++i] || "";
  else if (args[i] === "--limit") limit = Number(args[++i]) || 100;
  else if (!args[i].startsWith("-")) prefix = args[i];
}

async function listAll() {
  const objects = [];
  let cursor;
  do {
    const params = new URLSearchParams({ per_page: "1000" });
    if (prefix) params.set("prefix", prefix);
    if (cursor) params.set("cursor", cursor);
    const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/r2/buckets/${bucket}/objects?${params}`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const body = await res.json();
    if (!body.success) {
      console.error(JSON.stringify(body.errors || body, null, 2));
      process.exit(1);
    }
    for (const obj of body.result || []) {
      objects.push(obj);
      if (objects.length >= limit) break;
    }
    if (objects.length >= limit) break;
    cursor = body.result_info?.is_truncated ? body.result_info.cursor : null;
  } while (cursor);

  return objects;
}

const objects = await listAll();
const shown = objects.slice(0, Math.min(objects.length, limit === Infinity ? 30 : limit));
console.log(
  JSON.stringify(
    {
      bucket,
      prefix: prefix || "(all)",
      count: objects.length,
      totalBytes: objects.reduce((sum, object) => sum + Number(object.size || 0), 0),
      truncated: objects.length >= limit,
      sampleKeys: shown.map((o) => o.key),
      sample: shown.slice(0, 10).map((o) => ({
        key: o.key,
        size: o.size,
        last_modified: o.last_modified,
      })),
    },
    null,
    2
  )
);


