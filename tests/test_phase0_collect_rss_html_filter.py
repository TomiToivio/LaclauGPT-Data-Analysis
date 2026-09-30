"""Regression coverage for the HTML tag filter in the Phase 0 RSS collector.

A tag-stripping regular expression cannot remove ``script``/``style`` bodies
safely: HTML permits whitespace and line breaks inside an end tag, so a literal
``</script>`` pattern misses ``</script >`` and leaks the script body into the
collected text. CodeQL reported this as ``py/bad-tag-filter``.

The filter now uses ``html.parser.HTMLParser``, which understands end-tag
syntax. These tests pin both the security property (nothing hidden leaks) and
the visible-text behaviour the previous implementation produced.
"""
from __future__ import annotations

import laclaugpt_collect_rss
import pytest

# A marker that must never survive extraction from inside a hidden element.
HIDDEN_BODY = "HIDDENMARKER"


@pytest.mark.parametrize(
    "raw",
    [
        f"<p>ok</p><script>{HIDDEN_BODY}</script><p>done</p>",
        # HTML allows whitespace before the '>' of an end tag; the old regex
        # required a literal "</script>" and therefore leaked these.
        f"<p>ok</p><script>{HIDDEN_BODY}</script ><p>done</p>",
        f"<p>ok</p><script>{HIDDEN_BODY}</script\n><p>done</p>",
        f"<p>ok</p><script>{HIDDEN_BODY}</script\t><p>done</p>",
        f"<P>ok</P><SCRIPT>{HIDDEN_BODY}</SCRIPT ><P>done</P>",
        # Attributes, including a stray '>' inside a quoted attribute value.
        f'<script type="text/javascript" data-x="a>b">{HIDDEN_BODY}</script >',
        # Unterminated: nothing after the opening script tag may be emitted.
        f"<p>ok</p><script>{HIDDEN_BODY}",
        f"<style>{HIDDEN_BODY}</style ><p>text</p>",
        f"<style>{HIDDEN_BODY}",
    ],
)
def test_hidden_element_bodies_are_never_extracted(raw: str) -> None:
    assert HIDDEN_BODY not in laclaugpt_collect_rss._strip_html(raw)


def test_end_tag_variants_that_close_the_element_are_honoured() -> None:
    """Every spelling that actually closes a script element is treated as a close.

    The alert class was end tags a literal ``</script>`` pattern misses. A parser
    recognises all of these, so content *after* them is visible text while the
    element body stays hidden.
    """
    for end_tag in ("</script>", "</script >", "</script\n>", "</script\t>"):
        raw = f"<p>visible</p><script>{HIDDEN_BODY}{end_tag}after"
        out = laclaugpt_collect_rss._strip_html(raw)
        assert HIDDEN_BODY not in out, f"{end_tag!r} leaked the script body"
        assert "after" in out, f"{end_tag!r} was not recognised as a close"


def test_a_fake_end_tag_attribute_does_not_reopen_the_element() -> None:
    """An unrecognised close-like spelling must not end hiding mid-element.

    ``</script data-thing>`` is not a valid end tag for the element (an end tag
    carries no attributes), so the parser keeps the body hidden rather than
    emitting the remainder as visible text. This is the property the old
    substring pattern could not express at all.
    """
    raw = f"<script>x</script-bogus>{HIDDEN_BODY}</script >"
    assert HIDDEN_BODY not in laclaugpt_collect_rss._strip_html(raw)


def test_visible_text_is_kept_and_tags_become_separators() -> None:
    assert laclaugpt_collect_rss._strip_html("<p>a</p><p>b</p>") == "a b"
    assert laclaugpt_collect_rss._strip_html("<div>hello <b>world</b></div>") == "hello world"
    assert laclaugpt_collect_rss._strip_html("just words") == "just words"


def test_entities_are_decoded_once() -> None:
    assert laclaugpt_collect_rss._strip_html("a &amp; b &lt;tag&gt;") == "a & b <tag>"


def test_whitespace_is_collapsed_and_empty_input_is_safe() -> None:
    assert laclaugpt_collect_rss._strip_html("  a \n\n  b  ") == "a b"
    assert laclaugpt_collect_rss._strip_html("") == ""
    assert laclaugpt_collect_rss._strip_html("<p></p>") == ""
