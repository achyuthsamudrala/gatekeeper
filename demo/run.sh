#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# GateKeeper Blog Demo
#
# Runs two stories end-to-end through the real eval engine:
#   Story 1 — Blocked: low-accuracy model fails the accuracy gate
#   Story 2 — Passed:  high-accuracy model passes all gates
#
# Prerequisites: docker compose stack running (make up && make migrate)
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
GATEKEEPER_URL="${GATEKEEPER_URL:-http://localhost:8000}"
GATEKEEPER_SECRET="${GATEKEEPER_SECRET:-changeme}"
MOCK_PORT=9100
MOCK_PID=""

mkdir -p "$RESULTS_DIR"

cleanup() {
  echo ""
  echo "Cleaning up..."
  if [ -n "$MOCK_PID" ] && kill -0 "$MOCK_PID" 2>/dev/null; then
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
    echo "  Mock model stopped"
  fi
  # Restore original server.yaml
  cd "$PROJECT_DIR"
  cat > config/server.yaml <<'ORIGEOF'
version: "1.0"

registry:
  type: none

serving:
  type: none

llm_judge:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}

security:
  trigger_secret: ${GATEKEEPER_SECRET}
ORIGEOF
  echo "  Original server.yaml restored"
}
trap cleanup EXIT

# ── Generate demo data ────────────────────────────────────────────────────────

echo "Generating eval and reference datasets..."
cd "$PROJECT_DIR"
source .venv/bin/activate && python demo/generate_data.py
echo ""

# ── Start mock model server ───────────────────────────────────────────────────

echo "Starting mock model server on port $MOCK_PORT..."
# Kill any stale process on the port
lsof -ti :"$MOCK_PORT" | xargs kill -9 2>/dev/null || true
sleep 1
cd "$PROJECT_DIR"
python -m uvicorn demo.mock_model:app --port "$MOCK_PORT" --log-level warning &
MOCK_PID=$!
sleep 2

if ! curl -sf "http://localhost:$MOCK_PORT/health" > /dev/null 2>&1; then
  echo "ERROR: Mock model server failed to start"
  exit 1
fi
echo "  Mock model running (PID $MOCK_PID)"
echo ""

# ── Copy data into backend container ──────────────────────────────────────────

echo "Copying demo data into backend container..."
docker compose exec -T backend mkdir -p /demo-data
docker compose cp demo/data/eval.jsonl backend:/demo-data/eval.jsonl
docker compose cp demo/data/reference.jsonl backend:/demo-data/reference.jsonl
echo "  Done"
echo ""

# ── Detect host address for Docker ────────────────────────────────────────────
# macOS: host.docker.internal, Linux: 172.17.0.1

if docker compose exec -T backend sh -c "getent hosts host.docker.internal" > /dev/null 2>&1; then
  DOCKER_HOST_ADDR="host.docker.internal"
else
  DOCKER_HOST_ADDR="172.17.0.1"
fi
echo "Docker host address: $DOCKER_HOST_ADDR"
echo ""

# ── Helper functions ──────────────────────────────────────────────────────────

write_server_config() {
  local mock_path="$1"
  cat > "$PROJECT_DIR/config/server.yaml" <<EOF
version: "1.0"

registry:
  type: none

serving:
  type: none
  challenger_url: http://${DOCKER_HOST_ADDR}:${MOCK_PORT}/${mock_path}
  champion_url: http://${DOCKER_HOST_ADDR}:${MOCK_PORT}/${mock_path}

llm_judge:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: \${ANTHROPIC_API_KEY}

security:
  trigger_secret: \${GATEKEEPER_SECRET}
EOF
}

restart_backend() {
  echo "  Restarting backend with new config..."
  cd "$PROJECT_DIR"
  docker compose restart backend > /dev/null 2>&1
  # Wait for health
  for i in $(seq 1 30); do
    if curl -sf "$GATEKEEPER_URL/health" > /dev/null 2>&1; then
      echo "  Backend ready"
      return
    fi
    sleep 1
  done
  echo "ERROR: Backend didn't become healthy"
  exit 1
}

trigger_pipeline() {
  local model_name="$1"
  local version="$2"
  local yaml_file="$3"

  local yaml_content
  yaml_content=$(cat "$yaml_file")

  curl -sf \
    -X POST \
    -H "Content-Type: application/json" \
    -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
    -d "$(jq -n \
      --arg model_name "$model_name" \
      --arg version "$version" \
      --arg yaml "$yaml_content" \
      '{
        model_name: $model_name,
        candidate_version: $version,
        phase: "offline",
        gatekeeper_yaml: $yaml,
        triggered_by: "blog_demo"
      }')" \
    "$GATEKEEPER_URL/api/v1/pipeline/trigger"
}

wait_for_completion() {
  local run_id="$1"
  local max_wait=120

  for i in $(seq 1 $max_wait); do
    local status
    status=$(curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$run_id" | jq -r '.offline_status')
    if [ "$status" = "passed" ] || [ "$status" = "failed" ]; then
      echo "  Completed: offline_status=$status (${i}s)"
      return
    fi
    if [ $((i % 5)) -eq 0 ]; then
      echo "  [$i s] offline_status=$status"
    fi
    sleep 1
  done
  echo "  WARNING: Timed out after ${max_wait}s"
}

build_result_json() {
  local story_title="$1"
  local run_id="$2"
  local yaml_file="$3"

  local run_detail audit_log yaml_content
  run_detail=$(curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$run_id")
  audit_log=$(curl -sf "$GATEKEEPER_URL/api/v1/pipeline/runs/$run_id/audit")
  yaml_content=$(cat "$yaml_file")

  local gates
  gates=$(echo "$run_detail" | jq '[.gate_results[] | {
    gate_name,
    evaluator: .gate_type,
    metric_name,
    metric_value,
    threshold,
    comparator,
    verdict: (if .passed == true then "PASS" elif .passed == false then "FAIL" else "SKIP" end),
    blocking,
    detail
  }]')

  local audit
  audit=$(echo "$audit_log" | jq '[.[] | {
    action,
    phase,
    timestamp: .created_at,
    actor
  }]')

  jq -n \
    --arg title "$story_title" \
    --arg model "$(echo "$run_detail" | jq -r '.model_name')" \
    --arg version "$(echo "$run_detail" | jq -r '.candidate_version')" \
    --arg status "$(echo "$run_detail" | jq -r '.offline_status')" \
    --arg run_id "$run_id" \
    --argjson overall_passed "$(echo "$run_detail" | jq '.offline_status == "passed"')" \
    --arg yaml "$yaml_content" \
    --argjson gates "$gates" \
    --argjson audit "$audit" \
    '{
      story: $title,
      pipeline_run: {
        id: $run_id,
        model_name: $model,
        candidate_version: $version,
        offline_status: $status,
        overall_passed: $overall_passed
      },
      config: ($yaml | split("\n") | map(select(length > 0))),
      gates: $gates,
      audit_trail: $audit
    }'
}

# ── Story 1: Blocked ─────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════════"
echo "  Story 1: Blocked — low-accuracy model fails accuracy gate"
echo "═══════════════════════════════════════════════════════════════"
echo ""

write_server_config "bad"
restart_backend

# Re-copy data (restart may clear /demo-data)
docker compose exec -T backend mkdir -p /demo-data
docker compose cp demo/data/eval.jsonl backend:/demo-data/eval.jsonl
docker compose cp demo/data/reference.jsonl backend:/demo-data/reference.jsonl

echo "  Triggering pipeline for sentiment-classifier v2.1-rc1..."
RESPONSE=$(trigger_pipeline "sentiment-classifier" "v2.1-rc1" "$SCRIPT_DIR/gatekeeper_story1.yaml")
RUN_ID=$(echo "$RESPONSE" | jq -r '.pipeline_run_id')
echo "  Pipeline run: $RUN_ID"

echo "  Waiting for eval engine to complete..."
wait_for_completion "$RUN_ID"

echo "  Writing demo/results/story1_blocked.json"
build_result_json \
  "Blocked: candidate fails accuracy gate" \
  "$RUN_ID" \
  "$SCRIPT_DIR/gatekeeper_story1.yaml" \
  > "$RESULTS_DIR/story1_blocked.json"

echo ""
jq '{ story, pipeline_run: .pipeline_run, gates: [.gates[] | {gate_name, verdict, metric_value, threshold}] }' \
  "$RESULTS_DIR/story1_blocked.json"
echo ""

# ── Story 2: Passed ──────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════════"
echo "  Story 2: Passed — high-accuracy model passes all gates"
echo "═══════════════════════════════════════════════════════════════"
echo ""

write_server_config "good"
restart_backend

docker compose exec -T backend mkdir -p /demo-data
docker compose cp demo/data/eval.jsonl backend:/demo-data/eval.jsonl
docker compose cp demo/data/reference.jsonl backend:/demo-data/reference.jsonl

echo "  Triggering pipeline for sentiment-classifier v2.2-rc1..."
RESPONSE=$(trigger_pipeline "sentiment-classifier" "v2.2-rc1" "$SCRIPT_DIR/gatekeeper_story2.yaml")
RUN_ID=$(echo "$RESPONSE" | jq -r '.pipeline_run_id')
echo "  Pipeline run: $RUN_ID"

echo "  Waiting for eval engine to complete..."
wait_for_completion "$RUN_ID"

echo "  Writing demo/results/story2_passed.json"
build_result_json \
  "Passed: candidate passes all gates" \
  "$RUN_ID" \
  "$SCRIPT_DIR/gatekeeper_story2.yaml" \
  > "$RESULTS_DIR/story2_passed.json"

echo ""
jq '{ story, pipeline_run: .pipeline_run, gates: [.gates[] | {gate_name, verdict, metric_value, threshold}] }' \
  "$RESULTS_DIR/story2_passed.json"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════════"
echo "  Done!"
echo ""
echo "  Results:"
echo "    demo/results/story1_blocked.json"
echo "    demo/results/story2_passed.json"
echo ""
echo "  Dashboard: http://localhost:3000"
echo "═══════════════════════════════════════════════════════════════"
