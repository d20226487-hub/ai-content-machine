"""Tests for the two-fix bundle around trashed/active email collision.

1. ``POST /auth/login`` must filter ``deleted_at IS NULL`` in its lookup —
   otherwise when one trashed + one active row share an email,
   ``.scalar_one_or_none()`` raises ``MultipleResultsFound`` → 500.
2. ``POST /users`` must refuse creation with 409 when a trashed user
   already holds the requested email (the partial-unique index doesn't
   cover trashed rows, so without an explicit pre-check the insert
   succeeds and creates the collision in the first place).

These run against an in-memory ``_FakeDB`` shim — same approach as
``test_publish_state_machine.py``. We assert on the SQL the handlers
build (so we don't have to reproduce SQLAlchemy's query engine) and on
the exception they raise on the trashed-clash branch.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# --- helpers / fakes ---


class _Result:
    """Minimal stand-in for sqlalchemy.Result."""

    def __init__(self, *, scalar_value: Any = None):
        self._scalar = scalar_value

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class _CapturingDB:
    """AsyncSession shim that records every executed statement.

    ``results`` is a FIFO queue — pop one per ``execute`` call. If empty,
    returns an empty result (scalar_value=None). Used so the test can
    both verify *what* the handler asked for and decide *what* the DB
    answers.
    """

    def __init__(self, results: list[_Result] | None = None):
        self.executes: list[Any] = []
        self._results = list(results or [])
        self.commits = 0
        self.rollbacks = 0
        self.added: list[Any] = []
        self.refreshed: list[Any] = []

    async def execute(self, stmt, *_args, **_kwargs):
        self.executes.append(stmt)
        if self._results:
            return self._results.pop(0)
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)

    def add(self, obj):
        self.added.append(obj)


def _compiled_sql(stmt) -> str:
    """Compile a SQLAlchemy Core/ORM statement to a single SQL string.

    We use ``literal_binds=True`` so bound parameters get rendered inline
    — makes substring checks straightforward without juggling param dicts.
    """
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


# --- Fix #1: login filters deleted_at IS NULL ---


@pytest.mark.asyncio
async def test_login_query_filters_out_trashed_rows():
    """The login lookup must include ``deleted_at IS NULL``.

    Without this filter, the partial-unique index on email lets a
    trashed + active pair coexist, and ``.scalar_one_or_none()`` raises
    ``MultipleResultsFound`` → 500. We don't need a real DB to catch
    that regression — we just need to assert the WHERE clause is correct.
    """
    from app.api import auth as auth_module
    from app.schemas.auth import LoginRequest

    db = _CapturingDB()

    # Throttle gate: allow through. Verdict object only needs ``.allowed``.
    fake_verdict = MagicMock(allowed=True)
    with patch.object(
        auth_module.login_throttle, "check", AsyncMock(return_value=fake_verdict)
    ), patch.object(
        auth_module.login_throttle, "record_failure", AsyncMock()
    ), patch(
        # to_thread runs bcrypt verify in a worker thread — short-circuit
        # to False so the route hits the "wrong password" 401 branch
        # cleanly. The branch we actually care about (the SELECT) has
        # already executed by then.
        "app.api.auth.asyncio.to_thread", AsyncMock(return_value=False)
    ):
        req = MagicMock()
        req.client = MagicMock(host="127.0.0.1")
        payload = LoginRequest(email="dup@example.com", password="x")
        with pytest.raises(HTTPException) as exc:
            await auth_module.login(req, payload, db=db)
        # Empty result → no user → 401. That's fine; we're here for the SELECT.
        assert exc.value.status_code == 401

    assert len(db.executes) == 1, "login should execute exactly one SELECT"
    sql = _compiled_sql(db.executes[0]).lower()
    assert "users.email" in sql
    assert "users.deleted_at is null" in sql, (
        "login query is missing the deleted_at IS NULL filter — "
        "a trashed+active collision will raise MultipleResultsFound. "
        f"actual SQL: {sql}"
    )


# --- Fix #2: create_user refuses on trashed-email collision ---


@pytest.mark.asyncio
async def test_create_user_refuses_when_trashed_user_has_same_email():
    """A trashed user holding the requested email must surface a 409.

    Otherwise the insert succeeds (partial-unique index ignores trashed
    rows), two rows share the email, and the auth bug from fix #1 can
    fire on the next login attempt.
    """
    from app.api import users as users_module
    from app.db.models import Role, User
    from app.schemas.user import UserCreate

    # Three statements get executed before the early-exit on trashed-clash:
    # 1) _get_role_or_400 → return a valid role
    # 2) trashed_clash SELECT → return a stale user.id (i.e. clash exists)
    # That's where the handler raises.
    role = Role(id=2, name="editor")
    db = _CapturingDB(
        results=[
            _Result(scalar_value=role),       # role lookup
            _Result(scalar_value=999),         # trashed user id collides
        ]
    )

    actor = User(id=1, role_id=1)
    actor.role = Role(id=1, name="admin")

    payload = UserCreate(
        email="taken@example.com",
        full_name="New User",
        password="hunter22hunter22",
        role_id=2,
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc:
        await users_module.create_user(payload, actor=actor, db=db)

    assert exc.value.status_code == 409
    assert "trashed" in exc.value.detail.lower()
    assert "taken@example.com" in exc.value.detail
    # Critically: we must NOT have inserted a row when the clash exists.
    assert db.added == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_create_user_proceeds_when_no_trashed_clash():
    """No trashed row with this email → handler proceeds to insert + commit.

    Validates the pre-check is a *guard*, not an always-fail. Catches a
    regression where someone over-tightens the query (e.g. inverts the
    deleted_at predicate).
    """
    from app.api import users as users_module
    from app.db.models import Role, User
    from app.schemas.user import UserCreate

    role = Role(id=2, name="editor")
    db = _CapturingDB(
        results=[
            _Result(scalar_value=role),       # role lookup
            _Result(scalar_value=None),        # NO trashed clash
        ]
    )

    actor = User(id=1, role_id=1)
    actor.role = Role(id=1, name="admin")

    payload = UserCreate(
        email="brandnew@example.com",
        full_name="New User",
        password="hunter22hunter22",
        role_id=2,
        is_active=True,
    )

    # password_hash uses bcrypt; patch to keep the test fast and
    # independent of bcrypt's KDF cost setting.
    with patch("app.api.users.hash_password", MagicMock(return_value="hashed")):
        out = await users_module.create_user(payload, actor=actor, db=db)

    assert out.email == "brandnew@example.com"
    assert db.added and db.added[0].email == "brandnew@example.com"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_create_user_trashed_clash_query_targets_trashed_rows_only():
    """The clash query must filter ``deleted_at IS NOT NULL``.

    If someone refactors and accidentally drops the ``is_not(None)``,
    the handler would refuse to create a user when an *active* row
    already holds the email — duplicating the IntegrityError branch and
    breaking the distinct error messaging.
    """
    from app.api import users as users_module
    from app.db.models import Role, User
    from app.schemas.user import UserCreate

    role = Role(id=2, name="editor")
    db = _CapturingDB(
        results=[
            _Result(scalar_value=role),
            _Result(scalar_value=None),  # no clash; we just want the SQL
        ]
    )

    actor = User(id=1, role_id=1)
    actor.role = Role(id=1, name="admin")

    payload = UserCreate(
        email="check@example.com",
        full_name="x",
        password="hunter22hunter22",
        role_id=2,
        is_active=True,
    )

    with patch("app.api.users.hash_password", MagicMock(return_value="h")):
        await users_module.create_user(payload, actor=actor, db=db)

    # executes[0] = role lookup, executes[1] = trashed clash
    assert len(db.executes) >= 2
    sql = _compiled_sql(db.executes[1]).lower()
    assert "users.email" in sql
    assert "users.deleted_at is not null" in sql, (
        "trashed-clash query lost its `deleted_at IS NOT NULL` filter — "
        f"actual SQL: {sql}"
    )
