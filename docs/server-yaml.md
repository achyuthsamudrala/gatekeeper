# server.yaml Reference

Server-level configuration for GateKeeper. Placed at the path specified by `GATEKEEPER_CONFIG_PATH`.

```yaml
version: "1.0"

registry:
  type: mlflow              # mlflow | sagemaker | s3 | local | none
  tracking_uri: http://mlflow:5001

serving:
  type: openai_compatible   # openai_compatible | torchserve | custom_http | proxy | none
  champion_url: http://vllm-champion:8080/v1
  challenger_url: http://vllm-challenger:8081/v1
  auth:
    type: bearer            # bearer | api_key | none
    token: ${MODEL_API_KEY}
  ready_check:
    path: /health
    timeout_seconds: 120
    interval_seconds: 10
  canary:
    strategy: proxy         # proxy | none

llm_judge:
  provider: anthropic       # anthropic | openai
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}

security:
  trigger_secret: ${GATEKEEPER_SECRET}
```

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | string | yes | — | Always `"1.0"` |
| `registry.type` | string | no | `none` | Model artifact source |
| `registry.tracking_uri` | string | if mlflow | — | MLflow server URL |
| `registry.region` | string | if sagemaker | — | AWS region |
| `serving.type` | string | no | `none` | Model endpoint type |
| `serving.champion_url` | string | if not none | — | Champion model URL |
| `serving.challenger_url` | string | if not none | — | Challenger model URL |
| `serving.auth.type` | string | no | `none` | Auth method |
| `serving.auth.token` | string | if auth | — | Token or `${ENV_VAR}` |
| `serving.ready_check.path` | string | no | `/health` | Readiness probe path |
| `serving.ready_check.timeout_seconds` | int | no | `120` | Max wait time |
| `serving.ready_check.interval_seconds` | int | no | `10` | Poll interval |
| `llm_judge.provider` | string | if llm_judge gate | — | LLM provider |
| `llm_judge.model` | string | if llm_judge gate | — | Model ID |
| `llm_judge.api_key` | string | if llm_judge gate | — | API key |
| `security.trigger_secret` | string | yes | — | Shared secret for auth |
