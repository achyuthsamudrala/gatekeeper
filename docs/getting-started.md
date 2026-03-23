# Getting Started

This guide walks you from a fresh clone to your first pipeline run visible in the UI.

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- `curl` and `jq` (for triggering pipelines from the CLI)

## 1. Clone and Start

```bash
git clone https://github.com/achyuthsamudrala/gatekeeper.git
cd gatekeeper
```

Start all services:

```bash
make up
```

This starts four containers:
- **backend** — FastAPI server at `http://localhost:8000`
- **frontend** — React dashboard at `http://localhost:3000`
- **db** — PostgreSQL 15
- **mlflow** — MLflow server at `http://localhost:5001` (optional)

Wait for services to be healthy:

```bash
make health
```

You should see:

```json
{
    "status": "healthy",
    "registry": {"ok": true, "detail": "no serving configured"},
    "serving": {"ok": true, "detail": "no serving configured"},
    "registries": {
        "evaluators": ["accuracy", "drift", "llm_judge", "champion_challenger", "latency"],
        "model_types": ["llm", "pytorch"],
        "dataset_formats": ["jsonl", "parquet", "csv"],
        ...
    }
}
```

## 2. Run Database Migrations

```bash
make migrate
```

## 3. Open the Dashboard

Open `http://localhost:3000` in your browser. You'll see the **Pipeline Runs** page — empty for now.

## 4. Trigger Your First Pipeline Run

Trigger an offline eval pipeline using curl:

```bash
curl -s -X POST http://localhost:8000/api/v1/pipeline/trigger \
  -H "Content-Type: application/json" \
  -H "X-GateKeeper-Secret: changeme" \
  -d '{
    "model_name": "my-first-model",
    "candidate_version": "v1.0",
    "phase": "offline",
    "gatekeeper_yaml": "version: \"1.0\"\nmodel_type: llm\neval_dataset:\n  uri: ./data/eval.jsonl\n  label_column: label\n  task_type: classification\ngates:\n  - name: accuracy_gate\n    phase: offline\n    evaluator: accuracy\n    metric: f1_weighted\n    threshold: 0.80\n    comparator: \">=\"\n    blocking: true",
    "triggered_by": "manual"
  }' | jq .
```

You'll get back:

```json
{
  "pipeline_run_id": "some-uuid",
  "status": "accepted",
  "report_url": "/api/v1/pipeline/runs/some-uuid"
}
```

## 5. View Results in the Dashboard

1. Go to `http://localhost:3000` — your run appears in the Pipeline Runs table
2. Click the model name to open the **Gate Report** detail view
3. You'll see gate results with PASS/FAIL/SKIP labels, metric values, and thresholds

The dashboard auto-refreshes every 10 seconds, so you can watch the run progress from `pending` → `running` → `passed`/`failed` in real time.

## 6. Try a Demo Scenario

GateKeeper ships with four demo scenarios that exercise different workflow patterns:

```bash
# Pattern A: Offline only (accuracy + drift gates)
make demo-a

# Pattern B: Online only (latency + canary)
make demo-b

# Pattern C: Chained (offline → online)
make demo-c

# Pattern D: Custom evaluator plugin
make demo-plugin
```

Each demo triggers a pipeline and polls for results. Watch the dashboard while they run.

## 7. Check the Gate Report via API

```bash
# Replace <run-id> with the pipeline_run_id from step 4
curl -s http://localhost:8000/api/v1/pipeline/runs/<run-id>/report | jq .
```

This returns the gate policy result:

```json
{
  "pipeline_run_id": "...",
  "offline": {
    "phase": "offline",
    "overall_passed": true,
    "gates": [
      {
        "gate_name": "accuracy_gate",
        "passed": true,
        "metric_value": 0.92,
        "threshold": 0.80,
        "comparator": ">=",
        "blocking": true
      }
    ]
  }
}
```

## 8. View Audit Trail

Every action is logged:

```bash
curl -s http://localhost:8000/api/v1/pipeline/runs/<run-id>/audit | jq .
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEKEEPER_SECRET` | `changeme` | Trigger authentication secret |
| `GATEKEEPER_DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `GATEKEEPER_CONFIG_PATH` | `/config/server.yaml` | Path to server config |
| `ANTHROPIC_API_KEY` | (empty) | Required for LLM judge evaluator |
| `MODEL_API_KEY` | (empty) | Auth token for model serving endpoints |

## Configuration Files

- **`config/server.yaml`** — Server-level config: registry adapter, serving adapter, LLM judge settings. See [server.yaml reference](server-yaml.md).
- **`gatekeeper.yaml`** — Per-model config passed at trigger time: gates, thresholds, dataset config. See [gatekeeper.yaml reference](gatekeeper-yaml.md).

## Next Steps

- [UI Guide](ui.md) — Learn what each dashboard page shows
- [Deployment Guide](deployment.md) — Production setup with real model endpoints
- [Extending GateKeeper](plugins.md) — Write custom evaluators, dataset formats, and more
- [GitHub Action](github-action.md) — Integrate with CI/CD
