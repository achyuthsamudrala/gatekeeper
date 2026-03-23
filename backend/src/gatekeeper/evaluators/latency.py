"""Latency evaluator (online)."""

from __future__ import annotations

import asyncio

from gatekeeper.adapters.base_types import PredictionRequest
from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext


class LatencyEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "latency"

    @property
    def phase(self) -> str:
        return "online"

    @property
    def supported_model_types(self) -> list[str]:
        return ["*"]

    @property
    def primary_metric(self) -> str:
        return "p95_latency_ms"

    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        try:
            num_warmup = context.gate_config.get("num_warmup_requests", 5)
            num_benchmark = context.gate_config.get("num_benchmark_requests", 50)

            sample_inputs = []
            async for batch in context.dataset_loader.stream(
                context.eval_dataset_config.uri,
                context.eval_dataset_config,
                batch_size=num_warmup + num_benchmark,
            ):
                sample_inputs.extend(batch)
                break
            sample_inputs = sample_inputs[: num_warmup + num_benchmark]

            requests = [
                PredictionRequest(
                    inputs=[{"text": str(s.input)}],
                    model_role="challenger",
                )
                for s in sample_inputs
            ]

            # Warmup
            for req in requests[:num_warmup]:
                await context.serving_adapter.predict(req)

            # Benchmark with semaphore
            benchmark_requests = requests[num_warmup:]
            errors = 0
            semaphore = asyncio.Semaphore(10)

            async def _timed_predict(req: PredictionRequest) -> float | None:
                nonlocal errors
                async with semaphore:
                    start = asyncio.get_event_loop().time()
                    resp = await context.serving_adapter.predict(req)
                    elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
                    if resp.error:
                        errors += 1
                        return None
                    return elapsed_ms

            timed_results = await asyncio.gather(*[_timed_predict(r) for r in benchmark_requests])
            latencies = [r for r in timed_results if r is not None]

            stats = await asyncio.get_running_loop().run_in_executor(
                context.cpu_executor,
                _compute_latency_stats,
                latencies,
            )
            return EvalResult(
                gate_name=context.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=stats["p95"],
                passed=None,
                skip_reason=None,
                detail={**stats, "error_count": errors, "num_requests": num_benchmark},
            )
        except Exception as e:
            return EvalResult(
                gate_name=context.gate_config.get("name", "latency_gate"),
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                error=True,
                error_message=str(e),
            )


def _compute_latency_stats(latencies: list[float]) -> dict:
    """Synchronous — runs in thread pool."""
    if not latencies:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    import numpy as np

    arr = np.array(latencies)
    return {
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "mean": float(np.mean(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }
