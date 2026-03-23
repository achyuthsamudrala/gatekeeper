"""Inference encoding registry and base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx
    from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse


@dataclass
class EncodedRequest:
    method: str = "POST"
    headers: dict | None = None
    content: bytes | None = None
    json_body: dict | None = None


class BaseInferenceEncoding(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def encode_request(
        self,
        request: PredictionRequest,
        config: dict,
    ) -> EncodedRequest:
        """Serialise a PredictionRequest for HTTP transmission."""

    @abstractmethod
    async def decode_response(
        self,
        response: httpx.Response,
        config: dict,
    ) -> PredictionResponse:
        """Deserialise HTTP response into PredictionResponse."""


class InferenceEncodingRegistry:
    _registry: dict[str, BaseInferenceEncoding] = {}

    @classmethod
    def register(cls, encoding: BaseInferenceEncoding) -> None:
        cls._registry[encoding.name] = encoding

    @classmethod
    def get(cls, name: str) -> BaseInferenceEncoding:
        if name not in cls._registry:
            raise ValueError(
                f"Unknown inference encoding '{name}'. "
                f"Registered: {list(cls._registry.keys())}. "
                f"Install a plugin to add custom encodings."
            )
        return cls._registry[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def all(cls) -> dict[str, BaseInferenceEncoding]:
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
