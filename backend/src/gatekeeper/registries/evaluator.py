"""Evaluator registry and base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatekeeper.registries.model_type import ModelTypeDefinition


@dataclass
class DatasetConfig:
    uri: str
    format: str | None = None
    label_column: str | None = None
    task_type: str | None = None
    feature_columns: list[str] | None = None
    categorical_columns: list[str] | None = None


@dataclass
class LLMJudgeConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""


@dataclass
class EvaluationContext:
    run_id: str
    model_name: str
    candidate_version: str
    model_type: ModelTypeDefinition
    runner: object | None  # OfflineInferenceRunner | None
    serving_adapter: object | None  # ServingAdapter | None
    registry_adapter: object  # RegistryAdapter
    dataset_loader: object  # BaseDatasetLoader
    eval_dataset_config: DatasetConfig
    reference_dataset_config: DatasetConfig | None = None
    llm_judge_config: LLMJudgeConfig | None = None
    llm_judge_client: object | None = None
    gate_config: dict = field(default_factory=dict)
    cpu_executor: ThreadPoolExecutor | None = None


@dataclass
class EvalResult:
    gate_name: str
    evaluator_name: str
    phase: str
    metric_name: str
    metric_value: float | None
    passed: bool | None  # None = skipped
    skip_reason: str | None = None
    error: bool = False
    error_message: str | None = None
    detail: dict = field(default_factory=dict)

    def to_db_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "gate_type": self.evaluator_name,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "passed": self.passed,
            "skip_reason": self.skip_reason,
            "detail": {
                **(self.detail or {}),
                **({"error": True, "error_message": self.error_message} if self.error else {}),
            },
        }


class BaseEvaluator(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def phase(self) -> str:
        """'offline' or 'online'"""

    @property
    @abstractmethod
    def supported_model_types(self) -> list[str]:
        """['*'] for all types"""

    @property
    @abstractmethod
    def primary_metric(self) -> str: ...

    @abstractmethod
    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        """
        Always async. Never raises — catches exceptions and returns
        EvalResult with error=True and error_message set.
        CPU-bound work must be wrapped in run_in_executor().
        """


class EvaluatorRegistry:
    _registry: dict[str, BaseEvaluator] = {}

    @classmethod
    def register(cls, evaluator: BaseEvaluator) -> None:
        cls._registry[evaluator.name] = evaluator

    @classmethod
    def get(cls, name: str) -> BaseEvaluator:
        if name not in cls._registry:
            raise ValueError(
                f"Unknown evaluator '{name}'. "
                f"Registered: {list(cls._registry.keys())}. "
                f"Install a plugin to add custom evaluators."
            )
        return cls._registry[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def all(cls) -> dict[str, BaseEvaluator]:
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
