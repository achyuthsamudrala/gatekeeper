"""Base serving adapter."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse


class ServingAdapter(ABC):
    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> tuple[bool, str]: ...

    @abstractmethod
    async def predict(self, request: PredictionRequest) -> PredictionResponse:
        """Single prediction. Uses shared httpx.AsyncClient."""

    async def predict_batch(self, requests: list[PredictionRequest]) -> list[PredictionResponse]:
        """Run requests concurrently with semaphore."""
        semaphore = asyncio.Semaphore(10)

        async def _bounded_predict(req: PredictionRequest) -> PredictionResponse:
            async with semaphore:
                return await self.predict(req)

        return await asyncio.gather(
            *[_bounded_predict(r) for r in requests],
            return_exceptions=False,
        )

    @abstractmethod
    async def wait_for_ready(
        self,
        role: str,
        timeout_seconds: int,
        interval_seconds: int = 10,
    ) -> None:
        """Async polling. Uses asyncio.sleep(), never time.sleep()."""

    @abstractmethod
    async def set_traffic_split(self, weights: dict[str, float]) -> None: ...

    @abstractmethod
    async def get_traffic_split(self) -> dict[str, float]: ...
