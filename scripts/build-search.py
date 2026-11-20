"""Build the reader's search data from its Arabic corpus and translations."""

import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

PUBLIC = Path(__file__).resolve().parents[1] / "public"
FORTY = {
    "nawawi40": ("nawawi-arbain", 42),
    "qudsi40": ("qudsi-arbain", 40),
    "shahwaliullah40": ("shahwaliullah-arbain", 40),
}
BOOK_COLLECTIONS = (
    "bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah",
    "malik", "riyad", "musnad-ahmad", "darimi",
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def arabic(report):
    return " ".join(token["text"] for token in report["tokens"])


def edition(slug, language, upstream):
    url = (
        f"https://cdn.jsdelivr.net/gh/{upstream['repo']}@{upstream['commit']}"
        f"/editions/{language}-{slug}.min.json"
    )
    for attempt in range(3):
        try:
            with urlopen(url, timeout=25) as response:
                rows = json.load(response)["hadiths"]
            return {str(row["hadithnumber"]): row["text"] for row in rows}
        except OSError:
            if attempt == 2:
                raise


def book_records(slug):
    if slug == "darimi":
        english, urdu = {}, {}
    elif slug in {"riyad", "musnad-ahmad"}:
        translations = read_json(PUBLIC / "translation" / f"{slug}.json")["translations"]
        english = {str(row["n"]): row.get("en", "") for row in translations}
        urdu = {str(row["n"]): row.get("ur", "") for row in translations}
    else:
        upstream = read_json(PUBLIC / "translations-pinned" / "manifest.json")["upstream"]
        english = edition(slug, "eng", upstream)
        urdu = edition(slug, "urd", upstream)

    root = PUBLIC / slug
    records = {}
    for book in read_json(root / "index.json")["books"]:
        for report in read_json(root / f"book-{book['book']}.json")["hadith"]:
            number = str(report["n"])
            records.setdefault(number, [number, arabic(report), english.get(number, ""), urdu.get(number, "")])
    return list(records.values())


def forty_records(slug):
    corpus, count = FORTY[slug]
    translations = read_json(PUBLIC / "translation" / f"{slug}.json")["translations"]
    english = {row["witness"]: row.get("full") or row.get("matn", "") for row in translations}
    records = []
    for number in range(1, count + 1):
        report = read_json(PUBLIC / "recitation" / f"{corpus}.{number:03}.json")
        records.append([str(number), arabic(report), english.get(report["witness"], ""), ""])
    return records


def build(slug):
    records = forty_records(slug) if slug in FORTY else book_records(slug)
    path = PUBLIC / "search-data" / f"{slug}.json.gz"
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
    print(f"Search data for {slug}: {len(records):,} passages")


if __name__ == "__main__":
    (PUBLIC / "search-data").mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(build, (*BOOK_COLLECTIONS, *FORTY)))
