"""Shaping tests for the table generation-health summary.

The endpoint's SQL (per-column ``failed`` / ``truncated`` counts) is exercised
against the running stack; the interesting pure logic — which columns surface,
in what order, and how the table totals roll up — lives in ``_build_gen_health``
and is pinned here without a database, same style as the folder-cycle helper
tests in ``test_library_folders.py``.
"""
from __future__ import annotations

from app.api.library import _build_gen_health
from app.schemas.bulk import TableGenHealthRead


def _rows():
    # (column_id, name, failed, truncated)
    return [
        (1, "Article", 2, 3),
        (2, "Meta", 0, 0),   # clean — must be dropped
        (3, "Title", 1, 0),
        (4, "Body", 0, 5),
    ]


def test_drops_columns_with_no_problem():
    health = _build_gen_health(77, _rows())
    names = {c.column_name for c in health.columns}
    assert "Meta" not in names
    assert names == {"Article", "Title", "Body"}


def test_totals_sum_across_columns():
    health = _build_gen_health(77, _rows())
    assert health.table_id == 77
    assert health.failed == 3   # 2 (Article) + 1 (Title)
    assert health.truncated == 8  # 3 (Article) + 5 (Body)


def test_most_affected_column_is_first():
    # Article has 5 problem cells total, Body 5, Title 1. Article vs Body tie on
    # count breaks by name ('Article' < 'Body'), then Title trails.
    health = _build_gen_health(77, _rows())
    assert [c.column_name for c in health.columns] == ["Article", "Body", "Title"]


def test_clean_table_yields_empty_summary():
    health = _build_gen_health(5, [(1, "A", 0, 0), (2, "B", 0, 0)])
    assert health.failed == 0
    assert health.truncated == 0
    assert health.columns == []


def test_returns_the_response_model():
    assert isinstance(_build_gen_health(1, []), TableGenHealthRead)


def test_column_carries_its_own_split():
    # A column can hold both problem kinds at once; each is reported separately
    # so the banner can offer the right retry for each.
    health = _build_gen_health(1, [(9, "Mixed", 4, 6)])
    (col,) = health.columns
    assert (col.failed, col.truncated) == (4, 6)
