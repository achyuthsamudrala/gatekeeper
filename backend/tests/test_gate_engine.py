"""Tests for Phase 2 — Gate Policy Engine."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gatekeeper.core.database import Base
from gatekeeper.orm import GateResult, PipelineRun
from gatekeeper.services.gate_engine import _compare, evaluate_gates


@pytest.fixture
async def gate_db():
    """Standalone async DB for gate engine tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _create_run(db: AsyncSession, run_id: str) -> None:
    run = PipelineRun(
        id=run_id,
        model_name="test-model",
        candidate_version="v1",
        phase="offline",
        offline_status="running",
        online_status="skipped",
        gatekeeper_yaml="version: '1.0'",
    )
    db.add(run)
    await db.flush()


async def _add_gate_result(
    db: AsyncSession,
    run_id: str,
    gate_name: str,
    phase: str = "offline",
    metric_value: float | None = None,
    passed: bool | None = None,
    blocking: bool = True,
    skip_reason: str | None = None,
) -> None:
    db.add(
        GateResult(
            id=str(uuid4()),
            pipeline_run_id=run_id,
            phase=phase,
            gate_name=gate_name,
            gate_type="test",
            metric_name="score",
            metric_value=metric_value,
            passed=passed,
            blocking=blocking,
            skip_reason=skip_reason,
        )
    )
    await db.flush()


# ── Comparator tests ─────────────────────────────────────────────────────


def test_compare_gte():
    assert _compare(0.9, ">=", 0.85) is True
    assert _compare(0.85, ">=", 0.85) is True
    assert _compare(0.84, ">=", 0.85) is False


def test_compare_lt():
    assert _compare(100.0, "<", 500.0) is True
    assert _compare(500.0, "<", 500.0) is False
    assert _compare(600.0, "<", 500.0) is False


def test_compare_lte():
    assert _compare(0.5, "<=", 0.5) is True
    assert _compare(0.4, "<=", 0.5) is True
    assert _compare(0.6, "<=", 0.5) is False


def test_compare_gt():
    assert _compare(1.0, ">", 0.5) is True
    assert _compare(0.5, ">", 0.5) is False


def test_compare_eq():
    assert _compare(0.5, "==", 0.5) is True
    assert _compare(0.4, "==", 0.5) is False


def test_compare_none_value():
    assert _compare(None, ">=", 0.5) is False


def test_compare_none_threshold():
    assert _compare(0.5, ">=", None) is False


# ── Gate policy integration tests ─────────────────────────────────────────


async def test_all_blocking_gates_pass(gate_db):
    """All blocking gates passing → overall_passed=True."""
    run_id = str(uuid4())
    await _create_run(gate_db, run_id)
    await _add_gate_result(gate_db, run_id, "gate_a", metric_value=0.9, blocking=True)
    await _add_gate_result(gate_db, run_id, "gate_b", metric_value=0.1, blocking=True)
    await gate_db.commit()

    config = {
        "gates": [
            {
                "name": "gate_a",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            },
            {
                "name": "gate_b",
                "phase": "offline",
                "evaluator": "drift",
                "threshold": 0.2,
                "comparator": "<",
                "blocking": True,
            },
        ]
    }

    from unittest.mock import patch

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", return_value=gate_db):
        result = await evaluate_gates(run_id, "offline", config)

    assert result["overall_passed"] is True
    assert len(result["gates"]) == 2


async def test_blocking_gate_fails(gate_db):
    """One blocking gate failing → overall_passed=False."""
    run_id = str(uuid4())
    await _create_run(gate_db, run_id)
    await _add_gate_result(gate_db, run_id, "gate_a", metric_value=0.5, blocking=True)
    await gate_db.commit()

    config = {
        "gates": [
            {
                "name": "gate_a",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            },
        ]
    }

    from unittest.mock import patch

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", return_value=gate_db):
        result = await evaluate_gates(run_id, "offline", config)

    assert result["overall_passed"] is False
    gate_detail = result["gates"][0]
    assert gate_detail["passed"] is False


async def test_non_blocking_gate_fail_doesnt_block(gate_db):
    """Non-blocking gate failing → overall_passed still True."""
    run_id = str(uuid4())
    await _create_run(gate_db, run_id)
    await _add_gate_result(gate_db, run_id, "gate_a", metric_value=0.9, blocking=True)
    await _add_gate_result(gate_db, run_id, "gate_b", metric_value=0.5, blocking=False)
    await gate_db.commit()

    config = {
        "gates": [
            {
                "name": "gate_a",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            },
            {
                "name": "gate_b",
                "phase": "offline",
                "evaluator": "drift",
                "threshold": 0.2,
                "comparator": "<",
                "blocking": False,
            },
        ]
    }

    from unittest.mock import patch

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", return_value=gate_db):
        result = await evaluate_gates(run_id, "offline", config)

    assert result["overall_passed"] is True


async def test_skipped_gate_does_not_count(gate_db):
    """Skipped gate (passed=None, skip_reason set) doesn't affect overall."""
    run_id = str(uuid4())
    await _create_run(gate_db, run_id)
    await _add_gate_result(gate_db, run_id, "gate_a", metric_value=0.9, blocking=True)
    await _add_gate_result(
        gate_db,
        run_id,
        "gate_b",
        metric_value=None,
        passed=None,
        blocking=True,
        skip_reason="reference_dataset not configured",
    )
    await gate_db.commit()

    config = {
        "gates": [
            {
                "name": "gate_a",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            },
            {
                "name": "gate_b",
                "phase": "offline",
                "evaluator": "drift",
                "threshold": 0.2,
                "comparator": "<",
                "blocking": True,
            },
        ]
    }

    from unittest.mock import patch

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", return_value=gate_db):
        result = await evaluate_gates(run_id, "offline", config)

    assert result["overall_passed"] is True
    skipped = [g for g in result["gates"] if g.get("skip_reason")]
    assert len(skipped) == 1


async def test_missing_gate_result_fails(gate_db):
    """Gate with no DB result → fail with 'evaluator_not_run'."""
    run_id = str(uuid4())
    await _create_run(gate_db, run_id)
    await gate_db.commit()

    config = {
        "gates": [
            {
                "name": "missing_gate",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            },
        ]
    }

    from unittest.mock import patch

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", return_value=gate_db):
        result = await evaluate_gates(run_id, "offline", config)

    assert result["overall_passed"] is False
    assert result["gates"][0]["skip_reason"] == "evaluator_not_run"


async def test_gate_engine_uses_async_db(gate_db):
    """Gate engine uses async DB session throughout."""
    run_id = str(uuid4())
    await _create_run(gate_db, run_id)
    await _add_gate_result(gate_db, run_id, "gate_a", metric_value=0.9, blocking=True)
    await gate_db.commit()

    config = {
        "gates": [
            {
                "name": "gate_a",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            },
        ]
    }

    from unittest.mock import patch

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", return_value=gate_db):
        # This would fail if evaluate_gates used sync DB calls
        result = await evaluate_gates(run_id, "offline", config)

    assert result["phase"] == "offline"
    assert isinstance(result["gates"], list)
