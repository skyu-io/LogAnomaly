#!/usr/bin/env bash
set -euo pipefail

# discover_labels.sh <log_group> <label_key> <region> <start_iso> <end_iso>
# Prints a JSON array of distinct label values seen in the group for the time window.
# Requires: aws, jq, python, curl

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 2; }; }

# Check for python command (try different variants)
PYTHON_CMD=""
for cmd in python python3 py; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    echo "Missing dependency: python (tried python, python3, py)" >&2
    exit 2
fi

need aws; need jq; need curl

if [[ $# -lt 5 ]]; then
  echo "Usage: $0 <log_group> <label_key> <region> <start_iso> <end_iso>" >&2
  exit 1
fi

LOG_GROUP="$1"
LABEL_KEY="$2"
REGION_INPUT="$3"
START_ISO="$4"
END_ISO="$5"

detect_region() {
  local r="${REGION_INPUT:-}"
  if [[ -n "$r" ]]; then echo "$r"; return; fi
  if [[ -n "${AWS_REGION:-}" ]]; then echo "$AWS_REGION"; return; fi
  if [[ -n "${AWS_DEFAULT_REGION:-}" ]]; then echo "$AWS_DEFAULT_REGION"; return; fi
  local tok
  tok=$(curl -sS --connect-timeout 1 -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)
  if [[ -n "$tok" ]]; then
    curl -sS -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r '.region' || true
  else
    curl -sS http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r '.region' || true
  fi
}

REGION="$(detect_region)"
REGION="${REGION:-us-east-1}"

to_epoch_ms() {
  $PYTHON_CMD - "$1" <<'PY'
import sys, datetime
iso = sys.argv[1]
dt = datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))
print(int(dt.timestamp()*1000))
PY
}

START_MS="$(to_epoch_ms "$START_ISO")"
END_MS="$(to_epoch_ms "$END_ISO")"

# NOTE:
# If your logs are JSON, this regex is fine:
#   "kubernetes.labels.app":"value"
# If your label path is nested, pass the leaf key you want to extract into LABEL_KEY (e.g., "kubernetes.labels.app").
# This pattern will match ..."<LABEL_KEY>":"<value>"...
# If <value> can contain quotes, you'll need to refine the parse.
QUERY=$(cat <<EOF
fields @message
| parse @message /"${LABEL_KEY}"\\s*:\\s*"(?<label>[^"]+)"/
| filter ispresent(label)
| stats count() by label
| sort label asc
EOF
)

QUERY_ID="$(aws logs start-query \
  --region "$REGION" \
  --log-group-name "$LOG_GROUP" \
  --start-time "$START_MS" \
  --end-time "$END_MS" \
  --query-string "$QUERY" \
  --output text \
  --query 'queryId' 2>/dev/null || true)"

if [[ -z "$QUERY_ID" || "$QUERY_ID" == "None" ]]; then
  echo "[]" ; exit 0
fi

# Poll up to ~60s
STATUS="Running"
DEADLINE=$((SECONDS + 60))
while [[ "$STATUS" == "Running" || "$STATUS" == "Scheduled" ]]; do
  sleep 1
  STATUS="$(aws logs get-query-results --region "$REGION" --query-id "$QUERY_ID" --output text --query 'status' 2>/dev/null || echo "Failed")"
  if (( SECONDS > DEADLINE )); then
    STATUS="Timeout"
    break
  fi
done

if [[ "$STATUS" != "Complete" ]]; then
  # On timeout or failure, return an empty list so the caller can decide.
  echo "[]" ; exit 0
fi

# Return unique label values as a JSON array (sorted)
aws logs get-query-results --region "$REGION" --query-id "$QUERY_ID" \
| jq -r '[ .results[]
          | (map(select(.field=="label"))[0].value)
        ] | map(select(. != null))
          | unique
          | sort'