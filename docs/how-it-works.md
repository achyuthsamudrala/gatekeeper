# How GateKeeper Works

## Phase Model

GateKeeper sits between "model artifact exists" and "model serving production traffic". It provides two optional, composable evaluation phases:

### Offline Phase
Runs quality gates against the model artifact using evaluation datasets. No live traffic is involved.

**Built-in evaluators:**
- **accuracy** — Classification metrics (F1, accuracy) using sklearn
- **drift** — Data drift detection (PSI, KS test) against reference data
- **llm_judge** — LLM-as-judge quality scoring via Anthropic API
- **champion_challenger** — Compares candidate vs current champion model

### Online Phase
Runs latency/performance gates against a live model endpoint, then manages canary traffic.

**Built-in evaluators:**
- **latency** — P50/P95/P99 latency benchmarking with concurrent load

### Canary Traffic Management
After online gates pass, GateKeeper splits traffic between champion and challenger, monitors metrics, and auto-promotes or auto-rolls back based on configured thresholds.

## Workflow Patterns

| Pattern | Phases | Use Case |
|---------|--------|----------|
| A | Offline only | Quality validation before deployment |
| B | Online only | Latency testing + canary for pre-deployed models |
| C | Chained (offline → online) | Full pipeline: quality gates → latency → canary |
| D | Custom evaluator | Extend with your own evaluation logic |

## Pipeline Run Lifecycle

1. **Triggered** — `POST /api/v1/pipeline/trigger` creates a PipelineRun
2. **Offline Running** — Evaluators run concurrently via `asyncio.gather`
3. **Gate Policy** — Threshold comparisons determine pass/fail
4. **Online Running** — Latency benchmarks against live endpoint
5. **Canary** — Traffic split with observation window
6. **Promoted/Rolled Back** — Final state based on canary metrics

## Gate Classification

- **Blocking gates** — Must pass for the phase to pass
- **Non-blocking gates** — Reported but don't affect overall pass/fail
- **Skipped gates** — Missing config (e.g., no reference dataset for drift) — doesn't count
