"""End-to-end pipeline tests exercising the full FastAPI flow."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.orm import GateResult
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


async def _trigger_pipeline(
    client: AsyncClient,
    *,
    model_name: str = "test-model",
    candidate_version: str = "v1",
    phase: str = "offline",
    yaml_str: str = VALID_YAML,
) -> dict:
    """Helper: trigger pipeline and return the response JSON."""
    resp = await client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": model_name,
            "candidate_version": candidate_version,
            "phase": phase,
            "gatekeeper_yaml": yaml_str,
        },
        headers={"X-Gatekeeper-Secret": "changeme"},
    )
    assert resp.status_code == 200
    return resp.json()


async def _insert_gate_result(
    db: AsyncSession,
    run_id: str,
    *,
    passed: bool,
    metric_value: float = 0.90,
    threshold: float = 0.85,
) -> None:
    """Insert a GateResult row to simulate eval engine completion."""
    db.add(
        GateResult(
            pipeline_run_id=run_id,
            phase="offline",
            gate_name="accuracy_gate",
            gate_type="accuracy",
            metric_name="f1_weighted",
            metric_value=metric_value,
            threshold=threshold,
            comparator=">=",
            passed=passed,
            blocking=True,
        )
    )
    await db.flush()


async def test_e2e_offline_pass(async_client: AsyncClient, async_db: AsyncSession):
    """Trigger offline pipeline with passing gate results, verify all endpoints."""
    trigger_data = await _trigger_pipeline(async_client)
    run_id = trigger_data["pipeline_run_id"]

    # Simulate eval engine producing a passing result
    await _insert_gate_result(async_db, run_id, passed=True, metric_value=0.92)

    # GET /runs lists the run
    resp = await async_client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1
    assert any(r["id"] == run_id for r in runs)
    run_summary = next(r for r in runs if r["id"] == run_id)
    assert run_summary["offline_gates_passed"] == 1
    assert run_summary["offline_gates_total"] == 1

    # GET /runs/{id} returns full detail with gate_results
    resp = await async_client.get(f"/api/v1/pipeline/runs/{run_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == run_id
    assert len(detail["gate_results"]) == 1
    assert detail["gate_results"][0]["passed"] is True
    assert detail["gate_results"][0]["gate_name"] == "accuracy_gate"
    assert detail["gate_results"][0]["metric_value"] == 0.92

    # GET /runs/{id}/report returns gate policy with overall_passed=True
    # Patch gate_engine.AsyncSessionFactory to use our test DB session
    from unittest.mock import patch
    from sqlalchemy import select

    async def _mock_evaluate_gates(run_id_arg, phase, config):
        """Compute report from the test DB directly."""
        result = await async_db.execute(
            select(GateResult)
            .where(GateResult.pipeline_run_id == run_id_arg)
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
        if not gate_results:
            # No results for this phase — vacuously pass
            pass
        return {"phase": phase, "overall_passed": all_passed, "gates": gates}

    with patch(
        "gatekeeper.services.gate_engine.evaluate_gates",
        side_effect=_mock_evaluate_gates,
    ):
        resp = await async_client.get(f"/api/v1/pipeline/runs/{run_id}/report")
    assert resp.status_code == 200
    report = resp.json()
    assert report["offline"]["overall_passed"] is True
    assert len(report["offline"]["gates"]) == 1
    assert report["offline"]["gates"][0]["passed"] is True

    # GET /runs/{id}/audit has "triggered" entry
    resp = await async_client.get(f"/api/v1/pipeline/runs/{run_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()
    assert len(audit) >= 1
    assert any(a["action"] == "triggered" for a in audit)


async def test_e2e_offline_fail(async_client: AsyncClient, async_db: AsyncSession):
    """Trigger offline pipeline with failing gate results, verify overall_passed=False."""
    trigger_data = await _trigger_pipeline(async_client)
    run_id = trigger_data["pipeline_run_id"]

    # Simulate eval engine producing a failing result
    await _insert_gate_result(async_db, run_id, passed=False, metric_value=0.60)

    # Verify run detail shows failing gate
    resp = await async_client.get(f"/api/v1/pipeline/runs/{run_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["gate_results"][0]["passed"] is False
    assert detail["offline_gates_passed"] == 0
    assert detail["offline_gates_total"] == 1

    # Verify report shows overall_passed=False
    from unittest.mock import patch
    from sqlalchemy import select

    async def _mock_evaluate_gates(run_id_arg, phase, config):
        result = await async_db.execute(
            select(GateResult)
            .where(GateResult.pipeline_run_id == run_id_arg)
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
        resp = await async_client.get(f"/api/v1/pipeline/runs/{run_id}/report")
    assert resp.status_code == 200
    report = resp.json()
    assert report["offline"]["overall_passed"] is False
    assert report["offline"]["gates"][0]["passed"] is False


async def test_e2e_run_detail_404(async_client: AsyncClient, async_db: AsyncSession):
    """GET /runs/nonexistent returns 404."""
    resp = await async_client.get("/api/v1/pipeline/runs/nonexistent-id-12345")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_e2e_promote_requires_canary(async_client: AsyncClient, async_db: AsyncSession):
    """POST /runs/{id}/promote on non-canary run returns 400."""
    trigger_data = await _trigger_pipeline(async_client)
    run_id = trigger_data["pipeline_run_id"]

    resp = await async_client.post(
        f"/api/v1/pipeline/runs/{run_id}/promote",
        json={"reason": "test promote"},
    )
    assert resp.status_code == 400
    assert "canary" in resp.json()["detail"].lower()


async def test_e2e_rollback_requires_canary(async_client: AsyncClient, async_db: AsyncSession):
    """POST /runs/{id}/rollback on non-canary run returns 400."""
    trigger_data = await _trigger_pipeline(async_client)
    run_id = trigger_data["pipeline_run_id"]

    resp = await async_client.post(
        f"/api/v1/pipeline/runs/{run_id}/rollback",
        json={"reason": "test rollback"},
    )
    assert resp.status_code == 400
    assert "cannot be rolled back" in resp.json()["detail"].lower()


async def test_e2e_audit_log_entries(async_client: AsyncClient, async_db: AsyncSession):
    """Verify audit log endpoint returns entries after trigger."""
    trigger_data = await _trigger_pipeline(async_client)
    run_id = trigger_data["pipeline_run_id"]

    resp = await async_client.get(f"/api/v1/pipeline/runs/{run_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()

    assert len(audit) >= 1
    triggered_entry = next(a for a in audit if a["action"] == "triggered")
    assert triggered_entry["pipeline_run_id"] == run_id
    assert triggered_entry["phase"] == "offline"
    assert triggered_entry["actor"] == "api"
    assert triggered_entry["detail"]["model_name"] == "test-model"

    # Verify all required fields are present
    for entry in audit:
        assert "id" in entry
        assert "pipeline_run_id" in entry
        assert "phase" in entry
        assert "action" in entry
        assert "actor" in entry
        assert "created_at" in entry
