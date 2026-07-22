"""Schemas for public cell share links.

Two sides:
  * ``ShareLinkRead`` — what the OWNER sees in the app after sharing (the token
    to build the URL from, plus expiry/revocation state).
  * ``SharedCellRead`` — what an ANONYMOUS visitor gets from the public
    endpoint. Deliberately minimal: the cell's content plus just enough context
    to label the page. The table's name is NOT exposed — internal naming is
    nobody's business on a public URL.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ShareLinkRead(BaseModel):
    """An owner-side view of a share link. The frontend builds the public URL
    as ``/share/{token}``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    row_id: int
    column_id: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


class SharedCellRead(BaseModel):
    """The public payload. ``content`` is the cell's CURRENT value (these links
    are live), rendered client-side inside a sandboxed iframe."""

    content: str
    # Column label + 1-based row number, so the page can title itself without
    # leaking the table name.
    column_name: str
    row_number: int
    expires_at: datetime
