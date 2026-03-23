"""Canary proxy serving adapter."""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse
from gatekeeper.adapters.serving.base import ServingAdapter

logger = logging.getLogger(__name__)


class ProxyServingAdapter(ServingAdapter):
    """Routes traffic between champion and challenger based on traffic split."""

    def __init__(self, champion_url: str, challenger_url: str, auth_token: str | None = None):
        self.champion_url = champion_url
        self.challenger_url = challenger_url
        self.auth_token = auth_token
        self._client: httpx.AsyncClient | None = None
        self._traffic_split: dict[str, float] = {"champion": 1.0}

    async def startup(self) -> None:
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers=headers,
        )

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()

    async def health_check(self) -> tuple[bool, str]:
        return True, "proxy adapter"

    async def predict(self, request: PredictionRequest) -> PredictionResponse:
        assert self._client is not None, "Adapter not started"
        challenger_weight = self._traffic_split.get("challenger", 0.0)
        role = "challenger" if random.random() < challenger_weight else "champion"
        url = self.challenger_url if role == "challenger" else self.champion_url

        start = asyncio.get_event_loop().time()
        try:
            payload = {"messages": [{"role": "user", "content": str(request.inputs)}]}
            resp = await self._client.post(f"{url}/v1/chat/completions", json=payload)
            elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
            return PredictionResponse(
                model_role=role,
                latency_ms=elapsed_ms,
                status_code=resp.status_code,
                outputs=[resp.json()] if resp.status_code == 200 else None,
                error=resp.text if resp.status_code != 200 else None,
            )
        except Exception as e:
            elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
            return PredictionResponse(
                model_role=role,
                latency_ms=elapsed_ms,
                status_code=500,
                error=str(e),
            )

    async def wait_for_ready(
        self, role: str, timeout_seconds: int, interval_seconds: int = 10
    ) -> None:
        pass

    async def set_traffic_split(self, weights: dict[str, float]) -> None:
        self._traffic_split = weights

    async def get_traffic_split(self) -> dict[str, float]:
        return dict(self._traffic_split)
