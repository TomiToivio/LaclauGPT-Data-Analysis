"""Minimal AI26 RSS/Atom collector for Phase 0.

Reads the hand-maintained AI26 source list, attaches canonical actor/source
metadata, applies optional category filters and upserts all records into the
same project MongoDB corpus. Arenas/formations remain metadata only.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests

from ai26_rss import active_sources
from laclaugpt_mongo import upsert_document


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _strip_html(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def _canonicalize_url(url: str) -> str:
    """Normalize article URLs for stable identity and deduplication."""
    url = _text(url)
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return url
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not any(key.lower().startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _entry_url(entry: Any) -> str:
    return _canonicalize_url(entry.get("link") or entry.get("id"))


def _entry_summary(entry: Any) -> str:
    content = entry.get("content") or []
    if content and isinstance(content, list):
        value = content[0].get("value")
        if value:
            return _strip_html(_text(value))
    return _strip_html(_text(entry.get("summary") or entry.get("description") or entry.get("title")))


def _entry_categories(entry: Any) -> list[str]:
    values: list[str] = []
    for tag in entry.get("tags") or []:
        term = _text(tag.get("term"))
        if term:
            values.append(term)
    return values


def _entry_author(entry: Any) -> str:
    return _text(entry.get("author") or entry.get("creator"))


def _published(entry: Any) -> str:
    return _text(entry.get("published") or entry.get("updated")) or datetime.now(timezone.utc).isoformat()


def _matches_filters(source: dict[str, Any], entry: Any) -> bool:
    filters = source.get("filters") or {}
    wanted_categories = filters.get("category") or []
    if wanted_categories:
        categories = _entry_categories(entry)
        if not any(category in categories for category in wanted_categories):
            return False
    return True


def _fetch_full_text(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "LaclauGPT-Phase0-RSS/1.0"},
            allow_redirects=True,
        )
        response.raise_for_status()
        return _strip_html(response.text)
    except requests.RequestException:
        return ""


def collect_source(
    source: dict[str, Any],
    *,
    project_id: str = "ai26",
    limit: int = 100,
    fetch_full_text: bool = True,
) -> int:
    parsed = feedparser.parse(source["feed_url"])
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Could not parse RSS feed: {source['feed_url']}")

    written = 0
    for entry in parsed.entries[:limit]:
        if not _matches_filters(source, entry):
            continue

        source_url = _entry_url(entry)
        if not source_url:
            continue

        summary = _entry_summary(entry)
        full_text = _fetch_full_text(source_url) if fetch_full_text else ""
        source_text = full_text or summary
        if not source_text:
            continue

        source_url = _canonicalize_url(source_url)
        source_id = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        fields = {
            "document_id": source_id,
            "source_id": source_id,
            "project": source.get("project", project_id),
            "source_url": source_url,
            "source_name": source["source_name"],
            "source_type": "rss",
            "source_feed_url": source["feed_url"],
            "source_date": _published(entry),
            "source_title": _text(entry.get("title")),
            "source_text": source_text,
            "source_summary": summary,
            "source_author": _entry_author(entry),
            "source_categories": _entry_categories(entry),
            "content_hash": content_hash,
            "actor_name": source["actor_name"],
            "actor_type": source["actor_type"],
            "arena": source["arena"],
            "ai_formation": source.get("ai_formation", "unknown"),
            "political_formation": source.get("political_formation", "unknown"),
            "country": source.get("country", ""),
            "language": source.get("language", ""),
            "description": source.get("description", ""),
            "notes": source.get("notes", ""),
            "wikipedia_url": source.get("wikipedia_url", ""),
            "wikidata_id": source.get("wikidata_id", ""),
            "homepage_url": source.get("homepage_url", ""),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_document(source_url, fields, project_id=project_id)
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect AI26 Phase 0 RSS text into MongoDB")
    parser.add_argument("--project", default=os.getenv("LACLAUGPT_PROJECT_ID", "ai26"))
    parser.add_argument("--source", help="collect only one source id")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--no-full-text",
        action="store_true",
        help="use feed summary/content instead of fetching the article page",
    )
    args = parser.parse_args()

    sources = active_sources()
    if args.source:
        sources = [source for source in sources if source["id"] == args.source]
        if not sources:
            raise SystemExit(f"Unknown source id: {args.source}")

    total = 0
    failures = 0
    for source in sources:
        try:
            count = collect_source(
                source,
                project_id=args.project,
                limit=args.limit,
                fetch_full_text=not args.no_full_text,
            )
            print(f"{source['id']}: {count} entries upserted")
            total += count
        except Exception as exc:
            failures += 1
            print(f"{source['id']}: ERROR {exc}")
    print(f"Total: {total} entries upserted")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
