"""Issue #449: classify stored source text so boilerplate stops being read as prose.

The classifier exists because the fix cannot be "always strip": the canonical contract keeps
the captured material unchanged and evidence offsets index `content.text` as stored. A stage
that wants a readable body has to say so, and then validate offsets against that body.
"""
from __future__ import annotations

from laclaugpt_data_analysis.text_quality import (
    MIN_READABLE_CHARS,
    analyse_text_quality,
    strip_markup,
)

CSS_PAGE = """
#onetrust-pc-sdk .ot-cat-grp .ot-always-active { font-size: 14px !important; }
:root { --dotcom-chart-color-background: var(--color-background); --color-primary: #1a1a1a; }
@media (prefers-color-scheme: dark) { :root { background-color: #000; } }
.dotcom-chart-theme-scope[data-provider-scope="_R_3knpfivb_"] { --color-muted: rgba(0,0,0,.6); }
""" * 40

JS_PAGE = """
(window.NREUM||(NREUM={})).init={ajax:{deny_list:["bam.nr-data.net"]}};
window.WIZ_global_data = {"AfY8Hf":false,"FL1an":true,"MUE6Ne":"youtube_web"};
(()=>{var e={8122(e,t,r){"use strict";r.d(t,{a:()=>i});function i(e){try{return e}}catch(n){}}};
!function(){var root=document.documentElement;function apply(){}}();
""" * 30

RSS_WITH_TAGS = (
    "<p><i><span style=\"white-space: pre-wrap;\">"
    "AI in research and publishing: a discussion of how automated gatekeeping changes peer review, "
    "written as a long-form blog post with numbers, an argument and a conclusion.</span></i></p>"
)

PLAIN_PROSE = (
    "The European Commission fined a platform for failing to remove illegal content, and the "
    "decision sets out how the Digital Services Act will be enforced against very large platforms."
)


def test_stylesheet_dump_is_not_prose():
    quality = analyse_text_quality(CSS_PAGE)
    assert quality.kind == "code"
    assert quality.usable_for_interpretation is False
    assert quality.css_declarations >= 5


def test_javascript_bundle_is_not_prose():
    quality = analyse_text_quality(JS_PAGE)
    assert quality.kind == "code"
    assert quality.javascript_markers >= 3


def test_markup_wrapped_prose_is_markup_heavy_but_readable():
    quality = analyse_text_quality(RSS_WITH_TAGS)
    assert quality.kind in {"markup_heavy", "prose"}
    # The point of the class is that a reader can still recover the sentence.
    assert "automated gatekeeping" in strip_markup(RSS_WITH_TAGS)
    assert quality.markup_share > 0


def test_plain_prose_is_prose():
    quality = analyse_text_quality(PLAIN_PROSE)
    assert quality.kind == "prose"
    assert quality.usable_for_interpretation is True
    assert quality.markup_share == 0.0


def test_empty_and_missing_text_is_empty_not_sparse_prose():
    assert analyse_text_quality("").kind == "empty"
    assert analyse_text_quality(None).kind == "empty"
    assert analyse_text_quality("   \n\t ").kind == "empty"


def test_a_short_real_post_is_sparse_prose_not_unusable():
    short = "It was a great conversation."
    quality = analyse_text_quality(short)
    assert quality.kind == "sparse_prose"
    assert quality.readable_characters == len(short)
    assert quality.usable_for_interpretation is True


def test_strip_markup_unescapes_entities_and_drops_scripts():
    raw = "<p>A &amp; B</p><script>var x = 1;</script><style>.a{color:red}</style>"
    assert strip_markup(raw) == "A & B"


def test_the_audit_payload_is_json_serialisable_and_names_the_verdict():
    audit = analyse_text_quality(CSS_PAGE).audit()
    assert audit["kind"] == "code"
    assert audit["usable_for_interpretation"] is False
    assert set(audit) >= {"kind", "characters", "readable_characters", "markup_share", "tag_count"}


def test_minimum_readable_length_is_a_named_constant():
    assert MIN_READABLE_CHARS > 0
    body = "x" * (MIN_READABLE_CHARS - 1)
    assert analyse_text_quality(body).kind == "sparse_prose"
    body = "x" * (MIN_READABLE_CHARS + 1)
    assert analyse_text_quality(body).kind == "prose"
