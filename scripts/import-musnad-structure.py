"""Import Musnad Ahmad's verified two-level chapter structure into its web index."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Full ahmed.json with chapters and hadiths")
    parser.add_argument("index", type=Path, help="Hadith.to public/musnad-ahmad/index.json")
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    chapters = {row["id"]: row for row in source["chapters"]}

    sections = []
    previous = None
    for hadith in source["hadiths"]:
        chapter_id = hadith["chapterId"]
        if chapter_id == previous:
            continue
        chapter = chapters[chapter_id]
        parent = chapters.get(chapter.get("parentId"))
        sections.append({
            "from": int(hadith["idInBook"]),
            "chapterId": chapter_id,
            "sectionAr": chapter["names"].get("ar") or "",
            "sectionEn": chapter["names"].get("en") or "",
            "groupAr": (parent or {}).get("names", {}).get("ar") or "",
            "groupEn": (parent or {}).get("names", {}).get("en") or "",
        })
        previous = chapter_id

    if len(source["hadiths"]) != 27_648 or len(index["reportBook"]) != 27_648:
        raise SystemExit("Refusing import: corpus counts are not both 27,648")

    index["sections"] = sections
    args.index.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Imported {len(sections):,} verified section transitions")


if __name__ == "__main__":
    main()
