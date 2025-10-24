#!/usr/bin/env bash
set -euo pipefail

# Fix for Git Bash on Windows - prevent path conversion
export MSYS_NO_PATHCONV=1

# check_log_events.sh - Check if log groups have events in a time period
# Usage: ./check_log_events.sh [region] [start_time] [end_time]

REGION="${1:-ap-southeast-2}"
START_TIME="${2:-2025-10-19T14:14:49Z}"
END_TIME="${3:-2025-10-19T15:14:49Z}"

echo "Checking log events in region: $REGION"
echo "Time period: $START_TIME to $END_TIME"
echo ""

# Convert ISO times to epoch milliseconds
to_epoch_ms() {
  python - "$1" <<'PY'
import sys, datetime
iso = sys.argv[1]
dt = datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))
print(int(dt.timestamp()*1000))
PY
}

START_MS="$(to_epoch_ms "$START_TIME")"
END_MS="$(to_epoch_ms "$END_TIME")"

echo "Start time (ms): $START_MS"
echo "End time (ms): $END_MS"
echo ""

# List of log groups to check
LOG_GROUPS=(
  "/aws/lambda/aws-controltower-NotificationForwarder"
  "/aws/lambda/delete-name-tags-ap-southeast-2-w1lme"
  "/aws/lambda/BlueprinterStack-CustomVpcRestrictDefaultSGCustomR-2LwZWEd6uuhT"
)

for log_group in "${LOG_GROUPS[@]}"; do
  echo "Checking log group: $log_group"
  
  # Get a sample of events (limit to 1 to just check if any exist)
  result=$(aws logs filter-log-events \
    --region "$REGION" \
    --log-group-name "$log_group" \
    --start-time "$START_MS" \
    --end-time "$END_MS" \
    --max-items 1 \
    --output json 2>&1 || echo "ERROR")
  
  if echo "$result" | jq -e '.events | length > 0' >/dev/null 2>&1; then
    count=$(echo "$result" | jq '.events | length')
    echo "  ✓ Found $count event(s) (showing first 1)"
    echo "$result" | jq -r '.events[0] | "    " + (.timestamp | tostring) + " " + .message'
  elif echo "$result" | grep -q "ERROR"; then
    echo "  ✗ Error: $result"
  else
    echo "  ○ No events found in this time period"
  fi
  echo ""
done