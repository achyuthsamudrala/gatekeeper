"""CSV dataset loader — streams line-by-line, never loads full file."""

from __future__ import annotations

import csv as csv_mod
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
        label_col = config.label_column or "expected_output"
        headers: list[str] | None = None
        batch: list[Sample] = []

        async with aiofiles.open(uri, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                if headers is None:
                    # First line is the header row
                    headers = next(csv_mod.reader([line]))
                    continue
                values = next(csv_mod.reader([line]))
                row = dict(zip(headers, values))
                ground_truth = row.pop(label_col, None)
                batch.append(Sample(input=row, ground_truth=ground_truth))
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
