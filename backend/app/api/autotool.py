"""Public Autotool CSV endpoint.

This is the ONLY unauthenticated, publicly-readable route in the app. It lets
the external Autotool proxy fetch a bulk table's CSV over plain HTTP (no JWT)
so it can push the content to WordPress / target sites.

Security model — "capability URL":
  * The URL carries a random 128-bit token (/autotool/<token>.csv). The token
    is unguessable and not enumerable; possession of the URL is the only
    credential.
  * A table is reachable ONLY while autotool_enabled is true and it isn't
    trashed. Disabling clears the token (see library.disable_autotool), so the
    old link 404s immediately and forever.
  * The content (generated text, target domains, post ids) is therefore
    readable by anyone holding the link — an accepted trade-off chosen when the
    feature was designed.

Deliberately NOT placed on the `library` router (which carries a global
`Depends(get_current_user)`); this router has no auth dependency.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import BulkTable
from app.db.session import get_db
from app.services.bulk_csv import build_table_csv

router = APIRouter(prefix="/autotool", tags=["autotool"])


@router.get("/{token}.csv")
async def get_autotool_csv(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the live CSV for the enabled table owning ``token``, or 404.

    Regenerated from the DB on every request, so the Autotool always sees the
    current table state without any file to keep in sync.
    """
    t = (
        (
            await db.execute(
                select(BulkTable)
                .where(
                    BulkTable.autotool_token == token,
                    BulkTable.autotool_enabled.is_(True),
                    BulkTable.deleted_at.is_(None),
                )
                .options(
                    selectinload(BulkTable.columns),
                    selectinload(BulkTable.rows),
                )
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    csv_text = await build_table_csv(db, t)
    safe_name = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in t.name
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}.csv"',
            # The proxy polls this; let it cache briefly but always revalidate.
            "Cache-Control": "no-cache",
        },
    )
