"""GateKeeper FastAPI application."""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gatekeeper.adapters.factory import build_adapters
from gatekeeper.adapters.serving.none import NoneServingAdapter
from gatekeeper.api.v1.pipeline import router as pipeline_router
from gatekeeper.api.v1.proxy import router as proxy_router
from gatekeeper.inference.offline import OfflineInferenceRunner
from gatekeeper.registries.loader import load_all_plugins
from gatekeeper.settings import settings

logger = logging.getLogger(__name__)

_cpu_executor = ThreadPoolExecutor(
    max_workers=min(8, (os.cpu_count() or 4) + 2),
    thread_name_prefix="gatekeeper-cpu",
)
_active_canary_tasks: dict[str, asyncio.Task] = {}


def _load_server_config() -> dict:
    """Load server.yaml from disk."""
    config_path = settings.config_path
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _resolve_env_vars(config: dict) -> dict:
    """Resolve ${ENV_VAR} references in config values."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_env_vars(value)
        elif isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            resolved[key] = os.environ.get(env_var, "")
        else:
            resolved[key] = value
    return resolved


def print_startup_report(loaded_plugins: dict[str, list[str]]) -> None:
    """Print what was loaded at startup."""
    from gatekeeper.registries import (
        DatasetFormatRegistry,
        DriftMethodRegistry,
        EvaluatorRegistry,
        InferenceEncodingRegistry,
        JudgeModalityRegistry,
        ModelTypeRegistry,
    )

    logger.info("=" * 60)
    logger.info("GateKeeper startup report")
    logger.info("-" * 60)
    logger.info(f"  Evaluators:          {list(EvaluatorRegistry.all().keys())}")
    logger.info(f"  Model types:         {list(ModelTypeRegistry.all().keys())}")
    logger.info(f"  Dataset formats:     {list(DatasetFormatRegistry.all().keys())}")
    logger.info(f"  Drift methods:       {list(DriftMethodRegistry.all().keys())}")
    logger.info(f"  Inference encodings: {list(InferenceEncodingRegistry.all().keys())}")
    logger.info(f"  Judge modalities:    {list(JudgeModalityRegistry.all().keys())}")
    logger.info("-" * 60)
    for package, caps in loaded_plugins.items():
        logger.info(f"  Plugin '{package}': {caps}")
    logger.info("=" * 60)


def _warm_imports() -> None:
    """Pre-import heavy libraries so first evaluator run doesn't pay cold-start cost."""
    try:
        import sklearn.metrics  # noqa: F401
    except ImportError:
        pass
    try:
        import numpy  # noqa: F401
    except ImportError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    # Pre-import heavy dependencies in thread pool to avoid cold-start latency
    # sklearn import takes ~1.5s; doing it here prevents first-request penalty
    await asyncio.get_running_loop().run_in_executor(_cpu_executor, _warm_imports)

    # Load plugins
    loaded_plugins = load_all_plugins()

    # Load server config
    server_config = _resolve_env_vars(_load_server_config())

    # Build adapters
    adapters = build_adapters(server_config)
    await adapters.registry.startup()
    if not isinstance(adapters.serving, NoneServingAdapter):
        await adapters.serving.startup()

    # Build offline runner
    adapters.offline_runner = OfflineInferenceRunner(
        registry_adapter=adapters.registry,
        server_config=server_config,
        cpu_executor=_cpu_executor,
    )

    # Build LLM judge client if configured
    llm_judge_client = None
    lj_config = server_config.get("llm_judge", {})
    if lj_config.get("provider") == "anthropic" and lj_config.get("api_key"):
        try:
            import anthropic

            llm_judge_client = anthropic.AsyncAnthropic(api_key=lj_config["api_key"])
        except ImportError:
            logger.warning("anthropic package not installed; LLM judge disabled")

    # Store in app state
    app.state.cpu_executor = _cpu_executor
    app.state.active_canary_tasks = _active_canary_tasks
    app.state.loaded_plugins = loaded_plugins
    app.state.adapters = adapters
    app.state.server_config = server_config
    app.state.llm_judge_client = llm_judge_client
    app.state.registry_type = server_config.get("registry", {}).get("type", "none")
    app.state.serving_type = server_config.get("serving", {}).get("type", "none")

    print_startup_report(loaded_plugins)
    yield

    # Shutdown
    if adapters.offline_runner:
        await adapters.offline_runner.shutdown()
    if not isinstance(adapters.serving, NoneServingAdapter):
        await adapters.serving.shutdown()
    await adapters.registry.shutdown()
    for task in _active_canary_tasks.values():
        task.cancel()
    if _active_canary_tasks:
        await asyncio.gather(
            *_active_canary_tasks.values(),
            return_exceptions=True,
        )
    _cpu_executor.shutdown(wait=True)


app = FastAPI(
    title="GateKeeper",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(pipeline_router)
app.include_router(proxy_router)


@app.get("/health")
async def health():
    """Health check — responds without blocking the event loop."""
    adapters = getattr(app.state, "adapters", None)
    registry_health = (True, "not configured")
    serving_health = (True, "not configured")

    if adapters:
        registry_health = await adapters.registry.health_check()
        serving_health = await adapters.serving.health_check()

    from gatekeeper.registries import (
        DatasetFormatRegistry,
        DriftMethodRegistry,
        EvaluatorRegistry,
        InferenceEncodingRegistry,
        JudgeModalityRegistry,
        ModelTypeRegistry,
    )

    return {
        "status": "healthy",
        "registry": {"ok": registry_health[0], "detail": registry_health[1]},
        "serving": {"ok": serving_health[0], "detail": serving_health[1]},
        "registries": {
            "evaluators": list(EvaluatorRegistry.all().keys()),
            "model_types": list(ModelTypeRegistry.all().keys()),
            "dataset_formats": list(DatasetFormatRegistry.all().keys()),
            "drift_methods": list(DriftMethodRegistry.all().keys()),
            "inference_encodings": list(InferenceEncodingRegistry.all().keys()),
            "judge_modalities": list(JudgeModalityRegistry.all().keys()),
        },
        "active_canary_tasks": list(_active_canary_tasks.keys()),
    }
