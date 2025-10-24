#!/usr/bin/env bash
set -euo pipefail

# Fix for Git Bash on Windows - prevent path conversion
export MSYS_NO_PATHCONV=1

# download_logs.sh <jobs.json>
# Requires: aws, jq, python3, curl

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

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <jobs.json>" >&2
  exit 1
fi

JOBS_FILE="$1"

REGION_JSON="$(jq -r '.region' "$JOBS_FILE")"

detect_region() {
  local r="${REGION_JSON:-}"
  if [[ -n "$r" && "$r" != "null" ]]; then echo "$r"; return; fi
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

# Prevent Git Bash from converting paths on Windows
export MSYS_NO_PATHCONV=1

START_ISO="$(jq -r '.startISO' "$JOBS_FILE")"
END_ISO="$(jq -r '.endISO' "$JOBS_FILE")"

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

jobs_len="$(jq '.jobs | length' "$JOBS_FILE")"
echo "Downloading logs for $jobs_len job(s) from $START_ISO to $END_ISO in $REGION..."

# Escape a value for inclusion inside a double-quoted filter pattern.
escape_for_filter() {
  local s="$1"
  s="${s//\\/\\\\}"   # backslashes
  s="${s//\"/\\\"}"   # quotes
  printf '%s' "$s"
}

# Simple exponential backoff on throttling
aws_call() {
  local attempt=0
  local max_attempts=6
  local delay=1
  while :; do
    if out="$(eval "$1" 2>&1)"; then
      # Check if the output contains an AWS CLI error message (not application errors)
      if echo "$out" | grep -qiE '^An error occurred.*when calling.*operation'; then
        echo "$out" >&2
        return 1
      fi
      printf '%s' "$out"
      return 0
    fi
    if grep -qiE 'Throttl|Rate exceed|TooManyRequestsException' <<<"$out"; then
      attempt=$((attempt+1))
      if (( attempt >= max_attempts )); then
        echo "$out" >&2
        return 1
      fi
      sleep "$delay"
      delay=$((delay*2))
    else
      echo "$out" >&2
      return 1
    fi
  done
}

fetch_all_pages() {
  local log_group="$1"
  local filter_pattern="$2"  # may be empty
  local out_file="$3"

  # Debug output
  echo "DEBUG: fetch_all_pages called with log_group='$log_group'"
  echo "DEBUG: log_group hex dump: $(printf '%s' "$log_group" | od -c)"
  
  # Fix for Git Bash on Windows - prevent path conversion
  # Use MSYS_NO_PATHCONV=1 to prevent Git Bash from converting / paths to Windows paths
  export MSYS_NO_PATHCONV=1

  local next_token=""
  local first_page=true
  local tmp_json
  # Use a more Windows-compatible temporary file approach
  tmp_json="tmp_events_$$.json"
  # Start with empty file, not JSON array
  : > "$tmp_json"
  echo "DEBUG: Created temporary file: $tmp_json"

  while :; do
    local cmd
    if [[ -n "$filter_pattern" ]]; then
      if $first_page; then
        cmd="aws logs filter-log-events \
          --region '$REGION' \
          --log-group-name '$log_group' \
          --start-time '$START_MS' \
          --end-time '$END_MS' \
          --filter-pattern '$filter_pattern' \
          --output json"
      else
        cmd="aws logs filter-log-events \
          --region '$REGION' \
          --log-group-name '$log_group' \
          --start-time '$START_MS' \
          --end-time '$END_MS' \
          --filter-pattern '$filter_pattern' \
          --next-token '$next_token' \
          --output json"
      fi
    else
      if $first_page; then
        cmd="aws logs filter-log-events \
          --region '$REGION' \
          --log-group-name '$log_group' \
          --start-time '$START_MS' \
          --end-time '$END_MS' \
          --output json"
      else
        cmd="aws logs filter-log-events \
          --region '$REGION' \
          --log-group-name '$log_group' \
          --start-time '$START_MS' \
          --end-time '$END_MS' \
          --next-token '$next_token' \
          --output json"
      fi
    fi

    echo "DEBUG: About to execute AWS command: $cmd"
    resp="$(aws_call "$cmd" 2>&1)"
    aws_exit_code=$?
    
    echo "DEBUG: AWS command exit code: $aws_exit_code"
    echo "DEBUG: AWS response length: ${#resp}"
    
    if [[ $aws_exit_code -ne 0 ]]; then
      echo "ERROR: AWS command failed with exit code $aws_exit_code"
      echo "ERROR: Response: $resp"
      break
    fi
    
    # Check if the response is valid JSON
    if ! echo "$resp" | jq empty 2>/dev/null; then
      echo "ERROR: AWS response is not valid JSON:"
      echo "$resp"
      break
    fi
    
    # Check if the response contains an error
    if echo "$resp" | jq -e '.errorMessage' >/dev/null 2>&1; then
      echo "ERROR: AWS API returned an error:"
      echo "$resp" | jq -r '.errorMessage'
      break
    fi
    
    # Check if we have events in the response
    if echo "$resp" | jq -e '.events' >/dev/null 2>&1; then
      event_count=$(echo "$resp" | jq '.events | length')
      echo "DEBUG: Found $event_count events in response"
      echo "DEBUG: Writing events to temporary file: $tmp_json"
      printf '%s\n' "$resp" | jq -c '.events[]?' >> "$tmp_json"
      echo "DEBUG: Temporary file size after write: $(wc -c < "$tmp_json")"
    else
      echo "DEBUG: No events found in response"
    fi

    next_token="$(printf '%s\n' "$resp" | jq -r '.nextToken // empty')"
    first_page=false
    [[ -z "$next_token" ]] && break
  done

  # Check if we have any data to process
  if [[ -s "$tmp_json" ]]; then
    echo "DEBUG: Processing temporary file: $tmp_json"
    echo "DEBUG: Temporary file content preview:"
    head -3 "$tmp_json"
    
    # Output as JSON array with all log events, properly sorted
    jq -s 'sort_by(.timestamp)' "$tmp_json" > "$out_file"
    count=$(jq '. | length' "$out_file")
    echo "DEBUG: Processed $count log entries to $out_file"
  else
    echo "DEBUG: No log entries found, creating empty JSON array: $out_file"
    echo "[]" > "$out_file"
  fi

  rm -f "$tmp_json"
}

idx=0
while [[ $idx -lt $jobs_len ]]; do
  job="$(jq -c ".jobs[$idx]" "$JOBS_FILE")"
  log_group="$(echo "$job" | jq -r '.logGroup')"
  out_name="$(echo "$job" | jq -r '.outputName')"
  label_key="$(echo "$job" | jq -r '.labelKey // empty')"
  label_val="$(echo "$job" | jq -r '.labelValue // empty')"
  
  # If output name ends with .json, create a raw version for transformation
  if [[ "$out_name" == *.json ]]; then
    raw_name="${out_name%.json}-raw.json"
  else
    raw_name="$out_name"
  fi
  
  # Debug output
  echo "DEBUG: Raw job data: $job"
  echo "DEBUG: Extracted log_group: '$log_group'"
  echo "DEBUG: log_group length: ${#log_group}"
  echo "DEBUG: log_group hex dump: $(printf '%s' "$log_group" | od -c)"

  filter_pattern=""
  if [[ -n "$label_key" && -n "$label_val" ]]; then
    esc_val="$(escape_for_filter "$label_val")"
    # Example: { $.kubernetes.labels.app = "ms1" }
    filter_pattern="{ \$.$label_key = \"$esc_val\" }"
    echo "[$((idx+1))/$jobs_len] $log_group label $label_key=$label_val -> $raw_name"
  else
    echo "[$((idx+1))/$jobs_len] $log_group (no label filter) -> $raw_name"
  fi

  fetch_all_pages "$log_group" "$filter_pattern" "$raw_name"

  idx=$((idx+1))
done

echo "Done."