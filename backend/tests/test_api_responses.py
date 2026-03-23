"""Tests that seed the DB and verify API response shapes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from gatekeeper.orm import AuditLog, CanarySnapshot, GateResult, PipelineRun
from gatekeeper.registries.loader import load_all_plugins
from gatekeeper.registries.evaluator import EvaluatorRegistry
from gatekeeper.registries.model_type import ModelTypeRegistry
from gatekeeper.registries.dataset_format import DatasetFormatRegistry
from gatekeeper.registries.drift_method import DriftMethodRegistry
from gatekeeper.registries.inference_encoding import InferenceEncodingRegistry
from gatekeeper.registries.judge_modality import JudgeModalityRegistry


VALID_YAML = """\
version: "1.0"
model_type: llm
eval_dataset:
  uri: ./data/eval.jsonl
  label_column: expected_output
  task_type: classification
gates:
  - name: accuracy_gate
    phase: offline
    evaluator: accuracy
    metric: f1_weighted
    threshold: 0.85
    comparator: ">="
    blocking: true
"""


@pytest.fixture(autouse=True)
def load_plugins():
    EvaluatorRegistry.clear()
    ModelTypeRegistry.clear()
    DatasetFormatRegistry.clear()
    DriftMethodRegistry.clear()
    InferenceEncodingRegistry.clear()
    JudgeModalityRegistry.clear()
    load_all_plugins()
    yield


async def _seed_pipeline_run(db: AsyncSession) -> PipelineRun:
    """Insert a PipelineRun and return it."""
    run = PipelineRun(
        model_name="seed-model",
        candidate_version="v2",
        phase="offline",
        offline_status="completed",
        online_status="skipped",
        triggered_by="test",
        model_type="llm",
        registry_type="none",
        serving_type="none",
        gatekeeper_yaml=VALID_YAML,
    )
    db.add(run)
    await db.flush()
    return run


async def _seed_gate_results(db: AsyncSession, run_id: str) -> list[GateResult]:
    """Insert GateResult rows for a run."""
    results = []
    for passed, metric_val in [(True, 0.92), (False, 0.70)]:
        gr = GateResult(
            pipeline_run_id=run_id,
            phase="offline",
            gate_name=f"gate_{'pass' if passed else 'fail'}",
            gate_type="accuracy",
            metric_name="f1_weighted",
            metric_value=metric_val,
            threshold=0.85,
            comparator=">=",
            passed=passed,
            blocking=True,
        )
        db.add(gr)
        results.append(gr)
    await db.flush()
    return results


async def test_list_runs_with_data(async_client: AsyncClient, async_db: AsyncSession):
    """Verify GET /pipeline/runs returns PipelineRunSummary-shaped objects."""
    run = await _seed_pipeline_run(async_db)
    await _seed_gate_results(async_db, run.id)

    resp = await async_client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1

    summary = next(r for r in runs if r["id"] == run.id)

    # Verify PipelineRunSummary schema fields
    assert summary["model_name"] == "seed-model"
    assert summary["candidate_version"] == "v2"
    assert summary["offline_status"] == "completed"
    assert summary["online_status"] == "skipped"
    assert summary["triggered_by"] == "test"
    assert summary["registry_type"] == "none"
    assert summary["serving_type"] == "none"
    assert summary["model_type"] == "llm"
    assert summary["offline_gates_passed"] == 1
    assert summary["offline_gates_total"] == 2
    assert summary["online_gates_passed"] == 0
    assert summary["online_gates_total"] == 0
    assert "created_at" in summary
    assert "updated_at" in summary
    # champion_version and github_context can be None
    assert "champion_version" in summary
    assert "github_context" in summary


async def test_get_run_detail(async_client: AsyncClient, async_db: AsyncSession):
    """Verify GET /pipeline/runs/{id} returns gate_results, canary_snapshots, audit_log."""
    run = await _seed_pipeline_run(async_db)
    await _seed_gate_results(async_db, run.id)

    # Seed audit log
    db = async_db
    db.add(
        AuditLog(
            pipeline_run_id=run.id,
            phase="offline",
            action="triggered",
            actor="test",
            detail={"phase": "offline"},
        )
    )
    await db.flush()

    resp = await async_client.get(f"/api/v1/pipeline/runs/{run.id}")
    assert resp.status_code == 200
    detail = resp.json()

    # Core fields from PipelineRunSummary
    assert detail["id"] == run.id
    assert detail["model_name"] == "seed-model"

    # Detail-specific arrays
    assert isinstance(detail["gate_results"], list)
    assert len(detail["gate_results"]) == 2
    assert isinstance(detail["canary_snapshots"], list)
    assert isinstance(detail["audit_log"], list)
    assert len(detail["audit_log"]) >= 1

    # Verify gate result shape
    gr = detail["gate_results"][0]
    assert "id" in gr
    assert "pipeline_run_id" in gr
    assert "phase" in gr
    assert "gate_name" in gr
    assert "gate_type" in gr
    assert "metric_name" in gr
    assert "metric_value" in gr
    assert "threshold" in gr
    assert "comparator" in gr
    assert "passed" in gr
    assert "blocking" in gr
    assert "evaluated_at" in gr


async def test_get_gate_report(async_client: AsyncClient, async_db: AsyncSession):
    """Verify GET /pipeline/runs/{id}/report returns offline/online sections."""
    run = await _seed_pipeline_run(async_db)
    await _seed_gate_results(async_db, run.id)

    from sqlalchemy import select

    async def _mock_evaluate_gates(run_id, phase, config):
        result = await async_db.execute(
            select(GateResult)
            .where(GateResult.pipeline_run_id == run_id)
            .where(GateResult.phase == phase)
        )
        gate_results = result.scalars().all()
        gates = []
        all_passed = True
        for gr in gate_results:
            gates.append(
                {
                    "gate_name": gr.gate_name,
                    "passed": gr.passed,
                    "metric_value": gr.metric_value,
                    "threshold": gr.threshold,
                    "comparator": gr.comparator,
                    "blocking": gr.blocking,
                }
            )
            if not gr.passed and gr.blocking:
                all_passed = False
        return {"phase": phase, "overall_passed": all_passed, "gates": gates}

    with patch(
        "gatekeeper.services.gate_engine.evaluate_gates",
        side_effect=_mock_evaluate_gates,
    ):
        resp = await async_client.get(f"/api/v1/pipeline/runs/{run.id}/report")

    assert resp.status_code == 200
    report = resp.json()

    assert "pipeline_run_id" in report
    assert report["pipeline_run_id"] == run.id

    # Offline section
    assert "offline" in report
    offline = report["offline"]
    assert "overall_passed" in offline
    assert isinstance(offline["gates"], list)
    assert offline["overall_passed"] is False  # gate_fail has passed=False, blocking=True
    assert len(offline["gates"]) == 2

    # Each gate has expected keys
    for gate in offline["gates"]:
        assert "gate_name" in gate
        assert "passed" in gate
        assert "blocking" in gate

    # Online section (no online gate results seeded, so should be vacuously passing)
    assert "online" in report
    online = report["online"]
    assert "overall_passed" in online
    assert isinstance(online["gates"], list)


async def test_get_canary_snapshots(async_client: AsyncClient, async_db: AsyncSession):
    """Seed CanarySnapshot rows, verify GET /pipeline/runs/{id}/canary response shape."""
    run = await _seed_pipeline_run(async_db)

    async_db.add(
        CanarySnapshot(
            pipeline_run_id=run.id,
            champion_latency_p50_ms=12.5,
            champion_latency_p95_ms=45.0,
            challenger_latency_p50_ms=14.0,
            challenger_latency_p95_ms=50.0,
            champion_error_rate=0.01,
            challenger_error_rate=0.02,
            champion_request_count=1000,
            challenger_request_count=500,
            detail={"note": "test snapshot"},
        )
    )
    async_db.add(
        CanarySnapshot(
            pipeline_run_id=run.id,
            champion_latency_p50_ms=11.0,
            champion_latency_p95_ms=40.0,
            challenger_latency_p50_ms=13.0,
            challenger_latency_p95_ms=48.0,
            champion_error_rate=0.005,
            challenger_error_rate=0.015,
            champion_request_count=2000,
            challenger_request_count=1000,
        )
    )
    await async_db.flush()

    resp = await async_client.get(f"/api/v1/pipeline/runs/{run.id}/canary")
    assert resp.status_code == 200
    snapshots = resp.json()

    assert isinstance(snapshots, list)
    assert len(snapshots) == 2

    snap = snapshots[0]
    assert "id" in snap
    assert "pipeline_run_id" in snap
    assert snap["pipeline_run_id"] == run.id
    assert "timestamp" in snap
    assert "champion_latency_p50_ms" in snap
    assert "champion_latency_p95_ms" in snap
    assert "challenger_latency_p50_ms" in snap
    assert "challenger_latency_p95_ms" in snap
    assert "champion_error_rate" in snap
    assert "challenger_error_rate" in snap


async def test_get_audit_log(async_client: AsyncClient, async_db: AsyncSession):
    """Seed AuditLog rows, verify GET /pipeline/runs/{id}/audit response shape."""
    run = await _seed_pipeline_run(async_db)

    async_db.add(
        AuditLog(
            pipeline_run_id=run.id,
            phase="offline",
            action="triggered",
            actor="ci-bot",
            detail={"model_name": "seed-model"},
        )
    )
    async_db.add(
        AuditLog(
            pipeline_run_id=run.id,
            phase="offline",
            action="eval_started",
            actor="system",
            detail={"evaluator": "accuracy"},
        )
    )
    await async_db.flush()

    resp = await async_client.get(f"/api/v1/pipeline/runs/{run.id}/audit")
    assert resp.status_code == 200
    audit = resp.json()

    assert isinstance(audit, list)
    assert len(audit) == 2

    entry = audit[0]
    assert "id" in entry
    assert "pipeline_run_id" in entry
    assert entry["pipeline_run_id"] == run.id
    assert "phase" in entry
    assert "action" in entry
    assert "actor" in entry
    assert "created_at" in entry
    assert "detail" in entry

    # Verify specific values
    actions = {a["action"] for a in audit}
    assert "triggered" in actions
    assert "eval_started" in actions


async def test_proxy_predict(async_client: AsyncClient, async_db: AsyncSession):
    """POST /api/v1/proxy/predict with NoneServingAdapter returns mock response."""
    from gatekeeper.adapters.factory import AdapterBundle
    from gatekeeper.adapters.serving.none import NoneServingAdapter
    from gatekeeper.adapters.registry.none import NoneRegistryAdapter
    from gatekeeper.main import app

    # Set up adapters on app.state so the proxy endpoint finds them
    app.state.adapters = AdapterBundle(
        registry=NoneRegistryAdapter(),
        serving=NoneServingAdapter(),
    )

    try:
        resp = await async_client.post(
            "/api/v1/proxy/predict",
            json={"inputs": [{"text": "hello"}], "model_role": "champion"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "model_role" in data
        assert data["model_role"] == "champion"
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], (int, float))
        assert "status_code" in data
        assert data["status_code"] == 200
        assert "outputs" in data
        assert isinstance(data["outputs"], list)
        assert "error" in data
    finally:
        # Clean up app state
        if hasattr(app.state, "adapters"):
            del app.state.adapters


async def test_proxy_predict_no_adapter(async_client: AsyncClient, async_db: AsyncSession):
    """POST /api/v1/proxy/predict without adapter returns 503."""
    from gatekeeper.main import app

    # Ensure no adapters are set
    had_adapters = hasattr(app.state, "adapters")
    if had_adapters:
        saved_adapters = app.state.adapters
        del app.state.adapters

    try:
        resp = await async_client.post(
            "/api/v1/proxy/predict",
            json={"inputs": [{"text": "hello"}]},
        )
        assert resp.status_code == 503
        data = resp.json()
        assert "error" in data
        assert "no serving adapter" in data["error"].lower()
    finally:
        if had_adapters:
            app.state.adapters = saved_adapters
