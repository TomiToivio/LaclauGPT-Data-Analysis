from __future__ import annotations

import pytest

from laclaugpt_data_analysis.stage_contract import (
    STAGE_CAPABILITIES,
    resolve_stage_contract,
    stage_enabled,
)


def test_enabled_flag_must_be_implemented() -> None:
    with pytest.raises(ValueError, match="analysis.sna=true"):
        resolve_stage_contract({"analysis": {"sna": True}})


def test_unknown_flag_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown project analysis flags"):
        resolve_stage_contract({"analysis": {"telepathy": True}})


def test_ai26_core_flags_have_runtime_or_projection_contracts() -> None:
    for flag in (
        "laclau",
        "palonen",
        "sociotechnical_imaginaries",
        "sentiment",
        "topics",
        "entities",
        "context_memory",
        "temporal",
        "multimodal",
        "dna_statement_coding",
        "critical_ai",
    ):
        capability = STAGE_CAPABILITIES[flag]
        assert capability.status == "implemented"
        assert capability.runtime_stage


def test_negative_ai26_flags_are_explicit_exclusions() -> None:
    for flag in ("sna", "ant", "valueflows"):
        assert STAGE_CAPABILITIES[flag].status == "excluded"


def test_nested_optional_stage_enablement() -> None:
    config = {"analysis": {"critical_ai": {"enabled": True}}}
    assert stage_enabled(config, "critical_ai") is True
