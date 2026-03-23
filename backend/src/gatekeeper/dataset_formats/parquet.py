"""Parquet dataset loader (stub)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from gatekeeper.registries.dataset_format import BaseDatasetLoader, Sample
from gatekeeper.registries.evaluator import DatasetConfig


class ParquetLoader(BaseDatasetLoader):
    @property
    def format_name(self) -> str:
        return "parquet"

    async def stream(
        self,
        uri: str,
        config: DatasetConfig,
        batch_size: int,
    ) -> AsyncIterator[list[Sample]]:
        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(None, _read_parquet_sync, uri, config)
        for i in range(0, len(rows), batch_size):
            yield rows[i : i + batch_size]


def _read_parquet_sync(uri: str, config: DatasetConfig) -> list[Sample]:
    try:
        import pandas as pd

        df = pd.read_parquet(uri)
        samples = []
        label_col = config.label_column or "expected_output"
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            ground_truth = row_dict.pop(label_col, None)
            samples.append(Sample(input=row_dict, ground_truth=ground_truth))
        return samples
    except ImportError:
        return []
