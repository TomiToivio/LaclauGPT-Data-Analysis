from laclaugpt_data_analysis.memory import SQLiteMemory, stable_memory_id


def test_sqlite_memory_alias_resolution(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    memory.create("A-1", "actor", "Synthetic Actor", provenance="synthetic")
    memory.add_alias("A-1", "S. Actor")

    resolved = memory.resolve("s. actor", "actor")
    assert resolved.decision == "EXISTING"
    assert resolved.obj_id == "A-1"
    assert memory.resolve("unknown", "actor").decision == "NEW"


def test_stable_memory_id_uses_normalized_kind_and_label():
    first = stable_memory_id("actor", " Synthetic Actor ")
    second = stable_memory_id("actor", "synthetic actor")
    assert first == second
    assert first.startswith("A-")


def test_provisional_memory_never_resolves_as_accepted_until_explicitly_promoted(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    ref = memory.create_stable("signifier", "synthetic signifier", provenance="llm-candidate")

    assert memory.resolve("synthetic signifier", "signifier").obj_id == ref.obj_id
    assert memory.resolve_accepted("synthetic signifier", "signifier").decision == "NEW"

    memory.set_state(ref.obj_id, "CANONICAL")
    assert memory.resolve_accepted("synthetic signifier", "signifier").obj_id == ref.obj_id

    memory.set_state(ref.obj_id, "PROVISIONAL")
    assert memory.resolve_accepted("synthetic signifier", "signifier").decision == "NEW"


def test_ambiguous_alias_abstains_deterministically(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    memory.create("A-2", "actor", "Second Actor", state="CANONICAL")
    memory.create("A-1", "actor", "First Actor", state="CANONICAL")
    memory.add_alias("A-2", "shared alias")
    memory.add_alias("A-1", "shared alias")

    resolved = memory.resolve_accepted("shared alias", "actor")
    assert resolved.decision == "AMBIGUOUS"
    assert resolved.obj_id == ""


def test_sqlite_memory_persists_canonical_aliases_across_instances(tmp_path):
    path = tmp_path / "memory.sqlite3"
    first = SQLiteMemory(path)
    ref = first.create_stable("topic", "synthetic topic", provenance="researcher", state="CANONICAL")
    first.add_alias(ref.obj_id, "topic alias")

    reopened = SQLiteMemory(path)
    resolved = reopened.resolve_accepted("topic alias", "topic")
    assert resolved.decision == "EXISTING"
    assert resolved.obj_id == ref.obj_id
