"""AI26 RSS source metadata for the minimal Phase 0 corpus.

One corpus, many metadata views. Arenas and formations are filters/hints only.
Phase 0 collects RSS/Atom only, while actor_name is the canonical cross-platform
identity for later X/YouTube/etc. adapters.
"""

AI_FORMATIONS = {
    "existential_risk",
    "accelerationist",
    "left_accelerationist",
    "ai_safety",
    "critical_ai",
    "anti_ai",
    "other",
    "unknown",
}

POLITICAL_FORMATIONS = {
    "far_left",
    "centre_left",
    "centre",
    "centre_right",
    "far_right",
    "unknown",
}

ARENAS = {"elite", "parliamentary", "grassroots", "media", "science", "corporation", "other"}

ACTOR_TYPES = {
    "individual",
    "ai_system",
    "corporation",
    "party",
    "government",
    "parliament",
    "media",
    "movement",
    "institute",
    "publication",
    "other",
}

# Keep the seed list intentionally small and editable. Add only feeds that are
# known/stable enough to be useful for the first Phase 0 corpus.
SOURCES = [
    {
        "id": "lesswrong",
        "project": "ai26",
        "arena": "elite",
        "actor_name": "LessWrong",
        "actor_type": "publication",
        "ai_formation": "existential_risk",
        "political_formation": "unknown",
        "source_type": "rss",
        "source_name": "LessWrong RSS",
        "source_url": "https://www.lesswrong.com/",
        "feed_url": "https://www.lesswrong.com/feed.xml",
        "country": "US",
        "language": "en",
        "description": "Seed publication for AI existential-risk discourse.",
        "notes": "Preserve post authors; non-public users should be anonymized in published outputs.",
        "homepage_url": "https://www.lesswrong.com/",
        "active": True,
    },
    {
        "id": "nick_srnicek",
        "project": "ai26",
        "arena": "elite",
        "actor_name": "Nick Srnicek",
        "actor_type": "individual",
        "ai_formation": "left_accelerationist",
        "political_formation": "far_left",
        "source_type": "rss",
        "source_name": "Silicon Empires",
        "source_url": "https://siliconempires.substack.com/",
        "feed_url": "https://siliconempires.substack.com/feed",
        "country": "GB",
        "language": "en",
        "description": "Seed actor for left-accelerationist and post-work technological discourse.",
        "notes": "",
        "homepage_url": "https://siliconempires.substack.com/",
        "active": True,
    },
    {
        "id": "pauseai",
        "project": "ai26",
        "arena": "grassroots",
        "actor_name": "PauseAI",
        "actor_type": "movement",
        "ai_formation": "anti_ai",
        "political_formation": "unknown",
        "source_type": "rss",
        "source_name": "PauseAI RSS",
        "source_url": "https://pauseai.info/",
        "feed_url": "https://pauseai.substack.com/feed",
        "country": "NL",
        "language": "en",
        "description": "Seed grassroots pause/anti-AI movement.",
        "notes": "",
        "homepage_url": "https://pauseai.info/",
        "active": True,
    },
    {
        "id": "openai",
        "project": "ai26",
        "arena": "corporation",
        "actor_name": "OpenAI",
        "actor_type": "corporation",
        "ai_formation": "unknown",
        "political_formation": "unknown",
        "source_type": "rss",
        "source_name": "OpenAI News RSS",
        "source_url": "https://openai.com/news/",
        "feed_url": "https://openai.com/news/rss.xml",
        "country": "US",
        "language": "en",
        "description": "Major AI corporation.",
        "notes": "",
        "homepage_url": "https://openai.com/",
        "active": True,
    },
    {
        "id": "yle_ai",
        "project": "ai26",
        "arena": "media",
        "actor_name": "Yle",
        "actor_type": "media",
        "ai_formation": "unknown",
        "political_formation": "unknown",
        "source_type": "rss",
        "source_name": "Yle latest news, AI category filter",
        "source_url": "https://yle.fi/uutiset",
        "feed_url": "https://yle.fi/rss/uutiset/tuoreimmat",
        "country": "FI",
        "language": "fi",
        "description": "Finnish public-service media source filtered to AI-tagged items.",
        "notes": "",
        "filters": {"category": ["Tekoäly"]},
        "homepage_url": "https://yle.fi/",
        "active": True,
    },
]


def active_sources():
    """Return validated-shape active RSS source configs."""
    result = []
    for source in SOURCES:
        if not source.get("active", True):
            continue
        source = dict(source)
        source.setdefault("ai_formation", "unknown")
        source.setdefault("political_formation", "unknown")
        source.setdefault("notes", "")
        if source.get("source_type") != "rss":
            raise ValueError(f"Phase 0 supports RSS only: {source['id']}")
        if source["arena"] not in ARENAS:
            raise ValueError(f"Unknown arena for {source['id']}: {source['arena']}")
        if source["actor_type"] not in ACTOR_TYPES:
            raise ValueError(f"Unknown actor_type for {source['id']}: {source['actor_type']}")
        if source["ai_formation"] not in AI_FORMATIONS:
            raise ValueError(f"Unknown ai_formation for {source['id']}: {source['ai_formation']}")
        if source["political_formation"] not in POLITICAL_FORMATIONS:
            raise ValueError(
                f"Unknown political_formation for {source['id']}: {source['political_formation']}"
            )
        result.append(source)
    return result
