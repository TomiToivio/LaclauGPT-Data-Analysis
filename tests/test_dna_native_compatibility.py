import os
import sqlite3
from pathlib import Path

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


def _project_with_annotation(tmp_path: Path) -> Path:
    """A synthetic project shaped like leifeld-lab/dna's sample: coded statements
    plus a separate 'Annotation' statement type carrying document notes."""
    path = tmp_path / "with-annotation.dna"
    export_dna_project([_statement()], path)
    con = sqlite3.connect(path)
    try:
        con.execute(
            "INSERT INTO STATEMENTTYPES(ID,Label) VALUES (3,'Annotation')"
        )
        con.execute(
            "INSERT INTO VARIABLES(Variable,DataType,StatementTypeId) VALUES ('note','long text',3)"
        )
        note_var = con.execute(
            "SELECT ID FROM VARIABLES WHERE Variable='note' AND StatementTypeId=3"
        ).fetchone()[0]
        doc = con.execute("SELECT ID FROM DOCUMENTS LIMIT 1").fetchone()[0]
        con.execute(
            "INSERT INTO STATEMENTS(StatementTypeId,DocumentId,Start,Stop,Coder) VALUES (3,?,0,5,1)",
            (doc,),
        )
        note_stmt = con.execute("SELECT MAX(ID) FROM STATEMENTS").fetchone()[0]
        con.execute(
            "INSERT INTO DATALONGTEXT(StatementId,VariableId,Value) VALUES (?,?,?)",
            (note_stmt, note_var, "This is a note."),
        )
        con.commit()
    finally:
        con.close()
    return path


def test_annotation_statement_types_are_not_imported_as_statements(tmp_path: Path):
    """A project holding an Annotation type must import only the coded statements.

    Regression for the leifeld-lab/dna sample, where the document note is a
    statement of a different type with no actor variables. Reading it as a coded
    statement raised a validation error, so the whole genuine project failed to
    import even though every coded statement was valid.
    """
    path = _project_with_annotation(tmp_path)

    statements = import_dna_statements(path)

    assert len(statements) == 1
    assert statements[0].actor_name == "Joel Bluestein"
    assert all(statement.actor_name for statement in statements)


def test_annotation_type_can_be_requested_and_is_refused_clearly(tmp_path: Path):
    """Selecting a non-statement type fails with a clear ValueError, not a
    validation error raised deep inside the model layer."""
    path = _project_with_annotation(tmp_path)

    with pytest.raises(ValueError, match="no actor variables"):
        import_dna_statements(path, statement_type="Annotation")

    with pytest.raises(ValueError, match="no statement type"):
        import_dna_statements(path, statement_type="Does Not Exist")
