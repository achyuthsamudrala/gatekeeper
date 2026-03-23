"""PyTorch model type definition."""

from __future__ import annotations

from gatekeeper.registries.model_type import ModelTypeDefinition


class PyTorchModelType(ModelTypeDefinition):
    def __init__(self):
        super().__init__(
            name="pytorch",
            inference_mode="local_artifact",
            supported_input_formats=["jsonl", "csv", "parquet"],
            supported_output_formats=["json"],
            compatible_evaluators=["accuracy", "drift", "champion_challenger", "latency"],
            artifact_loader=None,
            description="PyTorch model loaded from artifact",
        )
