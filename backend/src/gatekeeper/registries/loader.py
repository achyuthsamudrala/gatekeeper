"""Plugin loader using importlib.metadata entry points."""

from __future__ import annotations

import logging

import importlib.metadata

from gatekeeper.registries.dataset_format import DatasetFormatRegistry
from gatekeeper.registries.drift_method import DriftMethodRegistry
from gatekeeper.registries.evaluator import EvaluatorRegistry
from gatekeeper.registries.inference_encoding import InferenceEncodingRegistry
from gatekeeper.registries.judge_modality import JudgeModalityRegistry
from gatekeeper.registries.model_type import ModelTypeRegistry

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUPS = {
    "gatekeeper.evaluators": EvaluatorRegistry,
    "gatekeeper.model_types": ModelTypeRegistry,
    "gatekeeper.dataset_formats": DatasetFormatRegistry,
    "gatekeeper.drift_methods": DriftMethodRegistry,
    "gatekeeper.inference_encodings": InferenceEncodingRegistry,
    "gatekeeper.judge_modalities": JudgeModalityRegistry,
}


def load_all_plugins() -> dict[str, list[str]]:
    """
    Discovers all installed packages that declare gatekeeper.*
    entry points. Registers each into the appropriate registry.
    Returns dict of package_name -> registered capability names.
    """
    loaded: dict[str, list[str]] = {}

    for group, registry in ENTRY_POINT_GROUPS.items():
        for ep in importlib.metadata.entry_points(group=group):
            try:
                plugin_class = ep.load()
                instance = plugin_class()
                # ModelTypeRegistry takes ModelTypeDefinition, not instances with .name
                if group == "gatekeeper.model_types":
                    registry.register(instance)
                else:
                    registry.register(instance)
                package = ep.dist.name if ep.dist else "unknown"
                cap_type = group.split(".")[-1]
                cap_name = getattr(instance, "name", getattr(instance, "format_name", ep.name))
                loaded.setdefault(package, []).append(f"{cap_type}:{cap_name}")
            except Exception as e:
                logger.warning(
                    f"Failed to load plugin entry point '{ep.name}' from group '{group}': {e}"
                )

    return loaded
