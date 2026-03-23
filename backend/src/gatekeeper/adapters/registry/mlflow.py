"""MLflow registry adapter (stub — full implementation in later phase)."""

from __future__ import annotations

import httpx

from gatekeeper.adapters.base_types import ModelVersion
from gatekeeper.adapters.registry.base import RegistryAdapter


class MLflowRegistryAdapter(RegistryAdapter):
    def __init__(self, tracking_uri: str):
        self.tracking_uri = tracking_uri
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.tracking_uri,
            timeout=httpx.Timeout(30.0, connect=5.0),
        )

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()

    async def health_check(self) -> tuple[bool, str]:
        if not self._client:
            return False, "mlflow client not started"
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200, f"mlflow at {self.tracking_uri}"
        except Exception as e:
            return False, str(e)

    async def get_model_version(self, name: str, version: str) -> ModelVersion:
        assert self._client is not None, "Adapter not started"
        resp = await self._client.get(
            "/api/2.0/mlflow/model-versions/get-model-version",
            params={"name": name, "version": version},
        )
        resp.raise_for_status()
        data = resp.json().get("model_version", {})
        return ModelVersion(
            name=name,
            version=version,
            model_type=data.get("tags", {}).get("model_type", "unknown"),
            artifact_uri=data.get("source"),
        )

    async def get_champion_version(self, name: str) -> ModelVersion | None:
        assert self._client is not None, "Adapter not started"
        try:
            resp = await self._client.get(
                "/api/2.0/mlflow/registered-models/get",
                params={"name": name},
            )
            resp.raise_for_status()
            versions = resp.json().get("registered_model", {}).get("latest_versions", [])
            for v in versions:
                if v.get("current_stage") == "Production":
                    return ModelVersion(
                        name=name,
                        version=v["version"],
                        model_type=v.get("tags", {}).get("model_type", "unknown"),
                        artifact_uri=v.get("source"),
                        stage="Production",
                    )
        except Exception:
            pass
        return None

    async def set_champion(self, name: str, version: str) -> None:
        assert self._client is not None, "Adapter not started"
        await self._client.post(
            "/api/2.0/mlflow/model-versions/transition-stage",
            json={"name": name, "version": version, "stage": "Production"},
        )

    async def download_artifact(self, artifact_uri: str, local_path: str) -> str:
        # Simplified — real implementation would handle S3, GCS, etc.
        return artifact_uri
