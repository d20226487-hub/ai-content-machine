"""Statistics — monthly bulk-generation + publication + spend rollup.

Read access: admin or manager. Everything is aggregated on the fly from the
durable per-item logs (see services/stats.py); no new data is stored.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.stats import StatsResponse
from app.services import stats as stats_svc

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=StatsResponse)
async def get_stats(
    month: str | None = Query(default=None, description="Specific 'YYYY-MM'; overrides `months`"),
    months: int = Query(default=12, ge=1, le=36, description="Lookback window (calendar months)"),
    user_id: int | None = Query(default=None),
    domain_id: int | None = Query(default=None),
    group_by: str = Query(default="user", description="user | table | domain | channel"),
    only_content: bool = Query(
        default=False,
        description="Count only publications that shipped a non-empty content field",
    ),
    _viewer: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """Monthly figures + a one-dimension breakdown, honoring month/user/domain filters."""
    return await stats_svc.get_stats(
        db,
        month=month,
        months=months,
        user_id=user_id,
        domain_id=domain_id,
        group_by=group_by,
        only_content=only_content,
    )
