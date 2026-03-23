"""Accuracy evaluator."""

from __future__ import annotations

from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext


class AccuracyEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "accuracy"

    @property
    def phase(self) -> str:
        return "offline"

    @property
    def supported_model_types(self) -> list[str]:
        return ["*"]

    @property
    def primary_metric(self) -> str:
        return "f1_weighted"

    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        try:
            all_predictions, all_ground_truth = [], []
            async for batch in context.dataset_loader.stream(
                context.eval_dataset_config.uri,
                context.eval_dataset_config,
                batch_size=context.dataset_loader.default_batch_size,
            ):
                outputs = await context.runner.run(
                    context.model_name,
                    context.candidate_version,
                    batch,
                )
                all_predictions.extend(outputs)
                all_ground_truth.extend([s.ground_truth for s in batch])

            import asyncio

            metrics = await asyncio.get_running_loop().run_in_executor(
                context.cpu_executor,
                _compute_classification_metrics,
                all_ground_truth,
                all_predictions,
            )
            return EvalResult(
                gate_name=context.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=metrics["f1_weighted"],
                passed=None,
                skip_reason=None,
                detail=metrics,
            )
        except Exception as e:
            return EvalResult(
                gate_name=context.gate_config.get("name", "accuracy_gate"),
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                error=True,
                error_message=str(e),
            )


def _compute_classification_metrics(ground_truth: list, predictions: list) -> dict:
    """Synchronous sklearn work — safe to call from thread pool."""
    try:
        from sklearn.metrics import accuracy_score, f1_score

        y_true = [str(g) for g in ground_truth]
        y_pred = [str(p.get("text", p) if isinstance(p, dict) else p) for p in predictions]
        return {
            "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
            "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
            "accuracy": accuracy_score(y_true, y_pred),
        }
    except ImportError:
        return {"f1_weighted": 0.0, "f1_macro": 0.0, "accuracy": 0.0}
