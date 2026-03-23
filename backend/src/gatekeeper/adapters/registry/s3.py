"""S3 registry adapter (stub)."""

from __future__ import annotations

from gatekeeper.adapters.base_types import ModelVersion
from gatekeeper.adapters.registry.base import RegistryAdapter


class S3RegistryAdapter(RegistryAdapter):
    def __init__(self, bucket: str = "", prefix: str = ""):
        self.bucket = bucket
        self.prefix = prefix

    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> tuple[bool, str]:
        return True, f"s3://{self.bucket}/{self.prefix}"

    async def get_model_version(self, name: str, version: str) -> ModelVersion:
        return ModelVersion(
            name=name,
            version=version,
            model_type="unknown",
            artifact_uri=f"s3://{self.bucket}/{self.prefix}/{name}/{version}",
        )

    async def get_champion_version(self, name: str) -> ModelVersion | None:
        return None

    async def set_champion(self, name: str, version: str) -> None:
        pass

    async def download_artifact(self, artifact_uri: str, local_path: str) -> str:
        return local_path
