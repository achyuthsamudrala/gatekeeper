"""Canary traffic proxy endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gatekeeper.adapters.base_types import PredictionRequest

router = APIRouter(prefix="/api/v1")


@router.post("/proxy/predict")
async def proxy_predict(request: Request):
    """Route prediction through canary proxy."""
    adapters = getattr(request.app.state, "adapters", None)
    if not adapters:
        return JSONResponse(status_code=503, content={"error": "No serving adapter configured"})

    body = await request.json()
    pred_request = PredictionRequest(
        inputs=body.get("inputs", [body]),
        model_role=body.get("model_role", "champion"),
    )

    response = await adapters.serving.predict(pred_request)
    return {
        "model_role": response.model_role,
        "latency_ms": response.latency_ms,
        "status_code": response.status_code,
        "outputs": response.outputs,
        "error": response.error,
    }
