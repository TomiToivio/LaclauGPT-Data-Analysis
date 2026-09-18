"""Minimal Phase 0 RSS collector.

Reads RSS/Atom feeds, extracts text-only entries and upserts them directly into
MongoDB. No Telegram, media download, translation, Redis, Allas or multimodal
processing.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from datetime import datetime, timezone
from typing import Any

import feedparser

from laclaugpt_mongo import upsert_document


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _entry_url(entry: Any) -> str:
    return _text(entry.get("link") or entry.get("id"))


def _entry_text(entry: Any) -> str:
    content = entry.get("content") or []
    if content and isinstance(content, list):
        value = content[0].get("value")
        if value:
            return _text(value)
    return _text(entry.get("summary") or entry.get("description") or entry.get("title"))


def _published(entry: Any) -> str:
    return _text(entry.get("published") or entry.get("updated")) or datetime.now(timezone.utc).isoformat()


def collect_feed(feed_url: str, *, project_id: str = "ai26", limit: int = 100) -> int:
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Could not parse RSS feed: {feed_url}")

    feed_title = _text(parsed.feed.get("title")) or feed_url
    written = 0
    for entry in parsed.entries[:limit]:
        source_url = _entry_url(entry)
        source_text = _entry_text(entry)
        if not source_url or not source_text:
            continue

        fields = {
            "source_url": source_url,
            "source_id": hashlib.sha256(source_url.encode("utf-8")).hexdigest(),
            "source_name": feed_title,
            "source_type": "rss",
            "source_feed_url": feed_url,
            "source_date": _published(entry),
            "title": _text(entry.get("title")),
            "source_text": source_text,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_document(source_url, fields, project_id=project_id)
        written += 1
    return written


def _feed_urls(cli_urls: list[str]) -> list[str]:
    if cli_urls:
        return cli_urls
    return [url.strip() for url in os.getenv("LACLAUGPT_RSS_FEEDS", "").split(",") if url.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect RSS text into MongoDB")
    parser.add_argument("feed_url", nargs="*")
    parser.add_argument("--project", default=os.getenv("LACLAUGPT_PROJECT_ID", "ai26"))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    feeds = _feed_urls(args.feed_url)
    if not feeds:
        raise SystemExit("Provide RSS URLs or set comma-separated LACLAUGPT_RSS_FEEDS")

    total = 0
    for feed_url in feeds:
        count = collect_feed(feed_url, project_id=args.project, limit=args.limit)
        print(f"{feed_url}: {count} entries upserted")
        total += count
    print(f"Total: {total} entries upserted")


if __name__ == "__main__":
    main()
