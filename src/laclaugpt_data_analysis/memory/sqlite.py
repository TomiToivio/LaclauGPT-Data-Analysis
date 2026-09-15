"""SQLite-backed stable-ID memory with deterministic alias resolution."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from .models import MemoryRef, Resolution, display_label, normalize
class SQLiteMemory:
    def __init__(self,path:str|Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute('CREATE TABLE IF NOT EXISTS objects (obj_id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, norm TEXT NOT NULL, state TEXT NOT NULL DEFAULT "PROVISIONAL", provenance TEXT NOT NULL DEFAULT "")')
            c.execute('CREATE TABLE IF NOT EXISTS aliases (norm TEXT NOT NULL, obj_id TEXT NOT NULL, UNIQUE(norm,obj_id))')
    def resolve(self, raw:str, kind:str)->Resolution:
        norm=normalize(raw)
        with sqlite3.connect(self.path) as c: row=c.execute('SELECT o.obj_id,o.label FROM aliases a JOIN objects o ON o.obj_id=a.obj_id WHERE a.norm=? AND o.kind=? AND o.state NOT IN ("REJECTED","MERGED")',(norm,kind)).fetchone()
        return Resolution(raw=raw,kind=kind,obj_id=row[0],label=row[1],decision='EXISTING',matched_via='alias',score=1.0) if row else Resolution(raw=raw,kind=kind,decision='NEW')
    def create(self,obj_id:str,kind:str,label:str,provenance:str='')->MemoryRef:
        norm=normalize(label)
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT INTO objects(obj_id,kind,label,norm,provenance) VALUES (?,?,?,?,?)',(obj_id,kind,display_label(norm,kind),norm,provenance)); c.execute('INSERT OR IGNORE INTO aliases(norm,obj_id) VALUES (?,?)',(norm,obj_id))
        return MemoryRef(obj_id,display_label(norm,kind),kind,label)
    def add_alias(self,obj_id:str,alias:str)->None:
        with sqlite3.connect(self.path) as c: c.execute('INSERT OR IGNORE INTO aliases(norm,obj_id) VALUES (?,?)',(normalize(alias),obj_id))
