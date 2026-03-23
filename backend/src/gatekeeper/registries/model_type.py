"""ModelType registry."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelTypeDefinition:
    name: str
    inference_mode: str  # 'local_artifact' | 'sequential_http'
    supported_input_formats: list[str] = field(default_factory=list)
    supported_output_formats: list[str] = field(default_factory=list)
    compatible_evaluators: list[str] = field(default_factory=list)
    artifact_loader: type | None = None
    description: str = ""


class ModelTypeRegistry:
    _registry: dict[str, ModelTypeDefinition] = {}

    @classmethod
    def register(cls, definition: ModelTypeDefinition) -> None:
        cls._registry[definition.name] = definition

    @classmethod
    def get(cls, name: str) -> ModelTypeDefinition:
        if name not in cls._registry:
            raise ValueError(
                f"Unknown model_type '{name}'. "
                f"Registered: {list(cls._registry.keys())}. "
                f"Install a plugin to add support for this model type."
            )
        return cls._registry[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def all(cls) -> dict[str, ModelTypeDefinition]:
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
