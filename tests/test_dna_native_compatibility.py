import os
from pathlib import Path
import sqlite3

import pytest

from laclaugpt_data_analysis.discourse_network import DiscourseStatement, EvidenceSpan
from laclaugpt_data_analysis.interoperability.dna import (
    export_dna_project,
    import_dna_statements,
)


def _statement(**overrides):
    data = {
        "statement_id": "s-native",
        "source_url": "https://example.org/native",
        "actor_id": "person:1",
        "actor_name": "Joel Bluestein",
        "person_id": "person:1",
        "person_name": "Joel Bluestein",
        "organization_id": "org:1",
        "organization_name": "Energy and Environmental Analysis, Inc.",
        "concept_id": "concept:1",
        "concept_label": "CO2 legislation will not hurt the economy.",
        "concept_type": "concept",
        "stance": "oppose",
        "agreement": False,
        "evidence": EvidenceSpan(quote="CO2 legislation", start_char=0, end_char=15, exact=True),
    }
    data.update(overrides)
    return DiscourseStatement(**data)


def test_export_uses_native_dna_actor_variables(tmp_path: Path):
    path = tmp_path / "native-actors.dna"
    export_dna_project([_statement()], path, document_texts={"https://example.org/native": "CO2 legislation"})

    con = sqlite3.connect(path)
    try:
        variables = {row[0] for row in con.execute("SELECT Variable FROM VARIABLES")}
        values = dict(
            con.execute(
                """
                SELECT v.Variable, e.Value
                FROM DATASHORTTEXT d
                JOIN VARIABLES v ON v.ID = d.VariableId
                JOIN ENTITIES e ON e.ID = d.Entity
                JOIN STATEMENTS s ON s.ID = d.StatementId
                WHERE s.ID = 1 AND v.Variable IN ('person', 'organization')
                """
            )
        )
    finally:
        con.close()

    assert {"person", "organization", "concept", "agreement"} <= variables
    assert values["person"] == "Joel Bluestein"
    assert values["organization"] == "Energy and Environmental Analysis, Inc."


def test_import_uses_person_and_organization_without_legacy_actor(tmp_path: Path):
    path = tmp_path / "native-only.dna"
    export_dna_project([_statement()], path, document_texts={"https://example.org/native": "CO2 legislation"})

    con = sqlite3.connect(path)
    try:
        actor_var = con.execute("SELECT ID FROM VARIABLES WHERE Variable='actor'").fetchone()[0]
        con.execute("DELETE FROM DATASHORTTEXT WHERE VariableId=?", (actor_var,))
        con.execute("DELETE FROM ENTITIES WHERE VariableId=?", (actor_var,))
        con.execute("DELETE FROM VARIABLES WHERE ID=?", (actor_var,))
        con.commit()
    finally:
        con.close()

    rows = import_dna_statements(path)

    assert len(rows) == 1
    assert rows[0].actor_name == "Joel Bluestein"
    assert rows[0].person_name == "Joel Bluestein"
    assert rows[0].organization_name == "Energy and Environmental Analysis, Inc."
    assert rows[0].agreement is False


SAMPLE = Path(os.environ.get("LACLAUGPT_DNA_SAMPLE", ""))


@pytest.mark.skipif(
    not os.environ.get("LACLAUGPT_DNA_SAMPLE") or not SAMPLE.exists(),
    reason="set LACLAUGPT_DNA_SAMPLE to leifeld-lab/dna sample.dna",
)
def test_imports_a_genuine_dna_project():
    statements = import_dna_statements(SAMPLE)

    assert statements
    assert all(
        statement.actor_name or statement.person_name or statement.organization_name
        for statement in statements
    )
