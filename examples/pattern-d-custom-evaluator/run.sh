#!/usr/bin/env bash
set -euo pipefail

GATEKEEPER_URL="${GATEKEEPER_URL:-http://localhost:8000}"
GATEKEEPER_SECRET="${GATEKEEPER_SECRET:-dev-secret}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Pattern D: Custom Evaluator Plugin ==="
echo "Installing custom evaluator..."
pip install -e "$SCRIPT_DIR/my_custom_eval" --quiet

echo "Triggering pipeline with custom word_count evaluator..."

RESPONSE=$(curl -sf \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
  -d "$(jq -n \
    --arg yaml "$(cat "$SCRIPT_DIR/gatekeeper.yaml")" \
    '{
      model_name: "demo-custom",
      candidate_version: "v1.0.0",
      phase: "offline",
      gatekeeper_yaml: $yaml,
      triggered_by: "demo"
    }')" \
  "$GATEKEEPER_URL/api/v1/pipeline/trigger")

RUN_ID=$(echo "$RESPONSE" | jq -r '.pipeline_run_id')
echo "Pipeline run: $RUN_ID"

echo "Polling for results..."
for i in $(seq 1 60); do
  sleep 5
  STATUS=$(curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID" | jq -r '.offline_status')
  echo "  [$((i * 5))s] offline_status=$STATUS"
  if [ "$STATUS" = "passed" ] || [ "$STATUS" = "failed" ]; then
    echo ""
    echo "=== Gate Report ==="
    curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID/report" | jq '.'
    exit 0
  fi
done

echo "Timeout waiting for results"
exit 1
