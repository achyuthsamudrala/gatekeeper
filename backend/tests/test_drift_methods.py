"""Tests for PSI and KS drift methods with known distributions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from gatekeeper.drift_methods.ks import KSDriftMethod
from gatekeeper.drift_methods.psi import PSIDriftMethod
from gatekeeper.registries.dataset_format import Sample
from gatekeeper.registries.drift_method import DriftResult
from gatekeeper.registries.evaluator import DatasetConfig


# ── In-memory loader ─────────────────────────────────────────────────────────


class InMemoryLoader:
    """Minimal loader that yields pre-built samples in a single batch."""

    def __init__(self, samples: list[Sample]):
        self.samples = samples

    @property
    def format_name(self):
        return "memory"

    async def stream(self, uri, config, batch_size):
        yield self.samples


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_samples(feature_a: np.ndarray, feature_b: np.ndarray) -> list[Sample]:
    return [
        Sample(input={"feature_a": float(a), "feature_b": float(b)}, ground_truth=None)
        for a, b in zip(feature_a, feature_b)
    ]


def _config() -> DatasetConfig:
    return DatasetConfig(uri="memory://data", feature_columns=["feature_a", "feature_b"])


def _drift_config() -> dict:
    return {"feature_columns": ["feature_a", "feature_b"]}


# ── PSI tests ────────────────────────────────────────────────────────────────


async def test_psi_identical_distributions():
    """Same data for ref and current should produce PSI close to 0."""
    rng = np.random.default_rng(42)
    vals_a = rng.normal(0, 1, 100)
    vals_b = rng.normal(5, 2, 100)
    samples = _make_samples(vals_a, vals_b)

    ref_loader = InMemoryLoader(samples)
    cur_loader = InMemoryLoader(samples)

    psi = PSIDriftMethod()
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = await psi.compute(
            _config(), _config(), ref_loader, cur_loader, _drift_config(), executor
        )

    assert isinstance(result, DriftResult)
    assert result.primary_metric_value == pytest.approx(0.0, abs=1e-6)


async def test_psi_shifted_distribution():
    """Significantly shifted current data should produce PSI > 0.1."""
    rng = np.random.default_rng(42)
    ref_a = rng.normal(0, 1, 100)
    ref_b = rng.normal(5, 2, 100)
    # Shift the mean substantially
    cur_a = rng.normal(5, 1, 100)
    cur_b = rng.normal(15, 2, 100)

    ref_loader = InMemoryLoader(_make_samples(ref_a, ref_b))
    cur_loader = InMemoryLoader(_make_samples(cur_a, cur_b))

    psi = PSIDriftMethod()
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = await psi.compute(
            _config(), _config(), ref_loader, cur_loader, _drift_config(), executor
        )

    assert result.primary_metric_value > 0.1


async def test_psi_empty_features():
    """No feature_columns in config should produce PSI = 0.0."""
    rng = np.random.default_rng(42)
    samples = _make_samples(rng.normal(0, 1, 50), rng.normal(0, 1, 50))

    ref_loader = InMemoryLoader(samples)
    cur_loader = InMemoryLoader(samples)

    psi = PSIDriftMethod()
    empty_config = DatasetConfig(uri="memory://data")
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = await psi.compute(empty_config, empty_config, ref_loader, cur_loader, {}, executor)

    assert result.primary_metric_value == 0.0


# ── KS tests ────────────────────────────────────────────────────────────────


async def test_ks_identical_distributions():
    """Same data for ref and current should produce KS close to 0."""
    rng = np.random.default_rng(42)
    vals_a = rng.normal(0, 1, 100)
    vals_b = rng.normal(5, 2, 100)
    samples = _make_samples(vals_a, vals_b)

    ref_loader = InMemoryLoader(samples)
    cur_loader = InMemoryLoader(samples)

    ks = KSDriftMethod()
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = await ks.compute(
            _config(), _config(), ref_loader, cur_loader, _drift_config(), executor
        )

    assert isinstance(result, DriftResult)
    assert result.primary_metric_value == pytest.approx(0.0, abs=1e-6)


async def test_ks_different_distributions():
    """Very different distributions should produce KS close to 1.0."""
    rng = np.random.default_rng(42)
    ref_a = rng.normal(-100, 0.01, 100)
    ref_b = rng.normal(-100, 0.01, 100)
    cur_a = rng.normal(100, 0.01, 100)
    cur_b = rng.normal(100, 0.01, 100)

    ref_loader = InMemoryLoader(_make_samples(ref_a, ref_b))
    cur_loader = InMemoryLoader(_make_samples(cur_a, cur_b))

    ks = KSDriftMethod()
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = await ks.compute(
            _config(), _config(), ref_loader, cur_loader, _drift_config(), executor
        )

    assert result.primary_metric_value > 0.9


async def test_ks_returns_drift_result():
    """Verify return type is DriftResult with correct metric name."""
    rng = np.random.default_rng(42)
    samples = _make_samples(rng.normal(0, 1, 50), rng.normal(0, 1, 50))

    ref_loader = InMemoryLoader(samples)
    cur_loader = InMemoryLoader(samples)

    ks = KSDriftMethod()
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = await ks.compute(
            _config(), _config(), ref_loader, cur_loader, _drift_config(), executor
        )

    assert isinstance(result, DriftResult)
    assert result.primary_metric_name == "max_ks_statistic"
    assert "ks_per_feature" in result.detail
    assert "feature_a" in result.detail["ks_per_feature"]
    assert "feature_b" in result.detail["ks_per_feature"]
