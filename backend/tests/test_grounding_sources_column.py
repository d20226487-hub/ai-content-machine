"""Grounded sources -> sibling column text (fed to Link-Check).

One markdown ``[label](url)`` per cited source so Link-Check's OUTPUT extractor
crawls the URLs; sources without a URI are dropped, and an untitled source uses
its URL as the label. The endpoint that builds the column is exercised against
the running stack.
"""
from __future__ import annotations

from app.api.library import _format_grounding_sources


def test_formats_markdown_link_per_source():
    gs = {
        "sources": [
            {"uri": "https://a.example/x", "title": "A"},
            {"uri": "https://b.example/y", "title": ""},  # no title -> URL label
            {"title": "no uri"},  # dropped
            {"uri": "https://c.example/z"},
        ]
    }
    out = _format_grounding_sources(gs)
    assert out == (
        "[A](https://a.example/x)\n"
        "[https://b.example/y](https://b.example/y)\n"
        "[https://c.example/z](https://c.example/z)"
    )


def test_empty_inputs_yield_empty_string():
    assert _format_grounding_sources(None) == ""
    assert _format_grounding_sources({}) == ""
    assert _format_grounding_sources({"sources": []}) == ""
