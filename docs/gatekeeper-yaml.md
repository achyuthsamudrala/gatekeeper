# gatekeeper.yaml Reference

Per-model configuration that defines evaluation gates. Stored in your model repository and passed to GateKeeper at trigger time.

```yaml
version: "1.0"
model_type: llm

eval_dataset:
  uri: s3://bucket/eval-data.jsonl
  format: jsonl
  label_column: label
  task_type: classification

reference_dataset:
  uri: s3://bucket/training-data.jsonl
  format: jsonl
  feature_columns: [text, category]
  categorical_columns: [category]

gates:
  - name: accuracy_gate
    phase: offline
    evaluator: accuracy
    metric: f1_weighted
    threshold: 0.85
    comparator: ">="
    blocking: true
    description: "F1 must be at least 0.85"

  - name: drift_gate
    phase: offline
    evaluator: drift
    metric: max_psi_score
    threshold: 0.25
    comparator: "<"
    blocking: true
    drift_method: psi

  - name: quality_gate
    phase: offline
    evaluator: llm_judge
    metric: llm_judge_score
    threshold: 0.70
    comparator: ">="
    blocking: false
    rubric: "Rate from 0-1 based on accuracy and completeness."
    num_samples: 20
    judge_modality: text

  - name: latency_gate
    phase: online
    evaluator: latency
    metric: p95_latency_ms
    threshold: 500
    comparator: "<"
    blocking: true
    num_warmup_requests: 5
    num_benchmark_requests: 50

canary:
  traffic_percent: 10
  observation_window_minutes: 30
  auto_promote_threshold:
    latency_p95_ms: 500
    error_rate: 0.05
  auto_rollback_threshold:
    latency_p95_ms: 2000
    error_rate: 0.20
```

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | string | yes | — | Always `"1.0"` |
| `model_type` | string | yes | — | `llm`, `pytorch`, or custom |
| `eval_dataset.uri` | string | yes | — | Path or URI to eval data |
| `eval_dataset.format` | string | no | inferred | `jsonl`, `parquet`, `csv`, or custom |
| `eval_dataset.label_column` | string | yes | — | Ground truth column |
| `eval_dataset.task_type` | string | yes | — | `classification`, `regression`, `summarisation`, `qa` |
| `reference_dataset.uri` | string | no | — | Training data for drift |
| `gates[].name` | string | yes | — | Unique gate identifier |
| `gates[].phase` | string | yes | — | `offline` or `online` |
| `gates[].evaluator` | string | yes | — | Registered evaluator name |
| `gates[].metric` | string | yes | — | Metric name from evaluator |
| `gates[].threshold` | float | yes | — | Comparison value |
| `gates[].comparator` | string | yes | — | `>=`, `<=`, `>`, `<`, `==` |
| `gates[].blocking` | bool | no | `true` | Whether failure blocks deployment |
| `gates[].drift_method` | string | drift only | `psi` | `psi` or `ks` |
| `gates[].rubric` | string | llm_judge only | — | Judge rubric text |
| `gates[].num_samples` | int | llm_judge only | `20` | Samples to judge |
| `gates[].num_warmup_requests` | int | latency only | `5` | Warmup requests |
| `gates[].num_benchmark_requests` | int | latency only | `50` | Benchmark requests |
| `canary.traffic_percent` | float | no | `10` | Challenger traffic % |
| `canary.observation_window_minutes` | int | no | `30` | Observation window |
| `canary.auto_promote_threshold.*` | float | no | — | Promote thresholds |
| `canary.auto_rollback_threshold.*` | float | no | — | Rollback thresholds |
