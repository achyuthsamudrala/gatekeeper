"""Kolmogorov-Smirnov drift method."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from gatekeeper.registries.dataset_format import BaseDatasetLoader
from gatekeeper.registries.drift_method import BaseDriftMethod, DriftResult
from gatekeeper.registries.evaluator import DatasetConfig


class KSDriftMethod(BaseDriftMethod):
    @property
    def name(self) -> str:
        return "ks"

    @property
    def primary_metric(self) -> str:
        return "max_ks_statistic"

    async def compute(
        self,
        reference_config: DatasetConfig,
        current_config: DatasetConfig,
        reference_loader: BaseDatasetLoader,
        current_loader: BaseDatasetLoader,
        config: dict,
        cpu_executor: ThreadPoolExecutor,
    ) -> DriftResult:
        import asyncio

        ref_samples = []
        async for batch in reference_loader.stream(
            reference_config.uri,
            reference_config,
            batch_size=256,
        ):
            ref_samples.extend(batch)

        cur_samples = []
        async for batch in current_loader.stream(
            current_config.uri,
            current_config,
            batch_size=256,
        ):
            cur_samples.extend(batch)

        feature_columns = config.get("feature_columns") or (reference_config.feature_columns or [])

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            cpu_executor,
            _compute_ks_sync,
            ref_samples,
            cur_samples,
            feature_columns,
        )


def _compute_ks_sync(ref_samples, cur_samples, feature_columns) -> DriftResult:
    from scipy import stats

    ks_scores = {}
    for col in feature_columns:
        ref_vals = [float(s.input.get(col, 0)) for s in ref_samples if isinstance(s.input, dict)]
        cur_vals = [float(s.input.get(col, 0)) for s in cur_samples if isinstance(s.input, dict)]
        if not ref_vals or not cur_vals:
            ks_scores[col] = 0.0
            continue
        stat, _ = stats.ks_2samp(ref_vals, cur_vals)
        ks_scores[col] = float(stat)

    max_ks = max(ks_scores.values()) if ks_scores else 0.0
    return DriftResult(
        primary_metric_name="max_ks_statistic",
        primary_metric_value=max_ks,
        detail={"ks_per_feature": ks_scores},
    )
