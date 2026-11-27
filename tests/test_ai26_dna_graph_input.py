"""Native DNA coder conversion uses exact spans and reviewed IDs."""

from copy import deepcopy

from laclaugpt_data_analysis.ai26_dna_graph_input import convert_coded_record

SOURCE = "https://example.test/article"
IDENTITIES = {"actors": {"a": "actor:a"}, "concepts": {"c": "concept:c"}}


def coded_record():
    return {
        "source_url": SOURCE,
        "content": {"text": "A supports safety."},
        "analysis": {
            "plugin_results": {
                "dna_statement_coding": {
                    "model_run": {"actual_model": "gemma4:12b"},
                    "proposal": {
                        "statements": [
                            {
                                "statement_id": "dna:1",
                                "source_url": SOURCE,
                                "actor_id": "a",
                                "actor_name": "A",
                                "concept_id": "c",
                                "concept_label": "Safety",
                                "agreement": True,
                                "stance": "support",
                                "evidence": {
                                    "quote": "A supports safety.",
                                    "start_char": 0,
                                    "end_char": 18,
                                    "exact": True,
                                },
                                "coder_type": "llm",
                                "coder_id_or_model": "gemma4:12b",
                            }
                        ],
                    },
                }
            },
        },
    }


def test_native_coder_bridge():
    source = coded_record()
    first = convert_coded_record(source, IDENTITIES)
    assert len(first) == 1
    assert first == convert_coded_record(deepcopy(source), IDENTITIES)
    assert first[0]["actor_id"] == "actor:a"
    assert first[0]["concept_id"] == "concept:c"
    assert first[0]["qualifier"] == "agree"
    assert first[0]["review_status"] == "PROVISIONAL"
    assert first[0]["evidence_id"]
    assert first[0]["provenance_id"]


def test_native_coder_abstains_when_not_grounded():
    source = coded_record()
    assert not convert_coded_record(source, {})
    source["content"]["text"] = "Different text"
    assert not convert_coded_record(source, IDENTITIES)
    source = coded_record()
    source["analysis"]["plugin_failures"] = {"dna_statement_coding": {"error": "Timeout"}}
    assert not convert_coded_record(source, IDENTITIES)
