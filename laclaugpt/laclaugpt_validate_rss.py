"""Validate AI26 Phase 0 RSS/Atom source feeds without writing to MongoDB.

Checks the feed-level acceptance criteria from issue #171:
- HTTP success
- valid RSS/Atom
- at least one item
- sensible item date where a date is present
- no obvious duplicate feed/canonical item URLs
- canonical article URL retained
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests

from ai26_rss import SOURCES
from laclaugpt_collect_rss import _canonicalize_url, _entry_url

USER_AGENT = "LaclauGPT-Phase0-RSS-Validator/1.0"


def _parse_entry_date(entry: Any) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if not struct:
            return None
        try:
            return datetime(*struct[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None


def validate_source(source: dict[str, Any], timeout: int = 20) -> tuple[bool, list[str]]:
    errors: list[str] = []
    feed_url = source["feed_url"]

    try:
        response = requests.get(
            feed_url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return False, [f"HTTP failure: {exc}"]

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        errors.append(f"invalid RSS/Atom: {parsed.bozo_exception}")
    if not parsed.entries:
        errors.append("feed has no items")
        return False, errors

    canonical_urls: list[str] = []
    future_dates = 0
    dated_items = 0
    now = datetime.now(timezone.utc)

    for entry in parsed.entries:
        url = _entry_url(entry)
        if not url:
            errors.append("item without canonical article URL")
            continue
        canonical_urls.append(_canonicalize_url(url))

        item_date = _parse_entry_date(entry)
        if item_date is not None:
            dated_items += 1
            if item_date > now:
                future_dates += 1

    if dated_items and future_dates:
        errors.append(f"{future_dates}/{dated_items} dated items are in the future")

    duplicates = [url for url, count in Counter(canonical_urls).items() if count > 1]
    if duplicates:
        errors.append(f"{len(duplicates)} duplicate canonical item URL(s)")

    return not errors, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate AI26 Phase 0 RSS/Atom source feeds")
    parser.add_argument("--source", help="validate only one source id")
    parser.add_argument(
        "--all",
        action="store_true",
        help="include inactive candidate feeds as well as active feeds",
    )
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    sources = SOURCES if args.all else [source for source in SOURCES if source.get("active", True)]
    if args.source:
        sources = [source for source in sources if source["id"] == args.source]
        if not sources:
            raise SystemExit(f"Unknown source id for selected scope: {args.source}")

    failures = 0
    for source in sources:
        ok, errors = validate_source(source, timeout=args.timeout)
        state = "PASS" if ok else "FAIL"
        activation = "active" if source.get("active", True) else "candidate"
        print(f"{state} {source['id']} ({activation}) {source['feed_url']}")
        for error in errors:
            print(f"  - {error}")
        if not ok:
            failures += 1

    print(f"Validated {len(sources)} source(s); failures: {failures}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
