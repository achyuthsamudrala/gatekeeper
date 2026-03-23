# Deployment Guide

How to deploy GateKeeper for production use with real model endpoints.

## Architecture Overview

```
                    ┌─────────────────┐
                    │   Load Balancer  │
                    └──────┬──────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────┴──┐  ┌─────┴────┐  ┌────┴─────┐
       │ Backend  │  │ Backend  │  │ Frontend │
       │ (port   │  │ (port   │  │ (Nginx)  │
       │  8000)  │  │  8000)  │  │          │
       └────┬────┘  └────┬────┘  └──────────┘
            │             │
       ┌────┴─────────────┴────┐
       │     PostgreSQL 15     │
       └───────────────────────┘
```

## Single-Node (Docker Compose)

The simplest deployment for small teams.

### 1. Create an `.env` file

```bash
# .env
GATEKEEPER_SECRET=your-strong-secret-here
ANTHROPIC_API_KEY=sk-ant-...          # Required for LLM judge evaluator
MODEL_API_KEY=your-model-api-key      # For authenticated model endpoints
```

### 2. Configure `config/server.yaml`

```yaml
version: "1.0"

registry:
  type: mlflow
  tracking_uri: http://mlflow:5001

serving:
  type: openai_compatible
  champion_url: http://your-champion-endpoint:8080/v1
  challenger_url: http://your-challenger-endpoint:8081/v1
  auth:
    type: bearer
    token: ${MODEL_API_KEY}
  ready_check:
    path: /health
    timeout_seconds: 120
    interval_seconds: 10
  canary:
    strategy: proxy

llm_judge:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}

security:
  trigger_secret: ${GATEKEEPER_SECRET}
```

### 3. Start

```bash
make up
make migrate
make health
```

### 4. Verify

```bash
# Check health
curl -s http://localhost:8000/health | jq .

# Check registered plugins
curl -s http://localhost:8000/api/v1/system/registries | jq .

# Open dashboard
open http://localhost:3000
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GATEKEEPER_SECRET` | Yes | `changeme` | Shared secret for trigger authentication. **Change in production.** |
| `GATEKEEPER_DATABASE_URL` | No | `postgresql+asyncpg://gatekeeper:gatekeeper@db:5432/gatekeeper` | Async PostgreSQL connection string. Must use `asyncpg` driver. |
| `GATEKEEPER_CONFIG_PATH` | No | `/config/server.yaml` | Path to server config file inside the container. |
| `GATEKEEPER_LOG_LEVEL` | No | `info` | Logging level (`debug`, `info`, `warning`, `error`). |
| `ANTHROPIC_API_KEY` | If LLM judge | (empty) | Anthropic API key for LLM-as-judge evaluator. |
| `MODEL_API_KEY` | If auth needed | (empty) | Token for model serving endpoints. Referenced as `${MODEL_API_KEY}` in server.yaml. |

## Configuring Adapters

### Registry Adapters

Registry adapters provide access to model artifacts.

**MLflow:**
```yaml
registry:
  type: mlflow
  tracking_uri: http://mlflow-server:5001
```

**S3:**
```yaml
registry:
  type: s3
  bucket: my-model-bucket
  prefix: models/
```

**SageMaker:**
```yaml
registry:
  type: sagemaker
  region: us-east-1
```

**Local filesystem:**
```yaml
registry:
  type: local
  base_path: /models
```

**None (skip artifact-dependent evaluators):**
```yaml
registry:
  type: none
```

### Serving Adapters

Serving adapters connect to model endpoints for inference and canary traffic.

**OpenAI-compatible (vLLM, TGI):**
```yaml
serving:
  type: openai_compatible
  champion_url: http://vllm-champion:8080/v1
  challenger_url: http://vllm-challenger:8081/v1
  auth:
    type: bearer
    token: ${MODEL_API_KEY}
```

**TorchServe:**
```yaml
serving:
  type: torchserve
  champion_url: http://torchserve-champion:8080
  challenger_url: http://torchserve-challenger:8081
```

**Custom HTTP:**
```yaml
serving:
  type: custom_http
  champion_url: http://my-model:8080
  challenger_url: http://my-model-v2:8081
  request_encoding: json
  custom_http:
    prediction_path: /predict
    input_key: inputs
    output_key: outputs
```

**None (skip online evaluators):**
```yaml
serving:
  type: none
```

## Scaling

### Single Worker Requirement

GateKeeper runs with **one uvicorn worker per process**. This is by design — the server uses in-process state for active canary tasks and shared httpx clients. The `--workers 1` flag in docker-compose.yml is intentional.

### Horizontal Scaling

To handle more load, run multiple single-worker containers behind a load balancer:

```yaml
# docker-compose.prod.yml
services:
  backend-1:
    build: ./backend
    command: uvicorn gatekeeper.main:app --host 0.0.0.0 --port 8000 --workers 1

  backend-2:
    build: ./backend
    command: uvicorn gatekeeper.main:app --host 0.0.0.0 --port 8000 --workers 1

  nginx:
    image: nginx:alpine
    # Load balance across backend-1 and backend-2
```

**Important:** Canary tasks are stored in-process (`app.state.active_canary_tasks`). With multiple instances, a canary task runs on whichever instance accepted the trigger request. Promote/rollback requests must reach the same instance, or use sticky sessions.

### Database

PostgreSQL is the only shared state. For production:
- Use a managed PostgreSQL service (RDS, Cloud SQL, etc.)
- Update `GATEKEEPER_DATABASE_URL` to point at your instance
- The connection string must use the `asyncpg` driver: `postgresql+asyncpg://...`

## Security

### Trigger Secret

Every `POST /api/v1/pipeline/trigger` requires the `X-GateKeeper-Secret` header. Set `GATEKEEPER_SECRET` to a strong random value in production.

### API Key References

In `server.yaml`, use `${ENV_VAR}` syntax to reference environment variables instead of hardcoding secrets:

```yaml
serving:
  auth:
    token: ${MODEL_API_KEY}    # Resolved at startup from env

llm_judge:
  api_key: ${ANTHROPIC_API_KEY}
```

### Network

- The backend listens on port 8000. In production, put it behind TLS termination.
- The frontend (Nginx) listens on port 3000 (mapped to 80 inside the container).
- The frontend proxies `/api` and `/health` requests to the backend — no CORS issues in production.

## Database Migrations

Run migrations after every upgrade:

```bash
# Docker
make migrate

# Manual
docker compose exec backend alembic upgrade head
```

Migrations live in `backend/migrations/versions/`. Alembic handles schema versioning.

## Troubleshooting

### Backend won't start

```bash
# Check logs
make logs

# Common issues:
# - DB not ready yet → backend retries on startup, wait for healthcheck
# - Bad server.yaml → check YAML syntax
# - Missing env vars → check .env file
```

### "No pipeline runs yet" in dashboard

The dashboard is at `http://localhost:3000`. The backend API is at `http://localhost:8000`. If the dashboard loads but shows no data:

1. Check the backend is healthy: `make health`
2. Trigger a test run (see [Getting Started](getting-started.md#4-trigger-your-first-pipeline-run))
3. Check browser console for API errors

### Evaluator errors

Gate results with `SKIP` status and a skip_reason usually mean missing configuration:

| Skip Reason | Fix |
|-------------|-----|
| `reference_dataset not configured` | Add `reference_dataset` section to `gatekeeper.yaml` |
| `registry not configured` | Set `registry.type` in `server.yaml` (needed for champion_challenger) |
| `evaluator_not_run` | The evaluator didn't execute — check backend logs for errors |

### Canary not progressing

The canary observation loop runs as a background asyncio task. Check:

```bash
# See active canary tasks
curl -s http://localhost:8000/health | jq '.active_canary_tasks'

# Check canary snapshots
curl -s http://localhost:8000/api/v1/pipeline/runs/{id}/canary | jq .
```

If no snapshots appear, the serving adapter may not be collecting metrics (check that `serving.type` is not `none`).

### Reset everything

```bash
make reset    # docker compose down -v && up (destroys DB data)
make migrate
```

## CI/CD Integration

See [GitHub Action](github-action.md) for integrating GateKeeper into your deployment pipeline. The action triggers eval gates and blocks the workflow until results are in.
