#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

# Default CONFIG - can be overridden by passing config parameter
DEFAULT_CONFIG = [
    {"name": "lambda-app0",   "logGroup": "/aws/lambda/musatest1",                                                          "uniqueLabel": ""},
    {"name": "lambda-app1",   "logGroup": "/aws/lambda/cloudzero-connected-account-Disc-DiscoveryFunction-b2kdydG5QuEX",     "uniqueLabel": ""},
    {"name": "lambda-cluster0","logGroup": "/aws/eks/skyu-sandbox-k8s-cluster/cluster",                                      "uniqueLabel": "cluster"},
]

DISCOVER_SCRIPT = "./discover_labels.sh"
DOWNLOAD_SCRIPT  = "./download_logs.sh"
TRANSFORM_SCRIPT = "./transform_logs.py"

def _run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    # Use bash explicitly for shell commands on Windows
    if os.name == 'nt':  # Windows
        cmd = f"bash -c {shlex.quote(cmd)}"
    return subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)

def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

def _iso_minus_minutes(m: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

def _detect_region_from_imds() -> Optional[str]:
    """
    Try env first; then IMDSv2; fall back to IMDSv1. Works only on EC2.
    """
    env_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if env_region:
        return env_region
    try:
        tok = _run('curl -sS --connect-timeout 1 -X PUT "http://169.254.169.254/latest/api/token" '
                   '-H "X-aws-ec2-metadata-token-ttl-seconds: 60"', check=False).stdout.strip()
        if tok:
            doc = _run(f'curl -sS -H "X-aws-ec2-metadata-token: {shlex.quote(tok)}" '
                       'http://169.254.169.254/latest/dynamic/instance-identity/document', check=False).stdout
        else:
            doc = _run('curl -sS http://169.254.169.254/latest/dynamic/instance-identity/document', check=False).stdout
        if doc:
            data = json.loads(doc)
            return data.get("region")
    except Exception:
        pass
    return None

def _safe_slug(s: str) -> str:
    """
    Create a filesystem-safe slug from name/logGroup pieces.
    """
    s = s.strip()
    # Replace slashes/colons and collapse whitespace
    s = s.replace("/", "_").replace(":", "_")
    s = re.sub(r"\s+", "-", s)
    # Keep alnum, dash, underscore, dot
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    return s or "logs"

def _ensure_script(path: str) -> None:
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found. Place it next to this script and chmod +x.")

def _ensure_test_data_dir() -> Path:
    """Create test_data directory if it doesn't exist."""
    test_data_dir = Path("test_data")
    test_data_dir.mkdir(exist_ok=True)
    return test_data_dir

def _ensure_temp_dir() -> Path:
    """Create temp directory for raw logs if it doesn't exist."""
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir

def transform_logs(input_file: str, output_file: str) -> None:
    """Transform logs using transform_logs.py script."""
    _ensure_script(TRANSFORM_SCRIPT)
    # Try different python commands in order of preference
    for python_cmd in ["python", "python3", "py"]:
        cmd = f"{python_cmd} {shlex.quote(TRANSFORM_SCRIPT)} {shlex.quote(input_file)} {shlex.quote(output_file)}"
        proc = _run(cmd, check=False)
        if proc.returncode == 0:
            print(f"Transformed {input_file} -> {output_file}")
            return
        elif "command not found" not in proc.stderr.lower():
            # If it's not a "command not found" error, break and show the error
            break
    
    print(f"Warning: Transform failed for {input_file}: {proc.stderr}", file=sys.stderr)

def discover_label_values(log_group: str, label_key: str, region: str, start_iso: str, end_iso: str) -> List[str]:
    _ensure_script(DISCOVER_SCRIPT)
    cmd = f"{shlex.quote(DISCOVER_SCRIPT)} {shlex.quote(log_group)} {shlex.quote(label_key)} {shlex.quote(region)} {shlex.quote(start_iso)} {shlex.quote(end_iso)}"
    proc = _run(cmd, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"discover_labels.sh failed for {log_group}/{label_key}:\n{proc.stderr}")
    try:
        values = json.loads(proc.stdout.strip() or "[]")
        if not isinstance(values, list):
            raise ValueError("discover_labels.sh did not return a JSON array")
        # De-dup & sort defensively
        uniq = sorted({str(v) for v in values if v is not None})
        return uniq
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from discover_labels.sh: {e}\nRAW:\n{proc.stdout}")

def main(args=None, config=None) -> None:
    if args is None:
        ap = argparse.ArgumentParser(description="Prepare jobs.json from config and optionally download logs.")
        ap.add_argument("--region", help="AWS region (auto-detect on EC2 if not provided)")
        ap.add_argument("--lookback-min", type=int, default=1440, help="Minutes to look back (default: 1440 = 24 hours)")
        ap.add_argument("--start", help="ISO8601 start (overrides --lookback-min)")
        ap.add_argument("--end", help="ISO8601 end (default: now)")
        ap.add_argument("--download", action="store_true", help="Run download_logs.sh after writing jobs.json")
        ap.add_argument("--transform", action="store_true", help="Transform downloaded logs to template format")
        ap.add_argument("--jobs-file", default="jobs.json", help="Output path (default: jobs.json)")
        args = ap.parse_args()
    else:
        # Convert dict to argparse.Namespace if needed
        if isinstance(args, dict):
            class Args:
                def __init__(self, **kwargs):
                    for key, value in kwargs.items():
                        setattr(self, key, value)
            args = Args(**args)
    
    # Use provided config or default config
    CONFIG = config if config is not None else DEFAULT_CONFIG

    region = args.region or _detect_region_from_imds() or "us-east-1"
    end_iso = args.end or _iso_now()
    start_iso = args.start or _iso_minus_minutes(args.lookback_min)

    jobs: List[Dict[str, Any]] = []

    # First: expand entries with uniqueLabel
    for entry in CONFIG:
        lg = entry.get("logGroup", "")
        label_key = (entry.get("uniqueLabel") or "").strip()
        if not label_key:
            continue

        try:
            vals = discover_label_values(lg, label_key, region, start_iso, end_iso)
        except Exception as e:
            print(f"[WARN] Discover failed for {lg} ({label_key}): {e}", file=sys.stderr)
            vals = []

        if not vals:
            print(f"[INFO] No distinct values discovered for {lg} ({label_key}) in window; skipping labeled jobs.", file=sys.stderr)
            continue

        base_name = entry.get("name") or _safe_slug(lg)
        for v in vals:
            jobs.append({
                "logGroup": lg,
                "outputName": f"temp/{_safe_slug(base_name)}-{_safe_slug(str(v))}.json",
                "finalOutput": f"test_data/{_safe_slug(base_name)}-{_safe_slug(str(v))}.json",
                "labelKey": label_key,
                "labelValue": v
            })

    # Then: add plain entries (no uniqueLabel)
    for entry in CONFIG:
        if (entry.get("uniqueLabel") or "").strip():
            continue
        lg = entry.get("logGroup", "")
        name = entry.get("name") or _safe_slug(lg)
        jobs.append({
            "logGroup": lg, 
            "outputName": f"temp/{_safe_slug(name)}.json",
            "finalOutput": f"test_data/{_safe_slug(name)}.json"
        })

    Path(args.jobs_file).write_text(json.dumps({
        "region": region,
        "startISO": start_iso,
        "endISO": end_iso,
        "jobs": jobs
    }, indent=2))
    print(f"Wrote {args.jobs_file} with {len(jobs)} job(s).")

    if args.download:
        # Ensure directories exist
        _ensure_test_data_dir()
        _ensure_temp_dir()
        
        try:
            _ensure_script(DOWNLOAD_SCRIPT)
        except FileNotFoundError:
            print(f"NOTE: {DOWNLOAD_SCRIPT} not found; skipping download.")
            return
        proc = _run(f"{shlex.quote(DOWNLOAD_SCRIPT)} {shlex.quote(args.jobs_file)}", check=False)
        print(proc.stdout, end="")
        if proc.returncode != 0:
            print(f"Download script stderr: {proc.stderr}", file=sys.stderr)
            print(f"Download script stdout: {proc.stdout}", file=sys.stderr)
            print(f"Download script return code: {proc.returncode}", file=sys.stderr)
            raise RuntimeError(f"Download script failed with return code {proc.returncode}. stdout: {proc.stdout}. stderr: {proc.stderr}")
        
        # Transform logs if requested
        if args.transform:
            print("\nTransforming downloaded logs...")
            for job in jobs:
                raw_file = job.get("outputName", "")
                final_file = job.get("finalOutput", "")
                
                if raw_file and final_file:
                    # The download script adds -raw to .json files, so adjust the filename
                    if raw_file.endswith('.json'):
                        actual_raw_file = raw_file.replace('.json', '-raw.json')
                    else:
                        actual_raw_file = raw_file
                    
                    # Check if the raw file exists (downloaded by the script)
                    if Path(actual_raw_file).exists():
                        print(f"Transforming {actual_raw_file} -> {final_file}")
                        transform_logs(actual_raw_file, final_file)
                        # Clean up raw file after transformation
                        Path(actual_raw_file).unlink()
                        print(f"Cleaned up raw file: {actual_raw_file}")
                    else:
                        print(f"Warning: No raw log file found for {actual_raw_file}")
                else:
                    print(f"Warning: Missing file paths in job: {job}")

if __name__ == "__main__":
    main()