"""Cancel + watchdog recovery for stranded bulk-generation cells.

Two independent recovery paths keep a cancelled run from leaving cells spinning
on 'generating' forever:

  1. The cancel endpoint sweeps in-flight cells the instant Cancel is clicked.
  2. The watchdog reconciles 'cancelled' (not just 'running') runs as a backstop
     for cells the sweep missed / runs cancelled by older code.

Both hinge on *branch* behaviour — "does the per-task pre-check count a cell it
didn't actually flip?", "does the watchdog now act on a cancelled run?" — which
is exactly what a hand-fed fake ``AsyncSession`` pins, same style as
``test_publish_state_machine``. The guarded-UPDATE *semantics* (row-level
locking, RETURNING) are SQL and are exercised against the running stack.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest


# --- fakes -------------------------------------------------------------------


class _PreRes:
    """Result shim whose ``.first()`` returns a hand-fed row."""

    def __init__(self, first_val):
        self._first = first_val

    def first(self):
        return self._first


class _PreDB:
    """Feeds ``execute`` results in order; counts commits."""

    def __init__(self):
        self.queue: list[_PreRes] = []
        self.commits = 0

    async def execute(self, _stmt, *_a, **_k):
        return self.queue.pop(0) if self.queue else _PreRes(None)

    async def commit(self):
        self.commits += 1


# --- cancel pre-check: count only what it claims -----------------------------


@pytest.mark.asyncio
async def test_precheck_counts_skipped_only_when_it_claims_the_cell():
    """A queued task waking up after cancel must count `skipped` iff its guarded
    claim actually flips the cell — otherwise the endpoint sweep already did."""
    from app.services import bulk_generation as svc

    # Cell still 'generating' -> claim RETURNS a row -> skipped bumped once.
    db = _PreDB()
    db.queue.append(_PreRes(("cancelled",)))  # _is_run_cancelled: SELECT status
    db.queue.append(_PreRes((123,)))          # guarded UPDATE ... RETURNING id
    with patch.object(svc, "_bump_run_counter", new=AsyncMock()) as bump:
        await svc.generate_one_cell(
            db, table_id=1, row_id=10, column_id=2, run_id=5
        )
    bump.assert_awaited_once_with(db, 5, field="skipped")


@pytest.mark.asyncio
async def test_precheck_does_not_count_when_cell_already_settled():
    """Sweep already flipped the cell: the claim RETURNs nothing, so the task
    must NOT bump skipped again (that would push the run past `total`)."""
    from app.services import bulk_generation as svc

    db = _PreDB()
    db.queue.append(_PreRes(("cancelled",)))  # _is_run_cancelled
    db.queue.append(_PreRes(None))            # guarded UPDATE claims nothing
    with patch.object(svc, "_bump_run_counter", new=AsyncMock()) as bump:
        await svc.generate_one_cell(
            db, table_id=1, row_id=10, column_id=2, run_id=5
        )
    bump.assert_not_awaited()


# --- watchdog: now reconciles cancelled runs ---------------------------------


_OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)  # far past the no-progress cutoff


class _RecRes:
    """One result covering every shape ``_reconcile_run`` reads: last-progress
    (``scalar_one_or_none``) and the claim (``scalars().all()``)."""

    def scalar_one_or_none(self):
        return None  # no cell activity -> falls back to started_at/created_at

    def scalars(self):
        return self

    def all(self):
        return [101, 102, 103]  # three stranded cells claimed

    def first(self):
        return None


class _RecordingDB:
    def __init__(self, run):
        self._run = run
        self.statements: list[str] = []
        self.commits = 0

    async def get(self, _model, _key):
        return self._run

    async def execute(self, stmt, *_a, **_k):
        self.statements.append(str(stmt))
        return _RecRes()

    async def commit(self):
        self.commits += 1


def _run(**over):
    from app.db.models import BulkGenerationRun

    base = dict(
        id=7, table_id=1, status="cancelled", total=250,
        done=247, failed=0, skipped=0,
        started_at=_OLD, created_at=_OLD, finished_at=None,
    )
    base.update(over)
    return BulkGenerationRun(**base)


@pytest.mark.asyncio
async def test_watchdog_recovers_a_cancelled_run():
    """A cancelled, not-yet-finalized run with stale progress gets its stranded
    cells claimed and (once drained) finished_at stamped."""
    from app.tasks import bulk_generation as wd

    db = _RecordingDB(_run())
    await wd._reconcile_run(db, 7)

    # It did NOT early-return: it queried + wrote + committed.
    assert db.statements, "watchdog ignored the cancelled run"
    assert db.commits >= 1
    # It swept the stranded cells (guarded UPDATE against the cells table)...
    assert any(
        "UPDATE bulk_table_cells" in s for s in db.statements
    ), "no straggler claim issued"
    # ...and stamped finished_at on the cancelled run (the new backstop line).
    assert any(
        "status = 'cancelled'" in s and "finished_at" in s.lower()
        for s in db.statements
    ), "cancelled run was never finalized"


@pytest.mark.asyncio
async def test_watchdog_still_ignores_terminal_runs():
    """A 'done' run is untouched — the guard must not admit terminal states."""
    from app.tasks import bulk_generation as wd

    db = _RecordingDB(_run(status="done", done=250, finished_at=_OLD))
    await wd._reconcile_run(db, 7)

    assert db.statements == []
    assert db.commits == 0
