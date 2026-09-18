from __future__ import annotations

from laclaugpt_data_analysis.prompt_library import assemble_prompt_stack, load_prompt


def test_prompt_stack_keeps_dynamic_context_out_of_system() -> None:
    stack = assemble_prompt_stack(
        system_prompt=load_prompt("laclau.system", version="v1"),
        context_prompt=load_prompt("context.research", version="v1"),
        task_prompt=load_prompt("ep24.postprocess", version="v1"),
        context_values={
            "project_name": "AI26",
            "research_question": "How is AGI articulated?",
            "current_datetime": "2026-09-18T09:00:00+03:00",
            "project_context": "DYNAMIC_PROJECT_CONTEXT",
            "codebook_context": "DYNAMIC_CODEBOOK",
            "rag_context": "DYNAMIC_RAG",
            "previous_analysis": "DYNAMIC_PREVIOUS_ANALYSIS",
            "researcher_notes": "DYNAMIC_RESEARCHER_NOTES",
            "provenance": "researcher:note-1",
        },
        task_values={"source_analysis": "SOURCE_ANALYSIS"},
    )

    assert stack.system.role == "system"
    assert "DYNAMIC_PROJECT_CONTEXT" not in stack.system.text
    assert "DYNAMIC_RAG" not in stack.system.text
    assert stack.context.role == "user"
    assert "DYNAMIC_PROJECT_CONTEXT" in stack.context.text
    assert "DYNAMIC_RAG" in stack.context.text
    assert stack.task.role == "user"
    assert "SOURCE_ANALYSIS" in stack.task.text


def test_prompt_stack_is_deterministic() -> None:
    kwargs = {
        "system_prompt": load_prompt("laclau.system", version="v1"),
        "context_prompt": load_prompt("context.research", version="v1"),
        "task_prompt": load_prompt("ep24.postprocess", version="v1"),
        "context_values": {
            "project_name": "EP24",
            "research_question": "",
            "current_datetime": "",
            "project_context": "",
            "codebook_context": "",
            "rag_context": "",
            "previous_analysis": "",
            "researcher_notes": "",
            "provenance": "",
        },
        "task_values": {"source_analysis": "analysis"},
    }
    first = assemble_prompt_stack(**kwargs)
    second = assemble_prompt_stack(**kwargs)
    assert first == second


def test_postprocess_prompt_preserves_exact_structured_keys() -> None:
    text = load_prompt("ep24.postprocess", version="v1").text
    for key in ("topics", "entities", "positive", "neutral", "negative"):
        assert f"`{key}`" in text
    assert "exactly these keys" in text.lower()


def test_empty_optional_context_does_not_create_invalid_stack() -> None:
    stack = assemble_prompt_stack(
        system_prompt=load_prompt("laclau.system", version="v1"),
        context_prompt=load_prompt("context.research", version="v1"),
        task_prompt=load_prompt("ep24.postprocess", version="v1"),
        context_values={
            "project_name": "EP24",
            "research_question": "",
            "current_datetime": "",
            "project_context": "",
            "codebook_context": "",
            "rag_context": "",
            "previous_analysis": "",
            "researcher_notes": "",
            "provenance": "",
        },
        task_values={"source_analysis": "analysis"},
    )
    assert stack.context.text.strip()
    assert stack.task.text.strip()
