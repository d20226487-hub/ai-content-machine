"""Schema + validator tests for the /publish/domains folder tree.

Endpoint-level CRUD lives behind an authenticated session + a Postgres
connection, which the existing test suite stubs out for unit-test speed.
This file mirrors the style of ``test_domains_picker.py``: pin the
schema contracts (what the wire payloads accept / reject) and the small
algorithmic helpers (cycle detection, folder_id query parsing) where we
can exercise them without spinning up the whole API.

End-to-end exercises happen against the running stack via manual curl
(see CI smoke list); the schema layer is what regresses subtly when
the model grows.
"""
from __future__ import annotations

import pytest

from app.schemas.domain_folder import (
    DomainBulkMove,
    DomainBulkTrash,
    DomainBulkTrashResult,
    DomainFolderCreate,
    DomainFolderRead,
    DomainFolderUpdate,
)


# ---- create / update payload validation ------------------------------------


def test_create_payload_requires_name():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainFolderCreate(name="")


def test_create_payload_caps_name_length():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainFolderCreate(name="x" * 121)


def test_create_payload_accepts_null_parent():
    """Null parent = top-level folder. Must round-trip cleanly."""
    payload = DomainFolderCreate(name="Projects", parent_id=None)
    assert payload.parent_id is None


def test_update_payload_distinguishes_unset_from_null_parent():
    """`exclude_unset=True` is what lets PATCH leave parent unchanged
    when the caller omits the field. Pin the behavior so a future
    pydantic upgrade doesn't quietly flip it."""
    omit = DomainFolderUpdate()
    set_to_null = DomainFolderUpdate(parent_id=None)

    assert "parent_id" not in omit.model_dump(exclude_unset=True)
    # Explicit None remains in the dump — that's how the API knows to
    # move the folder to the implicit root.
    assert "parent_id" in set_to_null.model_dump(exclude_unset=True)


# ---- bulk-move payload -----------------------------------------------------


def test_bulk_move_requires_at_least_one_id():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainBulkMove(domain_ids=[], folder_id=1)


def test_bulk_move_caps_batch_size():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainBulkMove(domain_ids=list(range(501)), folder_id=1)


def test_bulk_move_accepts_null_folder_for_root():
    """folder_id=null is the canonical way to move domains back to the
    implicit root. Must validate cleanly — the API uses this on the
    "Move to root" menu item."""
    payload = DomainBulkMove(domain_ids=[1, 2, 3], folder_id=None)
    assert payload.folder_id is None


# ---- bulk-trash ----------------------------------------------------------


def test_bulk_trash_requires_at_least_one_id():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainBulkTrash(domain_ids=[])


def test_bulk_trash_caps_batch_size():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainBulkTrash(domain_ids=list(range(501)))


def test_bulk_trash_result_partial_success_shape():
    """The partial-success contract is important: even if some rows are
    blocked, the call returns 200 with per-row reasons so the UI can
    show "X trashed, Y blocked" instead of refusing the whole batch."""
    result = DomainBulkTrashResult(
        trashed=3,
        blocked=[
            {"id": 7, "name": "site-a.example.com", "reason": "Active bulk publish run #42"},
            {"id": 99, "name": None, "reason": "Domain not found or already trashed."},
        ],
    )
    dumped = result.model_dump()
    assert dumped["trashed"] == 3
    assert len(dumped["blocked"]) == 2
    assert dumped["blocked"][0]["reason"].startswith("Active bulk publish")


def test_bulk_trash_result_empty_blocked_is_default():
    """A clean run yields blocked=[] (not null) so the UI can iterate
    unconditionally."""
    result = DomainBulkTrashResult(trashed=5)
    assert result.blocked == []


# ---- DomainFolderRead shape ------------------------------------------------


def test_folder_read_with_counts_fields_default_to_null():
    """`with_counts=false` (the cheap default) returns null counts so
    the response stays tiny. Frontend treats null as "not requested",
    not zero."""
    from datetime import datetime, timezone

    rec = DomainFolderRead(
        id=1,
        name="Projects",
        parent_id=None,
        created_by_id=42,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dumped = rec.model_dump()
    assert dumped["domain_count"] is None
    assert dumped["subfolder_count"] is None


# ---- cycle detection helper -----------------------------------------------


@pytest.mark.asyncio
async def test_cycle_helper_rejects_self_parent():
    """Setting a folder's parent_id to itself is a one-step cycle."""
    from unittest.mock import AsyncMock, MagicMock

    from app.api.domain_folders import _would_create_cycle

    db = MagicMock()
    db.execute = AsyncMock()  # never called when new_parent_id == folder_id

    assert await _would_create_cycle(db, folder_id=5, new_parent_id=5) is True


@pytest.mark.asyncio
async def test_cycle_helper_rejects_transitive_cycle():
    """Folder 5 → parent 7 → parent 5 is a transitive cycle and must be
    refused when the user tries to set folder 5's parent to 7."""
    from unittest.mock import AsyncMock, MagicMock

    from app.api.domain_folders import _would_create_cycle

    # Walk from new_parent_id (7) upward. The mock returns parent_id=5
    # for folder 7, which equals folder_id → cycle.
    db = MagicMock()
    walk_result = MagicMock()
    walk_result.scalar_one_or_none = MagicMock(return_value=5)
    db.execute = AsyncMock(return_value=walk_result)

    assert await _would_create_cycle(db, folder_id=5, new_parent_id=7) is True


@pytest.mark.asyncio
async def test_cycle_helper_allows_unrelated_parent():
    """Moving folder 5 to parent 7 where 7's parent_id is None: no
    cycle, allowed."""
    from unittest.mock import AsyncMock, MagicMock

    from app.api.domain_folders import _would_create_cycle

    db = MagicMock()
    walk_result = MagicMock()
    walk_result.scalar_one_or_none = MagicMock(return_value=None)  # 7 is top-level
    db.execute = AsyncMock(return_value=walk_result)

    assert await _would_create_cycle(db, folder_id=5, new_parent_id=7) is False


@pytest.mark.asyncio
async def test_cycle_helper_handles_null_parent():
    """Moving to the implicit root (parent_id=null) can never cycle."""
    from unittest.mock import AsyncMock, MagicMock

    from app.api.domain_folders import _would_create_cycle

    db = MagicMock()
    db.execute = AsyncMock()

    assert await _would_create_cycle(db, folder_id=5, new_parent_id=None) is False
    db.execute.assert_not_called()  # short-circuit before any DB hit


# ---- folder_id query-string parsing ----------------------------------------


def test_folder_clause_omitted_means_no_filter():
    from app.api.domains import _folder_clause

    assert _folder_clause(None) is None
    assert _folder_clause("") is None


def test_folder_clause_root_means_null_filter():
    from app.api.domains import _folder_clause
    from app.db.models import Domain

    clause = _folder_clause("root")
    # Stringify because SQLAlchemy boolean clauses aren't directly
    # comparable, but the SQL fragment is.
    assert "folder_id IS NULL" in str(clause.compile())


def test_folder_clause_numeric_filters_to_that_folder():
    from app.api.domains import _folder_clause

    clause = _folder_clause("42")
    assert "folder_id = " in str(clause.compile())


def test_folder_clause_rejects_garbage():
    from fastapi import HTTPException

    from app.api.domains import _folder_clause

    with pytest.raises(HTTPException) as exc:
        _folder_clause("abc")
    assert exc.value.status_code == 400
