"""Source-text quality for AI26 (#449).

A share of collected records stores the page's markup, stylesheet or script bundle as
`content.text`. The interpretive stages then read CSS custom properties or a New Relic
bundle and, because nothing tells them the input is unusable, produce formations and
signifiers from it.

This module does not rewrite the source. The canonical contract in `stages/preprocess.py`
is that the captured material survives untouched, and evidence offsets are validated
against `content.text` exactly as stored, so silently substituting a cleaned body would
break the audit trail. What it provides instead:

* a classifier that says what a text *is* (`prose`, `markup_heavy`, `code`, `empty`) with
  the measurements behind the verdict, so a stage or an export can act on it;
* `strip_markup()`, for callers that explicitly want a readable body and can say which
  representation they used.

The evidence-offset interaction is the reason this is a classifier first: if the model
reads a stripped body, its quotations come from that body and must be validated against
it, not against the raw capture.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

_TAG = re.compile(r"<[a-zA-Z/!][^>]{0,300}>")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_CSS_DECLARATION = re.compile(r"--[a-zA-Z-]+\s*:|[a-zA-Z-]+\s*:\s*(?:#[0-9a-fA-F]{3,8}|rgba?\(|\d+px)")
_JS_TOKENS = re.compile(r"\bfunction\s*\(|=>\s*\{|window\.[A-Za-z_]+|\bvar\s+[A-Za-z_$]|!function\(")
_JSON_LD = re.compile(r'"@(?:context|type)"\s*:')
_WHITESPACE = re.compile(r"\s+")

#: Below this many characters after stripping, a record cannot support interpretation.
MIN_READABLE_CHARS = 120
#: Above this share of the text inside tags or CSS declarations, the body is not prose.
MARKUP_SHARE_LIMIT = 0.25


@dataclass(frozen=True)
class TextQuality:
    """What a stored text is, and the numbers the verdict rests on."""

    kind: str
    characters: int
    readable_characters: int
    markup_share: float
    tag_count: int
    css_declarations: int
    javascript_markers: int
    json_ld: bool

    @property
    def usable_for_interpretation(self) -> bool:
        return self.kind in {"prose", "sparse_prose"}

    def audit(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "characters": self.characters,
            "readable_characters": self.readable_characters,
            "markup_share": round(self.markup_share, 3),
            "tag_count": self.tag_count,
            "css_declarations": self.css_declarations,
            "javascript_markers": self.javascript_markers,
            "json_ld": self.json_ld,
            "usable_for_interpretation": self.usable_for_interpretation,
        }


def strip_markup(text: str) -> str:
    """Scripts, styles and tags removed, entities unescaped, whitespace collapsed.

    A readable body for a caller that says which representation it is using. It is not a
    substitute for the captured text: offsets computed here do not index `content.text`.
    """
    without_code = _SCRIPT_OR_STYLE.sub(" ", text or "")
    without_tags = _TAG.sub(" ", without_code)
    return _WHITESPACE.sub(" ", html.unescape(without_tags)).strip()


def analyse_text_quality(text: str | None) -> TextQuality:
    """Classify a stored text and report the measurements behind the class."""
    original = text or ""
    characters = len(original)
    stripped = strip_markup(original)
    readable = len(stripped)

    tag_count = len(_TAG.findall(original))
    css = len(_CSS_DECLARATION.findall(original))
    js = len(_JS_TOKENS.findall(original))
    json_ld = bool(_JSON_LD.search(original))
    braces = original.count("{") + original.count("}")

    removed = max(characters - readable, 0)
    markup_share = removed / characters if characters else 0.0

    if not original.strip() or readable == 0:
        kind = "empty"
    # A stylesheet, a script bundle or an embedded JSON blob has no markup to strip — the
    # whole body *is* code — so these are decided by marker density, not by how much a tag
    # strip removed. Braces are the tell: prose does not carry them in bulk.
    elif braces >= 5 and css >= 5:
        kind = "code"
    elif braces >= 5 and js >= 3:
        kind = "code"
    elif braces >= 3 and json_ld:
        kind = "code"
    elif markup_share >= MARKUP_SHARE_LIMIT and tag_count >= 5:
        kind = "markup_heavy"
    elif readable < MIN_READABLE_CHARS:
        kind = "sparse_prose"
    else:
        kind = "prose"

    return TextQuality(
        kind=kind,
        characters=characters,
        readable_characters=readable,
        markup_share=markup_share,
        tag_count=tag_count,
        css_declarations=css,
        javascript_markers=js,
        json_ld=json_ld,
    )
