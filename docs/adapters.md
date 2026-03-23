# Adapters

GateKeeper uses two types of adapters to integrate with external systems.

## Registry Adapters

Registry adapters provide access to model artifacts (downloads, version listing, champion identification).

| Adapter | Config `type` | Description |
|---------|--------------|-------------|
| MLflow | `mlflow` | MLflow Model Registry |
| SageMaker | `sagemaker` | AWS SageMaker Model Registry (aiobotocore) |
| S3 | `s3` | Direct S3 artifact access (aiobotocore) |
| Local | `local` | Local filesystem artifacts (aiofiles) |
| None | `none` | No registry — skip artifact-dependent evaluators |

### Configuration

```yaml
# server.yaml
registry:
  type: mlflow
  tracking_uri: http://mlflow:5001
```

## Serving Adapters

Serving adapters provide access to model endpoints for inference and traffic management.

| Adapter | Config `type` | Description |
|---------|--------------|-------------|
| OpenAI Compatible | `openai_compatible` | vLLM, TGI, and OpenAI-compatible APIs |
| TorchServe | `torchserve` | PyTorch TorchServe endpoints |
| Custom HTTP | `custom_http` | Generic HTTP endpoints with configurable paths |
| Proxy | `proxy` | Pass-through proxy for canary traffic splitting |
| None | `none` | No serving — skip online evaluators |

### Configuration

```yaml
# server.yaml
serving:
  type: openai_compatible
  champion_url: http://vllm-champion:8080/v1
  challenger_url: http://vllm-challenger:8081/v1
  auth:
    type: bearer
    token: ${MODEL_API_KEY}
  ready_check:
    path: /health
    timeout_seconds: 120
    interval_seconds: 10
```

## Async Requirements

All adapters follow these async rules:
- `startup()` and `shutdown()` are async, called from app lifespan
- `httpx.AsyncClient` is shared per adapter instance, not created per request
- `wait_for_ready()` uses `asyncio.sleep()` for polling, never `time.sleep()`
- `predict()` and `predict_batch()` are async with semaphore-bounded concurrency
