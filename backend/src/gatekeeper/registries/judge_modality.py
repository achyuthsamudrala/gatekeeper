"""Judge modality registry and base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatekeeper.registries.dataset_format import BinaryInput, Sample


class BaseJudgeModality(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def build_judge_message(
        self,
        rubric: str,
        input_sample: Sample,
        candidate_output: dict | BinaryInput,
        reference_output: dict | BinaryInput | None,
        config: dict,
        cpu_executor: ThreadPoolExecutor,
    ) -> list[dict]:
        """Build the messages list for the judge API call."""


class JudgeModalityRegistry:
    _registry: dict[str, BaseJudgeModality] = {}

    @classmethod
    def register(cls, modality: BaseJudgeModality) -> None:
        cls._registry[modality.name] = modality

    @classmethod
    def get(cls, name: str) -> BaseJudgeModality:
        if name not in cls._registry:
            raise ValueError(
                f"Unknown judge modality '{name}'. "
                f"Registered: {list(cls._registry.keys())}. "
                f"Install a plugin to add custom modalities."
            )
        return cls._registry[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def all(cls) -> dict[str, BaseJudgeModality]:
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
