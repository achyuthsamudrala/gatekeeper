"""Local filesystem registry adapter."""

from __future__ import annotations


import aiofiles.os

from gatekeeper.adapters.base_types import ModelVersion
from gatekeeper.adapters.registry.base import RegistryAdapter


class LocalRegistryAdapter(RegistryAdapter):
    def __init__(self, base_path: str = "/models"):
        self.base_path = base_path

    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> tuple[bool, str]:
        exists = await aiofiles.os.path.exists(self.base_path)
        if exists:
            return True, f"local registry at {self.base_path}"
        return False, f"path {self.base_path} does not exist"

    async def get_model_version(self, name: str, version: str) -> ModelVersion:
        return ModelVersion(
            name=name,
            version=version,
            model_type="unknown",
            artifact_uri=f"{self.base_path}/{name}/{version}",
        )

    async def get_champion_version(self, name: str) -> ModelVersion | None:
        champion_path = f"{self.base_path}/{name}/champion"
        if await aiofiles.os.path.exists(champion_path):
            return ModelVersion(
                name=name,
                version="champion",
                model_type="unknown",
                artifact_uri=champion_path,
            )
        return None

    async def set_champion(self, name: str, version: str) -> None:
        pass

    async def download_artifact(self, artifact_uri: str, local_path: str) -> str:
        return artifact_uri
