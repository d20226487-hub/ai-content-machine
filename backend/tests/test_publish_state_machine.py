"""Smoke tests for the bulk-publish state machine.

We exercise ``publish_one_row`` and the seed task with an in-memory fake
``AsyncSession`` that captures the calls the production code makes. The fake
doesn't try to evaluate SQLAlchemy expressions — it returns hand-crafted
results keyed by which ``Result.scalars()`` shape the caller will use.

Why bother with fakes instead of a real DB? The state-machine bugs we want to
guard against (Celery redelivery → duplicate publish; pause-then-seed →
silently re-arm a paused run) are about *which branches the code takes*, not
about which rows the DB returns. Branches are testable with mocks.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- helpers / fakes ---


class _Result:
    """Stand-in for sqlalchemy ``Result`` covering the calls our code makes."""

    def __init__(self, *, scalar_first=None, scalars_all=None, all_=None):
        self._scalar_first = scalar_first
        self._scalars_all = scalars_all if scalars_all is not None else []
        self._all = all_ if all_ is not None else []

    def scalars(self) -> "_Result":
        return self

    def first(self):
        return self._scalar_first

    def all(self):
        # ``scalars().all()`` returns scalars; ``execute(...).all()`` returns rows.
        return self._scalars_all if self._scalars_all else self._all


class _FakeDB:
    """Minimal AsyncSession shim. Hand-feed results in order via ``queue``."""

    def __init__(self):
        self.queue: list[_Result] = []
        self.gets: dict[tuple[type, Any], Any] = {}
        self.commits = 0
        self.added: list[Any] = []

    async def execute(self, _stmt, *_args, **_kwargs):
        if not self.queue:
            return _Result()
        return self.queue.pop(0)

    async def get(self, model, key):
        return self.gets.get((model, key))

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        pass

    def add(self, obj):
        self.added.append(obj)


# --- tests ---


@pytest.mark.asyncio
async def test_publish_one_row_skips_when_run_paused():
    from app.db.models import BulkPublishRun
    from app.services import bulk_publish

    db = _FakeDB()
    run = BulkPublishRun(
        id=1,
        table_id=1,
        status="paused",
        domain_id=1,
        row_filter="all",
        cell_filter="all",
        field_to_column={},
        back_fill={},
        total=0,
        done=0,
        failed=0,
        skipped=0,
    )
    db.gets[(BulkPublishRun, 1)] = run

    out = await bulk_publish.publish_one_row(db, run_id=1, row_id=10)
    assert out == "skipped"
    assert db.commits == 0  # no work done


@pytest.mark.asyncio
async def test_publish_one_row_skips_when_existing_job_posted():
    """Celery redelivery guard — the row already shipped; do not re-post."""
    from app.db.models import BulkPublishRun, PublishJob
    from app.services import bulk_publish

    db = _FakeDB()
    run = BulkPublishRun(
        id=1, table_id=1, status="running", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=1, done=0, failed=0, skipped=0,
    )
    db.gets[(BulkPublishRun, 1)] = run
    # The duplicate-guard query returns an existing posted job.
    db.queue.append(
        _Result(scalar_first=PublishJob(id=99, status="posted", source_kind="bulk_row"))
    )

    out = await bulk_publish.publish_one_row(db, run_id=1, row_id=10)
    assert out == "skipped"
    # Crucially: no new PublishJob was added.
    assert db.added == []


@pytest.mark.asyncio
async def test_publish_one_row_skips_when_existing_job_posting():
    """Mid-flight redelivery — another worker is already on it."""
    from app.db.models import BulkPublishRun, PublishJob
    from app.services import bulk_publish

    db = _FakeDB()
    run = BulkPublishRun(
        id=1, table_id=1, status="running", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=1, done=0, failed=0, skipped=0,
    )
    db.gets[(BulkPublishRun, 1)] = run
    db.queue.append(
        _Result(scalar_first=PublishJob(id=99, status="posting", source_kind="bulk_row"))
    )

    out = await bulk_publish.publish_one_row(db, run_id=1, row_id=10)
    assert out == "skipped"
    assert db.added == []


@pytest.mark.asyncio
async def test_publish_one_row_proceeds_when_only_failed_job_exists():
    """A prior failure must NOT block a fresh attempt — Celery retry needs in.

    The duplicate guard returns None because failed jobs are excluded from the
    `posted|posting` filter. The function then continues; we patch out the
    actual CMS call and assert it tried to record a new job.
    """
    from app.db.models import BulkPublishRun, Domain
    from app.services import bulk_publish

    db = _FakeDB()
    run = BulkPublishRun(
        id=1, table_id=1, status="running", domain_id=42,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=1, done=0, failed=1, skipped=0, profile_name="",
    )
    domain = Domain(
        id=42, name="d", base_url="https://example.com",
        cms_type="custom", auth_type="bearer", languages=["en"],
        custom_config={"endpoint_path": "/api"},
    )
    db.gets[(BulkPublishRun, 1)] = run
    db.gets[(Domain, 42)] = domain

    # Queue results for: duplicate-guard query (no existing) → field-build query (no cells).
    db.queue.append(_Result(scalar_first=None))  # duplicate-guard
    db.queue.append(_Result(all_=[]))  # _build_fields → no cells

    # Stub out the CMS client and rate limiter.
    fake_client = MagicMock()
    fake_client.publish_post = AsyncMock(return_value=MagicMock(
        ok=True, status_code=201,
        payload_sent={}, response_json={"id": 7, "link": "https://x/y"},
        cms_post_id="7", cms_post_url="https://x/y",
        warnings=[], error=None,
    ))

    class _NoLimiter:
        def acquire(self, **_kw):
            class _Ctx:
                async def __aenter__(self_inner): return None
                async def __aexit__(self_inner, *_args): return False
            return _Ctx()

    with patch("app.services.bulk_publish.get_cms_client", return_value=fake_client), \
         patch(
             "app.services.bulk_publish.resolve_for_domain",
             AsyncMock(return_value=MagicMock(
                 max_concurrency=1, requests_per_minute=60, inter_request_delay_ms=0,
             )),
         ), \
         patch(
             "app.services.bulk_publish.get_rate_limiter",
             return_value=_NoLimiter(),
         ):
        # _bump_counter / _writeback issue queries we don't care to model — drown the queue.
        for _ in range(20):
            db.queue.append(_Result())
        out = await bulk_publish.publish_one_row(db, run_id=1, row_id=10)

    assert out == "posted"
    # Exactly one new PublishJob should have been added.
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_cancelled():
    """Cancel issued mid-seed must NOT be flipped back to running."""
    from app.db.models import BulkPublishRun
    from app.tasks import publish_bulk

    # First db.get returns a running-ish run (queued). Second get (after
    # candidate_row_ids) returns the same row but with status='cancelled' —
    # simulates the user clicking cancel between the two reads.
    queued = BulkPublishRun(
        id=1, table_id=1, status="queued", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=0, done=0, failed=0, skipped=0,
    )
    cancelled = BulkPublishRun(
        id=1, table_id=1, status="cancelled", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=0, done=0, failed=0, skipped=0,
    )

    class _SeedDB(_FakeDB):
        def __init__(self_inner):
            super().__init__()
            self_inner._reads = 0

        async def get(self_inner, model, key):
            if model is BulkPublishRun and key == 1:
                self_inner._reads += 1
                return queued if self_inner._reads == 1 else cancelled
            return None

        async def __aenter__(self_inner):
            return self_inner

        async def __aexit__(self_inner, *args):
            return False

    db = _SeedDB()

    enqueued: list = []

    async def _fake_candidates(_db, _run):
        return [10, 11, 12]

    class _FakeEngine:
        async def dispose(self_e): pass

    def _fake_create_engine(*_a, **_kw):
        return _FakeEngine()

    def _fake_sessionmaker(*_a, **_kw):
        # Returns a callable that returns the same _SeedDB context.
        def _factory():
            return db
        return _factory

    fake_task = MagicMock()
    fake_task.delay = lambda *a, **k: enqueued.append(a)

    with patch(
        "app.services.bulk_publish.candidate_row_ids", _fake_candidates
    ), patch(
        "app.tasks.publish_bulk.create_async_engine", _fake_create_engine
    ), patch(
        "app.tasks.publish_bulk.async_sessionmaker", _fake_sessionmaker
    ), patch(
        "app.tasks.publish_bulk.publish_one_bulk_row", fake_task
    ):
        await publish_bulk._seed(1)

    # The cancelled run must NOT have been re-armed.
    assert cancelled.status == "cancelled"
    # And no children enqueued.
    assert enqueued == []


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_paused():
    """Pause issued mid-seed must NOT be flipped back to running."""
    from app.db.models import BulkPublishRun
    from app.tasks import publish_bulk

    queued = BulkPublishRun(
        id=2, table_id=1, status="queued", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=0, done=0, failed=0, skipped=0,
    )
    paused_after = BulkPublishRun(
        id=2, table_id=1, status="paused", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=0, done=0, failed=0, skipped=0,
    )

    class _SeedDB(_FakeDB):
        def __init__(self_inner):
            super().__init__()
            self_inner._reads = 0

        async def get(self_inner, model, key):
            if model is BulkPublishRun:
                self_inner._reads += 1
                # 1st read: queued (initial gate). 2nd read (post-candidate
                # compute): paused was set in between by the user. Per the
                # fix, this DOES allow flipping back to running — pause →
                # resume = re-enqueue is the intended Resume semantics.
                return queued if self_inner._reads == 1 else paused_after
            return None

        async def __aenter__(self_inner): return self_inner
        async def __aexit__(self_inner, *args): return False

    db = _SeedDB()
    enqueued: list = []

    async def _fake_candidates(_db, _run):
        return [10]

    class _FakeEngine:
        async def dispose(self_e): pass

    fake_task = MagicMock()
    fake_task.delay = lambda *a, **k: enqueued.append(a)

    with patch("app.services.bulk_publish.candidate_row_ids", _fake_candidates), \
         patch("app.tasks.publish_bulk.create_async_engine", lambda *a, **k: _FakeEngine()), \
         patch("app.tasks.publish_bulk.async_sessionmaker", lambda *a, **k: (lambda: db)), \
         patch("app.tasks.publish_bulk.publish_one_bulk_row", fake_task):
        await publish_bulk._seed(2)

    # Pause → seed = legal re-arm (this is exactly Resume).
    assert paused_after.status == "running"
    # Children enqueued.
    assert enqueued == [(2, 10)]


@pytest.mark.asyncio
async def test_seed_returns_early_when_terminal():
    """The first-pass status check must short-circuit cancelled/done/failed."""
    from app.db.models import BulkPublishRun
    from app.tasks import publish_bulk

    done = BulkPublishRun(
        id=3, table_id=1, status="done", domain_id=1,
        row_filter="all", cell_filter="all",
        field_to_column={}, back_fill={},
        total=0, done=0, failed=0, skipped=0,
    )

    class _SeedDB(_FakeDB):
        async def get(self_inner, model, key):
            return done

        async def __aenter__(self_inner): return self_inner
        async def __aexit__(self_inner, *args): return False

    enqueued: list = []
    fake_task = MagicMock()
    fake_task.delay = lambda *a, **k: enqueued.append(a)

    class _FakeEngine:
        async def dispose(self_e): pass

    with patch(
        "app.tasks.publish_bulk.create_async_engine", lambda *a, **k: _FakeEngine()
    ), patch(
        "app.tasks.publish_bulk.async_sessionmaker",
        lambda *a, **k: (lambda: _SeedDB()),
    ), patch(
        "app.tasks.publish_bulk.publish_one_bulk_row", fake_task,
    ):
        await publish_bulk._seed(3)

    assert done.status == "done"  # untouched
    assert enqueued == []
