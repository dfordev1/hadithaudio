import { readFileSync } from "node:fs";

const files = {};
for (const [path, filename, type] of [
  ["/admin/", "index.html", "text/html"],
  ["/admin/studio.js", "studio.js", "text/javascript"],
  ["/admin/studio.css", "studio.css", "text/css"],
]) {
  files[path] = { body:readFileSync(new URL("../cms/admin/" + filename, import.meta.url), "utf8"), type:type + "; charset=utf-8" };
}
process.stdout.write("const STUDIO_FILES = " + JSON.stringify(files) + ";\n" +
  readFileSync(new URL("../cms/worker.mjs", import.meta.url), "utf8"));
