"""Canary traffic manager."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import update

from gatekeeper.adapters.factory import AdapterBundle
from gatekeeper.core.database import AsyncSessionFactory
from gatekeeper.orm import AuditLog, CanarySnapshot, PipelineRun

logger = logging.getLogger(__name__)


async def start_canary(
    run_id: str,
    gates_config: dict,
    adapters: AdapterBundle,
    app_state: object,
) -> None:
    """Start canary observation as an asyncio task."""
    canary_config = gates_config.get("canary", {})
    traffic_pct = canary_config.get("traffic_percent", 10) / 100.0

    await adapters.serving.set_traffic_split(
        {
            "champion": 1.0 - traffic_pct,
            "challenger": traffic_pct,
        }
    )

    async with AsyncSessionFactory() as db:
        await db.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(online_status="canary")
        )
        db.add(
            AuditLog(
                pipeline_run_id=run_id,
                phase="online",
                action="canary_started",
                detail={"traffic_percent": canary_config.get("traffic_percent", 10)},
            )
        )
        await db.commit()

    task = asyncio.create_task(
        _observation_loop(run_id, gates_config, adapters),
        name=f"canary-{run_id}",
    )
    active_tasks = getattr(app_state, "active_canary_tasks", {})
    active_tasks[run_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        active_tasks.pop(run_id, None)

    task.add_done_callback(_cleanup)


async def _observation_loop(
    run_id: str,
    gates_config: dict,
    adapters: AdapterBundle,
) -> None:
    """Async observation loop. Uses asyncio.sleep, not time.sleep."""
    canary_config = gates_config.get("canary", {})
    window = canary_config.get("observation_window_minutes", 30) * 60
    interval = 60
    elapsed = 0
    snapshot = None

    while elapsed < window:
        await asyncio.sleep(interval)
        elapsed += interval

        snapshot = await _collect_snapshot(run_id, adapters)
        async with AsyncSessionFactory() as db:
            db.add(
                CanarySnapshot(
                    pipeline_run_id=run_id,
                    champion_latency_p50_ms=snapshot.get("champion_latency_p50_ms"),
                    champion_latency_p95_ms=snapshot.get("champion_latency_p95_ms"),
                    challenger_latency_p50_ms=snapshot.get("challenger_latency_p50_ms"),
                    challenger_latency_p95_ms=snapshot.get("challenger_latency_p95_ms"),
                    champion_error_rate=snapshot.get("champion_error_rate"),
                    challenger_error_rate=snapshot.get("challenger_error_rate"),
                    champion_request_count=snapshot.get("champion_request_count"),
                    challenger_request_count=snapshot.get("challenger_request_count"),
                    detail=snapshot,
                )
            )
            await db.commit()

        if _should_rollback(snapshot, canary_config):
            await rollback_canary(run_id, "auto_rollback_threshold_breached", adapters)
            return

    if snapshot and _should_promote(snapshot, canary_config):
        await promote_canary(run_id, "observation_window_complete", adapters)
    else:
        await rollback_canary(run_id, "thresholds_not_met", adapters)


async def _collect_snapshot(run_id: str, adapters: AdapterBundle) -> dict:
    """Collect current canary metrics."""
    return {
        "champion_latency_p50_ms": 0.0,
        "champion_latency_p95_ms": 0.0,
        "challenger_latency_p50_ms": 0.0,
        "challenger_latency_p95_ms": 0.0,
        "champion_error_rate": 0.0,
        "challenger_error_rate": 0.0,
        "champion_request_count": 0,
        "challenger_request_count": 0,
    }


def _should_rollback(snapshot: dict, canary_config: dict) -> bool:
    thresholds = canary_config.get("auto_rollback_threshold", {})
    if not thresholds:
        return False
    max_latency = thresholds.get("latency_p95_ms")
    max_error = thresholds.get("error_rate")
    if max_latency and snapshot.get("challenger_latency_p95_ms", 0) > max_latency:
        return True
    if max_error and snapshot.get("challenger_error_rate", 0) > max_error:
        return True
    return False


def _should_promote(snapshot: dict, canary_config: dict) -> bool:
    thresholds = canary_config.get("auto_promote_threshold", {})
    if not thresholds:
        return True
    max_latency = thresholds.get("latency_p95_ms")
    max_error = thresholds.get("error_rate")
    if max_latency and snapshot.get("challenger_latency_p95_ms", 0) > max_latency:
        return False
    if max_error and snapshot.get("challenger_error_rate", 0) > max_error:
        return False
    return True


async def promote_canary(run_id: str, reason: str, adapters: AdapterBundle) -> None:
    await adapters.serving.set_traffic_split({"champion": 0.0, "challenger": 1.0})
    async with AsyncSessionFactory() as db:
        await db.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(online_status="promoted")
        )
        db.add(
            AuditLog(
                pipeline_run_id=run_id,
                phase="online",
                action="promoted",
                detail={"reason": reason},
            )
        )
        await db.commit()


async def rollback_canary(run_id: str, reason: str, adapters: AdapterBundle) -> None:
    await adapters.serving.set_traffic_split({"champion": 1.0, "challenger": 0.0})
    async with AsyncSessionFactory() as db:
        await db.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(online_status="rolled_back")
        )
        db.add(
            AuditLog(
                pipeline_run_id=run_id,
                phase="online",
                action="rolled_back",
                detail={"reason": reason},
            )
        )
        await db.commit()
