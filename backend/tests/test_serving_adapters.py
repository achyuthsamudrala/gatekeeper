"""Tests for OpenAI-compatible serving adapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse
from gatekeeper.adapters.serving.openai_compatible import OpenAICompatibleAdapter


class MockResponse:
    """Lightweight stand-in for httpx.Response."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self) -> dict:
        return self._json


def _make_adapter(**overrides) -> OpenAICompatibleAdapter:
    defaults = dict(
        champion_url="http://champion:8000",
        challenger_url="http://challenger:8000",
    )
    defaults.update(overrides)
    return OpenAICompatibleAdapter(**defaults)


# ── Lifecycle tests ──────────────────────────────────────────────────────


async def test_startup_shutdown():
    adapter = _make_adapter()
    assert adapter._client is None

    await adapter.startup()
    assert adapter._client is not None
    assert isinstance(adapter._client, httpx.AsyncClient)

    await adapter.shutdown()
    assert adapter._client.is_closed


# ── Predict tests ────────────────────────────────────────────────────────


async def test_predict_champion():
    adapter = _make_adapter()
    await adapter.startup()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=MockResponse(
            status_code=200,
            json_data={"choices": [{"message": {"content": "hello"}}]},
        )
    )

    with patch.object(adapter, "_client", mock_client):
        req = PredictionRequest(model_role="champion", inputs=[{"text": "hi"}])
        resp = await adapter.predict(req)

    assert isinstance(resp, PredictionResponse)
    assert resp.model_role == "champion"
    assert resp.status_code == 200
    assert resp.latency_ms > 0
    assert resp.outputs is not None
    assert resp.error is None

    # Verify champion URL was used
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://champion:8000/v1/chat/completions"


async def test_predict_challenger():
    adapter = _make_adapter()
    await adapter.startup()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=MockResponse(
            status_code=200,
            json_data={"choices": [{"message": {"content": "world"}}]},
        )
    )

    with patch.object(adapter, "_client", mock_client):
        req = PredictionRequest(model_role="challenger", inputs=[{"text": "hi"}])
        resp = await adapter.predict(req)

    assert resp.model_role == "challenger"
    assert resp.status_code == 200

    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://challenger:8000/v1/chat/completions"


async def test_predict_error_response():
    adapter = _make_adapter()
    await adapter.startup()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=MockResponse(status_code=500, text="Internal Server Error")
    )

    with patch.object(adapter, "_client", mock_client):
        req = PredictionRequest(model_role="champion", inputs=[{"text": "hi"}])
        resp = await adapter.predict(req)

    assert resp.status_code == 500
    assert resp.error is not None
    assert "Internal Server Error" in resp.error


async def test_predict_connection_error():
    adapter = _make_adapter()
    await adapter.startup()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch.object(adapter, "_client", mock_client):
        req = PredictionRequest(model_role="champion", inputs=[{"text": "hi"}])
        resp = await adapter.predict(req)

    assert resp.status_code == 500
    assert resp.error is not None
    assert "Connection refused" in resp.error


# ── Auth header tests ────────────────────────────────────────────────────


def test_auth_headers_bearer():
    adapter = _make_adapter(auth_type="bearer", auth_token="test-token")
    headers = adapter._auth_headers()
    assert headers == {"Authorization": "Bearer test-token"}


def test_auth_headers_api_key():
    adapter = _make_adapter(auth_type="api_key", auth_token="my-key")
    headers = adapter._auth_headers()
    assert headers == {"X-API-Key": "my-key"}


def test_auth_headers_none():
    adapter = _make_adapter(auth_type="none")
    headers = adapter._auth_headers()
    assert headers == {}


# ── Traffic split tests ──────────────────────────────────────────────────


async def test_traffic_split():
    adapter = _make_adapter()
    weights = {"champion": 0.8, "challenger": 0.2}
    await adapter.set_traffic_split(weights)
    result = await adapter.get_traffic_split()
    assert result == weights
    # Verify it's a copy, not the same object
    assert result is not weights


# ── Readiness probe tests ────────────────────────────────────────────────


async def test_wait_for_ready_success():
    adapter = _make_adapter()
    await adapter.startup()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MockResponse(status_code=200))

    with patch.object(adapter, "_client", mock_client):
        # Should not raise
        await adapter.wait_for_ready("champion", timeout_seconds=5, interval_seconds=1)

    mock_client.get.assert_called_once_with("http://champion:8000/health")
    await adapter.shutdown()


async def test_wait_for_ready_timeout():
    adapter = _make_adapter()
    await adapter.startup()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MockResponse(status_code=503))

    with patch.object(adapter, "_client", mock_client):
        with pytest.raises(asyncio.TimeoutError):
            await adapter.wait_for_ready("champion", timeout_seconds=1, interval_seconds=1)

    await adapter.shutdown()
