"""What a step receives.

``IncomingRecord`` is the readable view of one collected post, assembled by the
incoming database helper (``../db/incoming.py``). It carries identity, source
metadata and whatever upstream collection produced, and it is the only input a
step reads.

The canonical record in ``laclaugpt_data_analysis.canonical`` remains the
authoritative persisted schema. This model exists so the step files can stay
short, and every field here maps onto that schema.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MediaItem(BaseModel):
    """One image, video or other attachment, with whatever local path is known."""

    kind: str = ""  # image | video | audio | other
    url: str = ""
    local_path: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceInfo(BaseModel):
    """Where the record came from. Source lists are collection metadata, not theory."""

    platform: str = ""
    source_name: str = ""
    url: str = ""
    author: str = ""
    language: str | None = None
    country: str | None = None
    published_at: datetime | None = None
    # arena is an ordinary filterable metadata field, not a database partition.
    arena: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncomingRecord(BaseModel):
    """One record entering the analysis chain.

    ``source_url`` is the canonical identity (AGENTS.md: it must survive
    Collection -> Analysis -> Visualization unchanged). Every other identifier is
    a derived alias and must never replace it.
    """

    source_url: str
    source: SourceInfo = Field(default_factory=SourceInfo)

    # Text
    text: str = ""
    title: str | None = None
    language: str | None = None

    # Media, when collection captured any. A text-only record is valid
    # (AGENTS.md: never manufacture empty multimodal observations).
    media: list[MediaItem] = Field(default_factory=list)

    # Upstream collection output, passed through unchanged.
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    # Earlier steps' results, so a step can read what upstream steps produced.
    step_outputs: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_media(self) -> bool:
        """Whether this record carries anything the media steps can read."""
        return any(item.kind in {"image", "video"} for item in self.media)

    @property
    def video_items(self) -> list[MediaItem]:
        return [item for item in self.media if item.kind == "video"]

    @property
    def image_items(self) -> list[MediaItem]:
        return [item for item in self.media if item.kind == "image"]
