"""No-op registry adapter."""

from __future__ import annotations

from gatekeeper.adapters.base_types import ModelVersion
from gatekeeper.adapters.registry.base import RegistryAdapter


class NoneRegistryAdapter(RegistryAdapter):
    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> tuple[bool, str]:
        return True, "no registry configured"

    async def get_model_version(self, name: str, version: str) -> ModelVersion:
        return ModelVersion(name=name, version=version, model_type="unknown")

    async def get_champion_version(self, name: str) -> ModelVersion | None:
        return None

    async def set_champion(self, name: str, version: str) -> None:
        pass

    async def download_artifact(self, artifact_uri: str, local_path: str) -> str:
        return local_path
