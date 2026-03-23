"""Adapter factory — builds adapters from server.yaml config."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from gatekeeper.adapters.registry.base import RegistryAdapter
from gatekeeper.adapters.registry.local import LocalRegistryAdapter
from gatekeeper.adapters.registry.mlflow import MLflowRegistryAdapter
from gatekeeper.adapters.registry.none import NoneRegistryAdapter
from gatekeeper.adapters.registry.s3 import S3RegistryAdapter
from gatekeeper.adapters.registry.sagemaker import SageMakerRegistryAdapter
from gatekeeper.adapters.serving.base import ServingAdapter
from gatekeeper.adapters.serving.custom_http import CustomHTTPAdapter
from gatekeeper.adapters.serving.none import NoneServingAdapter
from gatekeeper.adapters.serving.openai_compatible import OpenAICompatibleAdapter
from gatekeeper.adapters.serving.proxy import ProxyServingAdapter
from gatekeeper.adapters.serving.torchserve import TorchServeAdapter

logger = logging.getLogger(__name__)


@dataclass
class AdapterBundle:
    registry: RegistryAdapter
    serving: ServingAdapter
    offline_runner: object | None = None  # Set after construction


REGISTRY_ADAPTERS: dict[str, type] = {
    "mlflow": MLflowRegistryAdapter,
    "sagemaker": SageMakerRegistryAdapter,
    "s3": S3RegistryAdapter,
    "local": LocalRegistryAdapter,
    "none": NoneRegistryAdapter,
}

SERVING_ADAPTERS: dict[str, type] = {
    "openai_compatible": OpenAICompatibleAdapter,
    "torchserve": TorchServeAdapter,
    "custom_http": CustomHTTPAdapter,
    "proxy": ProxyServingAdapter,
    "none": NoneServingAdapter,
}


def build_registry_adapter(config: dict) -> RegistryAdapter:
    adapter_type = config.get("type", "none")
    if adapter_type == "mlflow":
        return MLflowRegistryAdapter(tracking_uri=config.get("tracking_uri", "http://mlflow:5001"))
    if adapter_type == "sagemaker":
        return SageMakerRegistryAdapter(region=config.get("region", "us-east-1"))
    if adapter_type == "s3":
        return S3RegistryAdapter(bucket=config.get("bucket", ""), prefix=config.get("prefix", ""))
    if adapter_type == "local":
        return LocalRegistryAdapter(base_path=config.get("base_path", "/models"))
    return NoneRegistryAdapter()


def build_serving_adapter(config: dict) -> ServingAdapter:
    adapter_type = config.get("type", "none")
    if adapter_type in ("openai_compatible", "torchserve", "custom_http"):
        cls = SERVING_ADAPTERS[adapter_type]
        auth = config.get("auth", {})
        ready = config.get("ready_check", {})
        return cls(
            champion_url=config.get("champion_url", ""),
            challenger_url=config.get("challenger_url", ""),
            auth_token=auth.get("token"),
            auth_type=auth.get("type", "none"),
            ready_check_path=ready.get("path", "/health"),
            ready_check_timeout=ready.get("timeout_seconds", 120),
            ready_check_interval=ready.get("interval_seconds", 10),
        )
    if adapter_type == "proxy":
        return ProxyServingAdapter(
            champion_url=config.get("champion_url", ""),
            challenger_url=config.get("challenger_url", ""),
            auth_token=config.get("auth", {}).get("token"),
        )
    return NoneServingAdapter()


def build_adapters(server_config: dict) -> AdapterBundle:
    registry = build_registry_adapter(server_config.get("registry", {}))
    serving = build_serving_adapter(server_config.get("serving", {}))
    return AdapterBundle(registry=registry, serving=serving)
