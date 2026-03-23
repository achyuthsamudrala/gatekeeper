"""Tests for JSONL and CSV dataset loaders with real fixture files."""

from __future__ import annotations

import math
from pathlib import Path


from gatekeeper.dataset_formats.csv import CSVLoader
from gatekeeper.dataset_formats.jsonl import JSONLLoader
from gatekeeper.registries.dataset_format import Sample
from gatekeeper.registries.evaluator import DatasetConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _make_config(uri: str, fmt: str) -> DatasetConfig:
    return DatasetConfig(uri=uri, format=fmt)


# ── JSONL tests ──────────────────────────────────────────────────────────────


async def test_jsonl_loader_stream():
    """Load eval.jsonl with batch_size=3. Verify batch count and sample structure."""
    loader = JSONLLoader()
    config = _make_config(str(FIXTURES / "eval.jsonl"), "jsonl")
    batches = []
    async for batch in loader.stream(config.uri, config, batch_size=3):
        batches.append(batch)

    # 8 rows / batch_size 3 → ceil(8/3) = 3 batches  (3, 3, 2)
    assert len(batches) == math.ceil(8 / 3)
    total = sum(len(b) for b in batches)
    assert total == 8

    sample = batches[0][0]
    assert isinstance(sample, Sample)
    assert isinstance(sample.input, dict)
    assert isinstance(sample.ground_truth, str)


async def test_jsonl_loader_single_batch():
    """batch_size=100 should yield exactly one batch with all 8 rows."""
    loader = JSONLLoader()
    config = _make_config(str(FIXTURES / "eval.jsonl"), "jsonl")
    batches = []
    async for batch in loader.stream(config.uri, config, batch_size=100):
        batches.append(batch)

    assert len(batches) == 1
    assert len(batches[0]) == 8


# ── CSV tests ────────────────────────────────────────────────────────────────


async def test_csv_loader_stream():
    """Load eval.csv with batch_size=3. Verify batch count and sample structure."""
    loader = CSVLoader()
    config = _make_config(str(FIXTURES / "eval.csv"), "csv")
    batches = []
    async for batch in loader.stream(config.uri, config, batch_size=3):
        batches.append(batch)

    assert len(batches) == math.ceil(8 / 3)
    total = sum(len(b) for b in batches)
    assert total == 8

    sample = batches[0][0]
    assert isinstance(sample, Sample)
    assert isinstance(sample.input, dict)
    assert isinstance(sample.ground_truth, str)


async def test_csv_loader_ground_truth():
    """ground_truth is extracted from the row and removed from input dict."""
    loader = CSVLoader()
    config = _make_config(str(FIXTURES / "eval.csv"), "csv")
    all_samples: list[Sample] = []
    async for batch in loader.stream(config.uri, config, batch_size=100):
        all_samples.extend(batch)

    for sample in all_samples:
        # expected_output should be the ground_truth, not in input
        assert sample.ground_truth is not None
        assert "expected_output" not in sample.input
        # input should still contain the other columns
        assert "text" in sample.input
        assert "category" in sample.input


# ── Edge-case tests ──────────────────────────────────────────────────────────


async def test_jsonl_empty_lines_skipped(tmp_path: Path):
    """Blank lines interspersed in JSONL are silently skipped."""
    data = (
        '{"text": "a", "expected_output": "yes"}\n'
        "\n"
        '{"text": "b", "expected_output": "no"}\n'
        "\n"
        "\n"
        '{"text": "c", "expected_output": "maybe"}\n'
    )
    jsonl_file = tmp_path / "sparse.jsonl"
    jsonl_file.write_text(data)

    loader = JSONLLoader()
    config = _make_config(str(jsonl_file), "jsonl")
    all_samples: list[Sample] = []
    async for batch in loader.stream(config.uri, config, batch_size=100):
        all_samples.extend(batch)

    assert len(all_samples) == 3
