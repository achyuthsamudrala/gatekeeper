# UI Guide

GateKeeper ships with a React dashboard at `http://localhost:3000`. It provides three views for monitoring pipeline runs, inspecting gate results, and comparing runs.

## Pipeline Runs (Home Page)

**URL:** `http://localhost:3000/`

The main view. Shows a table of all pipeline runs, sorted by most recent.

### Columns

| Column | Description |
|--------|-------------|
| **Model** | Model name (clickable — opens Gate Report) |
| **Version** | Candidate version being evaluated |
| **Offline** | Offline phase status badge + gate pass count (e.g. `passed 3/3`) |
| **Online** | Online phase status badge + gate pass count |
| **Triggered** | Who triggered the run (e.g. `github_actions`, `manual`, `demo`) |
| **Created** | Timestamp |

### Status Badges

| Badge | Color | Meaning |
|-------|-------|---------|
| `pending` | Gray | Phase not yet started |
| `running` | Blue | Evaluators are executing |
| `passed` | Green | All blocking gates passed |
| `failed` | Red | One or more blocking gates failed |
| `skipped` | Gray | Phase was skipped (e.g. offline failed, so online skipped) |
| `canary` | Yellow | Canary traffic is active, observation in progress |
| `promoted` | Green | Canary completed, challenger promoted to production |
| `rolled_back` | Red | Canary rolled back to champion |

### Auto-refresh

The page polls the API every 10 seconds. You can watch runs transition through statuses in real time without refreshing.

## Gate Report (Run Detail)

**URL:** `http://localhost:3000/runs/{id}`

Click any model name from the Pipeline Runs page to open its detail view.

### Sections

#### Header
Shows model name, candidate version, model type, who triggered it, and when.

#### Offline Gates
Each gate shows:
- **PASS / FAIL / SKIP** — Color-coded label
- **Gate name** — From `gatekeeper.yaml`
- **Evaluator type** — Which evaluator ran (e.g. `accuracy`, `drift`)
- **Metric value** — Computed value (4 decimal places)
- **Threshold** — Comparison value and operator (e.g. `>= 0.85`)
- **BLOCKING** — Orange badge if the gate blocks deployment

#### Online Gates
Same format as offline. Appears only if online phase was configured.

#### Canary Metrics
Appears when the run enters canary state. Shows a table with:
- **Timestamp** — When the snapshot was taken
- **Champion p95** — Champion model's p95 latency in ms
- **Challenger p95** — Challenger model's p95 latency in ms
- **Champion Err%** — Champion error rate as percentage
- **Challenger Err%** — Challenger error rate as percentage

Snapshots are collected every 60 seconds during the canary observation window.

#### Promote / Rollback Buttons
Appear only when the run is in `canary` status. Actions:
- **Promote** — Sends 100% traffic to challenger, marks run as `promoted`
- **Rollback** — Sends 100% traffic back to champion, marks run as `rolled_back`

These call `POST /api/v1/pipeline/runs/{id}/promote` and `/rollback` respectively.

#### Audit Log
Chronological list of all actions for this run:
- `triggered` — Pipeline was created
- `canary_started` — Canary observation began
- `promoted` / `rolled_back` — Final disposition
- Each entry shows timestamp, action name, and phase

### Auto-refresh

Detail view polls every 10 seconds. Watch gates complete and canary metrics accumulate in real time.

## Run Comparison

**URL:** `http://localhost:3000/compare`

Accessible from the **Compare** link in the navigation bar.

### How to Use

1. Enter two pipeline run IDs (copy from the Pipeline Runs page URL or API response)
2. Click **Compare**
3. Side-by-side view shows:
   - Model name and version for each run
   - Offline and online status badges
   - All gate results for both runs

Use this to compare a new candidate against a previous run, or to see how gate results changed after a model update.

## Navigation

The top navigation bar has two links:
- **Pipeline Runs** — Home page (run list)
- **Compare** — Side-by-side comparison view

## Accessing the API Directly

The dashboard talks to the backend API at `http://localhost:8000`. All API endpoints are accessible directly:

```bash
# List all runs
curl -s http://localhost:8000/api/v1/pipeline/runs | jq .

# Get run detail
curl -s http://localhost:8000/api/v1/pipeline/runs/{id} | jq .

# Get gate report
curl -s http://localhost:8000/api/v1/pipeline/runs/{id}/report | jq .

# Get registered plugins
curl -s http://localhost:8000/api/v1/system/registries | jq .
```

See the [API reference in the README](../README.md#api) for the full endpoint list.
