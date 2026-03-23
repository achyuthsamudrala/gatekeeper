"""Shared types for adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BinaryInput:
    """Reference to a binary file. URI, not inline bytes."""

    format: str
    uri: str
    metadata: dict = field(default_factory=dict)


@dataclass
class PredictionRequest:
    model_role: str = "champion"
    timeout_seconds: float = 30.0
    inputs: list[dict] | None = None
    binary_inputs: list[BinaryInput] | None = None


@dataclass
class PredictionResponse:
    model_role: str
    latency_ms: float
    status_code: int
    error: str | None = None
    outputs: list[dict] | None = None
    binary_outputs: list[BinaryInput] | None = None


@dataclass
class ModelVersion:
    name: str
    version: str
    model_type: str
    artifact_uri: str | None = None
    stage: str | None = None
    metadata: dict = field(default_factory=dict)
