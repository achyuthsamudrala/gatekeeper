"""Pipeline API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.api.v1.schemas import (
    AuditLogResponse,
    CanarySnapshotResponse,
    GateResultResponse,
    PipelineRunDetail,
    PipelineRunSummary,
    PromoteRollbackRequest,
    RegistryInfo,
    TriggerRequest,
    TriggerResponse,
)
from gatekeeper.core.database import get_db
from gatekeeper.orm import AuditLog, CanarySnapshot, GateResult, PipelineRun
from gatekeeper.registries import (
    DatasetFormatRegistry,
    DriftMethodRegistry,
    EvaluatorRegistry,
    InferenceEncodingRegistry,
    JudgeModalityRegistry,
    ModelTypeRegistry,
)
from gatekeeper.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _validate_config(config: dict) -> list[str]:
    """Validate gatekeeper.yaml against registries."""
    errors = []

    model_type = config.get("model_type")
    if model_type and not ModelTypeRegistry.has(model_type):
        errors.append(
            f"model_type '{model_type}' is not registered. "
            f"Known types: {list(ModelTypeRegistry.all())}. "
            f"Install a plugin to add support."
        )

    eval_ds = config.get("eval_dataset", {})
    if eval_ds.get("format") and not DatasetFormatRegistry.has(eval_ds["format"]):
        errors.append(f"eval_dataset.format '{eval_ds['format']}' is not registered.")

    for gate in config.get("gates", []):
        evaluator = gate.get("evaluator")
        if evaluator and not EvaluatorRegistry.has(evaluator):
            errors.append(
                f"Gate '{gate.get('name')}': evaluator '{evaluator}' is not registered. "
                f"Install a plugin to add custom evaluators."
            )
        elif evaluator:
            ev = EvaluatorRegistry.get(evaluator)
            if model_type not in ev.supported_model_types and "*" not in ev.supported_model_types:
                errors.append(
                    f"Gate '{gate.get('name')}': evaluator '{evaluator}' "
                    f"does not support model_type '{model_type}'."
                )

        drift_method = gate.get("drift_method")
        if drift_method and not DriftMethodRegistry.has(drift_method):
            errors.append(
                f"Gate '{gate.get('name')}': drift_method '{drift_method}' is not registered."
            )

        judge_modality = gate.get("judge_modality")
        if judge_modality and not JudgeModalityRegistry.has(judge_modality):
            errors.append(
                f"Gate '{gate.get('name')}': judge_modality '{judge_modality}' is not registered."
            )

    return errors


@router.post("/pipeline/trigger", response_model=TriggerResponse)
async def trigger_pipeline(
    req: TriggerRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_gatekeeper_secret: Annotated[str | None, Header()] = None,
):
    # Auth check
    if x_gatekeeper_secret != settings.secret:
        raise HTTPException(status_code=401, detail="Invalid or missing trigger secret")

    # Parse YAML
    try:
        config = yaml.safe_load(req.gatekeeper_yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}")

    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="gatekeeper_yaml must be a YAML mapping")

    # Validate against registries
    errors = _validate_config(config)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    # Determine phases
    phase = req.phase
    phases = []
    if phase in ("offline", "both"):
        phases.append("offline")
    if phase in ("online", "both"):
        phases.append("online")

    # Create pipeline run
    run = PipelineRun(
        model_name=req.model_name,
        candidate_version=req.candidate_version,
        phase=req.phase,
        offline_status="pending" if "offline" in phases else "skipped",
        online_status="pending" if "online" in phases else "skipped",
        triggered_by=req.triggered_by,
        model_type=config.get("model_type", "llm"),
        registry_type=getattr(request.app.state, "registry_type", "none"),
        serving_type=getattr(request.app.state, "serving_type", "none"),
        gatekeeper_yaml=req.gatekeeper_yaml,
        github_context=req.github_context,
    )

    if req.pipeline_run_id:
        run.id = req.pipeline_run_id

    db.add(run)
    await db.flush()

    db.add(
        AuditLog(
            pipeline_run_id=run.id,
            phase=req.phase,
            action="triggered",
            actor=req.triggered_by,
            detail={"phase": req.phase, "model_name": req.model_name},
        )
    )
    await db.flush()

    # Inject runtime metadata into config for the eval engine
    config["_model_name"] = req.model_name
    config["_candidate_version"] = req.candidate_version

    # Launch eval phases as background task
    from gatekeeper.services.eval_engine import run_eval_phases

    adapters = getattr(request.app.state, "adapters", None)
    cpu_executor = getattr(request.app.state, "cpu_executor", None)
    server_config = getattr(request.app.state, "server_config", None)
    llm_judge_client = getattr(request.app.state, "llm_judge_client", None)

    if adapters and cpu_executor:
        background_tasks.add_task(
            run_eval_phases,
            run_id=run.id,
            phases=phases,
            gates_config=config,
            adapters=adapters,
            cpu_executor=cpu_executor,
            server_config=server_config,
            llm_judge_client=llm_judge_client,
        )

    return TriggerResponse(
        pipeline_run_id=run.id,
        status="accepted",
        report_url=f"/api/v1/pipeline/runs/{run.id}",
    )


@router.get("/pipeline/runs", response_model=list[PipelineRunSummary])
async def list_pipeline_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    model_name: str | None = None,
    limit: int = 50,
):
    query = select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(limit)
    if model_name:
        query = query.where(PipelineRun.model_name == model_name)
    result = await db.execute(query)
    runs = result.scalars().all()

    summaries = []
    for run in runs:
        # Count gate results
        gr_result = await db.execute(select(GateResult).where(GateResult.pipeline_run_id == run.id))
        gate_results = gr_result.scalars().all()
        offline_results = [g for g in gate_results if g.phase == "offline"]
        online_results = [g for g in gate_results if g.phase == "online"]

        summaries.append(
            PipelineRunSummary(
                id=str(run.id),
                model_name=run.model_name,
                candidate_version=run.candidate_version,
                champion_version=run.champion_version,
                offline_status=run.offline_status,
                online_status=run.online_status,
                triggered_by=run.triggered_by,
                registry_type=run.registry_type,
                serving_type=run.serving_type,
                model_type=run.model_type,
                offline_gates_passed=sum(1 for g in offline_results if g.passed is True),
                offline_gates_total=len(offline_results),
                online_gates_passed=sum(1 for g in online_results if g.passed is True),
                online_gates_total=len(online_results),
                github_context=run.github_context,
                created_at=str(run.created_at),
                updated_at=str(run.updated_at),
            )
        )
    return summaries


@router.get("/pipeline/runs/{run_id}", response_model=PipelineRunDetail)
async def get_pipeline_run(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    gr_result = await db.execute(select(GateResult).where(GateResult.pipeline_run_id == run_id))
    gate_results = gr_result.scalars().all()

    cs_result = await db.execute(
        select(CanarySnapshot).where(CanarySnapshot.pipeline_run_id == run_id)
    )
    canary_snapshots = cs_result.scalars().all()

    al_result = await db.execute(select(AuditLog).where(AuditLog.pipeline_run_id == run_id))
    audit_logs = al_result.scalars().all()

    offline_results = [g for g in gate_results if g.phase == "offline"]
    online_results = [g for g in gate_results if g.phase == "online"]

    return PipelineRunDetail(
        id=str(run.id),
        model_name=run.model_name,
        candidate_version=run.candidate_version,
        champion_version=run.champion_version,
        offline_status=run.offline_status,
        online_status=run.online_status,
        triggered_by=run.triggered_by,
        registry_type=run.registry_type,
        serving_type=run.serving_type,
        model_type=run.model_type,
        offline_gates_passed=sum(1 for g in offline_results if g.passed is True),
        offline_gates_total=len(offline_results),
        online_gates_passed=sum(1 for g in online_results if g.passed is True),
        online_gates_total=len(online_results),
        github_context=run.github_context,
        created_at=str(run.created_at),
        updated_at=str(run.updated_at),
        gate_results=[
            GateResultResponse(
                id=str(g.id),
                pipeline_run_id=str(g.pipeline_run_id),
                phase=g.phase,
                gate_name=g.gate_name,
                gate_type=g.gate_type,
                metric_name=g.metric_name,
                metric_value=g.metric_value,
                threshold=g.threshold,
                comparator=g.comparator,
                passed=g.passed,
                blocking=g.blocking,
                skip_reason=g.skip_reason,
                detail=g.detail,
                evaluated_at=str(g.evaluated_at),
            )
            for g in gate_results
        ],
        canary_snapshots=[
            CanarySnapshotResponse(
                id=str(s.id),
                pipeline_run_id=str(s.pipeline_run_id),
                timestamp=str(s.timestamp),
                champion_latency_p50_ms=s.champion_latency_p50_ms,
                champion_latency_p95_ms=s.champion_latency_p95_ms,
                challenger_latency_p50_ms=s.challenger_latency_p50_ms,
                challenger_latency_p95_ms=s.challenger_latency_p95_ms,
                champion_error_rate=s.champion_error_rate,
                challenger_error_rate=s.challenger_error_rate,
                detail=s.detail,
            )
            for s in canary_snapshots
        ],
        audit_log=[
            AuditLogResponse(
                id=str(a.id),
                pipeline_run_id=str(a.pipeline_run_id),
                phase=a.phase,
                action=a.action,
                actor=a.actor,
                detail=a.detail,
                created_at=str(a.created_at),
            )
            for a in audit_logs
        ],
    )


@router.get("/pipeline/runs/{run_id}/report")
async def get_gate_report(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    config = yaml.safe_load(run.gatekeeper_yaml)
    from gatekeeper.services.gate_engine import evaluate_gates

    offline_report = await evaluate_gates(run_id, "offline", config)
    online_report = await evaluate_gates(run_id, "online", config)

    return {
        "pipeline_run_id": run_id,
        "offline": offline_report,
        "online": online_report,
    }


@router.get("/pipeline/runs/{run_id}/canary", response_model=list[CanarySnapshotResponse])
async def get_canary_snapshots(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(CanarySnapshot)
        .where(CanarySnapshot.pipeline_run_id == run_id)
        .order_by(CanarySnapshot.timestamp)
    )
    snapshots = result.scalars().all()
    return [
        CanarySnapshotResponse(
            id=str(s.id),
            pipeline_run_id=str(s.pipeline_run_id),
            timestamp=str(s.timestamp),
            champion_latency_p50_ms=s.champion_latency_p50_ms,
            champion_latency_p95_ms=s.champion_latency_p95_ms,
            challenger_latency_p50_ms=s.challenger_latency_p50_ms,
            challenger_latency_p95_ms=s.challenger_latency_p95_ms,
            champion_error_rate=s.champion_error_rate,
            challenger_error_rate=s.challenger_error_rate,
            detail=s.detail,
        )
        for s in snapshots
    ]


@router.get("/pipeline/runs/{run_id}/audit", response_model=list[AuditLogResponse])
async def get_audit_log(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(AuditLog).where(AuditLog.pipeline_run_id == run_id).order_by(AuditLog.created_at)
    )
    logs = result.scalars().all()
    return [
        AuditLogResponse(
            id=str(a.id),
            pipeline_run_id=str(a.pipeline_run_id),
            phase=a.phase,
            action=a.action,
            actor=a.actor,
            detail=a.detail,
            created_at=str(a.created_at),
        )
        for a in logs
    ]


@router.post("/pipeline/runs/{run_id}/promote")
async def promote_pipeline(
    run_id: str,
    req: PromoteRollbackRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if run.online_status != "canary":
        raise HTTPException(status_code=400, detail="Run is not in canary state")

    from gatekeeper.services.canary import promote_canary

    adapters = getattr(request.app.state, "adapters", None)
    if adapters:
        await promote_canary(run_id, req.reason or "manual_promote", adapters)
    return {"status": "promoted"}


@router.post("/pipeline/runs/{run_id}/rollback")
async def rollback_pipeline(
    run_id: str,
    req: PromoteRollbackRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if run.online_status not in ("canary", "promoted"):
        raise HTTPException(status_code=400, detail="Run cannot be rolled back")

    from gatekeeper.services.canary import rollback_canary

    adapters = getattr(request.app.state, "adapters", None)
    if adapters:
        await rollback_canary(run_id, req.reason or "manual_rollback", adapters)
    return {"status": "rolled_back"}


@router.get("/system/registries", response_model=RegistryInfo)
async def get_registries():
    return RegistryInfo(
        evaluators=list(EvaluatorRegistry.all().keys()),
        model_types=list(ModelTypeRegistry.all().keys()),
        dataset_formats=list(DatasetFormatRegistry.all().keys()),
        drift_methods=list(DriftMethodRegistry.all().keys()),
        inference_encodings=list(InferenceEncodingRegistry.all().keys()),
        judge_modalities=list(JudgeModalityRegistry.all().keys()),
    )
