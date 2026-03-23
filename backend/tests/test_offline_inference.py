"""Tests for OfflineInferenceRunner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from gatekeeper.adapters.base_types import ModelVersion
from gatekeeper.inference.offline import OfflineInferenceRunner
from gatekeeper.registries.dataset_format import Sample
from gatekeeper.registries.loader import load_all_plugins


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _register_model_types():
    """Ensure the LLM model type is registered for tests."""
    load_all_plugins()
    yield
    # Don't clear — other tests may depend on registry state.


@pytest.fixture
def server_config():
    return {
        "serving": {
            "challenger_url": "http://challenger:8080",
            "champion_url": "http://champion:8080",
        }
    }


@pytest.fixture
def samples():
    return [
        Sample(input={"text": "hello"}, ground_truth=None),
        Sample(input={"text": "world"}, ground_truth=None),
    ]


def _mock_registry_adapter(model_type: str = "llm") -> AsyncMock:
    adapter = AsyncMock()
    adapter.get_model_version.return_value = ModelVersion(
        name="test-model",
        version="v1",
        model_type=model_type,
    )
    return adapter


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_remote_inference_sequential(server_config, samples):
    """Mock httpx responses and verify results come back for each sample."""
    adapter = _mock_registry_adapter("llm")
    runner = OfflineInferenceRunner(adapter, server_config, ThreadPoolExecutor(max_workers=1))

    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "response"}}]},
    )

    with patch("gatekeeper.inference.offline.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await runner.run("test-model", "v1", samples, role="challenger")

    assert len(results) == len(samples)
    for result in results:
        assert "choices" in result


async def test_remote_inference_error_handling(server_config, samples):
    """When httpx raises, the error is captured in the result dict."""
    adapter = _mock_registry_adapter("llm")
    runner = OfflineInferenceRunner(adapter, server_config, ThreadPoolExecutor(max_workers=1))

    with patch("gatekeeper.inference.offline.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await runner.run("test-model", "v1", samples, role="challenger")

    assert len(results) == len(samples)
    for result in results:
        assert "error" in result


async def test_runner_uses_challenger_url(server_config, samples):
    """Verify the correct URL is used based on role."""
    adapter = _mock_registry_adapter("llm")
    runner = OfflineInferenceRunner(adapter, server_config, ThreadPoolExecutor(max_workers=1))

    mock_response = httpx.Response(200, json={"ok": True})

    with patch("gatekeeper.inference.offline.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # Test challenger role
        await runner.run("test-model", "v1", samples, role="challenger")
        challenger_url = mock_client.post.call_args_list[0][0][0]
        assert challenger_url == "http://challenger:8080/v1/chat/completions"

        mock_client.post.reset_mock()

        # Test champion role
        await runner.run("test-model", "v1", samples, role="champion")
        champion_url = mock_client.post.call_args_list[0][0][0]
        assert champion_url == "http://champion:8080/v1/chat/completions"
