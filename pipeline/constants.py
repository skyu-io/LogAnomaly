# constants.py
from __future__ import annotations
import os
from urllib.parse import urljoin

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv is not installed, environment variables must be set manually
    pass

def _req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

# Required at runtime (fail fast if missing)
# These are imported by worker.py

DEFAULT_PROVIDER = _req("DEFAULT_PROVIDER")
SKYU_API_BASE_URL = _req("DEFAULT_SKYU_API_URL")  # Base API URL, e.g. https://api.skyu.io/
EMAIL_NOTIFICATION_PATH = _req("SKYU_EMAIL_NOTIFICATION_PATH")  # Path like "/v1/email/send-template"
TO_EMAIL = _req("SKYU_ALERT_TO_EMAIL")   # e.g. alerts@yourco.com
TEMPLATE_NAME = _req("SKYU_TEMPLATE_NAME")    # e.g. siem-alert-aggregate
DEFAULT_RESOURCE_ID = _req("DEFAULT_RESOURCE_ID")    # e.g. siem-alert-aggregate

# Construct the full email notification URL
EMAIL_NOTIFICATION_URL = urljoin(SKYU_API_BASE_URL.rstrip("/") + "/", EMAIL_NOTIFICATION_PATH.lstrip("/"))

# Optional constants (only required if used by other modules)
# Note: Using os.getenv() for optional vars to avoid failing startup
SKYU_FILE_SERVICE_PATH = os.getenv("SKYU_FILE_SERVICE_URL", "/file-service")
OUT_DIR_DEFAULT = os.getenv("OUT_DIR_DEFAULT")

# Optional with sensible defaults
USER_AGENT = os.getenv("SKYU_USER_AGENT", "loganomaly-worker/1.0")
TIMEOUT    = int(os.getenv("SKYU_HTTP_TIMEOUT", "20"))

CLUSTER_ENV_ID    = os.getenv("OHO_CLUSTER_ENV_ID")
LAD_RESULT_OUTPUT_DIR = os.getenv("OUTPUT_DIR")
LOG_COLLECTION_DIR = os.getenv("INPUT_DIR")
GITOPS_CONFIG_REPO = os.getenv("CONFIG_REPO")