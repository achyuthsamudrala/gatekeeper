"""Gate policy engine — evaluates pass/fail for a phase."""

from __future__ import annotations

import logging

from sqlalchemy import select, update

from gatekeeper.core.database import AsyncSessionFactory
from gatekeeper.orm import GateResult

logger = logging.getLogger(__name__)


async def evaluate_gates(
    run_id: str,
    phase: str,
    gates_config: dict,
) -> dict:
    """
    Async gate policy evaluation.
    Loads GateResult rows from DB, applies threshold comparisons,
    and batches all updates into a single session/commit.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(GateResult)
            .where(GateResult.pipeline_run_id == run_id)
            .where(GateResult.phase == phase)
        )
        gate_results = result.scalars().all()

    config_gates = [g for g in gates_config.get("gates", []) if g.get("phase") == phase]
    gate_details = []
    all_blocking_passed = True
    updates: list[tuple[str, bool]] = []  # (gate_result_id, passed)

    for config_gate in config_gates:
        gate_name = config_gate["name"]
        db_result = next((r for r in gate_results if r.gate_name == gate_name), None)

        if db_result is None:
            gate_details.append(
                {
                    "gate_name": gate_name,
                    "passed": False,
                    "skip_reason": "evaluator_not_run",
                    "blocking": config_gate.get("blocking", True),
                }
            )
            if config_gate.get("blocking", True):
                all_blocking_passed = False
            continue

        if db_result.passed is None and db_result.skip_reason:
            gate_details.append(
                {
                    "gate_name": gate_name,
                    "passed": None,
                    "skip_reason": db_result.skip_reason,
                    "blocking": db_result.blocking,
                }
            )
            continue

        # Apply threshold comparison
        passed = _compare(
            db_result.metric_value,
            config_gate.get("comparator", ">="),
            config_gate.get("threshold"),
        )

        updates.append((db_result.id, passed))

        gate_details.append(
            {
                "gate_name": gate_name,
                "passed": passed,
                "metric_value": db_result.metric_value,
                "threshold": config_gate.get("threshold"),
                "comparator": config_gate.get("comparator"),
                "blocking": db_result.blocking,
            }
        )

        if not passed and db_result.blocking:
            all_blocking_passed = False

    # Batch all passed/failed updates into a single session
    if updates:
        async with AsyncSessionFactory() as db:
            for gate_id, passed in updates:
                await db.execute(
                    update(GateResult).where(GateResult.id == gate_id).values(passed=passed)
                )
            await db.commit()

    return {
        "phase": phase,
        "overall_passed": all_blocking_passed,
        "gates": gate_details,
    }


def _compare(value: float | None, comparator: str, threshold: float | None) -> bool:
    if value is None or threshold is None:
        return False
    ops = {
        ">=": lambda v, t: v >= t,
        "<=": lambda v, t: v <= t,
        ">": lambda v, t: v > t,
        "<": lambda v, t: v < t,
        "==": lambda v, t: v == t,
    }
    op = ops.get(comparator, ops[">="])
    return op(value, threshold)
