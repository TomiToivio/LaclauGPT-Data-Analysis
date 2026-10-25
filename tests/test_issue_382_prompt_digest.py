"""The published prompt digest must verify the published prompt text (issue #382).

Upstream #298 is the class: a value that survived a round trip in one representation was compared
against the same value in another representation, and the mismatch was reported as a failure. Here
the two representations are the file's on-disk bytes and the text the command publishes. On an LF
checkout they are the same bytes; on a checkout whose line endings were converted (CRLF, e.g. a
Windows working copy) they are not, and the published ``sha256`` no longer verified the ``text``
shipped beside it.

The contract pinned here does not depend on the platform: ``sha256(text.encode("utf-8"))`` must
equal the digest the command reports, for a CRLF file as much as for an LF one.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from laclaugpt_data_analysis import ai26
from laclaugpt_data_analysis.stages import prompt_map

SYSTEM_ID = "laclau.system"
TASK_ID = "laclau.discourse_analysis"


def _fake_prompts(tmp_path: Path, *, newline: str) -> Path:
    """Write one system and one task prompt with the requested line endings."""
    root = tmp_path / "prompts"
    for family, name in (SYSTEM_ID.split("."), TASK_ID.split(".")):
        target = root / family / f"{name}_v1.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        body = "You are a discourse analyst.\n\nRead the record, then answer.\n"
        target.write_bytes(body.replace("\n", newline).encode("utf-8"))
    return root


@pytest.mark.parametrize(("label", "newline"), [("lf", "\n"), ("crlf", "\r\n")])
def test_published_prompt_digest_verifies_published_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str, newline: str
) -> None:
    root = _fake_prompts(tmp_path, newline=newline)
    monkeypatch.setattr(ai26, "PROMPT_DIR", root)
    monkeypatch.setattr(ai26, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(prompt_map, "prompt_ids_for_stage", lambda profile, stage: (SYSTEM_ID, TASK_ID))

    record = ai26._prompt_record("discourse", "default")

    assert record["files"], label
    for item in record["files"]:
        text = (tmp_path / item["path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == item["sha256"], label
        assert item["chars"] == len(text), label


def test_digest_is_unchanged_on_an_lf_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The fix must not move the hashes published from an LF checkout (CI, Laskin)."""
    root = _fake_prompts(tmp_path, newline="\n")
    monkeypatch.setattr(ai26, "PROMPT_DIR", root)
    monkeypatch.setattr(ai26, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(prompt_map, "prompt_ids_for_stage", lambda profile, stage: (SYSTEM_ID, TASK_ID))

    record = ai26._prompt_record("discourse", "default")

    for item in record["files"]:
        raw = (tmp_path / item["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert item["chars"] == len(raw)
