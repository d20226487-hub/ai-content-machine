"""Autotool column selection: build_table_csv emits only the chosen columns.

The column filter is the pure part (which columns land in the header/body); the
cell lookup is DB, so we feed an empty cells result and assert the shape. The
enable endpoint + live CSV are exercised against the running stack.
"""
from __future__ import annotations

import pytest

from app.services.autotool_files import (
    missing_required_columns,
    required_columns_error,
)
from app.services.bulk_csv import build_table_csv


class _Res:
    def scalars(self):
        return self

    def all(self):
        return []  # no cells — we only care about which columns are emitted


class _FakeDB:
    async def execute(self, *_a, **_k):
        return _Res()


class _Col:
    def __init__(self, cid: int, name: str):
        self.id = cid
        self.name = name


class _Row:
    def __init__(self, rid: int):
        self.id = rid


class _Table:
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows


@pytest.mark.asyncio
async def test_include_column_ids_filters_header_and_body():
    table = _Table(
        columns=[_Col(1, "A"), _Col(2, "B"), _Col(3, "C")],
        rows=[_Row(10)],
    )
    csv = await build_table_csv(_FakeDB(), table, include_column_ids={1, 3})
    lines = csv.splitlines()
    assert lines[0] == "A,C"  # B is dropped
    assert lines[1] == ","  # one row, two empty cells (A, C)


@pytest.mark.asyncio
async def test_none_includes_every_column():
    table = _Table(columns=[_Col(1, "A"), _Col(2, "B")], rows=[])
    csv = await build_table_csv(_FakeDB(), table, include_column_ids=None)
    assert csv.splitlines()[0] == "A,B"


# ----- required-column guard (missing_required_columns) -----


def test_required_all_present():
    assert (
        missing_required_columns(["domain", "post_type", "slug", "status", "title"])
        == []
    )


def test_required_site_is_accepted_for_domain_role():
    # `site` satisfies the domain role; the other three still exact.
    assert missing_required_columns(["site", "post_type", "slug", "status"]) == []


def test_required_matching_is_case_insensitive_and_trimmed():
    assert (
        missing_required_columns([" Domain ", "POST_TYPE", "Slug", "  status"]) == []
    )


def test_required_reports_missing_in_spec_order():
    # Only slug present → the other three come back, in domain/post_type/status order.
    assert missing_required_columns(["slug", "title", "content"]) == [
        "domain",
        "post_type",
        "status",
    ]


def test_required_empty_input_misses_all_four():
    assert missing_required_columns([]) == ["domain", "post_type", "slug", "status"]


def test_required_matching_is_exact_no_synonyms():
    # Plurals / near-variants are NOT accepted (exact names only): `sites`,
    # `domains`, `url`, `post type` (space), `post_status` all fail to match.
    assert missing_required_columns(
        ["sites", "domains", "url", "post type", "post_status"]
    ) == ["domain", "post_type", "slug", "status"]


def test_required_error_lists_missing():
    msg = required_columns_error(["domain", "slug"])
    assert "domain, slug" in msg
    assert "Autotool" in msg
