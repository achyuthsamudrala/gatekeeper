"""Performance tests — thread pool saturation, CPU profiling, streaming memory,
concurrent DB writes, gate engine scaling, adapter throughput."""

from __future__ import annotations

import asyncio
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gatekeeper.core.database import Base
from gatekeeper.orm import GateResult, PipelineRun


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def perf_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _make_run(run_id: str) -> PipelineRun:
    return PipelineRun(
        id=run_id,
        model_name="perf-model",
        candidate_version="v1",
        phase="offline",
        offline_status="running",
        online_status="skipped",
        gatekeeper_yaml="version: '1.0'",
    )


# ── 1. Thread pool saturation ─────────────────────────────────────────────


async def test_thread_pool_saturation_with_4_workers():
    """With max_workers=4, 8 concurrent CPU tasks should still complete —
    they queue, not deadlock. Total time should be ~2x a single task,
    not 8x (proving parallelism within the pool)."""
    executor = ThreadPoolExecutor(max_workers=4)

    def cpu_work(duration: float) -> float:
        """Simulate CPU-bound work."""
        start = time.monotonic()
        # Busy-wait to actually hold the thread
        while time.monotonic() - start < duration:
            pass
        return duration

    duration = 0.05  # 50ms per task
    num_tasks = 8
    loop = asyncio.get_running_loop()

    t0 = time.monotonic()
    results = await asyncio.gather(
        *(loop.run_in_executor(executor, cpu_work, duration) for _ in range(num_tasks))
    )
    elapsed = time.monotonic() - t0

    assert len(results) == num_tasks
    # With 4 workers and 8 tasks: 2 batches of 4, so ~2 * 0.05 = 0.1s
    # Give generous margin but must be < sequential (8 * 0.05 = 0.4s)
    assert elapsed < duration * num_tasks * 0.75, (
        f"Thread pool took {elapsed:.3f}s — appears sequential "
        f"(expected < {duration * num_tasks * 0.75:.3f}s)"
    )
    executor.shutdown(wait=False)


async def test_thread_pool_does_not_block_event_loop():
    """CPU work in thread pool must not block async I/O on the event loop."""
    executor = ThreadPoolExecutor(max_workers=2)

    def heavy_cpu(duration: float) -> str:
        start = time.monotonic()
        while time.monotonic() - start < duration:
            pass
        return "done"

    async def async_io_task() -> str:
        """Should complete quickly even while CPU tasks run."""
        await asyncio.sleep(0.01)
        return "io_done"

    loop = asyncio.get_running_loop()

    t0 = time.monotonic()
    cpu_future = loop.run_in_executor(executor, heavy_cpu, 0.2)
    io_result = await async_io_task()
    io_elapsed = time.monotonic() - t0

    # I/O task should finish in ~10ms, not blocked by 200ms CPU task
    assert io_elapsed < 0.1, (
        f"Async I/O took {io_elapsed:.3f}s — event loop was blocked by CPU work"
    )
    assert io_result == "io_done"

    cpu_result = await cpu_future
    assert cpu_result == "done"
    executor.shutdown(wait=False)


# ── 2. CPU evaluator profiling ─────────────────────────────────────────────


async def test_sklearn_f1_at_scale():
    """Profile sklearn F1 computation on 5000 samples via run_in_executor.
    Warm import first — the cold import of sklearn adds ~1.5s one-time cost."""
    try:
        from gatekeeper.evaluators.accuracy import _compute_classification_metrics

        # Warm the sklearn import (one-time ~1.5s cost)
        _compute_classification_metrics(["a"], [{"text": "a"}])
    except ImportError:
        pytest.skip("sklearn not installed")

    executor = ThreadPoolExecutor(max_workers=4)
    n = 5000
    labels = ["pos", "neg", "neutral"]
    import random

    random.seed(42)
    ground_truth = [random.choice(labels) for _ in range(n)]
    predictions = [{"text": random.choice(labels)} for _ in range(n)]

    loop = asyncio.get_running_loop()
    t0 = time.monotonic()
    metrics = await loop.run_in_executor(
        executor, _compute_classification_metrics, ground_truth, predictions
    )
    elapsed = time.monotonic() - t0

    assert "f1_weighted" in metrics
    assert 0.0 <= metrics["f1_weighted"] <= 1.0
    # With warm imports, sklearn F1 on 5k samples should be ~10-20ms
    assert elapsed < 0.5, f"sklearn F1 on {n} samples took {elapsed:.3f}s"
    executor.shutdown(wait=False)


async def test_psi_computation_at_scale():
    """Profile PSI drift computation on 5000 samples."""
    try:
        from gatekeeper.drift_methods.psi import _compute_psi_sync
    except ImportError:
        pytest.skip("numpy not installed")

    from gatekeeper.registries.dataset_format import Sample

    executor = ThreadPoolExecutor(max_workers=4)
    import numpy as np

    rng = np.random.default_rng(42)
    n = 5000
    ref_samples = [
        Sample(input={"f1": float(v), "f2": float(v2)}, ground_truth=None)
        for v, v2 in zip(rng.normal(0, 1, n), rng.normal(5, 2, n))
    ]
    cur_samples = [
        Sample(input={"f1": float(v), "f2": float(v2)}, ground_truth=None)
        for v, v2 in zip(rng.normal(0.5, 1, n), rng.normal(5, 2, n))
    ]

    loop = asyncio.get_running_loop()
    t0 = time.monotonic()
    result = await loop.run_in_executor(
        executor, _compute_psi_sync, ref_samples, cur_samples, ["f1", "f2"]
    )
    elapsed = time.monotonic() - t0

    assert result.primary_metric_value >= 0.0
    assert "psi_per_feature" in result.detail
    # PSI on 5k samples with 2 features should be fast
    assert elapsed < 1.0, f"PSI on {n} samples took {elapsed:.3f}s"
    executor.shutdown(wait=False)


# ── 3. Dataset streaming memory ────────────────────────────────────────────


async def test_jsonl_streaming_memory_bounded():
    """Stream a 10k-row JSONL file and verify memory doesn't spike.
    With batch_size=100, only ~100 samples should be in memory at once."""
    from gatekeeper.dataset_formats.jsonl import JSONLLoader
    from gatekeeper.registries.evaluator import DatasetConfig

    import json

    n = 10_000
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for i in range(n):
            json.dump({"text": f"sample {i}", "label": f"class_{i % 5}"}, f)
            f.write("\n")
        path = f.name

    config = DatasetConfig(uri=path, label_column="label")
    loader = JSONLLoader()

    total_samples = 0
    max_batch_size_seen = 0
    async for batch in loader.stream(path, config, batch_size=100):
        max_batch_size_seen = max(max_batch_size_seen, len(batch))
        total_samples += len(batch)
        # Don't accumulate — just count (this is how a well-behaved consumer works)

    assert total_samples == n
    assert max_batch_size_seen == 100


async def test_csv_streaming_memory_bounded():
    """Stream a 5k-row CSV file. After the fix, CSV should stream
    line-by-line like JSONL, not load the whole file."""
    from gatekeeper.dataset_formats.csv import CSVLoader
    from gatekeeper.registries.evaluator import DatasetConfig

    n = 5_000
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("text,category,label\n")
        for i in range(n):
            f.write(f"sample {i},cat_{i % 3},class_{i % 5}\n")
        path = f.name

    config = DatasetConfig(uri=path, label_column="label")
    loader = CSVLoader()

    total_samples = 0
    max_batch_size_seen = 0
    async for batch in loader.stream(path, config, batch_size=100):
        max_batch_size_seen = max(max_batch_size_seen, len(batch))
        total_samples += len(batch)

    assert total_samples == n
    assert max_batch_size_seen == 100


async def test_csv_streaming_does_not_read_full_file():
    """Verify the CSV loader no longer calls f.read() — it streams line-by-line."""
    import ast
    import inspect

    from gatekeeper.dataset_formats import csv as csv_module

    source = inspect.getsource(csv_module)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Look for calls like f.read() or await f.read()
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "read":
                pytest.fail("CSV loader still calls .read() — should stream line-by-line")


# ── 4. Concurrent multi-pipeline DB writes ────────────────────────────────


async def test_concurrent_pipeline_writes(perf_db):
    """Multiple pipeline runs writing gate results concurrently should not
    deadlock or corrupt data."""
    num_runs = 10
    gates_per_run = 10

    async def write_run(factory, run_id: str):
        async with factory() as db:
            db.add(_make_run(run_id))
            for i in range(gates_per_run):
                db.add(
                    GateResult(
                        id=str(uuid4()),
                        pipeline_run_id=run_id,
                        phase="offline",
                        gate_name=f"gate_{i}",
                        gate_type="test",
                        metric_name="score",
                        metric_value=0.9,
                        passed=True,
                        blocking=True,
                    )
                )
            await db.commit()

    run_ids = [str(uuid4()) for _ in range(num_runs)]

    t0 = time.monotonic()
    await asyncio.gather(*(write_run(perf_db, rid) for rid in run_ids))
    elapsed = time.monotonic() - t0

    # Verify all data persisted correctly
    async with perf_db() as db:
        for rid in run_ids:
            result = await db.execute(select(GateResult).where(GateResult.pipeline_run_id == rid))
            gates = result.scalars().all()
            assert len(gates) == gates_per_run, (
                f"Run {rid}: expected {gates_per_run} gates, got {len(gates)}"
            )

    # 10 runs × 10 gates = 100 rows should be fast
    assert elapsed < 3.0, f"Concurrent writes took {elapsed:.3f}s"


# ── 5. Gate engine scaling ─────────────────────────────────────────────────


async def test_gate_engine_scales_to_20_gates(perf_db):
    """evaluate_gates with 20 gates should complete quickly.
    Each gate that needs a `passed` update opens a new session."""
    from unittest.mock import patch

    from gatekeeper.services.gate_engine import evaluate_gates

    run_id = str(uuid4())
    num_gates = 20

    async with perf_db() as db:
        db.add(_make_run(run_id))
        for i in range(num_gates):
            db.add(
                GateResult(
                    id=str(uuid4()),
                    pipeline_run_id=run_id,
                    phase="offline",
                    gate_name=f"gate_{i}",
                    gate_type="accuracy",
                    metric_name="f1_weighted",
                    metric_value=0.9,
                    passed=None,  # Not yet evaluated
                    blocking=True,
                )
            )
        await db.commit()

    config = {
        "gates": [
            {
                "name": f"gate_{i}",
                "phase": "offline",
                "evaluator": "accuracy",
                "threshold": 0.85,
                "comparator": ">=",
                "blocking": True,
            }
            for i in range(num_gates)
        ]
    }

    with patch("gatekeeper.services.gate_engine.AsyncSessionFactory", perf_db):
        t0 = time.monotonic()
        result = await evaluate_gates(run_id, "offline", config)
        elapsed = time.monotonic() - t0

    assert result["overall_passed"] is True
    assert len(result["gates"]) == num_gates
    # 20 gates with individual DB sessions should still be fast
    assert elapsed < 2.0, f"Gate engine with {num_gates} gates took {elapsed:.3f}s"


# ── 6. Serving adapter concurrent throughput ───────────────────────────────


async def test_serving_adapter_concurrent_predict():
    """Verify predict_batch with semaphore(10) processes requests concurrently."""
    from gatekeeper.adapters.base_types import PredictionRequest
    from gatekeeper.adapters.serving.openai_compatible import OpenAICompatibleAdapter

    adapter = OpenAICompatibleAdapter(
        champion_url="http://fake:8080",
        challenger_url="http://fake:8081",
    )
    await adapter.startup()

    call_count = 0

    async def mock_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.02)  # Simulate 20ms network latency

        class Resp:
            status_code = 200
            text = ""

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        return Resp()

    adapter._client.post = mock_post  # type: ignore[assignment]

    requests = [
        PredictionRequest(inputs=[{"text": f"input_{i}"}], model_role="champion") for i in range(20)
    ]

    t0 = time.monotonic()
    results = await adapter.predict_batch(requests)
    elapsed = time.monotonic() - t0

    assert len(results) == 20
    assert call_count == 20
    # With semaphore(10) and 20ms latency: 2 batches of 10 = ~40ms
    # Sequential would be 20 * 20ms = 400ms
    assert elapsed < 0.2, (
        f"predict_batch took {elapsed:.3f}s — should be concurrent, not sequential"
    )
    await adapter.shutdown()


async def test_serving_adapter_predict_batch_error_does_not_hang():
    """If some predictions fail, predict_batch should still return all results."""
    from gatekeeper.adapters.base_types import PredictionRequest
    from gatekeeper.adapters.serving.openai_compatible import OpenAICompatibleAdapter

    adapter = OpenAICompatibleAdapter(
        champion_url="http://fake:8080",
        challenger_url="http://fake:8081",
    )
    await adapter.startup()

    call_idx = 0

    async def mock_post(url, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx % 3 == 0:
            # Every 3rd request returns an error
            class ErrorResp:
                status_code = 500
                text = "internal error"

            return ErrorResp()

        class OkResp:
            status_code = 200
            text = ""

            def json(self):
                return {"result": "ok"}

        return OkResp()

    adapter._client.post = mock_post  # type: ignore[assignment]

    requests = [
        PredictionRequest(inputs=[{"text": f"input_{i}"}], model_role="champion") for i in range(9)
    ]

    results = await adapter.predict_batch(requests)
    assert len(results) == 9
    errors = [r for r in results if r.error]
    successes = [r for r in results if not r.error]
    assert len(errors) == 3  # Every 3rd
    assert len(successes) == 6
    await adapter.shutdown()
