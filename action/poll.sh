#!/usr/bin/env bash
set -euo pipefail

ELAPSED=0

echo "Polling pipeline run $PIPELINE_RUN_ID (interval: ${POLL_INTERVAL}s, timeout: ${TIMEOUT}s)..."

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  RESPONSE=$(curl -sf \
    -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
    "${GATEKEEPER_URL}/api/v1/pipeline/runs/${PIPELINE_RUN_ID}" 2>/dev/null || echo '{}')

  OFFLINE_STATUS=$(echo "$RESPONSE" | jq -r '.offline_status // "unknown"')
  ONLINE_STATUS=$(echo "$RESPONSE" | jq -r '.online_status // "unknown"')

  echo "  [${ELAPSED}s] offline=$OFFLINE_STATUS online=$ONLINE_STATUS"

  # Determine if we're done based on which phase was requested
  DONE=false
  RESULT="unknown"

  case "$PHASE" in
    offline)
      case "$OFFLINE_STATUS" in
        passed)  DONE=true; RESULT="passed" ;;
        failed)  DONE=true; RESULT="failed" ;;
      esac
      ;;
    online)
      case "$ONLINE_STATUS" in
        promoted)    DONE=true; RESULT="passed" ;;
        passed)      DONE=true; RESULT="passed" ;;
        failed)      DONE=true; RESULT="failed" ;;
        rolled_back) DONE=true; RESULT="failed" ;;
      esac
      ;;
    both)
      # For chained: wait for online phase to finish (or offline to fail)
      if [ "$OFFLINE_STATUS" = "failed" ]; then
        DONE=true; RESULT="failed"
      elif [ "$ONLINE_STATUS" = "promoted" ] || [ "$ONLINE_STATUS" = "passed" ]; then
        DONE=true; RESULT="passed"
      elif [ "$ONLINE_STATUS" = "failed" ] || [ "$ONLINE_STATUS" = "rolled_back" ]; then
        DONE=true; RESULT="failed"
      elif [ "$ONLINE_STATUS" = "skipped" ] && [ "$OFFLINE_STATUS" = "passed" ]; then
        DONE=true; RESULT="passed"
      fi
      ;;
  esac

  if [ "$DONE" = "true" ]; then
    echo "Pipeline complete: $RESULT"
    echo "result=$RESULT" >> "$GITHUB_OUTPUT"

    # Print gate summary
    REPORT=$(curl -sf \
      -H "X-GateKeeper-Secret: $GATEKEEPER_SECRET" \
      "${GATEKEEPER_URL}/api/v1/pipeline/runs/${PIPELINE_RUN_ID}/report" 2>/dev/null || echo '{}')

    echo ""
    echo "=== Gate Report ==="
    echo "$REPORT" | jq '.' 2>/dev/null || echo "$REPORT"
    echo "==================="

    if [ "$RESULT" = "failed" ]; then
      echo "::error::GateKeeper gates failed for $PIPELINE_RUN_ID"
      exit 1
    fi
    exit 0
  fi

  sleep "$POLL_INTERVAL"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

echo "::error::Timeout waiting for pipeline $PIPELINE_RUN_ID after ${TIMEOUT}s"
echo "result=timeout" >> "$GITHUB_OUTPUT"
exit 1
