"""LLM-as-Judge evaluator."""

from __future__ import annotations

import asyncio
import json
import logging

from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext
from gatekeeper.registries.judge_modality import JudgeModalityRegistry

logger = logging.getLogger(__name__)


class LLMJudgeEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "llm_judge"

    @property
    def phase(self) -> str:
        return "offline"

    @property
    def supported_model_types(self) -> list[str]:
        return ["*"]

    @property
    def primary_metric(self) -> str:
        return "llm_judge_score"

    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        try:
            num_samples = context.gate_config.get("num_samples", 20)
            modality = JudgeModalityRegistry.get(context.gate_config.get("judge_modality", "text"))
            samples = []
            async for batch in context.dataset_loader.stream(
                context.eval_dataset_config.uri,
                context.eval_dataset_config,
                batch_size=num_samples,
            ):
                samples.extend(batch)
                if len(samples) >= num_samples:
                    break
            samples = samples[:num_samples]

            outputs = await context.runner.run(
                context.model_name, context.candidate_version, samples
            )

            judge_tasks = [
                self._judge_one(sample, output, modality, context)
                for sample, output in zip(samples, outputs)
            ]
            scored = await asyncio.gather(*judge_tasks, return_exceptions=True)

            valid_scores = [
                s["score"] for s in scored if not isinstance(s, BaseException) and s is not None
            ]
            details = [s for s in scored if not isinstance(s, BaseException) and s is not None]

            mean_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
            return EvalResult(
                gate_name=context.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=mean_score,
                passed=None,
                skip_reason=None,
                detail={"num_samples_judged": len(valid_scores), "samples": details},
            )
        except Exception as e:
            return EvalResult(
                gate_name=context.gate_config.get("name", "quality_gate"),
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                error=True,
                error_message=str(e),
            )

    async def _judge_one(self, sample, output, modality, ctx) -> dict | None:
        try:
            messages = await modality.build_judge_message(
                rubric=ctx.gate_config.get("rubric", ""),
                input_sample=sample,
                candidate_output=output,
                reference_output=sample.ground_truth,
                config=ctx.gate_config.get("render_config", {}),
                cpu_executor=ctx.cpu_executor,
            )
            for attempt in range(3):
                try:
                    response = await ctx.llm_judge_client.messages.create(
                        model=ctx.llm_judge_config.model,
                        max_tokens=256,
                        messages=messages,
                    )
                    parsed = json.loads(response.content[0].text)
                    return {
                        "input": str(sample.input),
                        "output": str(output),
                        "score": float(parsed["score"]),
                        "reasoning": parsed.get("reasoning", ""),
                    }
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
        except Exception as e:
            logger.warning(f"Judge call failed for sample: {e}")
            return None
