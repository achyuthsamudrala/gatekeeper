"""Tests for plugin registries."""

from __future__ import annotations

import pytest

from gatekeeper.registries.evaluator import EvaluatorRegistry
from gatekeeper.registries.model_type import ModelTypeRegistry
from gatekeeper.registries.dataset_format import DatasetFormatRegistry
from gatekeeper.registries.drift_method import DriftMethodRegistry
from gatekeeper.registries.inference_encoding import InferenceEncodingRegistry
from gatekeeper.registries.judge_modality import JudgeModalityRegistry
from gatekeeper.registries.loader import load_all_plugins


@pytest.fixture(autouse=True)
def clear_registries():
    """Clear all registries before each test."""
    EvaluatorRegistry.clear()
    ModelTypeRegistry.clear()
    DatasetFormatRegistry.clear()
    DriftMethodRegistry.clear()
    InferenceEncodingRegistry.clear()
    JudgeModalityRegistry.clear()
    yield


def test_load_all_plugins_discovers_builtins():
    """load_all_plugins() registers all built-in capabilities."""
    loaded = load_all_plugins()
    assert len(loaded) > 0


def test_evaluator_registry_has_all_builtins():
    load_all_plugins()
    assert EvaluatorRegistry.has("accuracy")
    assert EvaluatorRegistry.has("drift")
    assert EvaluatorRegistry.has("llm_judge")
    assert EvaluatorRegistry.has("champion_challenger")
    assert EvaluatorRegistry.has("latency")
    assert len(EvaluatorRegistry.all()) == 5


def test_model_type_registry_has_builtins():
    load_all_plugins()
    assert ModelTypeRegistry.has("llm")
    assert ModelTypeRegistry.has("pytorch")
    assert len(ModelTypeRegistry.all()) == 2


def test_dataset_format_registry_has_builtins():
    load_all_plugins()
    assert DatasetFormatRegistry.has("jsonl")
    assert DatasetFormatRegistry.has("parquet")
    assert DatasetFormatRegistry.has("csv")
    assert len(DatasetFormatRegistry.all()) == 3


def test_drift_method_registry_has_builtins():
    load_all_plugins()
    assert DriftMethodRegistry.has("psi")
    assert DriftMethodRegistry.has("ks")
    assert len(DriftMethodRegistry.all()) == 2


def test_inference_encoding_registry_has_builtin():
    load_all_plugins()
    assert InferenceEncodingRegistry.has("json")


def test_judge_modality_registry_has_builtin():
    load_all_plugins()
    assert JudgeModalityRegistry.has("text")


def test_evaluator_get_unknown_raises():
    with pytest.raises(ValueError, match="Unknown evaluator"):
        EvaluatorRegistry.get("nonexistent")


def test_model_type_get_unknown_raises():
    with pytest.raises(ValueError, match="Unknown model_type"):
        ModelTypeRegistry.get("nonexistent")


def test_evaluator_phases_correct():
    load_all_plugins()
    assert EvaluatorRegistry.get("accuracy").phase == "offline"
    assert EvaluatorRegistry.get("drift").phase == "offline"
    assert EvaluatorRegistry.get("llm_judge").phase == "offline"
    assert EvaluatorRegistry.get("champion_challenger").phase == "offline"
    assert EvaluatorRegistry.get("latency").phase == "online"


def test_evaluator_supported_model_types():
    load_all_plugins()
    for name in ["accuracy", "drift", "llm_judge", "champion_challenger", "latency"]:
        ev = EvaluatorRegistry.get(name)
        assert "*" in ev.supported_model_types


def test_model_type_inference_modes():
    load_all_plugins()
    assert ModelTypeRegistry.get("llm").inference_mode == "sequential_http"
    assert ModelTypeRegistry.get("pytorch").inference_mode == "local_artifact"
