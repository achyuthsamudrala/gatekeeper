"""Performance and benchmark tests for GateKeeper."""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gatekeeper.orm import Base, GateResult, PipelineRun


# ── Helpers ──────────────────────────────────────────────────────────────


async def slow_evaluator(delay: float, result_value: float) -> float:
    """Simulates an evaluator that takes *delay* seconds."""
    await asyncio.sleep(delay)
    return result_value


async def failing_evaluator(delay: float) -> float:
    """Simulates an evaluator that fails after *delay* seconds."""
    await asyncio.sleep(delay)
    raise RuntimeError("evaluator exploded")


@pytest.fixture
async def bench_db():
    """In-memory async SQLite for benchmark tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_run(run_id: str) -> PipelineRun:
    return PipelineRun(
        id=run_id,
        model_name="bench-model",
        candidate_version="v1",
        phase="offline",
        offline_status="running",
        online_status="skipped",
        gatekeeper_yaml="version: '1.0'",
    )


def _make_gate_result(run_id: str, gate_name: str) -> GateResult:
    return GateResult(
        id=str(uuid4()),
        pipeline_run_id=run_id,
        phase="offline",
        gate_name=gate_name,
        gate_type="benchmark",
        metric_name="score",
        metric_value=0.95,
        passed=True,
        blocking=True,
    )


# ── Concurrency tests ───────────────────────────────────────────────────


async def test_concurrent_evaluators_faster_than_sequential():
    """asyncio.gather should run 5 evaluators concurrently, beating a sequential loop."""
    delay = 0.1
    num_evaluators = 5

    # Sequential
    t0 = time.monotonic()
    sequential_results = []
    for i in range(num_evaluators):
        sequential_results.append(await slow_evaluator(delay, float(i)))
    sequential_elapsed = time.monotonic() - t0

    # Concurrent
    t0 = time.monotonic()
    concurrent_results = await asyncio.gather(
        *(slow_evaluator(delay, float(i)) for i in range(num_evaluators))
    )
    concurrent_elapsed = time.monotonic() - t0

    # Both should produce the same values
    assert list(concurrent_results) == sequential_results

    # Concurrent must be meaningfully faster
    assert concurrent_elapsed < sequential_elapsed, (
        f"concurrent ({concurrent_elapsed:.3f}s) should be faster "
        f"than sequential ({sequential_elapsed:.3f}s)"
    )
    # Concurrent should be close to a single delay, sequential close to N * delay
    assert concurrent_elapsed < delay * 2, "concurrent run took too long"
    assert sequential_elapsed >= delay * (num_evaluators - 1), "sequential unexpectedly fast"


async def test_evaluator_error_isolation():
    """One failing evaluator must not cancel siblings when using return_exceptions=True."""
    delay = 0.1

    t0 = time.monotonic()
    results = await asyncio.gather(
        slow_evaluator(delay, 1.0),
        failing_evaluator(delay),
        slow_evaluator(delay, 3.0),
        return_exceptions=True,
    )
    elapsed = time.monotonic() - t0

    # First and third should succeed
    assert results[0] == 1.0
    assert results[2] == 3.0

    # Second should be the exception
    assert isinstance(results[1], RuntimeError)
    assert "evaluator exploded" in str(results[1])

    # Total time should be ~max(delays), not sum(delays)
    assert elapsed < delay * 2, (
        f"elapsed {elapsed:.3f}s suggests tasks ran sequentially, not concurrently"
    )


# ── Database throughput tests ────────────────────────────────────────────


async def test_db_write_throughput(bench_db):
    """Insert 100 GateResult rows; verify < 2 seconds on in-memory SQLite."""
    run_id = str(uuid4())
    bench_db.add(_make_run(run_id))
    await bench_db.flush()

    t0 = time.monotonic()
    for i in range(100):
        bench_db.add(_make_gate_result(run_id, f"gate_{i}"))
    await bench_db.flush()
    await bench_db.commit()
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0, f"100 inserts took {elapsed:.3f}s, expected < 2s"


async def test_concurrent_db_reads(bench_db):
    """Launch 10 concurrent SELECT queries; verify all complete quickly."""
    run_id = str(uuid4())
    bench_db.add(_make_run(run_id))
    await bench_db.flush()

    for i in range(20):
        bench_db.add(_make_gate_result(run_id, f"gate_{i}"))
    await bench_db.flush()
    await bench_db.commit()

    from sqlalchemy import select

    async def read_all() -> list:
        result = await bench_db.execute(
            select(GateResult).where(GateResult.pipeline_run_id == run_id)
        )
        return list(result.scalars().all())

    t0 = time.monotonic()
    results = await asyncio.gather(*(read_all() for _ in range(10)))
    elapsed = time.monotonic() - t0

    # All 10 queries should return the same 20 rows
    for result_set in results:
        assert len(result_set) == 20

    assert elapsed < 2.0, f"10 concurrent reads took {elapsed:.3f}s, expected < 2s"
