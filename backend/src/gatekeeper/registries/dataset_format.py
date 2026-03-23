"""Dataset format registry and base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatekeeper.registries.evaluator import DatasetConfig


@dataclass
class BinaryInput:
    format: str
    uri: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Sample:
    input: dict | BinaryInput
    ground_truth: dict | None = None
    metadata: dict = field(default_factory=dict)


class BaseDatasetLoader(ABC):
    @property
    @abstractmethod
    def format_name(self) -> str: ...

    @property
    def default_batch_size(self) -> int:
        return 256

    @abstractmethod
    async def stream(
        self,
        uri: str,
        config: DatasetConfig,
        batch_size: int,
    ) -> AsyncIterator[list[Sample]]:
        """Yields batches. Never loads full dataset into memory."""
        yield []  # type: ignore[misc]


class DatasetFormatRegistry:
    _registry: dict[str, BaseDatasetLoader] = {}

    @classmethod
    def register(cls, loader: BaseDatasetLoader) -> None:
        cls._registry[loader.format_name] = loader

    @classmethod
    def get(cls, name: str) -> BaseDatasetLoader:
        if name not in cls._registry:
            raise ValueError(
                f"Unknown dataset format '{name}'. "
                f"Registered: {list(cls._registry.keys())}. "
                f"Install a plugin to add custom dataset formats."
            )
        return cls._registry[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def all(cls) -> dict[str, BaseDatasetLoader]:
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
