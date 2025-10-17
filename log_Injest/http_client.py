# skyu_logs/http_client.py
import logging
import shlex
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import HTTP_TIMEOUT

logger = logging.getLogger(__name__)

def build_url(base_url: str, endpoint: str) -> str:
    if not base_url.endswith("/"):
        base_url += "/"
    return urljoin(base_url, endpoint)

def new_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

def build_headers(
    token: str,
    orgid: str,
    projectid: Optional[str] = None,
    *,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "cache-control": "no-cache",
        "origin": "https://console.skyu.io",
        "pragma": "no-cache",
        "referer": "https://console.skyu.io/",
        "x-organization-id": orgid,
        "x-trace-id": str(uuid.uuid4()),
        "x-auth-by": "sa",
    }
    if projectid:
        headers["x-project-id"] = projectid
    if extra:
        headers.update(extra)
    return headers

def _to_curl(req: requests.PreparedRequest) -> str:
    parts = ["curl", "-X", shlex.quote(req.method)]
    for k, v in req.headers.items():
        if k.lower() == "authorization" and isinstance(v, str) and v.startswith("Bearer "):
            v = "Bearer " + v[len("Bearer "):][:8] + "...redacted"
        parts += ["-H", shlex.quote(f"{k}: {v}")]
    if req.body:
        body = req.body.decode("utf-8", "replace") if isinstance(req.body, bytes) else str(req.body)
        parts += ["--data-binary", shlex.quote(body)]
    parts += ["--compressed", shlex.quote(req.url)]
    return " ".join(parts)

def request_json_and_trace(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    params: Dict[str, Any],
    trace_steps: List[Dict[str, str]],
    *,
    label: str,
) -> Any:
    """Perform GET with params, parse JSON, and record an exact cURL + status into trace_steps."""
    resp = session.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
    curl_str = _to_curl(resp.request)
    trace_steps.append({"label": label, "status": str(resp.status_code), "curl": curl_str})
    if resp.status_code != 200:
        preview = resp.text[:500].replace("\n", "\\n")
        raise RuntimeError(f"{label} HTTP {resp.status_code}: {preview}")
    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"{label} failed to parse JSON: {e}\nBody starts with: {resp.text[:500]}")
