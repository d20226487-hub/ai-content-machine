"""Pydantic schemas for the /publish/domains folder tree.

Mirrors ``schemas/category.py`` — same shape, same with_counts semantic.
Kept as a separate file (not a generic ``Folder`` type) because folder
metadata is likely to diverge: prompts categories are flat-ish on the
UI today, while domains may want per-folder rate-limit defaults or
project-level tags later.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DomainFolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    # Populated when the list endpoint is called with ?with_counts=true.
    # Null on requests without the param so the JSON stays cheap for
    # contexts that just want the tree skeleton (e.g. the "move to
    # folder…" picker dropdown).
    domain_count: int | None = None
    subfolder_count: int | None = None


class DomainFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None


class DomainFolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    # Setting parent_id to null moves the folder to the top level.
    # Setting it to a child of itself (directly or transitively) is
    # caught by the API's cycle check.
    parent_id: int | None = None


class DomainBulkMove(BaseModel):
    """Body for ``POST /domains/bulk-move``: move N domains to a folder.

    ``folder_id = null`` moves them out of any folder (back to the
    implicit root). Restricted to a sane batch size so a runaway client
    can't trigger an unbounded UPDATE.
    """

    domain_ids: list[int] = Field(min_length=1, max_length=500)
    folder_id: int | None = None
