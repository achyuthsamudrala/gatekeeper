"""Plugin registries."""

from gatekeeper.registries.dataset_format import BaseDatasetLoader, DatasetFormatRegistry, Sample
from gatekeeper.registries.drift_method import BaseDriftMethod, DriftMethodRegistry
from gatekeeper.registries.evaluator import (
    BaseEvaluator,
    DatasetConfig,
    EvalResult,
    EvaluationContext,
    EvaluatorRegistry,
)
from gatekeeper.registries.inference_encoding import (
    BaseInferenceEncoding,
    InferenceEncodingRegistry,
)
from gatekeeper.registries.judge_modality import BaseJudgeModality, JudgeModalityRegistry
from gatekeeper.registries.loader import load_all_plugins
from gatekeeper.registries.model_type import ModelTypeDefinition, ModelTypeRegistry

__all__ = [
    "BaseDatasetLoader",
    "BaseDriftMethod",
    "BaseEvaluator",
    "BaseInferenceEncoding",
    "BaseJudgeModality",
    "DatasetConfig",
    "DatasetFormatRegistry",
    "DriftMethodRegistry",
    "EvalResult",
    "EvaluationContext",
    "EvaluatorRegistry",
    "InferenceEncodingRegistry",
    "JudgeModalityRegistry",
    "ModelTypeDefinition",
    "ModelTypeRegistry",
    "Sample",
    "load_all_plugins",
]
