"""Tests for trigger endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from gatekeeper.registries.loader import load_all_plugins
from gatekeeper.registries.evaluator import EvaluatorRegistry
from gatekeeper.registries.model_type import ModelTypeRegistry
from gatekeeper.registries.dataset_format import DatasetFormatRegistry
from gatekeeper.registries.drift_method import DriftMethodRegistry
from gatekeeper.registries.inference_encoding import InferenceEncodingRegistry
from gatekeeper.registries.judge_modality import JudgeModalityRegistry


VALID_YAML = """
version: "1.0"
model_type: llm
eval_dataset:
  uri: ./data/eval.jsonl
  label_column: expected_output
  task_type: summarisation
gates:
  - name: quality_gate
    phase: offline
    evaluator: llm_judge
    metric: llm_judge_score
    threshold: 0.75
    comparator: ">="
    blocking: true
    num_samples: 10
    rubric: "Score 0-1."
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


async def test_trigger_valid_config(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": "test-model",
            "candidate_version": "v1",
            "phase": "offline",
            "gatekeeper_yaml": VALID_YAML,
        },
        headers={"X-Gatekeeper-Secret": "changeme"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_run_id" in data
    assert data["status"] == "accepted"


async def test_trigger_wrong_secret(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": "test-model",
            "candidate_version": "v1",
            "phase": "offline",
            "gatekeeper_yaml": VALID_YAML,
        },
        headers={"X-Gatekeeper-Secret": "wrong"},
    )
    assert resp.status_code == 401


async def test_trigger_invalid_yaml(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": "test-model",
            "candidate_version": "v1",
            "phase": "offline",
            "gatekeeper_yaml": "{{invalid yaml",
        },
        headers={"X-Gatekeeper-Secret": "changeme"},
    )
    assert resp.status_code == 422


async def test_trigger_unregistered_evaluator(async_client: AsyncClient):
    yaml_with_bad_evaluator = """
version: "1.0"
model_type: llm
eval_dataset:
  uri: ./data/eval.jsonl
  label_column: expected_output
  task_type: summarisation
gates:
  - name: bad_gate
    phase: offline
    evaluator: nonexistent_evaluator
    metric: score
    threshold: 0.5
    comparator: ">="
    blocking: true
"""
    resp = await async_client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": "test-model",
            "candidate_version": "v1",
            "phase": "offline",
            "gatekeeper_yaml": yaml_with_bad_evaluator,
        },
        headers={"X-Gatekeeper-Secret": "changeme"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "validation_errors" in data["detail"]


async def test_trigger_unregistered_model_type(async_client: AsyncClient):
    yaml_with_bad_model = """
version: "1.0"
model_type: spatial_3d
eval_dataset:
  uri: ./data/eval.jsonl
  label_column: expected_output
  task_type: summarisation
gates:
  - name: gate1
    phase: offline
    evaluator: accuracy
    metric: f1_weighted
    threshold: 0.5
    comparator: ">="
    blocking: true
"""
    resp = await async_client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": "test-model",
            "candidate_version": "v1",
            "phase": "offline",
            "gatekeeper_yaml": yaml_with_bad_model,
        },
        headers={"X-Gatekeeper-Secret": "changeme"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert any("model_type" in e for e in data["detail"]["validation_errors"])


async def test_trigger_unregistered_drift_method(async_client: AsyncClient):
    yaml_with_bad_drift = """
version: "1.0"
model_type: llm
eval_dataset:
  uri: ./data/eval.jsonl
  label_column: expected_output
  task_type: summarisation
gates:
  - name: drift_gate
    phase: offline
    evaluator: drift
    metric: max_psi_score
    threshold: 0.2
    comparator: "<"
    blocking: true
    drift_method: nonexistent_method
"""
    resp = await async_client.post(
        "/api/v1/pipeline/trigger",
        json={
            "model_name": "test-model",
            "candidate_version": "v1",
            "phase": "offline",
            "gatekeeper_yaml": yaml_with_bad_drift,
        },
        headers={"X-Gatekeeper-Secret": "changeme"},
    )
    assert resp.status_code == 422


async def test_health_endpoint(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "registries" in data


async def test_list_runs_empty(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_system_registries(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/system/registries")
    assert resp.status_code == 200
    data = resp.json()
    assert "accuracy" in data["evaluators"]
    assert "llm" in data["model_types"]
    assert "jsonl" in data["dataset_formats"]
