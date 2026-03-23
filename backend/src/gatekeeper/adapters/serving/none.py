"""No-op serving adapter."""

from __future__ import annotations

from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse
from gatekeeper.adapters.serving.base import ServingAdapter


class NoneServingAdapter(ServingAdapter):
    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> tuple[bool, str]:
        return True, "no serving configured"

    async def predict(self, request: PredictionRequest) -> PredictionResponse:
        return PredictionResponse(
            model_role=request.model_role,
            latency_ms=0.0,
            status_code=200,
            outputs=[{"text": "mock response"}],
        )

    async def wait_for_ready(
        self, role: str, timeout_seconds: int, interval_seconds: int = 10
    ) -> None:
        pass

    async def set_traffic_split(self, weights: dict[str, float]) -> None:
        pass

    async def get_traffic_split(self) -> dict[str, float]:
        return {"champion": 1.0}
