"""Population Stability Index (PSI) drift method."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from gatekeeper.registries.dataset_format import BaseDatasetLoader
from gatekeeper.registries.drift_method import BaseDriftMethod, DriftResult
from gatekeeper.registries.evaluator import DatasetConfig


class PSIDriftMethod(BaseDriftMethod):
    @property
    def name(self) -> str:
        return "psi"

    @property
    def primary_metric(self) -> str:
        return "max_psi_score"

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
        result = await loop.run_in_executor(
            cpu_executor,
            _compute_psi_sync,
            ref_samples,
            cur_samples,
            feature_columns,
        )
        return result


def _compute_psi_sync(ref_samples, cur_samples, feature_columns) -> DriftResult:
    """Synchronous PSI computation — runs in thread pool."""
    import numpy as np

    psi_scores = {}
    for col in feature_columns:
        ref_vals = [float(s.input.get(col, 0)) for s in ref_samples if isinstance(s.input, dict)]
        cur_vals = [float(s.input.get(col, 0)) for s in cur_samples if isinstance(s.input, dict)]
        if not ref_vals or not cur_vals:
            psi_scores[col] = 0.0
            continue
        ref_arr = np.array(ref_vals)
        cur_arr = np.array(cur_vals)
        bins = np.histogram_bin_edges(ref_arr, bins=10)
        ref_hist = np.histogram(ref_arr, bins=bins)[0] / len(ref_arr)
        cur_hist = np.histogram(cur_arr, bins=bins)[0] / len(cur_arr)
        ref_hist = np.clip(ref_hist, 1e-6, None)
        cur_hist = np.clip(cur_hist, 1e-6, None)
        psi = np.sum((cur_hist - ref_hist) * np.log(cur_hist / ref_hist))
        psi_scores[col] = float(psi)

    max_psi = max(psi_scores.values()) if psi_scores else 0.0
    return DriftResult(
        primary_metric_name="max_psi_score",
        primary_metric_value=max_psi,
        detail={"psi_per_feature": psi_scores},
    )
