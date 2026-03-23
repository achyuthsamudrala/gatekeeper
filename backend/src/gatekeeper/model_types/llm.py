"""LLM model type definition."""

from __future__ import annotations

from gatekeeper.registries.model_type import ModelTypeDefinition


class LLMModelType(ModelTypeDefinition):
    def __init__(self):
        super().__init__(
            name="llm",
            inference_mode="sequential_http",
            supported_input_formats=["jsonl", "csv"],
            supported_output_formats=["json"],
            compatible_evaluators=[
                "accuracy",
                "llm_judge",
                "drift",
                "champion_challenger",
                "latency",
            ],
            artifact_loader=None,
            description="Large language model served via HTTP endpoint",
        )
