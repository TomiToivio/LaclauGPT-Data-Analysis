"""Native Discourse Network Analyzer (.dna SQLite) interoperability.

This is adapted from the predecessor repository's tested DNA 3.x adapter. The
adapter writes new files only and keeps LaclauGPT semantics separate from DNA
qualifiers. It is optional and has no effect on the normal analysis pipeline.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...discourse_network.models import DiscourseStatement, EvidenceSpan

STATEMENT_TYPE = "LaclauGPT Statement"

# DNA numbers the first (default) statement type 1, and that is the type whose
# variables are the coded statement fields. Other types in the same project —
# an "Annotation" note attached to a document, for example — carry a different
# variable namespace and no actor/concept fields, so they must not be imported
# as statements.
_CODED_STATEMENT_TYPE_ID = 1

SUPPORTED_SCHEMA_PREFIXES = ("3.0", "3.1")

_DDL = (
    "CREATE TABLE SETTINGS(Property TEXT PRIMARY KEY, Value TEXT NOT NULL)",
    "CREATE TABLE CODERS(ID INTEGER NOT NULL PRIMARY KEY, Name TEXT NOT NULL, Red INTEGER NOT NULL DEFAULT 0, Green INTEGER NOT NULL DEFAULT 0, Blue INTEGER NOT NULL DEFAULT 0, Refresh INTEGER NOT NULL DEFAULT 0, FontSize INTEGER NOT NULL DEFAULT 14, Password TEXT NOT NULL DEFAULT '', PopupWidth INTEGER DEFAULT 300, ColorByCoder INTEGER NOT NULL DEFAULT 0, PopupDecoration INTEGER NOT NULL DEFAULT 0, PopupAutoComplete INTEGER NOT NULL DEFAULT 1, PermissionAddDocuments INTEGER NOT NULL DEFAULT 1, PermissionEditDocuments INTEGER NOT NULL DEFAULT 1, PermissionDeleteDocuments INTEGER NOT NULL DEFAULT 1, PermissionImportDocuments INTEGER NOT NULL DEFAULT 1, PermissionAddStatements INTEGER NOT NULL DEFAULT 1, PermissionEditStatements INTEGER NOT NULL DEFAULT 1, PermissionDeleteStatements INTEGER NOT NULL DEFAULT 1, PermissionEditAttributes INTEGER NOT NULL DEFAULT 1, PermissionEditRegex INTEGER NOT NULL DEFAULT 1, PermissionEditStatementTypes INTEGER NOT NULL DEFAULT 1, PermissionEditCoders INTEGER NOT NULL DEFAULT 1, PermissionEditCoderRelations INTEGER NOT NULL DEFAULT 1, PermissionViewOthersDocuments INTEGER NOT NULL DEFAULT 1, PermissionEditOthersDocuments INTEGER NOT NULL DEFAULT 1, PermissionViewOthersStatements INTEGER NOT NULL DEFAULT 1, PermissionEditOthersStatements INTEGER NOT NULL DEFAULT 1)",
    "CREATE TABLE DOCUMENTS(ID INTEGER NOT NULL PRIMARY KEY, Title TEXT NOT NULL, Text TEXT NOT NULL, Coder INTEGER, Author TEXT NOT NULL DEFAULT '', Source TEXT NOT NULL DEFAULT '', Section TEXT NOT NULL DEFAULT '', Notes TEXT NOT NULL DEFAULT '', Type TEXT NOT NULL DEFAULT '', Date INTEGER NOT NULL, FOREIGN KEY(Coder) REFERENCES CODERS(ID) ON DELETE CASCADE)",
    "CREATE TABLE STATEMENTTYPES(ID INTEGER NOT NULL PRIMARY KEY, Label TEXT NOT NULL, Red INTEGER NOT NULL DEFAULT 0, Green INTEGER NOT NULL DEFAULT 0, Blue INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE VARIABLES(ID INTEGER NOT NULL PRIMARY KEY, Variable TEXT NOT NULL, DataType TEXT NOT NULL DEFAULT 'short text', StatementTypeId INTEGER, FOREIGN KEY(StatementTypeId) REFERENCES STATEMENTTYPES(ID) ON DELETE CASCADE, UNIQUE(Variable, StatementTypeId))",
    "CREATE TABLE STATEMENTS(ID INTEGER NOT NULL PRIMARY KEY, StatementTypeId INTEGER, DocumentId INTEGER, Start INTEGER NOT NULL, Stop INTEGER NOT NULL, Coder INTEGER, FOREIGN KEY(StatementTypeId) REFERENCES STATEMENTTYPES(ID), FOREIGN KEY(DocumentId) REFERENCES DOCUMENTS(ID), FOREIGN KEY(Coder) REFERENCES CODERS(ID))",
    "CREATE TABLE ENTITIES(ID INTEGER PRIMARY KEY NOT NULL, VariableId INTEGER NOT NULL, Value TEXT NOT NULL DEFAULT '', Red INTEGER, Green INTEGER, Blue INTEGER, ChildOf INTEGER, UNIQUE(VariableId, Value), FOREIGN KEY(VariableId) REFERENCES VARIABLES(ID))",
    "CREATE TABLE DATABOOLEAN(ID INTEGER PRIMARY KEY NOT NULL, StatementId INTEGER NOT NULL, VariableId INTEGER NOT NULL, Value INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(StatementId) REFERENCES STATEMENTS(ID), FOREIGN KEY(VariableId) REFERENCES VARIABLES(ID), UNIQUE(StatementId, VariableId))",
    "CREATE TABLE DATAINTEGER(ID INTEGER PRIMARY KEY NOT NULL, StatementId INTEGER NOT NULL, VariableId INTEGER NOT NULL, Value INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(StatementId) REFERENCES STATEMENTS(ID), FOREIGN KEY(VariableId) REFERENCES VARIABLES(ID), UNIQUE(StatementId, VariableId))",
    "CREATE TABLE DATASHORTTEXT(ID INTEGER PRIMARY KEY NOT NULL, StatementId INTEGER NOT NULL, VariableId INTEGER NOT NULL, Entity INTEGER NOT NULL, FOREIGN KEY(StatementId) REFERENCES STATEMENTS(ID), FOREIGN KEY(VariableId) REFERENCES VARIABLES(ID), FOREIGN KEY(Entity) REFERENCES ENTITIES(ID), UNIQUE(StatementId, VariableId))",
    "CREATE TABLE DATALONGTEXT(ID INTEGER PRIMARY KEY NOT NULL, StatementId INTEGER NOT NULL, VariableId INTEGER NOT NULL, Value TEXT DEFAULT '', FOREIGN KEY(StatementId) REFERENCES STATEMENTS(ID), FOREIGN KEY(VariableId) REFERENCES VARIABLES(ID), UNIQUE(StatementId, VariableId))",
    "CREATE TABLE ATTRIBUTEVARIABLES(ID INTEGER PRIMARY KEY NOT NULL, VariableId INTEGER NOT NULL, AttributeVariable TEXT NOT NULL, UNIQUE(VariableId, AttributeVariable), FOREIGN KEY(VariableId) REFERENCES VARIABLES(ID))",
    "CREATE TABLE ATTRIBUTEVALUES(ID INTEGER PRIMARY KEY NOT NULL, EntityId INTEGER NOT NULL, AttributeVariableId INTEGER NOT NULL, AttributeValue TEXT NOT NULL DEFAULT '', UNIQUE(EntityId, AttributeVariableId), FOREIGN KEY(EntityId) REFERENCES ENTITIES(ID), FOREIGN KEY(AttributeVariableId) REFERENCES ATTRIBUTEVARIABLES(ID))",
)

_VARIABLES = {
    # DNA's conventional actor variables. Keep "actor" as a legacy
    # LaclauGPT compatibility field so projects exported before #312 remain
    # readable, but native DNA consumers can code against person/organization.
    "person": "short text",
    "organization": "short text",
    "actor": "short text",
    "concept": "short text",
    "stance": "short text",
    "concept_type": "short text",
    "relation_type": "short text",
    "source_url": "long text",
    "statement_id": "long text",
    "evidence": "long text",
    "metadata_json": "long text",
    "agreement": "boolean",
}


def _epoch(value: datetime | None) -> int:
    return int((value or datetime.now(timezone.utc)).timestamp())


def _document_text(statement: DiscourseStatement, document_texts: dict[str, str]) -> str:
    text = document_texts.get(statement.source_url, "")
    if text:
        return text
    return statement.evidence.quote or f"Source: {statement.source_url}"


def _anchor(statement: DiscourseStatement, text: str) -> tuple[int, int, bool]:
    e = statement.evidence
    if e.start_char is not None and e.end_char is not None and e.end_char <= len(text):
        exact = text[e.start_char:e.end_char] == e.quote if e.quote else e.exact
        return e.start_char, e.end_char, exact
    if e.quote:
        start = text.find(e.quote)
        if start >= 0:
            return start, start + len(e.quote), True
    return 0, max(1, len(text)), False


def validate_dna_project(path: str | Path) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"SETTINGS", "DOCUMENTS", "STATEMENTTYPES", "VARIABLES", "STATEMENTS", "ENTITIES"}
        missing = sorted(required - tables)
        version_row = con.execute("SELECT Value FROM SETTINGS WHERE Property='version'").fetchone() if "SETTINGS" in tables else None
        version = str(version_row[0]) if version_row else "unknown"
        return {
            "valid": not missing and (version == "unknown" or version.startswith(SUPPORTED_SCHEMA_PREFIXES)),
            "version": version,
            "missing_tables": missing,
            "supported_version": version == "unknown" or version.startswith(SUPPORTED_SCHEMA_PREFIXES),
        }
    finally:
        con.close()


def export_dna_project(
    statements: list[DiscourseStatement],
    out_path: str | Path,
    *,
    document_texts: dict[str, str] | None = None,
    statement_type: str = STATEMENT_TYPE,
) -> dict[str, int]:
    """Export statements into a fresh DNA 3.x-compatible SQLite project."""
    out = Path(out_path)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite existing DNA project: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    texts = document_texts or {}
    con = sqlite3.connect(out)
    try:
        cur = con.cursor()
        for ddl in _DDL:
            cur.execute(ddl)
        cur.execute("INSERT INTO SETTINGS VALUES (?, ?)", ("version", "3.0.7"))
        cur.execute("INSERT INTO SETTINGS VALUES (?, ?)", ("date", datetime.now(timezone.utc).date().isoformat()))
        cur.execute("INSERT INTO CODERS(ID,Name,Password) VALUES (1,'LaclauGPT','')")
        cur.execute("INSERT INTO STATEMENTTYPES(Label,Red,Green,Blue) VALUES (?,?,?,?)", (statement_type, 120, 120, 120))
        st_id = int(cur.lastrowid)
        var_ids: dict[str, int] = {}
        for name, dtype in _VARIABLES.items():
            cur.execute("INSERT INTO VARIABLES(Variable,DataType,StatementTypeId) VALUES (?,?,?)", (name, dtype, st_id))
            var_ids[name] = int(cur.lastrowid)

        entities: dict[tuple[str, str], int] = {}
        def entity(variable: str, value: str) -> int:
            key = (variable, value)
            if key not in entities:
                cur.execute("INSERT INTO ENTITIES(VariableId,Value) VALUES (?,?)", (var_ids[variable], value[:190]))
                entities[key] = int(cur.lastrowid)
            return entities[key]

        documents: dict[str, int] = {}
        for statement in statements:
            if statement.source_url not in documents:
                text = _document_text(statement, texts)
                cur.execute(
                    "INSERT INTO DOCUMENTS(Title,Text,Coder,Source,Section,Type,Date) VALUES (?,?,?,?,?,?,?)",
                    (statement.source_url[:190], text, 1, statement.source_url[:190], statement.collection_id or "", "laclaugpt", _epoch(statement.timestamp)),
                )
                documents[statement.source_url] = int(cur.lastrowid)
            text = _document_text(statement, texts)
            start, stop, exact = _anchor(statement, text)
            cur.execute("INSERT INTO STATEMENTS(StatementTypeId,DocumentId,Start,Stop,Coder) VALUES (?,?,?,?,1)", (st_id, documents[statement.source_url], start, stop))
            sid = int(cur.lastrowid)
            # DNA's native model distinguishes people and organizations.
            # Preserve the legacy generic actor field as an additional
            # LaclauGPT compatibility variable rather than using it in place
            # of the conventional DNA variables.
            person_name = statement.person_name or ""
            organization_name = statement.organization_name or ""
            if not person_name and not organization_name:
                person_name = statement.actor_name
            short_values = {
                "person": person_name,
                "organization": organization_name,
                "actor": statement.actor_name,
                "concept": statement.concept_label,
                "stance": statement.stance.value,
                "concept_type": statement.concept_type.value,
                "relation_type": statement.relation_type or "",
            }
            for variable, value in short_values.items():
                if not value and variable in {"person", "organization"}:
                    continue
                eid = entity(variable, value)
                cur.execute("INSERT INTO DATASHORTTEXT(StatementId,VariableId,Entity) VALUES (?,?,?)", (sid, var_ids[variable], eid))
            metadata = {
                "actor_id": statement.actor_id,
                "person_id": statement.person_id,
                "organization_id": statement.organization_id,
                "concept_id": statement.concept_id,
                "source_record_id": statement.source_record_id,
                "coder_type": statement.coder_type,
                "coder_id_or_model": statement.coder_id_or_model,
                "confidence": statement.confidence,
                "codebook_version": statement.codebook_version,
                "validation_status": statement.validation_status.value,
                "evidence_exact": exact,
                "provenance": statement.provenance,
            }
            for variable, value in {
                "source_url": statement.source_url,
                "statement_id": statement.statement_id,
                "evidence": statement.evidence.quote,
                "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            }.items():
                cur.execute("INSERT INTO DATALONGTEXT(StatementId,VariableId,Value) VALUES (?,?,?)", (sid, var_ids[variable], value))
            # DNA agreement is genuinely binary: support=1, reject=0. Missing or
            # ambiguous agreement remains missing instead of being coerced to support.
            if statement.agreement is not None:
                cur.execute(
                    "INSERT INTO DATABOOLEAN(StatementId,VariableId,Value) VALUES (?,?,?)",
                    (sid, var_ids["agreement"], 1 if statement.agreement else 0),
                )
        con.commit()
        return {"documents": len(documents), "statements": len(statements), "entities": len(entities)}
    except Exception:
        con.rollback()
        con.close()
        if out.exists():
            out.unlink()
        raise
    finally:
        if con:
            con.close()


def import_dna_documents(path: str | Path) -> list[dict[str, Any]]:
    """Import DNA documents without changing canonical analysis semantics."""
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    try:
        return [
            {
                "dna_document_id": str(row[0]), "title": row[1], "text": row[2],
                "author": row[3], "source": row[4], "section": row[5], "type": row[6],
                "timestamp": datetime.fromtimestamp(row[7], tz=timezone.utc).isoformat() if row[7] else None,
            }
            for row in con.execute("SELECT ID,Title,Text,Author,Source,Section,Type,Date FROM DOCUMENTS ORDER BY ID")
        ]
    finally:
        con.close()


def import_dna_statements(
    path: str | Path,
    *,
    human_coded: bool = True,
    statement_type: str | None = None,
) -> list[DiscourseStatement]:
    """Import statements from a DNA project, preserving human-edit lineage.

    A DNA project may hold several statement types (a ``.dna`` file also carries
    ``Annotation`` notes alongside its coded statements), each with its own
    variable namespace. Only one statement type is imported at a time: by default
    the first DNA-coded type found, otherwise the type named by ``statement_type``.
    Variables are resolved within that type, so identically named variables in
    other statement types cannot shadow the ones being read.
    """
    status = validate_dna_project(path)
    if not status["valid"]:
        raise ValueError(f"unsupported or invalid DNA project: {status}")
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        statement_types = {
            row["ID"]: row["Label"]
            for row in con.execute("SELECT ID, Label FROM STATEMENTTYPES")
        }
        present = [
            row["StatementTypeId"]
            for row in con.execute(
                "SELECT DISTINCT StatementTypeId FROM STATEMENTS ORDER BY StatementTypeId"
            )
            if row["StatementTypeId"] is not None
        ]
        if statement_type is not None:
            selected = next(
                (sid for sid, label in statement_types.items() if label == statement_type),
                None,
            )
            if selected is None:
                raise ValueError(f"DNA project has no statement type {statement_type!r}")
        else:
            selected = next((sid for sid in present if sid == _CODED_STATEMENT_TYPE_ID), None)
            if selected is None:
                selected = next((sid for sid in present if sid in statement_types), None)
        if selected is None:
            return []

        variables = {
            row["Variable"]: row["ID"]
            for row in con.execute(
                "SELECT ID,Variable FROM VARIABLES WHERE StatementTypeId=?", (selected,)
            )
        }
        if not ({"person", "organization", "actor"} & set(variables)):
            label = statement_types.get(selected, selected)
            raise ValueError(
                f"DNA statement type {label!r} has no actor variables "
                "(person/organization/actor), so it does not describe actor-concept "
                "statements; import it as documents/annotations instead"
            )

        def long_value(statement_id: int, name: str) -> str:
            vid = variables.get(name)
            if vid is None:
                return ""
            row = con.execute("SELECT Value FROM DATALONGTEXT WHERE StatementId=? AND VariableId=?", (statement_id, vid)).fetchone()
            return str(row[0]) if row else ""
        def short_value(statement_id: int, name: str) -> str:
            vid = variables.get(name)
            if vid is None:
                return ""
            row = con.execute("SELECT e.Value FROM DATASHORTTEXT d JOIN ENTITIES e ON e.ID=d.Entity WHERE d.StatementId=? AND d.VariableId=?", (statement_id, vid)).fetchone()
            return str(row[0]) if row else ""
        def boolean_value(statement_id: int, name: str) -> bool | None:
            vid = variables.get(name)
            if vid is None:
                return None
            row = con.execute(
                "SELECT Value FROM DATABOOLEAN WHERE StatementId=? AND VariableId=?",
                (statement_id, vid),
            ).fetchone()
            return bool(row[0]) if row else None

        result: list[DiscourseStatement] = []
        query = (
            "SELECT s.ID,s.Start,s.Stop,d.Text,d.Source,d.Date FROM STATEMENTS s "
            "JOIN DOCUMENTS d ON d.ID=s.DocumentId WHERE s.StatementTypeId=? ORDER BY s.ID"
        )
        for row in con.execute(query, (selected,)):
            metadata_raw = long_value(row["ID"], "metadata_json")
            metadata = json.loads(metadata_raw) if metadata_raw else {}
            quote = long_value(row["ID"], "evidence")
            source_url = long_value(row["ID"], "source_url") or row["Source"] or f"dna:document:{row['ID']}"
            exact = 0 <= row["Start"] < row["Stop"] <= len(row["Text"]) and (not quote or row["Text"][row["Start"]:row["Stop"]] == quote)
            provenance = dict(metadata.get("provenance") or {})
            provenance["dna_import"] = {"schema_version": status["version"], "human_coded": human_coded}
            agreement = boolean_value(row["ID"], "agreement")
            stance = short_value(row["ID"], "stance")
            if not stance and agreement is not None:
                stance = "support" if agreement else "oppose"
            person_name = short_value(row["ID"], "person")
            organization_name = short_value(row["ID"], "organization")
            legacy_actor_name = short_value(row["ID"], "actor")
            actor_name = person_name or organization_name or legacy_actor_name
            result.append(DiscourseStatement(
                statement_id=long_value(row["ID"], "statement_id") or f"dna:{row['ID']}",
                source_url=source_url,
                source_record_id=metadata.get("source_record_id"),
                actor_id=metadata.get("actor_id") or actor_name,
                actor_name=actor_name,
                person_id=metadata.get("person_id"),
                person_name=person_name or None,
                organization_id=metadata.get("organization_id"),
                organization_name=organization_name or None,
                concept_id=metadata.get("concept_id") or short_value(row["ID"], "concept"),
                concept_label=short_value(row["ID"], "concept"),
                concept_type=short_value(row["ID"], "concept_type") or "concept",
                stance=stance or "unknown",
                agreement=agreement,
                relation_type=short_value(row["ID"], "relation_type") or None,
                timestamp=datetime.fromtimestamp(row["Date"], tz=timezone.utc) if row["Date"] else None,
                evidence=EvidenceSpan(quote=quote, start_char=row["Start"], end_char=row["Stop"], exact=exact),
                coder_type="human" if human_coded else metadata.get("coder_type", "dna"),
                coder_id_or_model=metadata.get("coder_id_or_model"),
                confidence=metadata.get("confidence"),
                codebook_version=metadata.get("codebook_version"),
                validation_status="validated" if human_coded else metadata.get("validation_status", "provisional"),
                provenance=provenance,
            ))
        return result
    finally:
        con.close()


def import_dna_concepts(path: str | Path, variable: str = "concept") -> list[dict[str, str]]:
    """Return coder-defined concepts as typed candidates, never automatic signifiers."""
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT DISTINCT e.Value FROM ENTITIES e JOIN VARIABLES v ON v.ID=e.VariableId WHERE v.Variable=? ORDER BY e.Value",
            (variable,),
        )
        return [{"label": str(row[0]), "type": "concept", "source": "human_dna_coding", "status": "provisional"} for row in rows if row[0]]
    finally:
        con.close()
