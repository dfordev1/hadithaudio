#!/usr/bin/env python3
"""Generate crawlable report pages and a complete sitemap for Hadith.to."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
OUT = PUBLIC / "h"
ORIGIN = "https://www.hadith.to"
COLLECTIONS = {
    "bukhari": "Sahih al-Bukhari",
    "muslim": "Sahih Muslim",
    "malik": "Muwatta Malik",
    "tirmidhi": "Jami at-Tirmidhi",
    "abudawud": "Sunan Abi Dawud",
    "nasai": "Sunan an-Nasa'i",
    "ibnmajah": "Sunan Ibn Majah",
}


def page(slug: str, name: str, book: str, report: dict) -> str:
    number = str(report["n"])
    canonical = f"{ORIGIN}/h/{slug}/{number}/"
    reader = f"{ORIGIN}/#{slug}:{number}"
    isnad = str(report.get("isnad") or "")
    matn = " ".join(str(token.get("text") or "") for token in report.get("tokens", []))
    arabic = " ".join(part for part in (isnad, matn) if part).strip()
    title = f"{name} {number} — Hadith.to"
    excerpt = " ".join(arabic.split())[:700]
    description = excerpt[:220]
    structured = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{name} {number}",
        "inLanguage": "ar",
        "url": canonical,
        "isPartOf": {"@type": "CollectionPage", "name": name, "url": ORIGIN},
    }
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{description}"><link rel="canonical" href="{canonical}">
<meta property="og:type" content="article"><meta property="og:title" content="{title}"><meta property="og:description" content="{description}"><meta property="og:url" content="{canonical}">
<script type="application/ld+json">{structured}</script>
<style>body{{margin:0;background:#f7f3eb;color:#211d18;font:17px/1.7 system-ui,sans-serif}}main{{max-width:800px;margin:auto;padding:48px 22px}}.k{{color:#746b5d}}h1{{font-size:1.35rem}}.ar{{font-family:"Noto Naskh Arabic","Amiri",serif;font-size:2rem;line-height:2.15;text-align:right}}a{{display:inline-block;margin-top:28px;color:inherit;font-weight:700}}</style>
</head><body><main><div class="k">{name} · Book {book}</div><h1>Hadith {number}</h1><article class="ar" lang="ar" dir="rtl">{arabic}</article><a href="{reader}">Open word-by-word reader and audio →</a></main></body></html>""".format(
        title=html.escape(title), description=html.escape(description), canonical=canonical,
        structured=json.dumps(structured, ensure_ascii=False).replace("</", "<\/"),
        name=html.escape(name), book=html.escape(str(book)), number=html.escape(number),
        arabic=html.escape(excerpt), reader=reader,
    )


def main() -> int:
    if OUT.exists():
        import shutil
        shutil.rmtree(OUT)
    urls = [f"{ORIGIN}/"]
    count = 0
    for slug, name in COLLECTIONS.items():
        for source in sorted((PUBLIC / slug).glob("book-*.json")):
            data = json.loads(source.read_text(encoding="utf-8"))
            book = str(data.get("book", source.stem.removeprefix("book-")))
            for report in data.get("hadith", []):
                number = str(report["n"])
                target = OUT / slug / number / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(page(slug, name, book, report), encoding="utf-8")
                urls.append(f"{ORIGIN}/h/{slug}/{number}/")
                count += 1
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap.extend(f"  <url><loc>{html.escape(url)}</loc></url>" for url in urls)
    sitemap.append("</urlset>")
    (PUBLIC / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")
    print(json.dumps({"pages": count, "sitemapUrls": len(urls)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
