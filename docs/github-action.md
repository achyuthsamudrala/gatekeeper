# GitHub Action

GateKeeper provides a GitHub Action for triggering eval gates from CI/CD pipelines.

## Usage

```yaml
# .github/workflows/deploy.yml
name: Model Deploy
on:
  push:
    branches: [main]

jobs:
  eval-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run GateKeeper eval gates
        uses: your-org/gatekeeper/action@main
        with:
          gatekeeper_url: ${{ secrets.GATEKEEPER_URL }}
          gatekeeper_secret: ${{ secrets.GATEKEEPER_SECRET }}
          model_name: my-model
          phase: offline
          gatekeeper_yaml: ./gatekeeper.yaml
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `gatekeeper_url` | yes | — | GateKeeper server URL |
| `gatekeeper_secret` | yes | — | Shared trigger secret |
| `model_name` | yes | — | Model name |
| `candidate_version` | no | `$GITHUB_SHA` | Model version |
| `phase` | no | `offline` | `offline`, `online`, or `both` |
| `gatekeeper_yaml` | yes | — | Path to config file |
| `poll_interval` | no | `15` | Poll interval (seconds) |
| `timeout` | no | `1800` | Max wait time (seconds) |

## Outputs

| Output | Description |
|--------|-------------|
| `pipeline_run_id` | The created pipeline run ID |
| `result` | `passed`, `failed`, or `timeout` |
| `report_url` | URL to the full gate report |

## Workflow Patterns

### Pattern A: Offline Only
```yaml
with:
  phase: offline
  gatekeeper_yaml: ./gatekeeper.yaml
```

### Pattern B: Online Only
```yaml
with:
  phase: online
  gatekeeper_yaml: ./gatekeeper.yaml
```

### Pattern C: Chained
```yaml
with:
  phase: both
  gatekeeper_yaml: ./gatekeeper.yaml
  timeout: 3600  # longer for canary observation
```

### Pattern D: Custom Evaluator
Same as Pattern A, but `gatekeeper.yaml` references a custom evaluator installed in the GateKeeper server.
