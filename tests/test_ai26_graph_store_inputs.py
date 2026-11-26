"""Store-input tests: synthetic documents only, no model or database connection."""

from __future__ import annotations

from laclaugpt_data_analysis.ai26_graph_publish import (
    build_graph,
    publish_mongo,
    relations_from_records,
    statements_from_results,
    store_inputs,
)

SOURCE = "https://example.test/post/1"
OPTIONS = {"run_id": "synthetic", "codebook_version": "not-recorded", "prompt_version": "v1"}


def coded_statement(**overrides):
    statement = {
        "statement_id": "dna:one",
        "source_url": SOURCE,
        "source_record_id": "document_id:abc",
        "actor_id": "org_example",
        "actor_name": "Example Org",
        "concept_id": "conc_safety",
        "concept_label": "AI safety",
        "stance": "support",
        "evidence": {"quote": "We need safety", "start_char": 0, "end_char": 14, "exact": True},
        "timestamp": "2026-09-18T10:28:11Z",
        "platform": "x",
        "coder_type": "llm",
        "model_version": "gemma4:12b",
        "prompt_version": "v1",
        "confidence": 0.9,
        "validation_status": "provisional",
        "metadata": {"notes": "the source poses a question"},
    }
    statement.update(overrides)
    return statement


def result_document(*statements, run_id="ai26-distributed-001"):
    return {
        "run_id": run_id,
        "result": {
            "source_url": SOURCE,
            "analysis": {
                "plugin_results": {
                    "dna_statement_coding": {
                        "prompt_version": "v1",
                        "proposal": {"statements": list(statements)},
                    }
                }
            },
        },
    }


def record(source_url, author, platform="x", text="", mentions=None, parent=None):
    raw = {"parent_document_id": parent} if parent else {}
    if mentions is not None:
        raw["mentions"] = list(mentions)
    return {
        "source_url": source_url,
        "source": {
            "platform": platform,
            "author": author,
            "created_at": "2026-09-18T10:28:11Z",
            "raw_metadata": raw,
        },
        "content": {"text": text},
    }


def test_stored_statements_keep_qualifier_evidence_and_review_state():
    stored = statements_from_results([result_document(coded_statement())])
    assert stored.invalid == 0 and stored.duplicates == 0
    [statement] = stored.statements
    assert statement.qualifier == "support"
    assert statement.review_status == "PROVISIONAL"
    assert statement.source_document_id == "document_id:abc"
    assert statement.evidence_text == "We need safety"
    assert statement.evidence_id.startswith("evidence:")
    assert statement.provenance_id.startswith("prov:")
    assert statement.producer.id == "gemma4:12b"
    assert statement.producer.type == "model"
    assert stored.summary()["stance"] == {"support": 1}


def test_reanalysis_is_counted_and_an_invalid_statement_is_refused():
    documents = [
        result_document(coded_statement()),
        result_document(
            coded_statement(concept_label="reworded", validation_status="needs_review")
        ),
        result_document(coded_statement(statement_id="dna:two", evidence={"quote": ""})),
    ]
    stored = statements_from_results(documents)
    assert len(stored.statements) == 1
    assert stored.duplicates == 1
    assert stored.invalid == 1
    assert stored.validation == {"provisional": 1}
    # A coder that asked for review is still provisional, never quietly accepted.
    assert stored.statements[0].review_status == "PROVISIONAL"


def test_one_identity_cannot_play_two_roles_in_the_graph():
    documents = [
        result_document(
            coded_statement(statement_id="dna:a", actor_id="shared", concept_id="conc_a")
        ),
        result_document(
            coded_statement(statement_id="dna:b", actor_id="org_b", concept_id="shared")
        ),
        result_document(
            coded_statement(statement_id="dna:c", actor_id="org_c", concept_id="conc_c")
        ),
    ]
    stored = statements_from_results(documents)
    assert [statement.statement_id for statement in stored.statements] == ["dna:c"]
    assert stored.conflicted == ["dna:a", "dna:b"]
    assert stored.summary()["conflicted_statements"] == 2
    assert any("same identity" in note for note in stored.notes)


def test_unknown_stance_is_recorded_rather_than_assigned():
    stored = statements_from_results([result_document(coded_statement(stance="unknown"))])
    assert stored.statements[0].qualifier == "unknown"
    assert any("no recorded stance" in note for note in stored.notes)


def test_only_addressed_ties_become_relations():
    records = [
        record(SOURCE, "OpenAI", mentions=["NIST"], text="A joint statement with @NIST"),
        record("https://example.test/post/2", "OpenAI", text="RT @NIST: an announcement"),
        record(
            "https://example.test/post/3", "NIST", mentions=["NIST"], text="self reference @NIST"
        ),
        record(
            "https://example.test/post/4",
            "alice.bsky.social",
            platform="bluesky",
            text="hello @NIST",
        ),
        record(
            "https://example.test/post/5",
            "OpenAI",
            parent="2098118232133792050",
            text="a reply whose parent is only a conversation root",
        ),
    ]
    found = relations_from_records(records)
    kinds = sorted(relation.relation_type for relation in found.relations)
    assert kinds == ["mention", "repost"]
    assert found.structured_mentions == 1 and found.reposts == 1
    # The X handle is not resolved inside the bluesky corpus, and the self mention is not a tie.
    assert found.unresolved_handles == 1
    # A conversation root is not an immediate reply target, so no reply edge was invented.
    assert found.thread_pointers == 1
    assert any("no reply tie" in note for note in found.notes)
    for relation in found.relations:
        assert relation.source_url
        assert relation.evidence_ids and relation.provenance_id
        assert relation.source_actor_id != relation.target_actor_id
        assert relation.source_actor_id.startswith("actor:x:")


def test_store_inputs_project_into_both_layers_with_source_provenance():
    statements, relations, report = store_inputs(
        [result_document(coded_statement())],
        [
            record(SOURCE, "OpenAI", mentions=["NIST"], text="with @NIST"),
            record("https://example.test/post/9", "NIST", text="the announcement"),
        ],
    )
    graph = build_graph(statements, relations, **OPTIONS)
    assert {edge.layer for edge in graph.edges} == {"dna", "sna"}
    for edge in graph.edges:
        assert edge.provenance.source_url
        assert edge.provenance.evidence_ids
        assert edge.provenance.run_id == "synthetic"
        assert edge.provenance.codebook_refs == ["not-recorded"]
    dna = [edge for edge in graph.edges if edge.layer == "dna"]
    assert all(edge.properties["qualifier"] == "support" for edge in dna)
    assert all(edge.properties["review_status"] == "PROVISIONAL" for edge in dna)
    sna = [edge for edge in graph.edges if edge.layer == "sna"]
    assert all(edge.assertion_kind == "empirical" for edge in sna)
    assert report["statements"]["statements"] == 1
    assert report["relations"]["relations"] == 1


class MemoryCollection:
    def __init__(self):
        self.rows = []

    def create_index(self, *args, **kwargs):
        pass

    def find(self, query, *args):
        return [row for row in self.rows if all(row.get(k) == v for k, v in query.items())]

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def replace_one(self, query, payload, *, upsert):
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]
        self.rows.append(payload)

    def delete_many(self, query):
        before = len(self.rows)
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]

        class Result:
            deleted_count = before - len(self.rows)

        return Result()


def test_replacing_a_snapshot_is_an_explicit_operator_decision():
    statements, relations, _ = store_inputs(
        [result_document(coded_statement())],
        [
            record(SOURCE, "OpenAI", mentions=["NIST"]),
            record("https://example.test/post/9", "NIST", text="the announcement"),
        ],
    )
    graph = build_graph(statements, relations, **OPTIONS)
    database = {name: MemoryCollection() for name in ("kg_nodes", "kg_edges", "kg_meta")}
    publish_mongo(graph, database)

    smaller = build_graph(statements, [], **OPTIONS)
    try:
        publish_mongo(smaller, database)
    except ValueError:
        pass
    else:
        raise AssertionError("A different snapshot was published without an explicit decision")

    publish_mongo(smaller, database, replace_snapshot=True)
    assert len(database["kg_meta"].rows) == 1
    assert len(database["kg_edges"].rows) == len(smaller.edges)
    assert {row["layer"] for row in database["kg_edges"].rows} == {"dna"}
