#!/usr/bin/env python3
"""Upload Muwatta or Tirmidhi report audio/timing pairs to Cloudflare R2."""
from __future__ import annotations
import argparse,json,os,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
def load_env(path):
    for p in (path,ROOT/".env.local",ROOT/".env"):
        if p and Path(p).exists():
            for line in Path(p).read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
def assets(collection):
    base=ROOT/"qc"/("muwatta-full" if collection=="malik" else "tirmidhi-full")
    rows=[]
    for timing in sorted((base/"timings").glob("n*.json")):
        data=json.loads(timing.read_text(encoding="utf-8")); audio=base/"clips"/data["audio"]
        if not audio.exists(): continue
        rows += [(audio,f"{collection}/{data['audio']}","audio/mpeg"),(timing,f"{collection}-timings/{timing.name}","application/json; charset=utf-8")]
    for timing in sorted((base/"generated-timings").glob("n*.json")):
        data=json.loads(timing.read_text(encoding="utf-8")); audio=base/"generated-clips"/data["audio"]
        if not audio.exists(): continue
        rows += [(audio,f"{collection}/{data['audio']}","audio/mpeg"),(timing,f"{collection}-timings/{timing.name}","application/json; charset=utf-8")]
    return rows
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("collection",choices=["malik","tirmidhi"]); ap.add_argument("--env-file",type=Path); ap.add_argument("--concurrency",type=int,default=8); ap.add_argument("--missing-only",action="store_true"); ap.add_argument("--dry-run",action="store_true"); args=ap.parse_args(); load_env(args.env_file)
    token=os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN"); account=os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID"); bucket=os.environ.get("R2_BUCKET","hadithaudio")
    if not token or not account: raise SystemExit("Missing Cloudflare configuration")
    rows=assets(args.collection); endpoint=f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
    if args.missing_only:
        remote=set()
        with httpx.Client(timeout=120) as client:
            for prefix in (f"{args.collection}/",f"{args.collection}-timings/"):
                cursor=None
                while True:
                    params={"per_page":"1000","prefix":prefix};
                    if cursor: params["cursor"]=cursor
                    for attempt in range(7):
                        response=client.get(endpoint,params=params,headers={"Authorization":f"Bearer {token}"})
                        if response.status_code != 429 and response.status_code < 500: break
                        time.sleep(min(30,2**attempt))
                    response.raise_for_status(); body=response.json()
                    if not body.get("success",True): raise RuntimeError(body.get("errors") or body)
                    remote.update(x["key"] for x in body.get("result",[])); info=body.get("result_info") or {}
                    if not info.get("is_truncated"): break
                    cursor=info.get("cursor")
        rows=[r for r in rows if r[1] not in remote]
    print(json.dumps({"objects":len(rows),"audio":sum(k.endswith('.mp3') for _,k,_ in rows),"timings":sum(k.endswith('.json') for _,k,_ in rows),"bytes":sum(p.stat().st_size for p,_,_ in rows)},indent=2),flush=True)
    if args.dry_run:return
    upload_client=httpx.Client(timeout=180,limits=httpx.Limits(max_connections=max(20,args.concurrency*2),max_keepalive_connections=max(10,args.concurrency)))
    def upload(row):
        path,key,mime=row
        content=path.read_bytes()
        for attempt in range(7):
            response=upload_client.put(f"{endpoint}/{key}",content=content,headers={
                "Authorization":f"Bearer {token}",
                "Content-Type":mime,
                "Cache-Control":"public, max-age=31536000, immutable",
            })
            if response.status_code!=429 and response.status_code<500: response.raise_for_status(); return key
            time.sleep(min(30,2**attempt))
        raise RuntimeError(key)
    failed=[]
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures={pool.submit(upload,r):r for r in rows}
        for i,f in enumerate(as_completed(futures),1):
            try:f.result()
            except Exception as e:failed.append((futures[f][1],str(e)))
            if i%100==0 or i==len(rows):print(f"{args.collection}: {i}/{len(rows)} failed={len(failed)}",flush=True)
    upload_client.close()
    if failed: print(json.dumps(failed[:50],indent=2)); raise SystemExit(1)
if __name__=="__main__":main()
