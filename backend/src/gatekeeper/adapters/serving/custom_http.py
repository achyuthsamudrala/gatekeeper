"""Custom HTTP serving adapter (stub)."""

from __future__ import annotations

from gatekeeper.adapters.serving.openai_compatible import OpenAICompatibleAdapter


class CustomHTTPAdapter(OpenAICompatibleAdapter):
    """Custom HTTP adapter. Extends OpenAI adapter with encoding support."""

    pass
