from laclaugpt_data_analysis.memory import SQLiteMemory


def test_sqlite_memory_alias_resolution(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    memory.create("A-1", "actor", "Synthetic Actor", provenance="synthetic")
    memory.add_alias("A-1", "S. Actor")

    resolved = memory.resolve("s. actor", "actor")
    assert resolved.decision == "EXISTING"
    assert resolved.obj_id == "A-1"
    assert memory.resolve("unknown", "actor").decision == "NEW"
