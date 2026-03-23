#!/usr/bin/env bash
set -euo pipefail

# Read gatekeeper.yaml content
if [ ! -f "$GATEKEEPER_YAML" ]; then
  echo "::error::gatekeeper.yaml not found at $GATEKEEPER_YAML"
  exit 1
fi

YAML_CONTENT=$(cat "$GATEKEEPER_YAML")

# Build JSON payload
PAYLOAD=$(jq -n \
  --arg model_name "$MODEL_NAME" \
  --arg candidate_version "$CANDIDATE_VERSION" \
  --arg phase "$PHASE" \
  --arg gatekeeper_yaml "$YAML_CONTENT" \
  --arg triggered_by "github_actions" \
  --arg run_id "${GITHUB_RUN_ID:-}" \
  --arg sha "${GITHUB_SHA:-}" \
  --arg ref "${GITHUB_REF:-}" \
  --arg actor "${GITHUB_ACTOR:-}" \
  --arg run_url "${GITHUB_RUN_URL:-}" \
  '{
    model_name: $model_name,
    candidate_version: $candidate_version,
    phase: $phase,
    gatekeeper_yaml: $gatekeeper_yaml,
    triggered_by: $triggered_by,
    github_context: {
      run_id: $run_id,
      sha: $sha,
      ref: $ref,
      actor: $actor,
      run_url: $run_url
    }
  }')

echo "Triggering GateKeeper pipeline for $MODEL_NAME ($CANDIDATE_VERSION)..."

RESPONSE=$(curl -sf \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
  -d "$PAYLOAD" \
  "${GATEKEEPER_URL}/api/v1/pipeline/trigger")

PIPELINE_RUN_ID=$(echo "$RESPONSE" | jq -r '.pipeline_run_id')
REPORT_URL=$(echo "$RESPONSE" | jq -r '.report_url')

if [ -z "$PIPELINE_RUN_ID" ] || [ "$PIPELINE_RUN_ID" = "null" ]; then
  echo "::error::Failed to trigger pipeline. Response: $RESPONSE"
  exit 1
fi

echo "Pipeline triggered: $PIPELINE_RUN_ID"
echo "Report: ${GATEKEEPER_URL}${REPORT_URL}"

echo "pipeline_run_id=$PIPELINE_RUN_ID" >> "$GITHUB_OUTPUT"
echo "report_url=${GATEKEEPER_URL}${REPORT_URL}" >> "$GITHUB_OUTPUT"
