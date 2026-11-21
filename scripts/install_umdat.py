#!/usr/bin/env python3
"""Install the user-supplied Umdat al-Ahkam ZIP into this feature branch.
Usage: python scripts/install_umdat.py /path/to/umdat-al-ahkam-main-reader.zip
"""
import json, pathlib, sys, zipfile
if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/install_umdat.py PATH_TO_ZIP")
repo = pathlib.Path(__file__).resolve().parents[1]
target = repo / "public" / "umdat-al-ahkam"
target.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(sys.argv[1]) as archive:
    names = [n for n in archive.namelist()
             if n.startswith("umdat-al-ahkam/") and n.endswith(".json")]
    if len(names) != 83:
        raise ValueError(f"Expected 83 JSON files, got {len(names)}")
    for name in names:
        dest = target / pathlib.PurePosixPath(name).name
        data = archive.read(name)
        json.loads(data)
        dest.write_bytes(data)
index = json.loads((target / "index.json").read_text())
numbers = []
for i in range(1, 81):
    book = json.loads((target / f"book-{i}.json").read_text())
    if book["book"] != i:
        raise ValueError(f"Wrong chapter number: {i}")
    numbers.extend(int(h["n"]) for h in book["hadith"])
if len(index["books"]) != 80 or sorted(numbers) != list(range(1, 415)):
    raise ValueError("Book count or hadith numbering mismatch")
print("Validated 80 chapters and 414 hadith. Commit public/umdat-al-ahkam/ to the feature branch.")
