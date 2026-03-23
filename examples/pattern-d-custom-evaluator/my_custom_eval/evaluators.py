"""Example custom evaluator plugin — WordCountEvaluator."""

from __future__ import annotations

import asyncio

from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext


class WordCountEvaluator(BaseEvaluator):
    """
    Example custom evaluator. Checks average word count of model outputs.
    Demonstrates the full async BaseEvaluator interface.
    """

    name = "word_count"
    phase = "offline"
    supported_model_types = ["*"]
    primary_metric = "avg_word_count"

    async def evaluate(self, ctx: EvaluationContext) -> EvalResult:
        try:
            samples = []
            async for batch in ctx.dataset_loader.stream(
                ctx.eval_dataset_config.uri,
                ctx.eval_dataset_config,
                batch_size=50,
            ):
                samples.extend(batch)
                break

            outputs = await ctx.runner.run(
                ctx.model_name, ctx.candidate_version, samples[:50]
            )

            # CPU-bound word counting in thread pool
            avg_words = await asyncio.get_running_loop().run_in_executor(
                ctx.cpu_executor,
                lambda: sum(len(str(o).split()) for o in outputs) / max(len(outputs), 1),
            )

            return EvalResult(
                gate_name=ctx.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=avg_words,
                passed=None,
                skip_reason=None,
                detail={"num_samples": len(outputs)},
            )
        except Exception as e:
            return EvalResult(
                gate_name=ctx.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                skip_reason=str(e),
            )
