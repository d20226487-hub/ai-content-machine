from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.security import hash_password
from app.db.models import AppSetting, Role, User
from app.db.session import get_db
from app.schemas.usage import SpendWindow, UserSpendSummary
from app.schemas.user import (
    PasswordReset,
    RoleRead,
    TrashBulkIds,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.usage import summary_for_all_users, summary_for_user

ADMIN_OR_MANAGER = ("admin", "manager")

users_router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role(*ADMIN_OR_MANAGER))],
)

roles_router = APIRouter(
    prefix="/roles",
    tags=["roles"],
    dependencies=[Depends(require_role(*ADMIN_OR_MANAGER))],
)


# ---------- helpers ----------

async def _get_user_or_404(
    db: AsyncSession, user_id: int, *, include_trashed: bool = False
) -> User:
    """Fetch a user by id.

    By default trashed users are invisible — every API surface except
    /users/trash filters `deleted_at IS NULL`. Pass `include_trashed=True`
    for preview / restore / permanent-delete paths.
    """
    stmt = select(User).where(User.id == user_id)
    if not include_trashed:
        stmt = stmt.where(User.deleted_at.is_(None))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _get_trashed_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_not(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_role_or_400(db: AsyncSession, role_id: int) -> Role:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role_id")
    return role


# Arbitrary 32-bit-fitting integer — pg_advisory_xact_lock takes a bigint or
# a (classid, objid) pair. Any constant works; this one was picked with no
# meaning. The lock is released automatically when the transaction commits
# or rolls back.
_ADMIN_GUARD_LOCK_KEY = 91482038


async def _lock_admin_guard(db: AsyncSession) -> None:
    """Take a transaction-scoped advisory lock that serializes admin checks.

    Without this lock, two concurrent requests that each demote or deactivate
    a different admin user can both observe ``remaining == 1`` (they each
    exclude a different user from the count) and both succeed, dropping the
    active-admin count to zero. The advisory lock makes the
    "count + decision + write" sequence indivisible across requests.

    Released automatically at COMMIT/ROLLBACK — no manual unlock needed.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADMIN_GUARD_LOCK_KEY})


async def _count_active_admins(db: AsyncSession, *, exclude_user_id: int | None = None) -> int:
    """Count admins that can currently log in.

    "Active" here means `is_active=True` AND not in Trash — a trashed
    admin can't sign in (deps.get_current_user filters them), so they
    don't count toward "we still have at least one admin around".
    """
    stmt = (
        select(func.count(User.id))
        .join(Role, Role.id == User.role_id)
        .where(
            Role.name == "admin",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return int((await db.execute(stmt)).scalar_one())


def _ensure_can_target(actor: User, target: User) -> None:
    """Manager cannot touch admins."""
    if actor.role.name == "manager" and target.role.name == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managers cannot modify admin users",
        )


def _ensure_can_create_role(actor: User, new_role: Role) -> None:
    if actor.role.name == "manager" and new_role.name == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managers cannot create admin users",
        )


# ---------- /roles ----------

@roles_router.get("", response_model=list[RoleRead])
async def list_roles(db: AsyncSession = Depends(get_db)) -> list[Role]:
    return list((await db.execute(select(Role).order_by(Role.id))).scalars().all())


# ---------- /users ----------

@users_router.get("", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    """List active users. Trashed rows are hidden — see /users/trash."""
    return list(
        (
            await db.execute(
                select(User).where(User.deleted_at.is_(None)).order_by(User.id)
            )
        ).scalars().all()
    )


# ---------- trash ----------
#
# Literal `/trash*` paths come BEFORE `/{user_id}` so FastAPI matches them
# first (otherwise "trash" gets coerced to int and 422s).

_USER_TRASH_RETENTION_KEY = "user_trash_retention_days"
_USER_TRASH_RETENTION_DEFAULT = 50
_USER_TRASH_RETENTION_MAX = 3650


@users_router.get("/trash/count", response_model=dict)
async def trash_count(db: AsyncSession = Depends(get_db)) -> dict:
    n = int(
        (
            await db.execute(
                select(func.count(User.id)).where(User.deleted_at.is_not(None))
            )
        ).scalar_one()
    )
    return {"count": n}


@users_router.get("/trash/retention", response_model=dict)
async def get_trash_retention(
    db: AsyncSession = Depends(get_db),
    _viewer: User = Depends(require_role(*ADMIN_OR_MANAGER)),
) -> dict:
    row = (
        await db.execute(
            select(AppSetting.value).where(
                AppSetting.key == _USER_TRASH_RETENTION_KEY
            )
        )
    ).scalar_one_or_none()
    try:
        days = (
            max(0, int(row))
            if row is not None
            else _USER_TRASH_RETENTION_DEFAULT
        )
    except (TypeError, ValueError):
        days = _USER_TRASH_RETENTION_DEFAULT
    return {
        "days": days,
        "default": _USER_TRASH_RETENTION_DEFAULT,
        "max": _USER_TRASH_RETENTION_MAX,
    }


@users_router.put("/trash/retention", response_model=dict)
async def set_trash_retention(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> dict:
    raw = payload.get("days")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail="`days` must be an integer."
        )
    if days < 0 or days > _USER_TRASH_RETENTION_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"`days` must be between 0 and {_USER_TRASH_RETENTION_MAX}.",
        )
    existing = await db.get(AppSetting, _USER_TRASH_RETENTION_KEY)
    if existing is None:
        db.add(AppSetting(key=_USER_TRASH_RETENTION_KEY, value=days))
    else:
        existing.value = days
    await db.commit()
    try:
        from app.services.app_settings_cache import invalidate
        invalidate(_USER_TRASH_RETENTION_KEY)
    except Exception:
        pass
    return {
        "days": days,
        "default": _USER_TRASH_RETENTION_DEFAULT,
        "max": _USER_TRASH_RETENTION_MAX,
    }


@users_router.get("/trash", response_model=list[UserRead])
async def list_trashed_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    return list(
        (
            await db.execute(
                select(User)
                .where(User.deleted_at.is_not(None))
                .order_by(User.deleted_at.desc())
            )
        ).scalars().all()
    )


@users_router.get("/trash/{user_id}", response_model=UserRead)
async def preview_trashed_user(
    user_id: int, db: AsyncSession = Depends(get_db)
) -> User:
    return await _get_trashed_user_or_404(db, user_id)


@users_router.delete("/trash", response_model=dict)
async def empty_trash(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete every trashed user.

    Skips trashed users that are admins as a safety guard — auto-cleanup
    of an admin who happens to be in trash is risky enough that we
    require manual confirmation (per-row "Delete forever"). Same skip
    applies to the daily cleanup task.
    """
    rows = (
        await db.execute(
            select(User)
            .join(Role, Role.id == User.role_id)
            .where(User.deleted_at.is_not(None), Role.name != "admin")
        )
    ).scalars().all()
    for u in rows:
        await db.delete(u)
    await db.commit()
    return {"deleted": len(rows)}


@users_router.post("/trash/bulk-restore", response_model=dict)
async def bulk_restore_users(
    payload: TrashBulkIds, db: AsyncSession = Depends(get_db)
) -> dict:
    """Restore many users. Email collisions are checked per-row so a
    bulk restore of N users won't all-fail if one has a conflict."""
    rows = (
        await db.execute(
            select(User).where(
                User.id.in_(payload.ids), User.deleted_at.is_not(None)
            )
        )
    ).scalars().all()
    restored = 0
    skipped_email_conflicts: list[str] = []
    for u in rows:
        clash = (
            await db.execute(
                select(User.id).where(
                    User.deleted_at.is_(None),
                    User.id != u.id,
                    User.email == u.email,
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            skipped_email_conflicts.append(u.email)
            continue
        u.deleted_at = None
        restored += 1
    await db.commit()
    return {
        "restored": restored,
        "skipped_email_conflicts": skipped_email_conflicts,
    }


@users_router.delete("/trash/bulk", response_model=dict)
async def bulk_permanent_delete_users(
    payload: TrashBulkIds, db: AsyncSession = Depends(get_db)
) -> dict:
    """Bulk hard-delete. Admins are skipped (same posture as empty_trash)."""
    rows = (
        await db.execute(
            select(User)
            .join(Role, Role.id == User.role_id)
            .where(
                User.id.in_(payload.ids),
                User.deleted_at.is_not(None),
                Role.name != "admin",
            )
        )
    ).scalars().all()
    for u in rows:
        await db.delete(u)
    await db.commit()
    return {"deleted": len(rows)}


@users_router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    role = await _get_role_or_400(db, payload.role_id)
    _ensure_can_create_role(actor, role)

    # Block the trashed-collision case explicitly. The partial-unique index
    # on email only covers `deleted_at IS NULL`, so without this check the
    # insert would succeed and leave two rows sharing an email — which then
    # breaks /auth/login (MultipleResultsFound). Surface a 409 that points
    # the operator at Trash so they can restore or permanently delete first.
    trashed_clash = (
        await db.execute(
            select(User.id).where(
                User.email == payload.email,
                User.deleted_at.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if trashed_clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A trashed user with email {payload.email} already exists. "
                "Restore them or permanently delete them from /users/trash "
                "before creating a new account with this email."
            ),
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        role_id=role.id,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists",
        )
    await db.refresh(user)
    return user


@users_router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    target = await _get_user_or_404(db, user_id)
    _ensure_can_target(actor, target)

    data = payload.model_dump(exclude_unset=True)

    # Decide up-front whether the change can affect admin count. If so, take
    # the advisory lock before any check so two concurrent requests can't
    # each see remaining=1 and both proceed.
    role_change = "role_id" in data and data["role_id"] is not None
    active_change = "is_active" in data and data["is_active"] is not None
    needs_admin_guard = (
        target.role.name == "admin"
        and (role_change or active_change)
    )
    if needs_admin_guard:
        await _lock_admin_guard(db)

    # Role change
    if role_change:
        new_role = await _get_role_or_400(db, data["role_id"])
        _ensure_can_create_role(actor, new_role)
        # Demoting the last active admin?
        if target.role.name == "admin" and new_role.name != "admin":
            remaining = await _count_active_admins(db, exclude_user_id=target.id)
            if remaining == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the last remaining admin",
                )
        target.role_id = new_role.id

    # Active toggle — block self-deactivation and last-admin deactivation
    if active_change:
        new_active = bool(data["is_active"])
        if not new_active and target.id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate yourself",
            )
        if not new_active and target.role.name == "admin":
            remaining = await _count_active_admins(db, exclude_user_id=target.id)
            if remaining == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate the last active admin",
                )
        target.is_active = new_active

    if "full_name" in data:
        target.full_name = data["full_name"]

    await db.commit()
    await db.refresh(target)
    return target


@users_router.post("/{user_id}/reset-password", response_model=UserRead)
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    target = await _get_user_or_404(db, user_id)
    _ensure_can_target(actor, target)
    target.password_hash = hash_password(payload.new_password)
    await db.commit()
    await db.refresh(target)
    return target


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Move a user to Trash (soft-delete).

    Their JWT is invalidated immediately because `get_current_user`
    filters `deleted_at IS NULL`. Restoration is reversible (they have
    to log in fresh — we don't reissue tokens). Permanent delete is via
    `DELETE /users/{id}/permanent` from the Trash page.

    Same protections as the previous hard-delete: can't trash yourself,
    managers can't touch admins, can't trash the last active admin.
    """
    target = await _get_user_or_404(db, user_id)

    if target.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself",
        )
    _ensure_can_target(actor, target)

    if target.role.name == "admin":
        await _lock_admin_guard(db)
        remaining = await _count_active_admins(db, exclude_user_id=target.id)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last remaining admin",
            )

    target.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@users_router.post("/{user_id}/restore", response_model=UserRead)
async def restore_user(
    user_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Restore a trashed user to the active set.

    The partial-unique index on email skips trashed rows, so a new
    active user may have been created in the meantime with the same
    email. Check that explicitly so we surface a clean 409 instead of
    an IntegrityError on commit.
    """
    target = await _get_trashed_user_or_404(db, user_id)
    _ensure_can_target(actor, target)
    clash = (
        await db.execute(
            select(User.id).where(
                User.deleted_at.is_(None),
                User.id != target.id,
                User.email == target.email,
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot restore: an active user with the same email "
                f"({target.email}) already exists. Trash the conflicting "
                "user first, or change their email."
            ),
        )
    target.deleted_at = None
    await db.commit()
    await db.refresh(target)
    return target


@users_router.delete(
    "/{user_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def permanently_delete_user(
    user_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Hard-delete a trashed user.

    `created_by_id` FKs on prompts / domains / bulk_tables / publish_jobs
    etc. are ON DELETE SET NULL, so their attribution becomes "(deleted
    user)". Usage events for spend tracking aggregate into a
    `user_id=NULL` "Deleted users" bucket on `/users/spend`.

    Still refuses to delete the last admin even from Trash — if you
    really need to remove the last-admin row, restore them and demote
    via PATCH first.
    """
    target = await _get_trashed_user_or_404(db, user_id)
    _ensure_can_target(actor, target)
    if target.role.name == "admin":
        # _count_active_admins excludes trashed users, so a trashed
        # admin is by definition NOT counted as an active admin. The
        # only way this guard would fire is if there were exactly zero
        # active admins right now and the operator is trying to hard-
        # delete the trashed one. Surfaces a clearer error than an
        # invariant violation later.
        await _lock_admin_guard(db)
        remaining = await _count_active_admins(db)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot permanently delete the only admin user. "
                    "Restore them, demote via PATCH, then trash + delete."
                ),
            )
    await db.delete(target)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- spend tracking (#9) ----------


@users_router.get("/spend", response_model=list[UserSpendSummary])
async def list_user_spend(
    db: AsyncSession = Depends(get_db),
) -> list[UserSpendSummary]:
    """One row per user with daily/weekly/monthly/all-time spend totals.

    Includes a `(user_id=null)` row when there are usage events from users
    that have since been deleted — admins can still see that historical
    spend exists, just not which person it belonged to.
    """
    rows = await summary_for_all_users(db)
    return [
        UserSpendSummary(
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            spend=SpendWindow(**r["spend"]),
        )
        for r in rows
    ]


@users_router.get("/{user_id}/spend", response_model=SpendWindow)
async def get_user_spend(
    user_id: int, db: AsyncSession = Depends(get_db)
) -> SpendWindow:
    """Per-user spend windows. 404 if the user doesn't exist."""
    target = await _get_user_or_404(db, user_id)
    summary = await summary_for_user(db, target.id)
    return SpendWindow(**summary)
