"""CSV dataset loader."""

from __future__ import annotations

import csv as csv_mod
import io
from collections.abc import AsyncIterator

import aiofiles

from gatekeeper.registries.dataset_format import BaseDatasetLoader, Sample
from gatekeeper.registries.evaluator import DatasetConfig


class CSVLoader(BaseDatasetLoader):
    @property
    def format_name(self) -> str:
        return "csv"

    async def stream(
        self,
        uri: str,
        config: DatasetConfig,
        batch_size: int,
    ) -> AsyncIterator[list[Sample]]:
        async with aiofiles.open(uri, "r") as f:
            content = await f.read()
        reader = csv_mod.DictReader(io.StringIO(content))
        batch: list[Sample] = []
        label_col = config.label_column or "expected_output"
        for row in reader:
            ground_truth = row.pop(label_col, None)
            batch.append(Sample(input=dict(row), ground_truth=ground_truth))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
