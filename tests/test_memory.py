from laclaugpt_data_analysis.memory import SQLiteMemory
def test_sqlite_memory_alias_resolution(tmp_path):
 m=SQLiteMemory(tmp_path/'memory.sqlite3'); m.create('A-1','actor','Synthetic Actor',provenance='synthetic'); m.add_alias('A-1','S. Actor')
 r=m.resolve('s. actor','actor'); assert r.decision=='EXISTING' and r.obj_id=='A-1'
 assert m.resolve('unknown','actor').decision=='NEW'
