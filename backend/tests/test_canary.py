"""Tests for Phase 3 — Canary Manager."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gatekeeper.core.database import Base
from gatekeeper.orm import AuditLog, CanarySnapshot, PipelineRun
from gatekeeper.services.canary import (
    _should_promote,
    _should_rollback,
    promote_canary,
    rollback_canary,
    start_canary,
)


@pytest.fixture
async def canary_db():
    """Standalone async DB for canary tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


async def _create_run(db: AsyncSession, run_id: str, online_status: str = "pending") -> None:
    run = PipelineRun(
        id=run_id,
        model_name="test-model",
        candidate_version="v1",
        phase="online",
        offline_status="passed",
        online_status=online_status,
        gatekeeper_yaml="version: '1.0'",
    )
    db.add(run)
    await db.flush()
    await db.commit()


# ── Threshold logic tests ────────────────────────────────────────────────


def test_should_rollback_high_latency():
    snapshot = {"challenger_latency_p95_ms": 1000.0, "challenger_error_rate": 0.01}
    config = {"auto_rollback_threshold": {"latency_p95_ms": 500.0}}
    assert _should_rollback(snapshot, config) is True


def test_should_rollback_high_error_rate():
    snapshot = {"challenger_latency_p95_ms": 100.0, "challenger_error_rate": 0.15}
    config = {"auto_rollback_threshold": {"error_rate": 0.10}}
    assert _should_rollback(snapshot, config) is True


def test_should_not_rollback_healthy():
    snapshot = {"challenger_latency_p95_ms": 100.0, "challenger_error_rate": 0.01}
    config = {"auto_rollback_threshold": {"latency_p95_ms": 500.0, "error_rate": 0.10}}
    assert _should_rollback(snapshot, config) is False


def test_should_not_rollback_no_thresholds():
    snapshot = {"challenger_latency_p95_ms": 9999.0, "challenger_error_rate": 0.99}
    config = {}
    assert _should_rollback(snapshot, config) is False


def test_should_promote_within_thresholds():
    snapshot = {"challenger_latency_p95_ms": 100.0, "challenger_error_rate": 0.01}
    config = {"auto_promote_threshold": {"latency_p95_ms": 500.0, "error_rate": 0.05}}
    assert _should_promote(snapshot, config) is True


def test_should_not_promote_latency_too_high():
    snapshot = {"challenger_latency_p95_ms": 600.0, "challenger_error_rate": 0.01}
    config = {"auto_promote_threshold": {"latency_p95_ms": 500.0}}
    assert _should_promote(snapshot, config) is False


def test_should_not_promote_error_rate_too_high():
    snapshot = {"challenger_latency_p95_ms": 100.0, "challenger_error_rate": 0.15}
    config = {"auto_promote_threshold": {"error_rate": 0.10}}
    assert _should_promote(snapshot, config) is False


def test_should_promote_no_thresholds():
    """No promote thresholds configured → always promote."""
    snapshot = {"challenger_latency_p95_ms": 9999.0}
    config = {}
    assert _should_promote(snapshot, config) is True


# ── Promote / Rollback DB tests ──────────────────────────────────────────


async def test_promote_canary_updates_db(canary_db):
    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id, online_status="canary")

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)

    with patch("gatekeeper.services.canary.AsyncSessionFactory", factory):
        await promote_canary(run_id, "test_reason", adapters)

    serving.set_traffic_split.assert_called_once_with({"champion": 0.0, "challenger": 1.0})

    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one()
    assert run.online_status == "promoted"

    audit_result = await db.execute(select(AuditLog).where(AuditLog.pipeline_run_id == run_id))
    audit = audit_result.scalar_one()
    assert audit.action == "promoted"
    assert audit.detail["reason"] == "test_reason"


async def test_rollback_canary_updates_db(canary_db):
    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id, online_status="canary")

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)

    with patch("gatekeeper.services.canary.AsyncSessionFactory", factory):
        await rollback_canary(run_id, "error_detected", adapters)

    serving.set_traffic_split.assert_called_once_with({"champion": 1.0, "challenger": 0.0})

    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one()
    assert run.online_status == "rolled_back"

    audit_result = await db.execute(select(AuditLog).where(AuditLog.pipeline_run_id == run_id))
    audit = audit_result.scalar_one()
    assert audit.action == "rolled_back"


# ── start_canary tests ───────────────────────────────────────────────────


async def test_start_canary_creates_task(canary_db):
    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id)

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)
    app_state = SimpleNamespace(active_canary_tasks={})

    gates_config = {
        "canary": {
            "traffic_percent": 10,
            "observation_window_minutes": 1,
        }
    }

    with patch("gatekeeper.services.canary.AsyncSessionFactory", factory):
        with patch("gatekeeper.services.canary._observation_loop", new_callable=AsyncMock):
            await start_canary(run_id, gates_config, adapters, app_state)

    # Traffic split should be set
    serving.set_traffic_split.assert_called_once_with({"champion": 0.9, "challenger": 0.1})

    # Task should be stored
    assert run_id in app_state.active_canary_tasks
    task = app_state.active_canary_tasks[run_id]
    assert isinstance(task, asyncio.Task)
    task.cancel()

    # DB should reflect canary status
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one()
    assert run.online_status == "canary"

    # Audit log should be created
    audit_result = await db.execute(select(AuditLog).where(AuditLog.pipeline_run_id == run_id))
    audit = audit_result.scalar_one()
    assert audit.action == "canary_started"


async def test_start_canary_custom_traffic_percent(canary_db):
    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id)

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)
    app_state = SimpleNamespace(active_canary_tasks={})

    gates_config = {
        "canary": {
            "traffic_percent": 25,
            "observation_window_minutes": 1,
        }
    }

    with patch("gatekeeper.services.canary.AsyncSessionFactory", factory):
        with patch("gatekeeper.services.canary._observation_loop", new_callable=AsyncMock):
            await start_canary(run_id, gates_config, adapters, app_state)

    serving.set_traffic_split.assert_called_once_with({"champion": 0.75, "challenger": 0.25})
    task = app_state.active_canary_tasks[run_id]
    task.cancel()


async def test_canary_task_cleanup_on_done(canary_db):
    """Task cleanup callback removes from active_canary_tasks."""
    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id)

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)
    app_state = SimpleNamespace(active_canary_tasks={})

    async def _fast_loop(*args, **kwargs):
        return

    gates_config = {"canary": {"traffic_percent": 10, "observation_window_minutes": 1}}

    with patch("gatekeeper.services.canary.AsyncSessionFactory", factory):
        with patch("gatekeeper.services.canary._observation_loop", side_effect=_fast_loop):
            await start_canary(run_id, gates_config, adapters, app_state)

    # Give the event loop time to run the done callback
    await asyncio.sleep(0.1)

    # Task should have been cleaned up
    assert run_id not in app_state.active_canary_tasks


# ── Observation loop uses asyncio.sleep ──────────────────────────────────


def test_canary_uses_asyncio_sleep_not_time_sleep():
    """Verify canary module uses asyncio.sleep, not time.sleep in code."""
    import ast
    import inspect

    from gatekeeper.services import canary

    source = inspect.getsource(canary)
    assert "asyncio.sleep" in source

    # Parse AST to check no actual time.sleep calls exist
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "sleep":
            if isinstance(node.value, ast.Name) and node.value.id == "time":
                pytest.fail("Found time.sleep() call in canary module")


# ── Snapshot persistence test ────────────────────────────────────────────


async def test_observation_loop_persists_snapshots(canary_db):
    """Observation loop creates CanarySnapshot records in DB."""
    from gatekeeper.services.canary import _observation_loop

    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id, online_status="canary")

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)

    gates_config = {
        "canary": {
            "observation_window_minutes": 1,
            "auto_promote_threshold": {"latency_p95_ms": 500.0},
        }
    }

    call_count = 0

    async def fast_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            raise asyncio.CancelledError()

    with (
        patch("gatekeeper.services.canary.AsyncSessionFactory", factory),
        patch("gatekeeper.services.canary.asyncio.sleep", side_effect=fast_sleep),
        patch("gatekeeper.services.canary.promote_canary", new_callable=AsyncMock),
        patch("gatekeeper.services.canary.rollback_canary", new_callable=AsyncMock),
    ):
        try:
            await _observation_loop(run_id, gates_config, adapters)
        except asyncio.CancelledError:
            pass

    # Should have persisted snapshots
    result = await db.execute(
        select(CanarySnapshot).where(CanarySnapshot.pipeline_run_id == run_id)
    )
    snapshots = result.scalars().all()
    assert len(snapshots) >= 1


async def test_observation_loop_auto_rollback(canary_db):
    """Observation loop rolls back when thresholds breached."""
    from gatekeeper.services.canary import _observation_loop

    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id, online_status="canary")

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)

    gates_config = {
        "canary": {
            "observation_window_minutes": 30,
            "auto_rollback_threshold": {"error_rate": 0.05},
        }
    }

    bad_snapshot = {
        "champion_latency_p50_ms": 50.0,
        "champion_latency_p95_ms": 100.0,
        "challenger_latency_p50_ms": 60.0,
        "challenger_latency_p95_ms": 120.0,
        "champion_error_rate": 0.01,
        "challenger_error_rate": 0.15,  # Over threshold
        "champion_request_count": 100,
        "challenger_request_count": 10,
    }

    mock_rollback = AsyncMock()

    async def instant_sleep(seconds):
        pass

    with (
        patch("gatekeeper.services.canary.AsyncSessionFactory", factory),
        patch("gatekeeper.services.canary.asyncio.sleep", side_effect=instant_sleep),
        patch(
            "gatekeeper.services.canary._collect_snapshot",
            new_callable=AsyncMock,
            return_value=bad_snapshot,
        ),
        patch("gatekeeper.services.canary.rollback_canary", mock_rollback),
    ):
        await _observation_loop(run_id, gates_config, adapters)

    mock_rollback.assert_called_once_with(run_id, "auto_rollback_threshold_breached", adapters)


async def test_observation_loop_promotes_after_window(canary_db):
    """Observation loop promotes when window completes and thresholds pass."""
    from gatekeeper.services.canary import _observation_loop

    db, factory = canary_db
    run_id = str(uuid4())
    await _create_run(db, run_id, online_status="canary")

    serving = AsyncMock()
    adapters = SimpleNamespace(serving=serving)

    gates_config = {
        "canary": {
            "observation_window_minutes": 1,  # 60 seconds
            "auto_promote_threshold": {"latency_p95_ms": 500.0, "error_rate": 0.05},
        }
    }

    good_snapshot = {
        "champion_latency_p50_ms": 50.0,
        "champion_latency_p95_ms": 100.0,
        "challenger_latency_p50_ms": 55.0,
        "challenger_latency_p95_ms": 110.0,
        "champion_error_rate": 0.01,
        "challenger_error_rate": 0.02,
        "champion_request_count": 100,
        "challenger_request_count": 10,
    }

    mock_promote = AsyncMock()

    async def instant_sleep(seconds):
        pass

    with (
        patch("gatekeeper.services.canary.AsyncSessionFactory", factory),
        patch("gatekeeper.services.canary.asyncio.sleep", side_effect=instant_sleep),
        patch(
            "gatekeeper.services.canary._collect_snapshot",
            new_callable=AsyncMock,
            return_value=good_snapshot,
        ),
        patch("gatekeeper.services.canary.promote_canary", mock_promote),
        patch("gatekeeper.services.canary.rollback_canary", new_callable=AsyncMock),
    ):
        await _observation_loop(run_id, gates_config, adapters)

    mock_promote.assert_called_once_with(run_id, "observation_window_complete", adapters)
