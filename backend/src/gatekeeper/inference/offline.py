"""Offline inference runner."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx

from gatekeeper.adapters.registry.base import RegistryAdapter
from gatekeeper.registries.dataset_format import Sample
from gatekeeper.registries.model_type import ModelTypeRegistry


class OfflineInferenceRunner:
    """Drives offline model inference. Fully async.
    Shares a single httpx.AsyncClient for the lifetime of the runner."""

    def __init__(
        self,
        registry_adapter: RegistryAdapter,
        server_config: dict,
        cpu_executor: ThreadPoolExecutor,
    ):
        self.registry_adapter = registry_adapter
        self.server_config = server_config
        self.cpu_executor = cpu_executor
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init shared client. Created once, reused across calls."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._client

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def run(
        self,
        model_name: str,
        version: str,
        samples: list[Sample],
        role: str = "challenger",
    ) -> list[dict]:
        model_version = await self.registry_adapter.get_model_version(model_name, version)
        model_type_def = ModelTypeRegistry.get(model_version.model_type)

        if model_type_def.inference_mode == "local_artifact":
            return await self._run_local(model_name, version, samples, model_type_def)
        return await self._run_remote_sequential(samples, role)

    async def _run_local(self, name, version, samples, model_type_def) -> list[dict]:
        artifact_path = await self.registry_adapter.download_artifact(
            (await self.registry_adapter.get_model_version(name, version)).artifact_uri or "",
            local_path=f"/tmp/gatekeeper/{name}/{version}",
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.cpu_executor,
            self._load_and_infer_sync,
            artifact_path,
            samples,
            model_type_def,
        )

    def _load_and_infer_sync(self, artifact_path, samples, model_type_def) -> list[dict]:
        """Synchronous — runs in thread pool."""
        if model_type_def.artifact_loader:
            loader = model_type_def.artifact_loader()
            model = loader.load(artifact_path)
            return loader.predict(model, samples)
        return [{"text": "no artifact loader"} for _ in samples]

    async def _run_remote_sequential(self, samples, role) -> list[dict]:
        """Sequential async HTTP calls using shared client."""
        serving = self.server_config.get("serving", {})
        url = (
            serving.get("challenger_url", "")
            if role == "challenger"
            else serving.get("champion_url", "")
        )
        client = await self._get_client()
        results = []
        for sample in samples:
            try:
                response = await client.post(
                    f"{url}/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": str(sample.input)}]},
                )
                results.append(response.json())
            except Exception as e:
                results.append({"error": str(e)})
        return results
