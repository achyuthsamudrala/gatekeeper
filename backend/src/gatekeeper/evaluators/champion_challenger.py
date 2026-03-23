"""Champion vs Challenger evaluator."""

from __future__ import annotations

import asyncio
import dataclasses

from gatekeeper.adapters.registry.none import NoneRegistryAdapter
from gatekeeper.evaluators.accuracy import AccuracyEvaluator
from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext


class ChampionChallengerEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "champion_challenger"

    @property
    def phase(self) -> str:
        return "offline"

    @property
    def supported_model_types(self) -> list[str]:
        return ["*"]

    @property
    def primary_metric(self) -> str:
        return "champion_challenger_delta"

    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        try:
            if isinstance(context.registry_adapter, NoneRegistryAdapter):
                return EvalResult(
                    gate_name=context.gate_config["name"],
                    evaluator_name=self.name,
                    phase=self.phase,
                    metric_name=self.primary_metric,
                    metric_value=None,
                    passed=None,
                    skip_reason="registry not configured",
                )
            champion = await context.registry_adapter.get_champion_version(context.model_name)
            if champion is None:
                return EvalResult(
                    gate_name=context.gate_config["name"],
                    evaluator_name=self.name,
                    phase=self.phase,
                    metric_name=self.primary_metric,
                    metric_value=0.0,
                    passed=True,
                    skip_reason=None,
                    detail={"reason": "first_deployment"},
                )
            accuracy_eval = AccuracyEvaluator()
            challenger_ctx = dataclasses.replace(context)
            champion_ctx = dataclasses.replace(
                context,
                candidate_version=champion.version,
                gate_config={
                    **context.gate_config,
                    "name": f"{context.gate_config['name']}__champion",
                },
            )
            challenger_result, champion_result = await asyncio.gather(
                accuracy_eval.evaluate(challenger_ctx),
                accuracy_eval.evaluate(champion_ctx),
            )
            delta = (challenger_result.metric_value or 0.0) - (champion_result.metric_value or 0.0)
            return EvalResult(
                gate_name=context.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=delta,
                passed=None,
                skip_reason=None,
                detail={
                    "challenger_score": challenger_result.metric_value,
                    "champion_score": champion_result.metric_value,
                    "champion_version": champion.version,
                },
            )
        except Exception as e:
            return EvalResult(
                gate_name=context.gate_config.get("name", "regression_gate"),
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                error=True,
                error_message=str(e),
            )
