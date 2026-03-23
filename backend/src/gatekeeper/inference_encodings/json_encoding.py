"""JSON inference encoding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatekeeper.registries.inference_encoding import BaseInferenceEncoding, EncodedRequest

if TYPE_CHECKING:
    import httpx
    from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse


class JSONEncoding(BaseInferenceEncoding):
    @property
    def name(self) -> str:
        return "json"

    async def encode_request(
        self,
        request: PredictionRequest,
        config: dict,
    ) -> EncodedRequest:
        input_key = config.get("input_key", "inputs")
        return EncodedRequest(
            method="POST",
            headers={"Content-Type": "application/json"},
            json_body={input_key: request.inputs},
        )

    async def decode_response(
        self,
        response: httpx.Response,
        config: dict,
    ) -> PredictionResponse:
        from gatekeeper.adapters.base_types import PredictionResponse as PR

        output_key = config.get("output_key", "outputs")
        data = response.json()
        return PR(
            model_role="unknown",
            latency_ms=0.0,
            status_code=response.status_code,
            outputs=data.get(output_key, [data]),
        )
