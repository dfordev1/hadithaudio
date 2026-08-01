#!/usr/bin/env python3
"""Pilot sequential Abū Dāwūd aligner using QuranReciteToText phase-1 ASR.

Runs on a bounded prefix of one audio file. It emits hadith-level boundaries and
word-level ASR timestamps only where the ASR-to-reference match is strong. It
never fabricates word timings by proportional allocation.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, unicodedata
from pathlib import Path
from difflib import SequenceMatcher

AR_DIAC = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
NON_AR = re.compile(r"[^\u0621-\u063a\u0641-\u064a ]+")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = AR_DIAC.sub("", s)
    s = s.translate(str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ٱ":"ا","ى":"ي","ؤ":"و","ئ":"ي","ة":"ه"}))
    s = NON_AR.sub(" ", s)
    return " ".join(s.split())


def load_corpus(path: Path):
    data=json.loads(path.read_text(encoding='utf-8'))
    hs=data.get('hadiths', data if isinstance(data,list) else [])
    out=[]
    for h in hs:
        n=h.get('hadithnumber', h.get('arabicnumber', h.get('id')))
        text=h.get('text', h.get('arabic',''))
        try: n=int(float(n))
        except Exception: continue
        if text:
            out.append({'hadithnumber':n,'arabic':text,'norm':norm(text),'words':text.split()})
    out.sort(key=lambda x:x['hadithnumber'])
    return out


def best_span(hyp: str, refs, start_idx: int, lookahead=16):
    hn=norm(hyp)
    if not hn: return None
    best=None
    for i in range(start_idx, min(len(refs), start_idx+lookahead)):
        joined=''
        for j in range(i,min(len(refs),i+3)):
            joined=(joined+' '+refs[j]['norm']).strip()
            score=SequenceMatcher(None, hn, joined).ratio()
            a=set(hn.split()); b=set(joined.split())
            jac=len(a&b)/max(1,len(a|b))
            total=.65*score+.35*jac
            if best is None or total>best['score']:
                best={'i':i,'j':j,'score':total,'char_score':score,'jaccard':jac}
    return best


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--audio',required=True,type=Path)
    ap.add_argument('--corpus',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--limit-seconds',type=float,default=900)
    ap.add_argument('--start-hadith',type=int,default=1)
    args=ap.parse_args()

    refs=load_corpus(args.corpus)
    if not refs: raise SystemExit('empty corpus')
    start_idx=next((i for i,h in enumerate(refs) if h['hadithnumber']>=args.start_hadith),0)

    sys.path.insert(0,str(Path.cwd()))
    from src.phase1_transcribe.stream import run_asr_cpu
    from src.core import sdk_adapt

    pilot=args.out.with_suffix('.pilot.wav')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(args.audio),'-t',str(args.limit_seconds),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(pilot)],check=True)

    regions, emissions, stage_metrics, asr_time = run_asr_cpu(str(pilot),16000,'Base')
    intervals=sdk_adapt.intervals_from_regions(regions)
    raw=[]
    cursor=start_idx
    accepted=[]
    for k,it in enumerate(intervals):
        get=lambda name,default=None: getattr(it,name,it.get(name,default) if isinstance(it,dict) else default)
        st=float(get('start',get('start_time',0)))
        en=float(get('end',get('end_time',0)))
        txt=str(get('text',get('transcribed_text','')) or '')
        m=best_span(txt,refs,cursor)
        row={'chunk':k+1,'start':st,'end':en,'transcribed_text':txt,'match':m}
        raw.append(row)
        if m and m['score']>=0.25 and m['i']>=cursor:
            accepted.append(row)
            cursor=max(cursor,m['j']+1)

    by={}
    for r in accepted:
        m=r['match']
        for idx in range(m['i'],m['j']+1):
            n=refs[idx]['hadithnumber']
            e=by.setdefault(n,{'hadithnumber':n,'arabic':refs[idx]['arabic'],'start':r['start'],'end':r['end'],'anchors':[]})
            e['start']=min(e['start'],r['start']); e['end']=max(e['end'],r['end'])
            e['anchors'].append({'chunk':r['chunk'],'score':m['score'],'transcribed_text':r['transcribed_text']})
    hadiths=[]
    for n in sorted(by):
        e=by[n]
        e['confidence']=round(sum(a['score'] for a in e['anchors'])/len(e['anchors']),4)
        e['timestamp_level']='hadith_vad_anchor'
        e['words']=[]
        hadiths.append(e)

    payload={
      'collection':'Sunan Abi Dawud','source_audio':str(args.audio),'pilot_seconds':args.limit_seconds,
      'model':'QuranReciteToText FastConformer phase-1','asr_time_seconds':asr_time,
      'note':'Pilot: hadith spans use acoustic VAD boundaries. No proportional or fabricated word timestamps.',
      'hadiths':hadiths,'raw_chunks':raw
    }
    args.out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'hadiths':len(hadiths),'chunks':len(raw),'accepted':len(accepted),'out':str(args.out)},ensure_ascii=False))

if __name__=='__main__': main()
