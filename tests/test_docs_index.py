"""The docs index must list every document, and every link in it must resolve.

`docs/` carries 70+ topical notes and no one reads a directory listing; `docs/README.md` is the
entry point (generated from each file's own H1 by the same rules encoded here). An index that
silently omits the newest document is worse than none, because it looks complete.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
INDEX = DOCS / "README.md"


def documents() -> set[str]:
    return {path.name for path in DOCS.glob("*.md")} - {INDEX.name}


def links(index: str) -> set[str]:
    return set(re.findall(r"\]\(([A-Za-z0-9_.-]+\.md)\)", index))


def test_every_document_is_indexed():
    missing = documents() - links(INDEX.read_text(encoding="utf-8"))
    assert not missing, f"documented but not indexed in docs/README.md: {sorted(missing)}"


def test_the_index_links_nothing_that_is_missing():
    dangling = links(INDEX.read_text(encoding="utf-8")) - documents() - {"ARCHITECTURE.md"}
    assert not dangling, f"docs/README.md links files that do not exist: {sorted(dangling)}"


def test_the_architecture_map_exists_and_is_linked_from_the_root_readme():
    assert (DOCS / "ARCHITECTURE.md").is_file()
    root = (DOCS.parent / "README.md").read_text(encoding="utf-8")
    assert "docs/ARCHITECTURE.md" in root, "README must point a newcomer at the map"


@pytest.mark.parametrize("doc", ["ARCHITECTURE.md", "README.md"])
def test_the_entry_points_are_not_empty(doc: str):
    assert len((DOCS / doc).read_text(encoding="utf-8").strip()) > 300
