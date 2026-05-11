from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.security import hash_password
from app.db.models import Role, User
from app.db.session import get_db
from app.schemas.usage import SpendWindow, UserSpendSummary
from app.schemas.user import (
    PasswordReset,
    RoleRead,
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

async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
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
    stmt = (
        select(func.count(User.id))
        .join(Role, Role.id == User.role_id)
        .where(Role.name == "admin", User.is_active.is_(True))
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
    return list(
        (await db.execute(select(User).order_by(User.id))).scalars().all()
    )


@users_router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    role = await _get_role_or_400(db, payload.role_id)
    _ensure_can_create_role(actor, role)

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
    target = await _get_user_or_404(db, user_id)

    if target.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself",
        )
    _ensure_can_target(actor, target)

    if target.role.name == "admin":
        # Same TOCTOU concern as update_user — serialize via the advisory lock.
        await _lock_admin_guard(db)
        remaining = await _count_active_admins(db, exclude_user_id=target.id)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last remaining admin",
            )

    await db.delete(target)
    await db.commit()


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
