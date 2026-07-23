"""The em-dash transform for the Structure & Formatting tool.

Em dashes are a glaring "written by AI" tell; this transform swaps them for a
plain spaced hyphen. Pure-function tests (the module is deterministic regex, no
DB), plus the two contract facts the rest of the stack relies on: the op is
registered in the runner and ordered right after ``inline_css``.
"""
from __future__ import annotations

import pytest

from app.services.structure_format import (
    OPERATIONS,
    _FUNCS,
    apply_operations,
    apply_operations_traced,
    replace_em_dashes,
)


# ---- behaviour --------------------------------------------------------------


@pytest.mark.parametrize(
    "src,want",
    [
        # Glued (the common AI shape) gets spaces so it doesn't read as a
        # compound word.
        ("It was great—really great.", "It was great - really great."),
        ("fast—reliable", "fast - reliable"),
        # Already spaced collapses to a single spaced hyphen.
        ("spaced — dash", "spaced - dash"),
        ("wide  —  gap", "wide - gap"),
        # Multiple dashes in one string.
        ("a—b—c", "a - b - c"),
        # Horizontal bar (U+2015) is treated the same.
        ("a―b", "a - b"),
    ],
)
def test_replaces_em_dashes(src, want):
    assert replace_em_dashes(src) == want


@pytest.mark.parametrize(
    "src",
    [
        "",
        "no dashes here",
        "hyphen-minus stays as-is",
        "2020-2021",
        "en – dash is left alone",  # U+2013 is narrower and means "range"
    ],
)
def test_leaves_non_em_dashes_untouched(src):
    assert replace_em_dashes(src) == src


@pytest.mark.parametrize(
    "src,want",
    [
        # A dash flush against a line break or the cell edge must not leave a
        # dangling space, and must never merge two lines.
        ("line1—\nline2", "line1 -\nline2"),
        ("line1 — \nline2", "line1 -\nline2"),
        ("—lead", "- lead"),
        ("trail—", "trail -"),
        ("—", "-"),
    ],
)
def test_no_stray_space_at_boundaries(src, want):
    assert replace_em_dashes(src) == want


# ---- runner contract --------------------------------------------------------


def test_registered_in_runner():
    assert "em_dash" in _FUNCS
    assert set(_FUNCS) == set(OPERATIONS)


def test_ordered_directly_after_inline_css():
    # The UI renders operations in OPERATIONS order; the request placed this
    # tool "just under Inline CSS".
    assert OPERATIONS.index("em_dash") == OPERATIONS.index("inline_css") + 1


def test_apply_operations_runs_only_the_selected_op():
    # Selecting em_dash alone doesn't drag in other transforms.
    assert apply_operations("<p style='x'>great—stuff</p>", ["em_dash"]) == (
        "<p style='x'>great - stuff</p>"
    )


def test_traced_reports_em_dash_as_the_changer():
    out, changed = apply_operations_traced("great—stuff", ["inline_css", "em_dash"])
    assert out == "great - stuff"
    assert changed == ["em_dash"]  # inline_css didn't touch it
