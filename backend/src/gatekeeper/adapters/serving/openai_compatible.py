"""OpenAI-compatible serving adapter."""

from __future__ import annotations

import asyncio
import logging

import httpx

from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse
from gatekeeper.adapters.serving.base import ServingAdapter

logger = logging.getLogger(__name__)


class OpenAICompatibleAdapter(ServingAdapter):
    def __init__(
        self,
        champion_url: str,
        challenger_url: str,
        auth_token: str | None = None,
        auth_type: str = "none",
        ready_check_path: str = "/health",
        ready_check_timeout: int = 120,
        ready_check_interval: int = 10,
    ):
        self.champion_url = champion_url
        self.challenger_url = challenger_url
        self.auth_token = auth_token
        self.auth_type = auth_type
        self.ready_check_path = ready_check_path
        self.ready_check_timeout = ready_check_timeout
        self.ready_check_interval = ready_check_interval
        self._client: httpx.AsyncClient | None = None
        self._traffic_split: dict[str, float] = {"champion": 1.0}

    def _auth_headers(self) -> dict[str, str]:
        if self.auth_type == "bearer" and self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        if self.auth_type == "api_key" and self.auth_token:
            return {"X-API-Key": self.auth_token}
        return {}

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers=self._auth_headers(),
        )

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()

    async def health_check(self) -> tuple[bool, str]:
        if not self._client:
            return False, "serving client not started"
        try:
            resp = await self._client.get(f"{self.champion_url}{self.ready_check_path}")
            return resp.status_code == 200, f"openai_compatible at {self.champion_url}"
        except Exception as e:
            return False, str(e)

    async def predict(self, request: PredictionRequest) -> PredictionResponse:
        assert self._client is not None, "Adapter not started"
        url = self.challenger_url if request.model_role == "challenger" else self.champion_url
        start = asyncio.get_event_loop().time()
        try:
            payload = {"messages": [{"role": "user", "content": str(request.inputs)}]}
            resp = await self._client.post(f"{url}/v1/chat/completions", json=payload)
            elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
            if resp.status_code != 200:
                return PredictionResponse(
                    model_role=request.model_role,
                    latency_ms=elapsed_ms,
                    status_code=resp.status_code,
                    error=resp.text,
                )
            return PredictionResponse(
                model_role=request.model_role,
                latency_ms=elapsed_ms,
                status_code=200,
                outputs=[resp.json()],
            )
        except Exception as e:
            elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
            return PredictionResponse(
                model_role=request.model_role,
                latency_ms=elapsed_ms,
                status_code=500,
                error=str(e),
            )

    async def wait_for_ready(
        self, role: str, timeout_seconds: int, interval_seconds: int = 10
    ) -> None:
        assert self._client is not None, "Adapter not started"
        url = self.challenger_url if role == "challenger" else self.champion_url
        elapsed = 0
        while elapsed < timeout_seconds:
            try:
                resp = await self._client.get(f"{url}{self.ready_check_path}")
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)
            elapsed += interval_seconds
        raise asyncio.TimeoutError(f"{role} not ready after {timeout_seconds}s")

    async def set_traffic_split(self, weights: dict[str, float]) -> None:
        self._traffic_split = weights

    async def get_traffic_split(self) -> dict[str, float]:
        return dict(self._traffic_split)
