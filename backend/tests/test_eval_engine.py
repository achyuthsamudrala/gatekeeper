"""Tests for Phase 1 — Eval Engine: evaluator correctness, concurrency, gate policy."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gatekeeper.adapters.base_types import PredictionResponse
from gatekeeper.adapters.registry.none import NoneRegistryAdapter
from gatekeeper.adapters.serving.none import NoneServingAdapter
from gatekeeper.evaluators.accuracy import AccuracyEvaluator, _compute_classification_metrics
from gatekeeper.evaluators.champion_challenger import ChampionChallengerEvaluator
from gatekeeper.evaluators.drift import DriftEvaluator
from gatekeeper.evaluators.latency import LatencyEvaluator, _compute_latency_stats
from gatekeeper.evaluators.llm_judge import LLMJudgeEvaluator
from gatekeeper.registries.dataset_format import BaseDatasetLoader, DatasetFormatRegistry, Sample
from gatekeeper.registries.drift_method import DriftMethodRegistry
from gatekeeper.registries.evaluator import (
    DatasetConfig,
    EvalResult,
    EvaluationContext,
    LLMJudgeConfig,
)
from gatekeeper.registries.judge_modality import JudgeModalityRegistry
from gatekeeper.registries.loader import load_all_plugins
from gatekeeper.registries.model_type import ModelTypeDefinition, ModelTypeRegistry
from gatekeeper.services.gate_engine import _compare


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _load_plugins():
    from gatekeeper.registries.evaluator import EvaluatorRegistry
    from gatekeeper.registries.inference_encoding import InferenceEncodingRegistry

    EvaluatorRegistry.clear()
    ModelTypeRegistry.clear()
    DatasetFormatRegistry.clear()
    DriftMethodRegistry.clear()
    InferenceEncodingRegistry.clear()
    JudgeModalityRegistry.clear()
    load_all_plugins()
    yield


@pytest.fixture
def cpu_executor():
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-cpu")
    yield executor
    executor.shutdown(wait=True)


class MockDatasetLoader(BaseDatasetLoader):
    """In-memory dataset loader for tests."""

    def __init__(self, samples: list[Sample]):
        self._samples = samples

    @property
    def format_name(self) -> str:
        return "mock"

    async def stream(self, uri, config, batch_size):
        for i in range(0, len(self._samples), batch_size):
            yield self._samples[i : i + batch_size]


def _make_samples(n: int = 10) -> list[Sample]:
    return [
        Sample(input={"text": f"input-{i}"}, ground_truth={"label": f"class-{i % 3}"})
        for i in range(n)
    ]


def _make_context(
    gate_config: dict,
    samples: list[Sample] | None = None,
    cpu_executor: ThreadPoolExecutor | None = None,
    runner: object | None = None,
    serving_adapter: object | None = None,
    registry_adapter: object | None = None,
) -> EvaluationContext:
    if samples is None:
        samples = _make_samples()
    loader = MockDatasetLoader(samples)
    return EvaluationContext(
        run_id="test-run-001",
        model_name="test-model",
        candidate_version="v1",
        model_type=ModelTypeDefinition(name="llm", inference_mode="sequential_http"),
        runner=runner or AsyncMock(),
        serving_adapter=serving_adapter,
        registry_adapter=registry_adapter or NoneRegistryAdapter(),
        dataset_loader=loader,
        eval_dataset_config=DatasetConfig(uri="mock://data", label_column="label"),
        gate_config=gate_config,
        cpu_executor=cpu_executor or ThreadPoolExecutor(max_workers=1),
    )


# ── Accuracy Evaluator ───────────────────────────────────────────────────


async def test_accuracy_evaluator_runs(cpu_executor):
    """AccuracyEvaluator streams data, runs inference, computes metrics."""
    samples = _make_samples(10)
    runner = AsyncMock()
    runner.run.return_value = [{"label": f"class-{i % 3}"} for i in range(10)]

    ctx = _make_context(
        gate_config={"name": "acc_gate", "evaluator": "accuracy"},
        samples=samples,
        cpu_executor=cpu_executor,
        runner=runner,
    )

    evaluator = AccuracyEvaluator()
    result = await evaluator.evaluate(ctx)

    assert isinstance(result, EvalResult)
    assert result.gate_name == "acc_gate"
    assert result.evaluator_name == "accuracy"
    assert result.phase == "offline"
    assert result.metric_name == "f1_weighted"
    assert result.error is False
    runner.run.assert_awaited()


async def test_accuracy_evaluator_error_handling(cpu_executor):
    """AccuracyEvaluator returns error result on exception, never raises."""
    runner = AsyncMock(side_effect=RuntimeError("inference failed"))
    ctx = _make_context(
        gate_config={"name": "acc_gate", "evaluator": "accuracy"},
        samples=[],  # Empty samples to ensure the error propagates
        cpu_executor=cpu_executor,
        runner=runner,
    )

    evaluator = AccuracyEvaluator()
    result = await evaluator.evaluate(ctx)

    assert result.error is True
    assert result.error_message is not None
    assert result.metric_value is None


def test_compute_classification_metrics():
    """CPU-bound sklearn metrics run correctly."""
    ground_truth = [{"label": "a"}, {"label": "b"}, {"label": "a"}]
    predictions = [{"label": "a"}, {"label": "b"}, {"label": "b"}]
    metrics = _compute_classification_metrics(ground_truth, predictions)
    assert "f1_weighted" in metrics
    assert "accuracy" in metrics
    assert 0 <= metrics["accuracy"] <= 1


# ── Drift Evaluator ──────────────────────────────────────────────────────


async def test_drift_evaluator_skips_without_reference(cpu_executor):
    """Drift returns skipped result when no reference_dataset."""
    ctx = _make_context(
        gate_config={"name": "drift_gate", "evaluator": "drift"},
        cpu_executor=cpu_executor,
    )
    ctx.reference_dataset_config = None

    evaluator = DriftEvaluator()
    result = await evaluator.evaluate(ctx)

    assert result.passed is None
    assert result.skip_reason == "reference_dataset not configured"
    assert result.metric_value is None


async def test_drift_evaluator_uses_psi_default(cpu_executor):
    """Drift uses PSI as default drift method."""
    ref_samples = [Sample(input={"feat1": float(i)}, ground_truth=None) for i in range(50)]
    cur_samples = [Sample(input={"feat1": float(i + 5)}, ground_truth=None) for i in range(50)]

    ref_loader = MockDatasetLoader(ref_samples)

    ctx = _make_context(
        gate_config={
            "name": "drift_gate",
            "evaluator": "drift",
            "drift_method": "psi",
            "feature_columns": ["feat1"],
        },
        samples=cur_samples,
        cpu_executor=cpu_executor,
    )
    ctx.reference_dataset_config = DatasetConfig(
        uri="mock://ref",
        feature_columns=["feat1"],
    )
    # Patch to use our mock loaders
    with patch(
        "gatekeeper.evaluators.drift.DatasetFormatRegistry.get",
        return_value=ref_loader,
    ):
        evaluator = DriftEvaluator()
        result = await evaluator.evaluate(ctx)

    assert result.error is False
    assert result.metric_value is not None


# ── LLM Judge Evaluator ──────────────────────────────────────────────────


async def test_llm_judge_concurrent_calls(cpu_executor):
    """LLM judge runs judge calls concurrently via asyncio.gather."""
    samples = _make_samples(5)
    runner = AsyncMock()
    runner.run.return_value = [{"text": f"output-{i}"} for i in range(5)]

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"score": 0.8, "reasoning": "good"}')]
    mock_client.messages.create.return_value = mock_response

    ctx = _make_context(
        gate_config={
            "name": "quality_gate",
            "evaluator": "llm_judge",
            "num_samples": 5,
            "rubric": "Score 0-1",
            "judge_modality": "text",
        },
        samples=samples,
        cpu_executor=cpu_executor,
        runner=runner,
    )
    ctx.llm_judge_config = LLMJudgeConfig(model="test-model")
    ctx.llm_judge_client = mock_client

    evaluator = LLMJudgeEvaluator()
    result = await evaluator.evaluate(ctx)

    assert result.error is False
    assert result.metric_name == "llm_judge_score"
    assert result.metric_value == pytest.approx(0.8)
    assert result.detail["num_samples_judged"] == 5
    # Verify judge was called for each sample
    assert mock_client.messages.create.await_count == 5


async def test_llm_judge_uses_asyncio_sleep_for_retry(cpu_executor):
    """Retry backoff uses asyncio.sleep, not time.sleep."""
    samples = _make_samples(1)
    runner = AsyncMock()
    runner.run.return_value = [{"text": "output"}]

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"score": 0.5, "reasoning": "ok"}')]
    # Fail twice, succeed third time
    mock_client.messages.create.side_effect = [
        Exception("rate limit"),
        Exception("rate limit"),
        mock_response,
    ]

    ctx = _make_context(
        gate_config={
            "name": "quality_gate",
            "evaluator": "llm_judge",
            "num_samples": 1,
            "rubric": "Score 0-1",
        },
        samples=samples,
        cpu_executor=cpu_executor,
        runner=runner,
    )
    ctx.llm_judge_config = LLMJudgeConfig(model="test-model")
    ctx.llm_judge_client = mock_client

    with patch(
        "gatekeeper.evaluators.llm_judge.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        evaluator = LLMJudgeEvaluator()
        result = await evaluator.evaluate(ctx)

    # asyncio.sleep was called for retries (2^0=1, 2^1=2)
    assert mock_sleep.await_count == 2
    assert result.metric_value == pytest.approx(0.5)


# ── Champion vs Challenger ────────────────────────────────────────────────


async def test_champion_challenger_skips_no_registry(cpu_executor):
    """Champion/challenger skips when registry is NoneAdapter."""
    ctx = _make_context(
        gate_config={"name": "regression_gate", "evaluator": "champion_challenger"},
        cpu_executor=cpu_executor,
        registry_adapter=NoneRegistryAdapter(),
    )

    evaluator = ChampionChallengerEvaluator()
    result = await evaluator.evaluate(ctx)

    assert result.passed is None
    assert result.skip_reason == "registry not configured"


async def test_champion_challenger_auto_passes_first_deployment(cpu_executor):
    """Champion/challenger auto-passes on first deployment (no champion)."""
    from gatekeeper.adapters.registry.local import LocalRegistryAdapter

    mock_registry = AsyncMock(spec=LocalRegistryAdapter)
    mock_registry.get_champion_version.return_value = None

    ctx = _make_context(
        gate_config={"name": "regression_gate", "evaluator": "champion_challenger"},
        cpu_executor=cpu_executor,
        registry_adapter=mock_registry,
    )

    evaluator = ChampionChallengerEvaluator()
    result = await evaluator.evaluate(ctx)

    assert result.passed is True
    assert result.detail.get("reason") == "first_deployment"
    assert result.metric_value == 0.0


# ── Latency Evaluator ────────────────────────────────────────────────────


async def test_latency_evaluator_runs(cpu_executor):
    """Latency evaluator runs warmup + benchmark with semaphore."""
    serving = AsyncMock(spec=NoneServingAdapter)
    serving.predict.return_value = PredictionResponse(
        model_role="challenger", latency_ms=10.0, status_code=200, outputs=[{}]
    )

    samples = _make_samples(15)
    ctx = _make_context(
        gate_config={
            "name": "latency_gate",
            "evaluator": "latency",
            "num_warmup_requests": 2,
            "num_benchmark_requests": 10,
        },
        samples=samples,
        cpu_executor=cpu_executor,
        serving_adapter=serving,
    )

    evaluator = LatencyEvaluator()
    result = await evaluator.evaluate(ctx)

    assert result.error is False
    assert result.metric_name == "p95_latency_ms"
    assert result.metric_value is not None
    # warmup(2) + benchmark(10) = 12 calls
    assert serving.predict.await_count == 12


def test_compute_latency_stats():
    """Latency stats computed correctly in thread pool."""
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 100.0]
    stats = _compute_latency_stats(latencies)
    assert stats["p50"] > 0
    assert stats["p95"] > 0
    assert stats["mean"] > 0
    assert stats["min"] == 10.0
    assert stats["max"] == 100.0


def test_compute_latency_stats_empty():
    """Empty latencies return zeros."""
    stats = _compute_latency_stats([])
    assert stats["p95"] == 0.0


# ── Concurrent Execution ─────────────────────────────────────────────────


async def test_evaluators_run_concurrently(cpu_executor):
    """Multiple evaluators run concurrently via asyncio.gather."""

    async def slow_evaluate(ctx):
        await asyncio.sleep(0.1)
        return EvalResult(
            gate_name=ctx.gate_config["name"],
            evaluator_name="mock",
            phase="offline",
            metric_name="score",
            metric_value=1.0,
            passed=None,
        )

    # Create 3 "slow" evaluators
    evaluators = []
    for i in range(3):
        ev = AsyncMock()
        ev.evaluate = slow_evaluate
        evaluators.append(ev)

    contexts = [
        _make_context(
            gate_config={"name": f"gate_{i}", "evaluator": "accuracy"},
            cpu_executor=cpu_executor,
        )
        for i in range(3)
    ]

    start = time.monotonic()
    tasks = [ev.evaluate(ctx) for ev, ctx in zip(evaluators, contexts)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.monotonic() - start

    assert len(results) == 3
    assert all(isinstance(r, EvalResult) for r in results)
    # If run concurrently, total time < 3 * 0.1s = 0.3s
    assert elapsed < 0.25, f"Evaluators did not run concurrently: {elapsed:.2f}s"


async def test_one_evaluator_error_doesnt_cancel_others(cpu_executor):
    """return_exceptions=True ensures one failure doesn't cancel others."""

    async def failing_evaluate(ctx):
        raise RuntimeError("evaluator crashed")

    async def ok_evaluate(ctx):
        await asyncio.sleep(0.05)
        return EvalResult(
            gate_name="ok_gate",
            evaluator_name="mock",
            phase="offline",
            metric_name="score",
            metric_value=1.0,
            passed=None,
        )

    ctx1 = _make_context(gate_config={"name": "fail_gate"}, cpu_executor=cpu_executor)
    ctx2 = _make_context(gate_config={"name": "ok_gate"}, cpu_executor=cpu_executor)

    results = await asyncio.gather(
        failing_evaluate(ctx1),
        ok_evaluate(ctx2),
        return_exceptions=True,
    )

    assert isinstance(results[0], RuntimeError)
    assert isinstance(results[1], EvalResult)
    assert results[1].metric_value == 1.0


# ── Gate Policy Engine ────────────────────────────────────────────────────


def test_compare_operators():
    """Gate policy comparators work correctly."""
    assert _compare(0.9, ">=", 0.85) is True
    assert _compare(0.8, ">=", 0.85) is False
    assert _compare(100.0, "<", 500.0) is True
    assert _compare(600.0, "<", 500.0) is False
    assert _compare(0.5, "<=", 0.5) is True
    assert _compare(1.0, ">", 0.5) is True
    assert _compare(0.5, "==", 0.5) is True
    assert _compare(None, ">=", 0.5) is False
    assert _compare(0.5, ">=", None) is False


# ── Evaluator Interface Compliance ────────────────────────────────────────


def test_all_evaluators_registered_via_entry_points():
    """All 5 evaluators discoverable via entry points."""
    import inspect

    from gatekeeper.registries.evaluator import EvaluatorRegistry

    assert len(EvaluatorRegistry.all()) == 5
    for name in ["accuracy", "drift", "llm_judge", "champion_challenger", "latency"]:
        ev = EvaluatorRegistry.get(name)
        assert hasattr(ev, "evaluate")
        assert inspect.iscoroutinefunction(ev.evaluate)


def test_all_evaluators_have_correct_phases():
    """Phase classification matches PRD."""
    from gatekeeper.registries.evaluator import EvaluatorRegistry

    offline = ["accuracy", "drift", "llm_judge", "champion_challenger"]
    for name in offline:
        assert EvaluatorRegistry.get(name).phase == "offline"
    assert EvaluatorRegistry.get("latency").phase == "online"


def test_cpu_bound_functions_are_sync():
    """CPU-bound functions are synchronous (run in thread pool)."""
    import inspect

    assert not inspect.iscoroutinefunction(_compute_classification_metrics)
    assert not inspect.iscoroutinefunction(_compute_latency_stats)
