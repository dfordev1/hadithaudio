#!/usr/bin/env python3
"""Generate disclosed ElevenLabs audio only for reports absent from source recordings."""
from __future__ import annotations
import argparse, base64, gzip, json, os, subprocess, time, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; VOICE="JBFqnCBsd6RMkjVDRZzb"; TEMPO=.90
def env(path):
    for p in (path,ROOT/".env.local",ROOT/".env"):
        if p and Path(p).exists():
            for line in Path(p).read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
def stem(n): return str(n).zfill(4)
def sources(collection):
    if collection=="malik":
        for p in sorted((ROOT/"qc"/"muwatta-full"/"alignment").glob("*/reports/*.json")):
            d=json.loads(p.read_text(encoding="utf-8"))
            if d.get("start") is None: yield d["report"]["hadithNumber"],d["tokens"]
    else:
        with gzip.open(r"C:\Users\Dv\Downloads\tirmidhi.alignment.json.gz","rt",encoding="utf-8") as f: rows=json.load(f)["reports"]
        for d in rows:
            if d["status"]!="empty_source" and not d.get("segments"): yield d["report"]["readerHadithNumber"],d["tokens"]
def generate(collection,n,tokens,key):
    base=ROOT/"qc"/("muwatta-full" if collection=="malik" else "tirmidhi-full")
    out=base/"generated-clips"; timing=base/"generated-timings"; out.mkdir(parents=True,exist_ok=True); timing.mkdir(parents=True,exist_ok=True)
    audio=out/f"{stem(n)}.mp3"; sidecar=timing/f"n{stem(n)}.json"
    if audio.exists() and sidecar.exists(): return {"n":n,"status":"existing"}
    parts=[]; ranges=[]; cursor=0
    for token in tokens:
        if parts: parts.append(" "); cursor+=1
        value=token["text"]; start=cursor; parts.append(value); cursor+=len(value); ranges.append((start,cursor))
    text="".join(parts)
    body=json.dumps({"text":text,"model_id":"eleven_multilingual_v2","voice_settings":{"stability":.86,"similarity_boost":.72,"style":0,"use_speaker_boost":True}}).encode()
    req=urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps?output_format=mp3_22050_32",data=body,method="POST",headers={"xi-api-key":key,"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=240) as response: result=json.load(response)
    raw=out/f"{stem(n)}.raw.mp3"; raw.write_bytes(base64.b64decode(result["audio_base64"]))
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(raw),"-filter:a",f"atempo={TEMPO}","-c:a","libmp3lame","-b:a","32k",str(audio)],check=True); raw.unlink()
    duration=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(audio)],text=True))
    a=result["alignment"]; starts=a["character_start_times_seconds"]; ends=a["character_end_times_seconds"]; mapped=[]
    for position,(token,(lo,hi)) in enumerate(zip(tokens,ranges),1):
        valid=[i for i in range(lo,min(hi,len(starts))) if text[i].strip()]
        start=(starts[valid[0]] if valid else 0)/TEMPO; end=(ends[valid[-1]] if valid else start*TEMPO)/TEMPO
        mapped.append({"id":f"uh:token:{collection}.{stem(n)}:{position:04d}","position":position,"text":token["text"],"start":round(min(duration,start),4),"end":round(min(duration,max(start,end)),4),"timingEvidence":"elevenlabs_character_alignment"})
    payload={"kind":f"{collection}-synthetic-gap-v1","collection":collection,"n":n,"audio":audio.name,"duration":round(duration,4),"status":"synthetic_audio_not_in_original_recording","synthetic":True,"provider":"ElevenLabs","model":"eleven_multilingual_v2","voiceId":VOICE,"tempo":TEMPO,"disclosure":"Generated recitation; this report is not present in the supplied original recording.","tokens":mapped}
    sidecar.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8"); return {"n":n,"status":"generated","duration":duration,"tokens":len(mapped)}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("collection",choices=["malik","tirmidhi"]); ap.add_argument("--env-file",type=Path); args=ap.parse_args(); env(args.env_file)
    key=os.environ.get("ELEVENLABS_API_KEY");
    if not key: raise SystemExit("ELEVENLABS_API_KEY is not configured")
    results=[]
    for i,(n,tokens) in enumerate(sources(args.collection),1):
        try: result=generate(args.collection,n,tokens,key)
        except Exception as exc: result={"n":n,"status":"error","error":str(exc)}
        results.append(result); print(f"{args.collection} {i}: {n} {result['status']}",flush=True)
        if result["status"]=="error": time.sleep(5)
    key=""; print(json.dumps({"total":len(results),"generated":sum(x['status']=='generated' for x in results),"existing":sum(x['status']=='existing' for x in results),"errors":[x for x in results if x['status']=='error']},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
