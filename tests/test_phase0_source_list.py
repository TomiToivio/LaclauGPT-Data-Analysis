"""Phase 0 AI26 source-list and feed-validation contracts (issue #171).

The live-feed checks are exercised by ``laclaugpt_validate_rss.py`` against the
network; these tests pin the *offline* contract so a regression is caught in CI
without contacting a single external host.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laclaugpt"))

import ai26_rss  # noqa: E402

# --------------------------------------------------------------------------
# Source-list contract
# --------------------------------------------------------------------------

def test_every_source_declares_the_canonical_metadata_fields() -> None:
    required = {
        "id", "project", "arena", "actor_name", "actor_type", "ai_formation",
        "political_formation", "source_type", "source_name", "source_url",
        "feed_url", "country", "language", "description", "notes", "active",
    }
    for source in ai26_rss.SOURCES:
        missing = required - set(source)
        assert not missing, f"{source.get('id')} missing {sorted(missing)}"


def test_active_sources_are_shape_valid() -> None:
    """``active_sources()`` enforces the controlled vocabularies."""
    for source in ai26_rss.active_sources():
        assert source["source_type"] == "rss"
        assert source["arena"] in ai26_rss.ARENAS
        assert source["actor_type"] in ai26_rss.ACTOR_TYPES
        assert source["ai_formation"] in ai26_rss.AI_FORMATIONS
        assert source["political_formation"] in ai26_rss.POLITICAL_FORMATIONS


def test_formations_default_to_unknown() -> None:
    """Formation labels are provisional hints, never inferred defaults."""
    for source in ai26_rss.SOURCES:
        assert source["ai_formation"] in ai26_rss.AI_FORMATIONS
        assert source["political_formation"] in ai26_rss.POLITICAL_FORMATIONS


def test_canonical_ai_formations_are_the_documented_set() -> None:
    assert ai26_rss.AI_FORMATIONS == {
        "existential_risk", "accelerationist", "left_accelerationist",
        "ai_safety", "critical_ai", "anti_ai", "other", "unknown",
    }


def test_ai_system_is_an_actor_type() -> None:
    """Non-human actors are supported in the ontology."""
    assert "ai_system" in ai26_rss.ACTOR_TYPES


def test_arenas_are_the_documented_set() -> None:
    assert ai26_rss.ARENAS == {
        "elite", "parliamentary", "grassroots", "media", "science",
        "corporation", "other",
    }


def test_no_source_id_is_duplicated() -> None:
    ids = [source["id"] for source in ai26_rss.SOURCES]
    assert len(ids) == len(set(ids)), "source ids must be unique"


def test_no_feed_url_is_duplicated() -> None:
    urls = [source["feed_url"] for source in ai26_rss.SOURCES]
    duplicates = {url for url in urls if urls.count(url) > 1}
    assert not duplicates, f"duplicate feed_url(s): {sorted(duplicates)}"


def test_people_and_organizations_are_separate_actors() -> None:
    """#171: do not merge a person with the organization they are tied to."""
    actors = {source["actor_name"] for source in ai26_rss.SOURCES}
    for combined in ("LessWrong / Eliezer Yudkowsky", "Timnit Gebru / DAIR"):
        assert combined not in actors


def test_geographic_representation_is_present() -> None:
    """Phase 0 must not be US-only: core + semiperiphery + periphery."""
    countries = {source["country"] for source in ai26_rss.SOURCES}
    for country in ("US", "CN", "FI", "IN"):
        assert country in countries, f"missing representation for {country}"
    assert "EU" in countries


def test_science_and_corporation_arenas_are_represented() -> None:
    arenas = {source["arena"] for source in ai26_rss.SOURCES}
    assert "science" in arenas
    assert "corporation" in arenas


def test_no_source_requires_anything_but_rss() -> None:
    """Phase 0 collects RSS only; later platforms attach to the same actor."""
    assert all(source["source_type"] == "rss" for source in ai26_rss.SOURCES)
