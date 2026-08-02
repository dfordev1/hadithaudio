#!/usr/bin/env python3
"""Compact full-stream glosses into collection vocabulary pools for runtime alignment."""
import json,re
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def norm(text):
 text=re.sub(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06edـ]","",text or ""); text=re.sub(r"[^\u0621-\u063a\u0641-\u064a\u0671]","",text)
 return text.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه")
for coll in ("malik","tirmidhi"):
 pool=defaultdict(Counter)
 for bp in (ROOT/"public"/coll).glob("book-*.json"):
  for item in json.loads(bp.read_text(encoding="utf-8"))["hadith"]:
   gp=ROOT/"public"/"gloss"/f"{coll}-{item['n']}.json"; gloss=json.loads(gp.read_text(encoding="utf-8")).get("glosses",{})
   for token in item["tokens"]:
    value=gloss.get(token["id"]); key=norm(token["text"])
    if value and key: pool[key][json.dumps(value,ensure_ascii=False,sort_keys=True)]+=1
 words={key:json.loads(values.most_common(1)[0][0]) for key,values in sorted(pool.items())}
 payload={"kind":f"{coll}-full-stream-gloss-pool-v1","collection":coll,"reviewState":"machine-pooled","words":words}
 path=ROOT/"public"/f"{coll}-isnad-word-pool.json"; path.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
 print(coll,len(words),path.stat().st_size)
