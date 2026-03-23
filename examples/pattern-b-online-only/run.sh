#!/usr/bin/env bash
set -euo pipefail

GATEKEEPER_URL="${GATEKEEPER_URL:-http://localhost:8000}"
GATEKEEPER_SECRET="${GATEKEEPER_SECRET:-dev-secret}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Pattern B: Online-Only ==="
echo "Triggering online eval gates with canary..."

RESPONSE=$(curl -sf \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
  -d "$(jq -n \
    --arg yaml "$(cat "$SCRIPT_DIR/gatekeeper.yaml")" \
    '{
      model_name: "demo-llm",
      candidate_version: "v2.0.0",
      phase: "online",
      gatekeeper_yaml: $yaml,
      triggered_by: "demo"
    }')" \
  "$GATEKEEPER_URL/api/v1/pipeline/trigger")

RUN_ID=$(echo "$RESPONSE" | jq -r '.pipeline_run_id')
echo "Pipeline run: $RUN_ID"

echo "Polling for results..."
for i in $(seq 1 120); do
  sleep 5
  RUN=$(curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID")
  STATUS=$(echo "$RUN" | jq -r '.online_status')
  echo "  [$((i * 5))s] online_status=$STATUS"
  if [ "$STATUS" = "promoted" ] || [ "$STATUS" = "rolled_back" ] || [ "$STATUS" = "failed" ]; then
    echo ""
    echo "=== Gate Report ==="
    curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID/report" | jq '.'
    echo ""
    echo "=== Canary Snapshots ==="
    curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID/canary" | jq '.'
    exit 0
  fi
done

echo "Timeout waiting for results"
exit 1
