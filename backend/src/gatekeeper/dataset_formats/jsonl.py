"""JSONL dataset loader."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import aiofiles

from gatekeeper.registries.dataset_format import BaseDatasetLoader, Sample
from gatekeeper.registries.evaluator import DatasetConfig


class JSONLLoader(BaseDatasetLoader):
    @property
    def format_name(self) -> str:
        return "jsonl"

    async def stream(
        self,
        uri: str,
        config: DatasetConfig,
        batch_size: int,
    ) -> AsyncIterator[list[Sample]]:
        batch: list[Sample] = []
        async with aiofiles.open(uri, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                label_col = config.label_column or "expected_output"
                ground_truth = row.pop(label_col, None)
                batch.append(
                    Sample(
                        input=row,
                        ground_truth=ground_truth,
                    )
                )
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
