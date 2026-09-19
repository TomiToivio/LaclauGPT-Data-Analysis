"""EP24 Finland/Poland SQLite/CSV reprocessing on CSC Roihu.

Isolated from Phase 0. Uses private files, SQLite, Pandas CSV and localhost
Ollama. MongoDB and Redis are deliberately absent.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MODEL="gemma4:12b"
DEFAULT_PRIVATE_ROOT=Path("/scratch/project_2009497/LaclauGPT-Private/analysis/ep24")
PROMPT_VERSION="ep24-roihu-v1"
STAGES=("normalize","codebook","analysis","postprocess")
TEXT_FIELDS=("whisper_transcript","whisper_translated","summary_analysis","source_recording","caption","text","description","ocr_1","ocr_2","ocr_3","ocr_4","ocr_5","ocr_6")

def stable_json(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
def sha256_text(v): return hashlib.sha256(v.encode("utf-8")).hexdigest()
def clean(v):
    if v is None: return ""
    s=str(v).strip()
    return "" if s.casefold() in {"nan","none","null"} else s

def source_text(row):
    out=[]; seen=set()
    for field in TEXT_FIELDS:
        value=clean(row.get(field))
        if value and value not in seen: out.append(f"[{field}] {value}"); seen.add(value)
    return "\n".join(out)

def stable_record_id(row,*,country,source_name,row_number):
    for field in ("new_id","video_id","old_id","source_url","source_recording"):
        value=clean(row.get(field))
        if value: return f"ep24-{country.lower()}-{sha256_text(country+'|'+field+'|'+value)[:20]}"
    return f"ep24-{country.lower()}-{sha256_text(stable_json({'country':country,'source':source_name,'row':row_number,'data':row}))[:20]}"

def private_paths(root):
    b=Path(root)
    return {"root":b,"research_notes":b/"source"/"research_notes.xlsx","entities":b/"source"/"entities.xlsx","themes":b/"source"/"themes.xlsx","finland":b/"source"/"ep24_finland_dashboard_9_1_2026.csv","poland":b/"source"/"ep24_poland_dashboard_9_1_2026.csv","common_codebook":b/"codebooks"/"ep24_common_private.json","fi_codebook":b/"codebooks"/"ep24_finland_private.json","pl_codebook":b/"codebooks"/"ep24_poland_private.json","config":b/"run"/"ep24_roihu.yaml","db":b/"data"/"ep24.sqlite3","data":b/"data","logs":b/"logs","outputs":b/"outputs","qa":b/"qa","provenance":b/"provenance"}

def ensure_private_layout(root):
    p=private_paths(root)
    required=("research_notes","entities","themes","finland","poland","common_codebook","fi_codebook","pl_codebook","config")
    missing=[str(p[k]) for k in required if not p[k].exists()]
    if missing: raise FileNotFoundError("EP24 private runtime missing:\n  - "+"\n  - ".join(missing))
    for k in ("data","logs","outputs","qa","provenance"): p[k].mkdir(parents=True,exist_ok=True)
    return p

def load_yaml(path):
    import yaml
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

def _book_item(item,kind,country):
    label=clean(item.get("label") or item.get("name") or item.get("canonical"))
    if not label: return None
    aliases=item.get("aliases") or item.get("surface_forms") or []
    if isinstance(aliases,str): aliases=[aliases]
    return {"id":clean(item.get("id")) or sha256_text(f"{country}|{kind}|{label.casefold()}")[:16],"kind":clean(item.get("kind")) or kind,"label":label,"aliases":[clean(v) for v in aliases if clean(v)],"country":clean(item.get("country")) or country,"status":clean(item.get("status")) or "researcher-grounded","provenance":item.get("provenance") or item.get("source") or "private-researcher"}

def load_private_codebooks(paths):
    entries=[]; hashes=[]
    for country,key in (("COMMON","common_codebook"),("FI","fi_codebook"),("PL","pl_codebook")):
        path=paths[key]; payload=json.loads(path.read_text(encoding="utf-8")); hashes.append(hashlib.sha256(path.read_bytes()).hexdigest()); candidates=[]
        for item in payload.get("entries",[]) or []:
            if isinstance(item,dict): candidates.append((clean(item.get("kind")) or "concept",item))
        for field,kind in (("entities","entity"),("themes","theme"),("signifiers","signifier"),("actors","entity")):
            for item in payload.get(field,[]) or []: candidates.append((kind,{"label":item} if isinstance(item,str) else item))
        for kind,item in candidates:
            if isinstance(item,dict):
                value=_book_item(item,kind,country)
                if value: entries.append(value)
    index={}
    for e in entries:
        for form in [e["label"],*e["aliases"]]: index.setdefault(form.casefold(),set()).add(e["id"])
    collisions=sorted(k for k,v in index.items() if len(v)>1)
    if collisions: raise ValueError("Ambiguous EP24 codebook aliases: "+", ".join(collisions[:20]))
    return entries,sha256_text("|".join(hashes))

def match_codebook(text,entries,*,country):
    haystack=text.casefold(); out=[]
    for e in entries:
        if clean(e.get("country")).upper() not in {"","COMMON",country.upper()}: continue
        hit=next((form for form in [e["label"],*e["aliases"]] if form.casefold() in haystack),None)
        if hit: out.append({"id":e["id"],"kind":e["kind"],"label":e["label"],"matched_surface":hit,"status":e["status"],"provenance":e["provenance"]})
    return out

@dataclass(frozen=True)
class StageResult:
    record_id:str; stage:str; fingerprint:str; status:str; payload:dict[str,Any]; error:str=""

class EP24State:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db: db.executescript("""CREATE TABLE IF NOT EXISTS records(record_id TEXT PRIMARY KEY,country TEXT,language TEXT,source_file TEXT,row_number INTEGER,source_fingerprint TEXT,legacy_fingerprint TEXT,raw_json TEXT); CREATE TABLE IF NOT EXISTS stages(record_id TEXT,stage TEXT,fingerprint TEXT,status TEXT,attempt_count INTEGER,payload_json TEXT,error TEXT,updated_at REAL,PRIMARY KEY(record_id,stage)); CREATE TABLE IF NOT EXISTS failures(record_id TEXT,stage TEXT,error TEXT,updated_at REAL); CREATE TABLE IF NOT EXISTS run_metadata(key TEXT PRIMARY KEY,value TEXT);""")
    def connect(self):
        db=sqlite3.connect(self.path); db.row_factory=sqlite3.Row; return db
    def upsert(self,record_id,country,language,source_file,row_number,source_fp,legacy_fp,row):
        with self.connect() as db: db.execute("""INSERT INTO records VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET country=excluded.country,language=excluded.language,source_file=excluded.source_file,row_number=excluded.row_number,source_fingerprint=excluded.source_fingerprint,legacy_fingerprint=excluded.legacy_fingerprint,raw_json=excluded.raw_json""",(record_id,country,language,source_file,row_number,source_fp,legacy_fp,stable_json(row)))
    def cached(self,record_id,stage,fp):
        with self.connect() as db: row=db.execute("SELECT * FROM stages WHERE record_id=? AND stage=?",(record_id,stage)).fetchone()
        return json.loads(row["payload_json"]) if row and row["status"]=="ok" and row["fingerprint"]==fp else None
    def write(self,r):
        with self.connect() as db:
            prev=db.execute("SELECT attempt_count FROM stages WHERE record_id=? AND stage=?",(r.record_id,r.stage)).fetchone(); n=(prev["attempt_count"] if prev else 0)+1
            db.execute("""INSERT INTO stages VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(record_id,stage) DO UPDATE SET fingerprint=excluded.fingerprint,status=excluded.status,attempt_count=excluded.attempt_count,payload_json=excluded.payload_json,error=excluded.error,updated_at=excluded.updated_at""",(r.record_id,r.stage,r.fingerprint,r.status,n,stable_json(r.payload),r.error,time.time()))
            if r.status!="ok": db.execute("INSERT INTO failures VALUES(?,?,?,?)",(r.record_id,r.stage,r.error,time.time()))
    def metadata(self,key,value):
        with self.connect() as db: db.execute("INSERT INTO run_metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,stable_json(value)))
    def rows(self):
        with self.connect() as db: records=db.execute("SELECT * FROM records ORDER BY country,row_number").fetchall(); stages=db.execute("SELECT * FROM stages").fetchall()
        stage_map={(r["record_id"],r["stage"]):r for r in stages}; out=[]
        for rec in records:
            row=json.loads(rec["raw_json"]); row.update({"ep24_record_id":rec["record_id"],"ep24_country":rec["country"],"ep24_language":rec["language"],"ep24_source_file":rec["source_file"],"ep24_source_row":rec["row_number"],"ep24_source_fingerprint":rec["source_fingerprint"],"ep24_legacy_fingerprint":rec["legacy_fingerprint"]})
            for stage in STAGES:
                item=stage_map.get((rec["record_id"],stage)); row[f"ep24_{stage}_status"]=item["status"] if item else ""; row[f"ep24_{stage}_error"]=item["error"] if item else ""; row[f"ep24_{stage}_json"]=item["payload_json"] if item else ""
            out.append(row)
        return out

ANALYSIS_KEYS=("entities","themes","signifiers","demands","collective_subjects","frontiers","affects","chains_equivalence","chains_difference","nodal_point_candidates","floating_signifier_candidates","empty_signifier_candidates","evidence","uncertainty_notes")
SYSTEM_PROMPT="""Perform cautious evidence-first Laclau/Mouffe/Palonen analysis of EP24 evidence. Return one JSON object only with list-valued keys: entities, themes, signifiers, demands, collective_subjects, frontiers, affects, chains_equivalence, chains_difference, nodal_point_candidates, floating_signifier_candidates, empty_signifier_candidates, evidence, uncertainty_notes. Keep original-language evidence. Researcher codebook matches are normalization context, not proof. Co-occurrence is not articulation; criticism is not automatically antagonism; actor identity is not evidence of ideology or populism. Abstain when evidence is weak."""

def parse_object(raw):
    text=raw.strip(); fence=chr(96)*3
    if text.startswith(fence):
        lines=text.splitlines()[1:]
        if lines and lines[-1].strip()==fence: lines=lines[:-1]
        text="\n".join(lines)
    payload=json.loads(text)
    if not isinstance(payload,dict): raise ValueError("model response must be JSON object")
    for key in ANALYSIS_KEYS:
        value=payload.get(key,[]); payload[key]=value if isinstance(value,list) else ([] if value is None else [value])
    return payload

def analyze(model,country,text,matches,config):
    if os.getenv("LLM_ALLOW_CLOUD_FALLBACK","0") not in {"0","false","False",""}: raise ValueError("cloud fallback forbidden")
    host=os.getenv("OLLAMA_HOST","")
    if host and "127.0.0.1" not in host and "localhost" not in host: raise ValueError("localhost Ollama required")
    import ollama
    response=ollama.chat(model=model,messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":stable_json({"country":country,"source_evidence":text,"researcher_grounded_codebook_matches":matches})}],options={"temperature":0.0,"num_ctx":int(config.get("num_ctx",32768)),"num_predict":int(config.get("num_predict",3072))})
    return parse_object(str(response["message"]["content"]))

def load_rows(path,country):
    import pandas as pd
    frame=pd.read_csv(path,dtype=str,keep_default_na=False); out=[]
    for i,raw in frame.iterrows():
        row={str(k):clean(v) for k,v in raw.to_dict().items()}; row["ep24_input_row"]=int(i)+2; out.append(row)
    return out

def select_rows(fi,pl,mode,n):
    if mode=="smoke": n=2
    if mode in {"smoke","pilot"}: return [*[("FI",r) for r in fi[:n]],*[("PL",r) for r in pl[:n]]]
    return [*[("FI",r) for r in fi],*[("PL",r) for r in pl]]

def process(country,row,source_file,state,entries,model,book_hash,config_hash,config):
    rownum=int(row["ep24_input_row"]); rid=stable_record_id(row,country=country,source_name=source_file.name,row_number=rownum); text=source_text(row); source_fp=sha256_text(stable_json(row)); legacy={"entities":[clean(row.get(k)) for k in ("entities","spacy_entities","new_entity") if clean(row.get(k))],"themes":[clean(row.get(k)) for k in ("topics","political_themes","new_theme") if clean(row.get(k))]}; legacy_fp=sha256_text(stable_json(legacy)); lang=clean(row.get("whisper_language")) or ("fi" if country=="FI" else "pl"); state.upsert(rid,country,lang,source_file.name,rownum,source_fp,legacy_fp,row); fp=sha256_text(stable_json({"source":source_fp,"model":model,"prompt":PROMPT_VERSION,"book":book_hash,"config":config_hash}))
    if state.cached(rid,"normalize",fp) is None: state.write(StageResult(rid,"normalize",fp,"ok",{"text":text,"language":lang}))
    codebook=state.cached(rid,"codebook",fp)
    if codebook is None: codebook={"matches":match_codebook(text,entries,country=country)}; state.write(StageResult(rid,"codebook",fp,"ok",codebook))
    analysis=state.cached(rid,"analysis",fp)
    if analysis is None:
        try: analysis=analyze(model,country,text,codebook["matches"],config) if text else {k:[] for k in ANALYSIS_KEYS}
        except Exception as exc: state.write(StageResult(rid,"analysis",fp,"error",{},str(exc))); return
        state.write(StageResult(rid,"analysis",fp,"ok",analysis))
    if state.cached(rid,"postprocess",fp) is None: state.write(StageResult(rid,"postprocess",fp,"ok",{"legacy":legacy,"new_entities":analysis.get("entities",[]),"new_themes":analysis.get("themes",[]),"codebook_matches":codebook["matches"]}))

def export(state,paths):
    import pandas as pd
    rows=state.rows(); frame=pd.DataFrame(rows); outputs={}
    for code,name in (("FI","finland.csv"),("PL","poland.csv")):
        path=paths["data"]/name; frame.loc[frame["ep24_country"]==code].to_csv(path,index=False); outputs[code]=str(path)
    path=paths["data"]/"combined.csv"; frame.to_csv(path,index=False); outputs["combined"]=str(path)
    with state.connect() as db: failures=[dict(r) for r in db.execute("SELECT * FROM failures")]
    path=paths["data"]/"failures.csv"; pd.DataFrame(failures).to_csv(path,index=False); outputs["failures"]=str(path)
    comp=[{"ep24_record_id":r["ep24_record_id"],"country":r["ep24_country"],"legacy_json":r.get("ep24_postprocess_json",""),"analysis_json":r.get("ep24_analysis_json","")} for r in rows]
    path=paths["data"]/"legacy_comparison.csv"; pd.DataFrame(comp).to_csv(path,index=False); outputs["legacy_comparison"]=str(path)
    return outputs

def preflight(root,model):
    paths=ensure_private_layout(root); entries,book_hash=load_private_codebooks(paths); config=load_yaml(paths["config"])
    if config.get("cloud_fallback",False): raise ValueError("cloud_fallback must be false")
    return paths,entries,book_hash,config,{"private_root":str(paths["root"]),"model":model,"codebook_entries":len(entries),"codebook_hash":book_hash,"sqlite":str(paths["db"]),"cloud_fallback":False}

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("mode",choices=("preflight","smoke","pilot","full"),nargs="?",default="pilot"); parser.add_argument("--private-root",default=os.getenv("LACLAUGPT_EP24_PRIVATE_ROOT",str(DEFAULT_PRIVATE_ROOT))); parser.add_argument("--model",default=os.getenv("EP24_ANALYSIS_MODEL",DEFAULT_MODEL)); args=parser.parse_args(argv)
    paths,entries,book_hash,config,report=preflight(args.private_root,args.model)
    if args.mode=="preflight": print(json.dumps(report,indent=2)); return 0
    state=EP24State(paths["db"]); selected=select_rows(load_rows(paths["finland"],"FI"),load_rows(paths["poland"],"PL"),args.mode,int(config.get("pilot_size",20))); config_hash=sha256_text(stable_json(config)); state.metadata("run",{"mode":args.mode,"model":args.model,"prompt":PROMPT_VERSION,"book":book_hash,"config":config_hash})
    for country,row in selected: process(country,row,paths["finland"] if country=="FI" else paths["poland"],state,entries,args.model,book_hash,config_hash,config)
    outputs=export(state,paths); job=os.getenv("SLURM_JOB_ID","local"); validation=paths["outputs"]/f"roihu-reprocess-{job}.md"; validation.write_text("# EP24 Roihu reprocessing report\n\n"+f"mode: {args.mode}\nmodel: {args.model}\nrecords: {len(selected)}\nSQLite: {paths['db']}\noutputs: {stable_json(outputs)}\n",encoding="utf-8"); print(json.dumps({**report,"mode":args.mode,"outputs":outputs,"report":str(validation)},indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
