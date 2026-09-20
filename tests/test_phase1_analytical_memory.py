from laclaugpt_data_analysis.memory import SQLiteMemory
from laclaugpt_data_analysis.phase1_runtime import resolve_analytical_memory


def test_analytical_memory_resolves_only_accepted_aliases(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    memory.create("A-accepted", "actor", "Ada Lovelace")
    memory.add_alias("A-accepted", "A. Lovelace")
    memory.create("S-provisional", "signifier", "democratic AI")

    # Fixture persistence setup marks only the actor as researcher-accepted.
    import sqlite3
    with sqlite3.connect(memory.path) as connection:
        connection.execute("UPDATE objects SET state = 'CANONICAL' WHERE obj_id = 'A-accepted'")

    refs = resolve_analytical_memory(memory, [
        ("actor", "A. Lovelace"),
        ("signifier", "democratic AI"),
        ("actor", "unknown LLM guess"),
    ])

    assert refs == ["A-accepted"]
    assert memory.resolve("unknown LLM guess", "actor").decision == "NEW"
    assert memory.resolve_accepted("democratic AI", "signifier").decision == "NEW"
