"""TorchServe serving adapter (stub)."""

from __future__ import annotations

from gatekeeper.adapters.serving.openai_compatible import OpenAICompatibleAdapter


class TorchServeAdapter(OpenAICompatibleAdapter):
    """TorchServe uses a similar HTTP API pattern. Extends OpenAI adapter."""

    pass
