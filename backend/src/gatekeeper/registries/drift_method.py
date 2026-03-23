"""Drift method registry and base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatekeeper.registries.dataset_format import BaseDatasetLoader
    from gatekeeper.registries.evaluator import DatasetConfig


@dataclass
class DriftResult:
    primary_metric_name: str
    primary_metric_value: float
    detail: dict = field(default_factory=dict)


class BaseDriftMethod(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def primary_metric(self) -> str: ...

    @abstractmethod
    async def compute(
        self,
        reference_config: DatasetConfig,
        current_config: DatasetConfig,
        reference_loader: BaseDatasetLoader,
        current_loader: BaseDatasetLoader,
        config: dict,
        cpu_executor: ThreadPoolExecutor,
    ) -> DriftResult:
        """Async. CPU-bound statistical computation must use cpu_executor."""


class DriftMethodRegistry:
    _registry: dict[str, BaseDriftMethod] = {}

    @classmethod
    def register(cls, method: BaseDriftMethod) -> None:
        cls._registry[method.name] = method

    @classmethod
    def get(cls, name: str) -> BaseDriftMethod:
        if name not in cls._registry:
            raise ValueError(
                f"Unknown drift method '{name}'. "
                f"Registered: {list(cls._registry.keys())}. "
                f"Install a plugin to add custom drift methods."
            )
        return cls._registry[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def all(cls) -> dict[str, BaseDriftMethod]:
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
