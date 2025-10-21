#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Optional, List

def check_instance_or_exit(
    instance_id: str,
    timeout: int = 60,
    profile: Optional[str] = None,
    region: Optional[str] = None,
) -> Optional[str]:
    """
    Single function that:
      1) checks EC2 health (running + both status checks 'ok') via AWS CLI
      2) if healthy -> returns Public IP (or None if no public IP)
      3) if unhealthy/not found/error -> prints message and exits(1)

    Args:
        instance_id: e.g., "i-0793b8fd8e26328a2"
        timeout: seconds for each AWS CLI call
        profile: optional AWS CLI profile
        region:  optional AWS region

    Returns:
        Public IP as string, or None if the instance has no public IP.
        (Process will have already exited with code 1 if unhealthy.)
    """
    base: List[str] = ["aws", "--no-cli-pager"]
    if profile:
        base += ["--profile", profile]
    if region:
        base += ["--region", region]

    # --- 1) Health check (your query; force JSON) ---
    status_cmd = base + [
        "ec2", "describe-instance-status",
        "--include-all-instances",
        "--instance-ids", instance_id,
        "--query", "InstanceStatuses[].{ID:InstanceId,State:InstanceState.Name,Sys:SystemStatus.Status,Inst:InstanceStatus.Status}",
        "--output", "json",
    ]
    try:
        print(f"Running command: {' '.join(status_cmd)}");
        status_proc = subprocess.run(
            status_cmd, capture_output=True, text=True, timeout=timeout, check=True
        )
        statuses = json.loads(status_proc.stdout or "[]")
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Timed out after {timeout}s checking {instance_id}.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] AWS CLI failed (exit {e.returncode}).\nSTDERR:\n{(e.stderr or '').strip()}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("[ERROR] Could not parse describe-instance-status output as JSON.", file=sys.stderr)
        sys.exit(1)

    if not statuses:
        print(f"[ERROR] No status returned for {instance_id}. Check region/profile/permissions.", file=sys.stderr)
        sys.exit(1)

    row = statuses[0]
    state = (row.get("State") or "").lower()
    sys_s = (row.get("Sys") or "").lower()
    inst_s = (row.get("Inst") or "").lower()
    healthy = (state == "running") and (sys_s == "ok") and (inst_s == "ok")

    if not healthy:
        print(
            f"[ERROR] Instance not healthy.\n"
            f"  ID: {row.get('ID')}  State: {row.get('State')}  "
            f"System: {row.get('Sys')}  Instance: {row.get('Inst')}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- 2) Healthy -> fetch Public IP (may be None) ---
    ip_cmd = base + [
        "ec2", "describe-instances",
        "--instance-ids", instance_id,
        "--query", "Reservations[].Instances[].PublicIpAddress",
        "--output", "json",
    ]
    try:
        ip_proc = subprocess.run(
            ip_cmd, capture_output=True, text=True, timeout=timeout, check=True
        )
        ips = json.loads(ip_proc.stdout or "[]")
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Timed out after {timeout}s fetching IP for {instance_id}.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] AWS CLI failed (exit {e.returncode}) while fetching IP.\nSTDERR:\n{(e.stderr or '').strip()}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("[ERROR] Could not parse describe-instances output as JSON.", file=sys.stderr)
        sys.exit(1)

    public_ip: Optional[str] = None
    if isinstance(ips, list):
        for ip in ips:
            if isinstance(ip, str) and ip.strip():
                public_ip = ip.strip()
                break

    return public_ip
