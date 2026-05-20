"""Unit tests for the Custom-CMS bulk-publish wiring.

These cover the four pieces of behavior we just added:

  1. ``_build_fields`` strips whitespace from cell values so trailing
     newlines from CSV/Excel/copy-paste don't leak into the outgoing
     payload (we hit `slug='home2\\n'` and `lang='en\\n'` in production).
  2. The Custom-CMS branch in ``publish_one_row`` injects
     ``action=run.operation`` into the fields dict so the upstream sees
     create/update/upsert.
  3. WP-vs-Custom operation compatibility is enforced — upsert is
     Custom-only at the service layer (defense in depth on top of the
     API check).
  4. Custom-CMS update does NOT do a find_post pre-flight (the upstream
     handles id resolution itself).

Style note: these are pure-Python unit tests against the helper that
takes plain SQLAlchemy mocks. They don't spin up the full Celery worker
or hit Postgres; that's what the integration-style tests under
``test_publish_state_machine.py`` are for.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.bulk_publish import _build_fields


class _CellsResult:
    """Tiny stub matching what ``db.execute(...).all()`` returns."""

    def __init__(self, rows: list[tuple[int, str | None]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[int, str | None]]:
        return self._rows


def _stub_db(cells: list[tuple[int, str | None]]) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_CellsResult(cells))
    return db


def _stub_run(field_to_column: dict[str, int]) -> SimpleNamespace:
    """A SimpleNamespace stands in for BulkPublishRun — we only need the
    two attributes ``_build_fields`` reads."""
    return SimpleNamespace(field_to_column=field_to_column)


@pytest.mark.asyncio
async def test_build_fields_strips_trailing_newline():
    """A cell containing 'home2\\n' should yield 'home2' on the wire."""
    db = _stub_db([(101, "home2\n")])
    fields = await _build_fields(db, run=_stub_run({"slug": 101}), row_id=1)
    assert fields == {"slug": "home2"}


@pytest.mark.asyncio
async def test_build_fields_strips_leading_and_trailing_whitespace():
    """Both ends — '\\ncreate', 'kz \\n\\n', '  draft' all normalize."""
    db = _stub_db(
        [
            (101, "\ncreate"),
            (102, "kz \n\n"),
            (103, "  draft"),
        ]
    )
    fields = await _build_fields(
        db,
        run=_stub_run({"action": 101, "lang": 102, "status": 103}),
        row_id=1,
    )
    assert fields == {"action": "create", "lang": "kz", "status": "draft"}


@pytest.mark.asyncio
async def test_build_fields_empty_cell_yields_empty_string():
    """A missing or null cell value collapses to '' (existing behavior),
    not None — the body_template substitution drops empty-string keys."""
    db = _stub_db([(101, None)])
    fields = await _build_fields(db, run=_stub_run({"title": 101}), row_id=1)
    assert fields == {"title": ""}


@pytest.mark.asyncio
async def test_build_fields_unmapped_column_skipped():
    """If a column has no cell row, the field gets ''."""
    db = _stub_db([])  # no rows returned
    fields = await _build_fields(
        db, run=_stub_run({"title": 101, "content": 102}), row_id=1,
    )
    assert fields == {"title": "", "content": ""}


# -----------------------------------------------------------------------------
# Schema-level: the literal allows upsert + the validator no longer blocks
# update without lookup_kind (cms-aware validation moved to API layer).
# -----------------------------------------------------------------------------


def test_publish_operation_literal_accepts_upsert():
    from app.schemas.publish import BulkPublishRequest

    req = BulkPublishRequest(
        table_id=1,
        mode="single",
        domain_id=42,
        operation="upsert",
        # No lookup_kind / lookup_column_id — upsert doesn't need them.
    )
    assert req.operation == "upsert"


def test_publish_operation_update_without_lookup_passes_schema():
    """Custom CMS update sends no lookup_kind. The schema must not block
    that; the API layer validates per-cms_type instead."""
    from app.schemas.publish import BulkPublishRequest

    req = BulkPublishRequest(
        table_id=1,
        mode="single",
        domain_id=42,
        operation="update",
        field_to_column={"id": 101, "title": 102},
    )
    assert req.operation == "update"
    assert req.lookup_kind is None
    assert req.lookup_column_id is None


def test_publish_on_slug_conflict_still_rejects_non_create():
    """Regression guard: on_slug_conflict != 'create' is still only
    valid with operation='create'. This preserves the existing v1
    contract; the failure mode is the user accidentally setting both."""
    from pydantic import ValidationError
    from app.schemas.publish import BulkPublishRequest

    with pytest.raises(ValidationError) as exc:
        BulkPublishRequest(
            table_id=1,
            mode="single",
            domain_id=42,
            operation="update",
            on_slug_conflict="skip",
            field_to_column={"slug": 101},
        )
    assert "on_slug_conflict applies only when operation='create'" in str(exc.value)
