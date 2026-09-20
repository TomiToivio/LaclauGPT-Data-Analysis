from laclaugpt_data_analysis.memory import SQLiteMemory, stable_memory_id


def test_sqlite_memory_alias_resolution(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    memory.create("A-1", "actor", "Synthetic Actor", provenance="synthetic")
    memory.add_alias("A-1", "S. Actor")

    resolved = memory.resolve("s. actor", "actor")
    assert resolved.decision == "EXISTING"
    assert resolved.obj_id == "A-1"
    assert memory.resolve("unknown", "actor").decision == "NEW"


def test_stable_memory_id_is_normalization_deterministic():
    assert stable_memory_id("entity", "OpenAI") == stable_memory_id(
        "entity", "  openai (company)  "
    )
    assert stable_memory_id("topic", "OpenAI") != stable_memory_id("entity", "OpenAI")


def test_provisional_guess_is_never_accepted_automatically(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    proposed = memory.propose("signifier", "AGI", provenance="llm-proposal")

    assert memory.resolve("agi", "signifier").obj_id == proposed.obj_id
    assert memory.resolve_accepted("agi", "signifier").decision == "NEW"

    memory.accept(proposed.obj_id)
    assert memory.resolve_accepted("agi", "signifier").obj_id == proposed.obj_id


def test_alias_collision_abstains_deterministically(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    memory.create("A-1", "actor", "Alpha", state="CANONICAL")
    memory.create("A-2", "actor", "Beta", state="CANONICAL")
    memory.add_alias("A-1", "Shared Alias")
    memory.add_alias("A-2", "Shared Alias")

    result = memory.resolve_accepted("shared alias", "actor")
    assert result.decision == "AMBIGUOUS"
    assert result.obj_id == ""


def test_sqlite_memory_persists_accepted_aliases_across_reopen(tmp_path):
    path = tmp_path / "memory.sqlite3"
    memory = SQLiteMemory(path)
    ref = memory.propose("topic", "Artificial Intelligence", provenance="researcher")
    memory.add_alias(ref.obj_id, "AI")
    memory.accept(ref.obj_id)

    reopened = SQLiteMemory(path)
    resolved = reopened.resolve_accepted("AI", "topic")
    assert resolved.decision == "EXISTING"
    assert resolved.obj_id == ref.obj_id
