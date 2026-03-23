"""API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class TriggerRequest(BaseModel):
    model_name: str
    candidate_version: str
    phase: str = "offline"
    gatekeeper_yaml: str
    triggered_by: str = "api"
    pipeline_run_id: str | None = None
    github_context: dict | None = None


class TriggerResponse(BaseModel):
    pipeline_run_id: str
    status: str
    report_url: str


class PipelineRunSummary(BaseModel):
    id: str
    model_name: str
    candidate_version: str
    champion_version: str | None = None
    offline_status: str
    online_status: str
    triggered_by: str
    registry_type: str
    serving_type: str
    model_type: str
    offline_gates_passed: int = 0
    offline_gates_total: int = 0
    online_gates_passed: int = 0
    online_gates_total: int = 0
    github_context: dict | None = None
    created_at: str
    updated_at: str


class PipelineRunDetail(PipelineRunSummary):
    gate_results: list[GateResultResponse] = []
    canary_snapshots: list[CanarySnapshotResponse] = []
    audit_log: list[AuditLogResponse] = []


class GateResultResponse(BaseModel):
    id: str
    pipeline_run_id: str
    phase: str
    gate_name: str
    gate_type: str
    metric_name: str
    metric_value: float | None = None
    threshold: float | None = None
    comparator: str | None = None
    passed: bool | None = None
    blocking: bool = True
    skip_reason: str | None = None
    detail: dict | None = None
    evaluated_at: str


class CanarySnapshotResponse(BaseModel):
    id: str
    pipeline_run_id: str
    timestamp: str
    champion_latency_p50_ms: float | None = None
    champion_latency_p95_ms: float | None = None
    challenger_latency_p50_ms: float | None = None
    challenger_latency_p95_ms: float | None = None
    champion_error_rate: float | None = None
    challenger_error_rate: float | None = None
    detail: dict | None = None


class AuditLogResponse(BaseModel):
    id: str
    pipeline_run_id: str
    phase: str
    action: str
    actor: str
    detail: dict | None = None
    created_at: str


class PromoteRollbackRequest(BaseModel):
    reason: str = ""


class RegistryInfo(BaseModel):
    evaluators: list[str]
    model_types: list[str]
    dataset_formats: list[str]
    drift_methods: list[str]
    inference_encodings: list[str]
    judge_modalities: list[str]


# Forward reference resolution
PipelineRunDetail.model_rebuild()
