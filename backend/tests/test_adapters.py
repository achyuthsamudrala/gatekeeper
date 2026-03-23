"""Tests for adapters."""

from __future__ import annotations


from gatekeeper.adapters.base_types import PredictionRequest
from gatekeeper.adapters.factory import build_adapters
from gatekeeper.adapters.registry.none import NoneRegistryAdapter
from gatekeeper.adapters.serving.none import NoneServingAdapter


async def test_none_registry_adapter():
    adapter = NoneRegistryAdapter()
    await adapter.startup()
    ok, detail = await adapter.health_check()
    assert ok is True
    version = await adapter.get_model_version("test-model", "v1")
    assert version.name == "test-model"
    assert version.version == "v1"
    champion = await adapter.get_champion_version("test-model")
    assert champion is None
    await adapter.shutdown()


async def test_none_serving_adapter():
    adapter = NoneServingAdapter()
    await adapter.startup()
    ok, detail = await adapter.health_check()
    assert ok is True

    req = PredictionRequest(inputs=[{"text": "hello"}], model_role="challenger")
    resp = await adapter.predict(req)
    assert resp.status_code == 200
    assert resp.outputs is not None

    split = await adapter.get_traffic_split()
    assert split["champion"] == 1.0

    await adapter.shutdown()


async def test_build_adapters_defaults():
    bundle = build_adapters({})
    assert isinstance(bundle.registry, NoneRegistryAdapter)
    assert isinstance(bundle.serving, NoneServingAdapter)


async def test_build_adapters_mlflow():
    bundle = build_adapters(
        {
            "registry": {"type": "mlflow", "tracking_uri": "http://mlflow:5001"},
            "serving": {"type": "none"},
        }
    )
    from gatekeeper.adapters.registry.mlflow import MLflowRegistryAdapter

    assert isinstance(bundle.registry, MLflowRegistryAdapter)


async def test_none_serving_predict_batch():
    adapter = NoneServingAdapter()
    await adapter.startup()
    requests = [PredictionRequest(inputs=[{"text": f"input-{i}"}]) for i in range(5)]
    results = await adapter.predict_batch(requests)
    assert len(results) == 5
    for r in results:
        assert r.status_code == 200
    await adapter.shutdown()
