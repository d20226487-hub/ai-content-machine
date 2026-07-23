"""The link-fix "reuse a same-named column" rule.

Re-running an AI link fix with the same target name (the default "Fixed links",
most often) should feed the column that's already there rather than pile up
duplicates beside it. The endpoint decides this via ``_pick_named_column``; the
match rule is pinned here without a database, same style as the folder-cycle
helper tests in ``test_library_folders.py``.
"""
from __future__ import annotations

import pytest

from app.api.library import _pick_named_column


COLS = [(10, "content"), (11, "Fixed links"), (12, "Meta description")]


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("Fixed links", 11),      # exact
        ("fixed links", 11),      # case-insensitive
        ("FIXED LINKS", 11),      # upper
        ("  Fixed links  ", 11),  # surrounding whitespace ignored
        ("content", 10),          # matches any column, not just output ones
    ],
)
def test_matches_existing_column(requested, expected):
    assert _pick_named_column(COLS, requested) == expected


@pytest.mark.parametrize(
    "requested",
    [
        "Fixed links corrected",  # distinct name → new column
        "Fixed  links",           # collapsed interior space is a different name
        "Links",
        "",
    ],
)
def test_no_match_returns_none(requested):
    assert _pick_named_column(COLS, requested) is None


def test_empty_table_never_matches():
    assert _pick_named_column([], "Fixed links") is None


def test_first_match_wins_when_duplicates_already_exist():
    # Tables from before this change may already hold two "Fixed links"
    # columns; collapse future runs onto the first (lowest-position) one.
    dupes = [(1, "Fixed links"), (2, "fixed links")]
    assert _pick_named_column(dupes, "FIXED LINKS") == 1


def test_none_column_name_is_safe():
    # Defensive: a NULL name in the row set must not blow up the scan.
    assert _pick_named_column([(1, None), (2, "Fixed links")], "fixed links") == 2
