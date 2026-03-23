"""Eval engine — runs evaluators concurrently within phases."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from gatekeeper.adapters.factory import AdapterBundle
from gatekeeper.core.database import AsyncSessionFactory
from gatekeeper.registries.dataset_format import DatasetFormatRegistry
from gatekeeper.registries.evaluator import (
    DatasetConfig,
    EvalResult,
    EvaluationContext,
    EvaluatorRegistry,
    LLMJudgeConfig,
)
from gatekeeper.registries.model_type import ModelTypeRegistry

logger = logging.getLogger(__name__)


def _infer_format(uri: str) -> str:
    if uri.endswith(".parquet"):
        return "parquet"
    if uri.endswith(".csv"):
        return "csv"
    return "jsonl"


def _error_result(gate: dict, error_msg: str) -> EvalResult:
    return EvalResult(
        gate_name=gate.get("name", "unknown"),
        evaluator_name=gate.get("evaluator", "unknown"),
        phase=gate.get("phase", "unknown"),
        metric_name=gate.get("metric", "unknown"),
        metric_value=None,
        passed=None,
        error=True,
        error_message=error_msg,
    )


async def run_eval_phases(
    run_id: str,
    phases: list[str],
    gates_config: dict,
    adapters: AdapterBundle,
    cpu_executor: ThreadPoolExecutor,
    server_config: dict | None = None,
    llm_judge_client: object | None = None,
) -> None:
    """Run evaluation phases. Called as a background task."""

    if "offline" in phases:
        await _run_phase(
            run_id,
            "offline",
            gates_config,
            adapters,
            cpu_executor,
            server_config=server_config,
            llm_judge_client=llm_judge_client,
        )
        if "online" in phases:
            async with AsyncSessionFactory() as db:
                from sqlalchemy import select, update
                from gatekeeper.orm import PipelineRun

                result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
                run = result.scalar_one_or_none()
                if run and run.offline_status != "passed":
                    await db.execute(
                        update(PipelineRun)
                        .where(PipelineRun.id == run_id)
                        .values(online_status="skipped")
                    )
                    await db.commit()
                    return

    if "online" in phases:
        await _run_phase(
            run_id,
            "online",
            gates_config,
            adapters,
            cpu_executor,
            server_config=server_config,
            llm_judge_client=llm_judge_client,
        )


async def _run_phase(
    run_id: str,
    phase: str,
    gates_config: dict,
    adapters: AdapterBundle,
    cpu_executor: ThreadPoolExecutor,
    server_config: dict | None = None,
    llm_judge_client: object | None = None,
) -> None:
    from gatekeeper.services.gate_engine import evaluate_gates

    gates = gates_config.get("gates", [])
    phase_gates = [g for g in gates if g.get("phase") == phase]
    if not phase_gates:
        return

    model_type_name = gates_config.get("model_type", "llm")
    model_type_def = ModelTypeRegistry.get(model_type_name)

    eval_ds = gates_config.get("eval_dataset", {})
    eval_dataset_config = DatasetConfig(
        uri=eval_ds.get("uri", ""),
        format=eval_ds.get("format"),
        label_column=eval_ds.get("label_column"),
        task_type=eval_ds.get("task_type"),
    )

    ref_ds = gates_config.get("reference_dataset")
    reference_dataset_config = None
    if ref_ds:
        reference_dataset_config = DatasetConfig(
            uri=ref_ds.get("uri", ""),
            format=ref_ds.get("format"),
            label_column=ref_ds.get("label_column"),
            feature_columns=ref_ds.get("feature_columns"),
            categorical_columns=ref_ds.get("categorical_columns"),
        )

    dataset_format = eval_dataset_config.format or _infer_format(eval_dataset_config.uri)
    dataset_loader = DatasetFormatRegistry.get(dataset_format)

    llm_judge_config = None
    if server_config and server_config.get("llm_judge"):
        lj = server_config["llm_judge"]
        llm_judge_config = LLMJudgeConfig(
            provider=lj.get("provider", "anthropic"),
            model=lj.get("model", "claude-sonnet-4-20250514"),
            api_key=lj.get("api_key", ""),
        )

    # Update phase status to running
    async with AsyncSessionFactory() as db:
        from sqlalchemy import update
        from gatekeeper.orm import PipelineRun

        status_field = "offline_status" if phase == "offline" else "online_status"
        await db.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(**{status_field: "running"})
        )
        await db.commit()

    # Build contexts and run evaluators concurrently
    contexts = [
        EvaluationContext(
            run_id=run_id,
            model_name=gates_config.get("_model_name", "unknown"),
            candidate_version=gates_config.get("_candidate_version", "unknown"),
            model_type=model_type_def,
            runner=adapters.offline_runner if phase == "offline" else None,
            serving_adapter=adapters.serving if phase == "online" else None,
            registry_adapter=adapters.registry,
            dataset_loader=dataset_loader,
            eval_dataset_config=eval_dataset_config,
            reference_dataset_config=reference_dataset_config,
            llm_judge_config=llm_judge_config,
            llm_judge_client=llm_judge_client,
            gate_config=gate,
            cpu_executor=cpu_executor,
        )
        for gate in phase_gates
    ]

    evaluators = [EvaluatorRegistry.get(gate["evaluator"]) for gate in phase_gates]
    tasks = [ev.evaluate(ctx) for ev, ctx in zip(evaluators, contexts)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Persist results
    async with AsyncSessionFactory() as db:
        from gatekeeper.orm import GateResult as GateResultORM

        for gate, result in zip(phase_gates, results):
            if isinstance(result, BaseException):
                result = _error_result(gate, str(result))
            record = GateResultORM(
                pipeline_run_id=run_id,
                phase=phase,
                gate_name=result.gate_name,
                gate_type=result.evaluator_name,
                metric_name=result.metric_name,
                metric_value=result.metric_value,
                threshold=gate.get("threshold"),
                comparator=gate.get("comparator"),
                passed=result.passed,
                blocking=gate.get("blocking", True),
                skip_reason=result.skip_reason,
                detail={
                    **(result.detail or {}),
                    **(
                        {"error": True, "error_message": result.error_message}
                        if result.error
                        else {}
                    ),
                },
            )
            db.add(record)
        await db.commit()

    # Evaluate gate policy
    policy = await evaluate_gates(run_id, phase, gates_config)

    # Finalize phase
    async with AsyncSessionFactory() as db:
        from sqlalchemy import update
        from gatekeeper.orm import PipelineRun

        status_field = "offline_status" if phase == "offline" else "online_status"
        new_status = "passed" if policy["overall_passed"] else "failed"
        await db.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(**{status_field: new_status})
        )
        await db.commit()
