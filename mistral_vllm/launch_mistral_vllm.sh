#!/usr/bin/env bash
# launch_mistral_vllm.sh
# Spin up a (Dedicated Instance or Dedicated Host) EC2 and auto-run a Mistral vLLM server on port 8000.
# Requires: AWS CLI v2, jq. Assumes a GPU-ready AMI (e.g., AWS DLAMI/NVIDIA) with drivers + nvidia-docker.
# Be strict; fall back if pipefail unsupported (some minimal bash environments)
set -euo pipefail 2>/dev/null || set -eu

# --- Usage & config -----------------------------------------------------------
ENV_FILE="${1:-mistral.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Config file not found: $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

# Required vars (must be present in mistral.env or via environment)
: "${AWS_REGION:?}"
: "${AMI_ID:?}"
: "${INSTANCE_TYPE:?}"
: "${SUBNET_ID:?}"
: "${SECURITY_GROUP_ID:?}"
: "${KEY_NAME:?}"
: "${TENANCY:?}"               # dedicated | host
: "${MODEL_ID:?}"
: "${EXPOSE_PORT:=8000}"
: "${IAM_INSTANCE_PROFILE_ARN:?}"

# Optional
: "${HOST_ID:=}"               # required if TENANCY=host
: "${AVAILABILITY_ZONE:=}"     # required if TENANCY=host
: "${SSM_HF_TOKEN_PARAM:=}"    # optional: SSM SecureString name for HF token
: "${EIP_ALLOCATION_ID:=}"     # optional: allocate/associate EIP
: "${TARGET_GROUP_ARN:=}"      # optional: register instance to ALB/NLB
: "${TAGS:=Project=LLM,Env=Dev,Owner=YourTeam}"

# Wait knobs (bounded waits; can override in env file)
: "${INSTANCE_WAIT_SECS:=1800}"     # time budget for instance state 'running'
: "${STATUS_OK_WAIT_SECS:=1800}"    # time budget for both status checks 'ok'
: "${HEALTH_WAIT_SECS:=1200}"       # time budget for vLLM HTTP health
: "${HEALTH_URL_PATH:=/v1/models}"  # cheap GET path
: "${HEALTH_EXPECT:=200}"           # expected HTTP code

command -v aws >/dev/null 2>&1 || { echo "aws CLI not found in PATH" >&2; exit 1; }
command -v jq  >/dev/null 2>&1 || { echo "jq not found in PATH" >&2; exit 1; }

# --- TagSpecifications builder ------------------------------------------------
IFS=',' read -r -a __tag_pairs <<< "$TAGS"
TAG_JSON=$(printf '%s\n' "${__tag_pairs[@]}" | jq -R 'split("=") | {Key:.[0], Value:.[1]}' | jq -s '.')
# For CLI arg (single-line)
TAG_JSON_COMPACT=$(echo "$TAG_JSON" | jq -c '.')

# --- Build User Data (bootstrap on instance) ---------------------------------
USERDATA_FILE="$(mktemp /tmp/vllm-userdata.XXXXXX.sh)"

cat > "$USERDATA_FILE" <<'EOF'
#!/bin/bash
set -euxo pipefail

# Persist a few values for sub-steps (set by the launcher below)
# shellcheck disable=SC1091
source /etc/environment || true
: "${AWS_REGION:?Missing AWS_REGION in /etc/environment}"
: "${EXPOSE_PORT:?Missing EXPOSE_PORT in /etc/environment}"
: "${MODEL_ID:?Missing MODEL_ID in /etc/environment}"
SSM_HF_TOKEN_PARAM="${SSM_HF_TOKEN_PARAM:-}"

# Install Docker if missing (DLAMI usually has it)
if ! command -v docker >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y docker.io
    systemctl enable docker
    systemctl start docker
  else
    yum -y update || true
    yum install -y docker
    systemctl enable docker
    systemctl start docker
  fi
fi

# Fetch Hugging Face token from SSM (optional)
HF_TOKEN=""
if [[ -n "${SSM_HF_TOKEN_PARAM}" ]]; then
  # AWS CLI is in DLAMI; if not, install a minimal one (rare)
  if ! command -v aws >/dev/null 2>&1; then
    echo "AWS CLI missing on instance; installing..." || true
    # Minimal fallback omitted for brevity; DLAMI should already have it.
  fi
  set +e
  HF_TOKEN="$(aws ssm get-parameter \
    --name "${SSM_HF_TOKEN_PARAM}" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text \
    --region "${AWS_REGION}")"
  set -e
fi

# Write token to env file for docker
echo "HF_TOKEN=${HF_TOKEN}" > /root/vllm.env

# Pull & run vLLM OpenAI-compatible server
docker pull vllm/vllm-openai:latest
docker rm -f vllm || true
docker run -d --name vllm --gpus all --ipc=host \
  --env-file /root/vllm.env \
  -p ${EXPOSE_PORT}:8000 \
  vllm/vllm-openai:latest \
  --model ${MODEL_ID} \
  --tokenizer-mode mistral \
  --config-format mistral \
  --load-format mistral

sleep 8
docker logs vllm > /var/log/vllm.log || true
EOF

# Prepend environment lines that the instance will need:
{
  echo "echo 'AWS_REGION=${AWS_REGION}' >> /etc/environment"
  echo "echo 'EXPOSE_PORT=${EXPOSE_PORT}' >> /etc/environment"
  echo "echo 'MODEL_ID=${MODEL_ID}' >> /etc/environment"
  if [[ -n "${SSM_HF_TOKEN_PARAM}" ]]; then
    echo "echo 'SSM_HF_TOKEN_PARAM=${SSM_HF_TOKEN_PARAM}' >> /etc/environment"
  fi
} | cat - "$USERDATA_FILE" > "${USERDATA_FILE}.tmp" && mv "${USERDATA_FILE}.tmp" "$USERDATA_FILE"

# --- Placement args -----------------------------------------------------------
PLACEMENT_ARGS=( "--placement" "Tenancy=${TENANCY}" )
if [[ "${TENANCY}" == "host" ]]; then
  : "${HOST_ID:?TENANCY=host requires HOST_ID}"
  : "${AVAILABILITY_ZONE:?TENANCY=host requires AVAILABILITY_ZONE}"
  PLACEMENT_ARGS=( "--placement" "Tenancy=host,HostId=${HOST_ID},AvailabilityZone=${AVAILABILITY_ZONE}" )
fi

# --- Launch the instance ------------------------------------------------------
echo "Launching EC2 instance in ${AWS_REGION}..."
RUN_JSON=$(aws ec2 run-instances \
  --region "$AWS_REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --network-interfaces "DeviceIndex=0,SubnetId=${SUBNET_ID},Groups=${SECURITY_GROUP_ID},AssociatePublicIpAddress=true" \
  "${PLACEMENT_ARGS[@]}" \
  --iam-instance-profile Arn="${IAM_INSTANCE_PROFILE_ARN}" \
  --user-data "file://${USERDATA_FILE}" \
  --tag-specifications \
    "ResourceType=instance,Tags=${TAG_JSON_COMPACT}" \
    "ResourceType=volume,Tags=${TAG_JSON_COMPACT}" \
  --output json)

INSTANCE_ID=$(echo "$RUN_JSON" | jq -r '.Instances[0].InstanceId')
if [[ -z "${INSTANCE_ID}" || "${INSTANCE_ID}" == "null" ]]; then
  echo "Failed to obtain InstanceId" >&2
  exit 1
fi
echo "Instance: ${INSTANCE_ID}"

# --- Wait bounded for 'running' ----------------------------------------------
deadline=$(( $(date +%s) + INSTANCE_WAIT_SECS ))
while true; do
  state=$(aws ec2 describe-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" \
          --query "Reservations[0].Instances[0].State.Name" --output text 2>/dev/null || echo "unknown")
  if [[ "$state" == "running" ]]; then
    break
  fi
  if (( $(date +%s) > deadline )); then
    echo "Timed out waiting for instance to be 'running' (budget ${INSTANCE_WAIT_SECS}s)" >&2
    exit 1
  fi
  echo "Waiting for 'running' (current: $state)..."
  sleep 10
done

DESC_JSON=$(aws ec2 describe-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID")
PUBLIC_IP=$(echo "$DESC_JSON"  | jq -r '.Reservations[0].Instances[0].PublicIpAddress // empty')
PUBLIC_DNS=$(echo "$DESC_JSON" | jq -r '.Reservations[0].Instances[0].PublicDnsName // empty')
AZ=$(echo "$DESC_JSON"         | jq -r '.Reservations[0].Instances[0].Placement.AvailabilityZone')

echo "AZ: $AZ"
echo "Public IP: ${PUBLIC_IP:-<none>}"
echo "Public DNS: ${PUBLIC_DNS:-<none>}"

# --- Optionally wait for both status checks OK (bounded) ----------------------
deadline=$(( $(date +%s) + STATUS_OK_WAIT_SECS ))
while true; do
  js=$(aws ec2 describe-instance-status --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" --include-all-instances)
  istat=$(echo "$js" | jq -r '.InstanceStatuses[0].InstanceStatus.Status // "initializing"')
  sstat=$(echo "$js" | jq -r '.InstanceStatuses[0].SystemStatus.Status   // "initializing"')
  if [[ "$istat" == "ok" && "$sstat" == "ok" ]]; then
    break
  fi
  if (( $(date +%s) > deadline )); then
    echo "Timed out waiting for instance status checks (Instance=$istat, System=$sstat)" >&2
    exit 1
  fi
  echo "Waiting for status checks OK (Instance=$istat, System=$sstat)..."
  sleep 15
done

# --- Optional: associate EIP --------------------------------------------------
if [[ -n "${EIP_ALLOCATION_ID}" ]]; then
  echo "Associating Elastic IP allocation ${EIP_ALLOCATION_ID}..."
  aws ec2 associate-address --region "$AWS_REGION" \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$EIP_ALLOCATION_ID" >/dev/null
  sleep 3
  DESC_JSON=$(aws ec2 describe-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID")
  PUBLIC_IP=$(echo "$DESC_JSON" | jq -r '.Reservations[0].Instances[0].PublicIpAddress // empty')
  echo "Elastic IP now: $PUBLIC_IP"
fi

# --- Optional: register to Target Group --------------------------------------
if [[ -n "${TARGET_GROUP_ARN}" ]]; then
  echo "Registering instance to target group ${TARGET_GROUP_ARN} on port ${EXPOSE_PORT}..."
  aws elbv2 register-targets --region "$AWS_REGION" \
    --target-group-arn "$TARGET_GROUP_ARN" \
    --targets "Id=${INSTANCE_ID},Port=${EXPOSE_PORT}" >/dev/null
  echo "Registered."
fi

# --- Optional: vLLM health check (bounded) -----------------------------------
if [[ -n "${PUBLIC_IP:-}" ]]; then
  url="http://${PUBLIC_IP}:${EXPOSE_PORT}${HEALTH_URL_PATH}"
  echo "Probing vLLM health at ${url} (expect ${HEALTH_EXPECT})..."
  health_deadline=$(( $(date +%s) + HEALTH_WAIT_SECS ))
  while true; do
    code=$(curl -s -o /dev/null -m 3 -w "%{http_code}" "$url" || echo 000)
    if [[ "$code" == "${HEALTH_EXPECT}" ]]; then
      echo "vLLM healthy at: ${url}"
      break
    fi
    if (( $(date +%s) > health_deadline )); then
      echo "Timed out waiting for vLLM health at ${url} (last code ${code})" >&2
      exit 1
    fi
    echo "Waiting for vLLM health... last=${code}"
    sleep 5
  done
fi

# --- Final summary (parsed by Python wrapper) --------------------------------
API_URL="http://${PUBLIC_IP:-<set up LB or EIP>}:${EXPOSE_PORT}/v1/chat/completions"
echo ""
echo "=== Done ==="
echo "Instance ID: ${INSTANCE_ID}"
echo "Public IP:   ${PUBLIC_IP:-<none>}"
echo "Public DNS:  ${PUBLIC_DNS:-<none>}"
echo "API URL:     ${API_URL}"
