#!/usr/bin/env python3
"""Build full-word-stream Tirmidhi clips, timing maps, and reader data."""

from __future__ import annotations

import argparse, gzip, json, re, subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = Path(r"C:\Users\Dv\Downloads\tirmidhi.alignment.json.gz")
AUDIO = Path(r"C:\Users\Dv\Downloads\Tirmidi")
BASE = ROOT / "qc" / "tirmidhi-full"
CLIPS, TIMINGS = BASE / "clips", BASE / "timings"

def norm(text):
    text = re.sub(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06edـ]", "", text or "")
    text = re.sub(r"[^\u0621-\u063a\u0641-\u064a\u0671]", "", text)
    return text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")

def stem(number): return str(number).zfill(4)

def load_reports():
    with gzip.open(MASTER, "rt", encoding="utf-8") as handle:
        return json.load(handle)["reports"]

def allocate(tokens, duration):
    changed = 0; i = 0
    while i < len(tokens):
        if tokens[i].get("start") is not None: i += 1; continue
        first = i
        while i + 1 < len(tokens) and tokens[i + 1].get("start") is None: i += 1
        last = i
        left = next((x for x in range(first - 1, -1, -1) if tokens[x].get("end") is not None), None)
        right = next((x for x in range(last + 1, len(tokens)) if tokens[x].get("start") is not None), None)
        start = float(tokens[left]["end"]) if left is not None else 0.0
        end = float(tokens[right]["start"]) if right is not None else duration
        if end <= start:
            start = float(tokens[left]["start"]) if left is not None else 0.0
            end = float(tokens[right]["end"]) if right is not None else duration
        if end > start:
            group = tokens[first:last + 1]; weights = [max(1, len(norm(x["text"]))) for x in group]
            cursor = start; total = sum(weights)
            for offset, (item, weight) in enumerate(zip(group, weights)):
                stop = end if offset == len(group) - 1 else cursor + (end - start) * weight / total
                item.update(displayStart=round(cursor, 4), displayEnd=round(stop, 4), timingEvidence="derived_between_acoustic_constraints")
                cursor = stop; changed += 1
        i += 1
    return changed

def pieces(report):
    rows = [dict(item) for item in report.get("segments", [])]
    if not rows: return []
    rows[0]["start"] = max(0.0, float(rows[0]["start"]) - .18)
    rows[-1]["end"] = float(rows[-1]["end"]) + .28
    return rows

def relative_time(token, rows, field):
    value = token.get(field); recording = token.get("recording")
    if value is None or recording is None: return None
    elapsed = 0.0
    for row in rows:
        if str(row["recording"]).zfill(2) == str(recording).zfill(2):
            return round(elapsed + float(value) - float(row["start"]), 4)
        elapsed += float(row["end"]) - float(row["start"])
    return None

def convert(report, make_clip):
    if report["status"] == "empty_source": return {"status":"empty_source"}
    number = report["report"]["readerHadithNumber"]
    rows = pieces(report)
    if not rows: return {"n":number,"status":"synthetic_required"}
    duration = sum(float(x["end"]) - float(x["start"]) for x in rows)
    tokens = []
    for position, token in enumerate(report["tokens"], 1):
        tokens.append({"id":f"uh:token:tirmidhi.{stem(number)}:{position:04d}","position":position,"text":token["text"],
            "start":relative_time(token,rows,"start"),"end":relative_time(token,rows,"end"),"asrText":token.get("asrText"),
            "similarity":token.get("similarity"),"status":token.get("status")})
    derived = allocate(tokens, duration); CLIPS.mkdir(parents=True,exist_ok=True); TIMINGS.mkdir(parents=True,exist_ok=True)
    name=f"{stem(number)}.mp3"
    payload={"kind":"tirmidhi-full-word-stream-v1","collection":"tirmidhi","n":number,"audio":name,"duration":round(duration,4),
        "sourceSegments":rows,"coverage":report.get("coverage"),"meanSimilarity":report.get("meanSimilarity"),"status":report.get("status"),
        "derivedDisplayTokens":derived,"disclosure":"Derived display timings are constrained by neighbouring acoustic matches.","tokens":tokens}
    (TIMINGS/f"n{stem(number)}.json").write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    destination=CLIPS/name
    if make_clip and (not destination.exists() or not destination.stat().st_size):
        command=["ffmpeg","-hide_banner","-loglevel","error","-y"]
        for row in rows:
            command += ["-ss",f'{float(row["start"]):.4f}',"-t",f'{float(row["end"])-float(row["start"]):.4f}',"-i",str(AUDIO/row["audioFile"])]
        if len(rows)>1:
            command += ["-filter_complex","".join(f"[{i}:a]" for i in range(len(rows)))+f"concat=n={len(rows)}:v=0:a=1[out]","-map","[out]"]
        command += ["-map_metadata","-1","-ac","1","-ar","24000","-c:a","libmp3lame","-b:a","32k",str(destination)]
        subprocess.run(command,check=True)
    return {"n":number,"status":"original","duration":duration,"derived":derived,"tokens":len(tokens)}

def merge_reader(reports):
    sources={str(r["report"]["readerHadithNumber"]):r for r in reports if r["status"]!="empty_source"}
    pool=defaultdict(Counter)
    index=json.loads((ROOT/"public"/"tirmidhi"/"index.json").read_text(encoding="utf-8"))
    for path in (ROOT/"public"/"gloss").glob("tirmidhi-*.json"):
        n=path.stem.split("-",1)[1]; book=index["reportBook"].get(n)
        if not book: continue
        data=json.loads((ROOT/"public"/"tirmidhi"/f"book-{book}.json").read_text(encoding="utf-8"))
        item=next((x for x in data["hadith"] if str(x["n"])==n),None)
        if not item: continue
        gloss=json.loads(path.read_text(encoding="utf-8")).get("glosses",{})
        for token in item.get("tokens",[]):
            value=gloss.get(token["id"]); key=norm(token["text"])
            if value and key: pool[key][json.dumps(value,ensure_ascii=False,sort_keys=True)]+=1
    changed=glossed=0
    for book_path in sorted((ROOT/"public"/"tirmidhi").glob("book-*.json")):
        book=json.loads(book_path.read_text(encoding="utf-8"))
        for item in book["hadith"]:
            n=str(item["n"]); source=sources[n]; new=[]; glosses={}
            for position,token in enumerate(source["tokens"],1):
                tid=f"uh:token:tirmidhi.{stem(n)}:{position:04d}"; new.append({"id":tid,"text":token["text"]})
                candidates=pool.get(norm(token["text"]))
                if candidates: glosses[tid]=json.loads(candidates.most_common(1)[0][0]); glossed+=1
            item.update(tokens=new,isnad="",fullWordStream=True)
            gp=ROOT/"public"/"gloss"/f"tirmidhi-{n}.json"; gd=json.loads(gp.read_text(encoding="utf-8")); gd["glosses"]=glosses
            gd["note"]="Full canonical isnad and matn word stream; pooled machine glosses."
            gp.write_text(json.dumps(gd,ensure_ascii=False,separators=(",",":")),encoding="utf-8"); changed+=1
        book_path.write_text(json.dumps(book,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    return {"reports":changed,"pooledGlosses":glossed,"poolWords":len(pool)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--clips",action="store_true"); ap.add_argument("--merge-reader",action="store_true"); ap.add_argument("--workers",type=int,default=8); args=ap.parse_args()
    reports=load_reports()
    with ThreadPoolExecutor(max_workers=args.workers) as pool: results=list(pool.map(lambda r:convert(r,args.clips),reports))
    summary={"sourceRows":len(results),"original":sum(x["status"]=="original" for x in results),"syntheticRequired":sum(x["status"]=="synthetic_required" for x in results),"emptySource":sum(x["status"]=="empty_source" for x in results),"derivedDisplayTokens":sum(x.get("derived",0) for x in results)}
    if args.merge_reader: summary["reader"]=merge_reader(reports)
    BASE.mkdir(parents=True,exist_ok=True); (BASE/"release-manifest.json").write_text(json.dumps({"summary":summary,"items":results},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
