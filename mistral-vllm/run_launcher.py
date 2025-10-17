# python/run_launcher.py
from __future__ import annotations

import os
import re
import sys
import subprocess
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

@dataclass
class LaunchResult:
    returncode: int
    stdout: str
    stderr: str
    instance_id: Optional[str]
    public_ip: Optional[str]
    public_dns: Optional[str]
    api_url: Optional[str]

_INSTANCE_RE   = re.compile(r"Instance ID:\s+(\S+)")
_PUBLIC_IP_RE  = re.compile(r"Public IP:\s+(\S+)")
_PUBLIC_DNS_RE = re.compile(r"Public DNS:\s+(\S+)")
_API_URL_RE    = re.compile(r"API URL:\s+(\S+)")

def _parse_outputs(text: str) -> LaunchResult:
    """Parse the summary lines printed by launch_mistral_vllm.sh."""
    return LaunchResult(
        returncode=0,  # placeholder; caller sets real returncode later
        stdout=text,
        stderr="",
        instance_id = _INSTANCE_RE.search(text).group(1) if _INSTANCE_RE.search(text) else None,
        public_ip   = _PUBLIC_IP_RE.search(text).group(1) if _PUBLIC_IP_RE.search(text) else None,
        public_dns  = _PUBLIC_DNS_RE.search(text).group(1) if _PUBLIC_DNS_RE.search(text) else None,
        api_url     = _API_URL_RE.search(text).group(1) if _API_URL_RE.search(text) else None,
    )

def make_executable(path: Path) -> None:
    """Add +x for user, group, others (u+x,g+x,o+x)."""
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

def run_launcher(
    env_file: os.PathLike | str = "mistral.env",
    script_path: os.PathLike | str = "test.sh", #launch_mistral_vllm.sh
    *,
    extra_env: Optional[Dict[str, str]] = None,
    timeout_sec: Optional[int] = None,
    stream: bool = False,
    stream_sink: Callable[[str], None] = lambda s: sys.stdout.write(s),
) -> LaunchResult:
    """
    Execute the bash launcher with the given env file.

    Args:
        env_file: Path to your filled env file (e.g., mistral.env).
        script_path: Path to launch_mistral_vllm.sh.
        extra_env: Extra environment vars to inject (e.g., {"AWS_PROFILE": "prod"}).
        timeout_sec: Kill the process if it exceeds this many seconds.
        stream: If True, stream combined stdout/stderr line-by-line to stream_sink.
        stream_sink: Function to consume streamed lines (only used when stream=True).

    Returns:
        LaunchResult with return code, captured output, and parsed instance info.

    Raises:
        FileNotFoundError: if script or env file is missing.
        RuntimeError: if the script exits non-zero (includes stderr tail).
        subprocess.TimeoutExpired: if timeout_sec is exceeded.
    """
    env_path = Path(env_file)
    sh_path = Path(script_path)

    if not env_path.exists():
        raise FileNotFoundError(f"env file not found: {env_path}")
    if not sh_path.exists():
        raise FileNotFoundError(f"script not found: {sh_path}")

    # Ensure the script is executable; fall back to running via bash anyway.
    try:
        sh_path.chmod(sh_path.stat().st_mode | 0o111)
    except Exception:
        # Not fatal—will still run with 'bash <script>'
        pass

    cmd = ["bash", str(sh_path), str(env_path)]  # portable across OSes

    env = os.environ.copy()
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})

    if stream:
        # Stream output live
        proc = subprocess.Popen(
            cmd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        all_out: list[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                all_out.append(line)
                stream_sink(line)
            rc = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        stdout = "".join(all_out)
        stderr = ""  # combined into stdout
        res = _parse_outputs(stdout)
        res.returncode = rc
        res.stderr = stderr
        if rc != 0:
            tail = "\n".join(stdout.splitlines()[-50:])
            raise RuntimeError(f"launcher failed (rc={rc}). Output tail:\n{tail}")
        return res

    # Capture after completion
    try:
        completed = subprocess.run(
            cmd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,  # we'll handle non-zero ourselves for better message
        )
    except subprocess.TimeoutExpired:
        raise

    res = _parse_outputs(completed.stdout + ("\n" + completed.stderr if completed.stderr else ""))
    res.returncode = completed.returncode
    res.stdout = completed.stdout
    res.stderr = completed.stderr

    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or completed.stdout).splitlines()[-50:])
        raise RuntimeError(f"launcher failed (rc={completed.returncode}). Tail:\n{tail}")

    return res
