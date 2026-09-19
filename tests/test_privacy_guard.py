"""Privacy/publication guard tests (issue #2).

These tests verify the repository-level publication rules: ignored private
paths, ignored data/config artefacts and a public-tree hygiene scan. All
fixtures are synthetic.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _is_ignored(relpath: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=REPO_ROOT,
    )
    return proc.returncode == 0


def test_private_codebook_directory_is_ignored():
    assert _is_ignored("codebooks/private/anything.md")
    assert _is_ignored("codebooks/private/nested/study_codebook.md")


def test_public_and_example_codebooks_are_tracked():
    assert not _is_ignored("codebooks/public/seed_ai_formations.md")
    assert not _is_ignored("codebooks/examples/synthetic_example.md")
    assert not _is_ignored("codebooks/README.md")


def test_research_data_and_config_patterns_are_ignored():
    for path in (
        "var/data/corpus.sqlite3",
        "artifacts/export.jsonl",
        ".env",
        "config.private.toml",
        "secrets.json",
        "credentials.json",
    ):
        assert _is_ignored(path), f"{path} must stay ignored"


def test_no_real_codebook_material_in_public_tree():
    """Diary-grounded legacy codebooks must never enter the public tree."""
    public_codebooks = list((REPO_ROOT / "codebooks" / "public").rglob("*.md"))
    forbidden_markers = ("research diary", "diary rows", "entities.xlsx")
    for codebook in public_codebooks:
        text = codebook.read_text(encoding="utf-8").lower()
        for marker in forbidden_markers:
            assert marker not in text, f"{codebook.name} contains private-source marker {marker!r}"


def test_public_codebooks_declare_synthetic_or_public_grounding():
    public_codebooks = list((REPO_ROOT / "codebooks" / "public").rglob("*.md"))
    assert public_codebooks, "public codebooks must exist"
    for codebook in public_codebooks:
        text = codebook.read_text(encoding="utf-8").lower()
        assert ("paper" in text or "synthetic" in text or "exploratory" in text), (
            f"{codebook.name} does not declare its grounding"
        )

def test_no_hard_coded_mapbox_token_in_tracked_python():
    """Mapbox credentials must come from environment/private configuration only."""
    token_prefixes = ("pk.", "sk.")
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "venv"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        if "mapbox" not in lowered:
            continue
        for prefix in token_prefixes:
            assert prefix not in text, f"{path.relative_to(REPO_ROOT)} appears to contain a hard-coded Mapbox token"
