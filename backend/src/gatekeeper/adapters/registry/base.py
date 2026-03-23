"""Base registry adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod

from gatekeeper.adapters.base_types import ModelVersion


class RegistryAdapter(ABC):
    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> tuple[bool, str]: ...

    @abstractmethod
    async def get_model_version(self, name: str, version: str) -> ModelVersion: ...

    @abstractmethod
    async def get_champion_version(self, name: str) -> ModelVersion | None: ...

    @abstractmethod
    async def set_champion(self, name: str, version: str) -> None: ...

    @abstractmethod
    async def download_artifact(self, artifact_uri: str, local_path: str) -> str:
        """Async download. Returns local path."""
