#!/usr/bin/env bash
set -euo pipefail

GATEKEEPER_URL="${GATEKEEPER_URL:-http://localhost:8000}"
GATEKEEPER_SECRET="${GATEKEEPER_SECRET:-dev-secret}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Pattern C: Chained (Offline → Online) ==="
echo "Triggering both phases..."

RESPONSE=$(curl -sf \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
  -d "$(jq -n \
    --arg yaml "$(cat "$SCRIPT_DIR/gatekeeper.yaml")" \
    '{
      model_name: "demo-chained",
      candidate_version: "v3.0.0",
      phase: "both",
      gatekeeper_yaml: $yaml,
      triggered_by: "demo"
    }')" \
  "$GATEKEEPER_URL/api/v1/pipeline/trigger")

RUN_ID=$(echo "$RESPONSE" | jq -r '.pipeline_run_id')
echo "Pipeline run: $RUN_ID"

echo "Polling for results..."
for i in $(seq 1 180); do
  sleep 5
  RUN=$(curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID")
  OFFLINE=$(echo "$RUN" | jq -r '.offline_status')
  ONLINE=$(echo "$RUN" | jq -r '.online_status')
  echo "  [$((i * 5))s] offline=$OFFLINE online=$ONLINE"

  if [ "$OFFLINE" = "failed" ]; then
    echo "Offline gates failed — online phase skipped."
    curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID/report" | jq '.'
    exit 1
  fi

  if [ "$ONLINE" = "promoted" ] || [ "$ONLINE" = "rolled_back" ] || [ "$ONLINE" = "failed" ]; then
    echo ""
    echo "=== Gate Report ==="
    curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$RUN_ID/report" | jq '.'
    exit 0
  fi
done

echo "Timeout waiting for results"
exit 1
