# worker.py
import os
import sys
import shlex
import signal
import subprocess
from typing import List, Optional

PYTHON_BIN = os.getenv("PYTHON_BIN", "python")

# ---------- Required config for step 1 (fail fast if missing) ----------
REQ = {
    "SKYU_TOKEN": os.getenv("SKYU_TOKEN"),
    "SKYU_ORGID": os.getenv("SKYU_ORGID"),
    "SKYU_START": os.getenv("SKYU_START"),
    "SKYU_END": os.getenv("SKYU_END"),
    "SKYU_CREDENTIAL_ID": os.getenv("SKYU_CREDENTIAL_ID"),
    "SKYU_NAMESPACE": os.getenv("SKYU_NAMESPACE"),
    "SKYU_PROJECTID": os.getenv("SKYU_PROJECTID"),
}
# Optional with defaults
OUT_DIR = os.getenv("SKYU_OUT_DIR", "./outLog")

# ---------- Config for step 2 (loganomaly) ----------
LA_INPUT = os.getenv("LA_INPUT", OUT_DIR)            # default: same as step 1 output
LA_OUTPUT = os.getenv("LA_OUTPUT", "./results")
LA_CONFIG = os.getenv("LA_CONFIG", "loganomly.yaml") # ensure filename is correct

# ---------- Bootstrap: pip install ----------
PIP_INSTALL_ENABLED = os.getenv("PIP_INSTALL", "1") not in ("0", "false", "False")
REQUIREMENTS_FILE = os.getenv("REQUIREMENTS_FILE", "requirements.txt")

_current_child: Optional[subprocess.Popen] = None

def die(msg: str, code: int = 1):
    print(f"[worker][FATAL] {msg}", flush=True)
    sys.exit(code)

def validate_envs():
    missing = [k for k, v in REQ.items() if v is None]
    if missing:
        die(f"Missing required envs: {', '.join(missing)}", code=2)

def build_pip_install_cmd() -> List[str]:
    """Bootstrap: install Python deps via requirements file."""
    return [PYTHON_BIN, "-m", "pip", "install", "-r", REQUIREMENTS_FILE]

def build_extract_cmd() -> List[str]:
    """Step 1: export logs with LAD_worker/log_extractor.py."""
    return [
        PYTHON_BIN, "-u", "LAD_worker/log_extractor.py",
        "--token", REQ["SKYU_TOKEN"],
        "--orgid", REQ["SKYU_ORGID"],
        "--start", REQ["SKYU_START"],
        "--end", REQ["SKYU_END"],
        "--credential-id", REQ["SKYU_CREDENTIAL_ID"],
        "--out_dir", OUT_DIR,
        "--namespace", REQ["SKYU_NAMESPACE"],
        "--projectid", REQ["SKYU_PROJECTID"],
    ]

def build_LAD_detector_cmd() -> List[str]:
    """Step 2: run log anomaly detector (python -m loganomaly ...)."""
    return [
        PYTHON_BIN, "-u", "-m", "loganomaly",
        "--input", LA_INPUT,
        "--output", LA_OUTPUT,
        "--config", LA_CONFIG,
    ]

def _forward_signal(signum, _frame):
    global _current_child
    if _current_child and _current_child.poll() is None:
        try:
            _current_child.send_signal(signum)
        except Exception:
            pass

# Forward termination signals to the child process
signal.signal(signal.SIGTERM, _forward_signal)
signal.signal(signal.SIGINT, _forward_signal)

def _redact(cmd: List[str]) -> str:
    """Render a shell-like command string with token redacted."""
    token = REQ.get("SKYU_TOKEN") or ""
    def mask(arg: str) -> str:
        return arg if arg != token else (token[:8] + "...redacted")
    return " ".join(shlex.quote(mask(a)) for a in cmd)

def run_step(name: str, cmd: List[str]) -> int:
    """Run a single step, stream output, return its exit code."""
    global _current_child
    print(f"[worker] starting {name}: {_redact(cmd)}", flush=True)
    try:
        _current_child = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError as e:
        print(f"[worker][ERROR] {name}: command not found: {e}", flush=True)
        return 127
    except Exception as e:
        print(f"[worker][ERROR] {name}: failed to start: {e}", flush=True)
        return 1

    try:
        _current_child.wait()
    except KeyboardInterrupt:
        _current_child.wait()

    code = _current_child.returncode if _current_child else 1
    print(f"[worker] {name} exited with code {code}", flush=True)
    return code

def main():
    validate_envs()

    # Optional bootstrap: pip install -r requirements.txt
    if PIP_INSTALL_ENABLED:
        if not os.path.exists(REQUIREMENTS_FILE):
            die(f"requirements file not found: {REQUIREMENTS_FILE}", code=3)
        code = run_step("bootstrap:pip_install", build_pip_install_cmd())
        if code != 0:
            sys.exit(code)  # fail fast

    # Make sure output dir for detector exists
    try:
        os.makedirs(LA_OUTPUT, exist_ok=True)
    except Exception as e:
        die(f"cannot create output directory '{LA_OUTPUT}': {e}", code=4)

    # Step 1: export logs
    step1 = run_step("step1:log_extractor", build_extract_cmd())
    if step1 != 0:
        sys.exit(step1)  # fail fast

    # Step 2: run log anomaly module
    step2 = run_step("step2:loganomaly", build_LAD_detector_cmd())
    if step2 != 0:
        sys.exit(step2)  # fail fast

    print("[worker] all steps completed successfully", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()
