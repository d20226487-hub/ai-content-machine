"""Dashboard endpoints.

``GET /dashboard/activity`` returns an on-demand snapshot of every in-flight
background job across ALL users (see services.dashboard_activity). Open to any
authenticated user — the dashboard is visible to everyone — but it is pull-only,
so it only runs when the operator clicks "Check now".
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.dashboard import ActivityResponse
from app.services.dashboard_activity import list_active_processes

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    _actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityResponse:
    """Every queued/running/paused background job, for everyone. On-demand."""
    return await list_active_processes(db)
