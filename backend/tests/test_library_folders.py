"""Schema + cycle-helper tests for the Library (bulk-table) folder tree.

Mirrors ``test_domain_folders.py``: Library folders gained nesting
(``parent_id``) so subfolders work, after the "create folder inside a folder
lands it at root" bug. Pin the wire-payload contracts and the cycle guard
here; end-to-end CRUD is exercised against the running stack.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.bulk import FolderCreate, FolderRead, FolderUpdate


# ---- create / update payload validation ------------------------------------


def test_create_requires_name():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FolderCreate(name="")


def test_create_caps_name_length():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FolderCreate(name="x" * 201)


def test_create_defaults_to_top_level():
    """No parent_id given → top-level folder (back-compat with old callers
    that only passed a name)."""
    assert FolderCreate(name="Projects").parent_id is None


def test_create_accepts_parent_id():
    assert FolderCreate(name="Sub", parent_id=7).parent_id == 7


def test_update_distinguishes_unset_from_null_parent():
    """exclude_unset is what lets a PATCH rename without touching the parent,
    and move-to-root (explicit null) stay distinct from omitted."""
    omit = FolderUpdate(name="Renamed")
    to_root = FolderUpdate(parent_id=None)

    assert "parent_id" not in omit.model_dump(exclude_unset=True)
    assert "name" not in FolderUpdate(parent_id=5).model_dump(exclude_unset=True)
    assert "parent_id" in to_root.model_dump(exclude_unset=True)


def test_read_counts_default_to_null():
    rec = FolderRead(
        id=1,
        name="Projects",
        parent_id=None,
        created_by_id=42,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dumped = rec.model_dump()
    assert dumped["table_count"] is None
    assert dumped["subfolder_count"] is None
    assert dumped["parent_id"] is None


# ---- cycle detection helper -------------------------------------------------


@pytest.mark.asyncio
async def test_cycle_helper_short_circuits_on_null_parent():
    from unittest.mock import AsyncMock, MagicMock

    from app.api.library import _would_create_folder_cycle

    db = MagicMock()
    db.execute = AsyncMock()
    assert await _would_create_folder_cycle(db, folder_id=5, new_parent_id=None) is False
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_cycle_helper_rejects_self_parent():
    from unittest.mock import AsyncMock, MagicMock

    from app.api.library import _would_create_folder_cycle

    db = MagicMock()
    db.execute = AsyncMock()  # never reached: cursor == folder_id on first compare
    assert await _would_create_folder_cycle(db, folder_id=5, new_parent_id=5) is True


@pytest.mark.asyncio
async def test_cycle_helper_rejects_transitive_cycle():
    """folder 5 → new parent 7 whose parent is 5 → cycle."""
    from unittest.mock import AsyncMock, MagicMock

    from app.api.library import _would_create_folder_cycle

    db = MagicMock()
    walk = MagicMock()
    walk.scalar_one_or_none = MagicMock(return_value=5)
    db.execute = AsyncMock(return_value=walk)
    assert await _would_create_folder_cycle(db, folder_id=5, new_parent_id=7) is True


@pytest.mark.asyncio
async def test_cycle_helper_allows_unrelated_parent():
    from unittest.mock import AsyncMock, MagicMock

    from app.api.library import _would_create_folder_cycle

    db = MagicMock()
    walk = MagicMock()
    walk.scalar_one_or_none = MagicMock(return_value=None)  # 7 is top-level
    db.execute = AsyncMock(return_value=walk)
    assert await _would_create_folder_cycle(db, folder_id=5, new_parent_id=7) is False
