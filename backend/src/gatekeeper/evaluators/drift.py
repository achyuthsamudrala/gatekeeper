"""Drift evaluator."""

from __future__ import annotations

from gatekeeper.registries.dataset_format import DatasetFormatRegistry
from gatekeeper.registries.drift_method import DriftMethodRegistry
from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext


def _infer_format(uri: str) -> str:
    if uri.endswith(".parquet"):
        return "parquet"
    if uri.endswith(".csv"):
        return "csv"
    return "jsonl"


class DriftEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "drift"

    @property
    def phase(self) -> str:
        return "offline"

    @property
    def supported_model_types(self) -> list[str]:
        return ["*"]

    @property
    def primary_metric(self) -> str:
        return "max_psi_score"

    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        if context.reference_dataset_config is None:
            return EvalResult(
                gate_name=context.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                skip_reason="reference_dataset not configured",
            )
        try:
            drift_method_name = context.gate_config.get("drift_method", "psi")
            drift_method = DriftMethodRegistry.get(drift_method_name)

            ref_format = context.reference_dataset_config.format or _infer_format(
                context.reference_dataset_config.uri
            )
            ref_loader = DatasetFormatRegistry.get(ref_format)

            result = await drift_method.compute(
                reference_config=context.reference_dataset_config,
                current_config=context.eval_dataset_config,
                reference_loader=ref_loader,
                current_loader=context.dataset_loader,
                config=context.gate_config,
                cpu_executor=context.cpu_executor,
            )
            return EvalResult(
                gate_name=context.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=result.primary_metric_name,
                metric_value=result.primary_metric_value,
                passed=None,
                skip_reason=None,
                detail=result.detail,
            )
        except Exception as e:
            return EvalResult(
                gate_name=context.gate_config.get("name", "drift_gate"),
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                error=True,
                error_message=str(e),
            )
