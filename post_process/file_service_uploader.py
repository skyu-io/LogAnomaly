# utils/file_service_uploader.py
from __future__ import annotations
import os, zipfile, tempfile, secrets, time, fnmatch
from pathlib import Path
from typing import Optional, Iterable, Dict, Tuple
import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urljoin
import logging
import json

from datetime import datetime
import re

logger = logging.getLogger(__name__)


from pipeline.constants import (
    SKYU_API_BASE_URL,
    SKYU_FILE_SERVICE_PATH,
    DEFAULT_PROVIDER as PROVIDER,
    DEFAULT_RESOURCE_ID
    )

# Construct the full file service URL from base URL
FILE_SERVICE_API_URL = urljoin(SKYU_API_BASE_URL.rstrip("/") + "/", SKYU_FILE_SERVICE_PATH.lstrip("/"))


# ----- ULID -----
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
def generate_ulid() -> str:
    ts_ms = int(time.time() * 1000)
    n = int.from_bytes(ts_ms.to_bytes(6, "big") + secrets.token_bytes(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 31])
        n >>= 5
    return "".join(reversed(chars))

# ----- requests session -----
def _build_session(total_retries: int = 3, backoff: float = 0.5) -> requests.Session:
    sess = requests.Session()
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    return sess

# ----- zipper -----
def zip_folder_for_upload(
    folder_path: str | Path,
    *,
    out_zip: Optional[str | Path] = None,
    ignore_globs: Optional[Iterable[str]] = None,
    compression=zipfile.ZIP_DEFLATED,
) -> Path:
    root = Path(folder_path).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    if out_zip is None:
        fd, temp_path = tempfile.mkstemp(prefix=f"{root.name}_", suffix=".zip")
        os.close(fd)
        out_zip = Path(temp_path)
    else:
        out_zip = Path(out_zip).resolve()

    ignore_globs = tuple(ignore_globs or ())

    def _ignored(p: Path) -> bool:
        rel = p.relative_to(root).as_posix()
        for pat in ignore_globs:
            if pat.endswith("/") and rel.startswith(pat.rstrip("/")):
                return True
            if fnmatch.fnmatch(p.name, pat) or fnmatch.fnmatch(rel, pat):
                return True
        return False

    with zipfile.ZipFile(out_zip, "w", compression=compression, allowZip64=True) as zf:
        for path in root.rglob("*"):
            if _ignored(path):
                continue
            if path.is_file():
                zf.write(path, path.relative_to(root))
    return out_zip

# ----- headers builder (mix worker overrides + constants defaults) -----
def build_headers(
    *,
    project_id: str,
    org_id: str,
    api_token: str,
    env_id: str,
    resource_id: str = DEFAULT_RESOURCE_ID,
) -> Dict[str, str]:
    return {
        "x-project-id": project_id,
        "x-organization-id": org_id,
        "x-resource-id": resource_id,
        "x-environment-id": env_id,
        "x-auth-by": 'sa', # hardcoded value for skyU service token
        "Authorization": f"Bearer {api_token}",
    }

def upload_folder_as_zip(
    folder_path: str | Path,
    *,
    headers: Dict[str, str],                  # <- pass build_headers(...) output here
    provider: str,
    resource_type: str,
    cloud_storage_path: str,
    api_url: str = FILE_SERVICE_API_URL,  # Default to the generated URL from constants
    zip_name: Optional[str] = None,
    timeout: Tuple[float, float] = (10.0, 180.0),
    ignore_globs: Optional[Iterable[str]] = None,
    session: Optional[requests.Session] = None,
    raise_for_status: bool = True,
    extra_headers: Optional[Dict[str, str]] = None,  # optional overrides
) -> requests.Response:
    """
    Upload a folder (zipped on the fly) or an existing .zip to the file-service.

    Required form fields:
      - provider -> "provider"
      - resource_type -> "resourceType"
      - cloud_storage_path -> "cloudStoragePath"

    Notes:
      - If folder_path points to a .zip, it is sent as-is (name can be overridden via zip_name).
      - Otherwise, the folder is zipped to a temp file before upload.
      - 'Content-Type' is intentionally NOT set in headers so requests can build multipart boundaries.
    """
    if not resource_type or not cloud_storage_path:
        raise ValueError("Both 'resource_type' and 'cloud_storage_path' are required.")

    src = Path(folder_path).resolve()

    # Start from provided headers, strip any Content-Type, and merge extras
    merged_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    if extra_headers:
        merged_headers.update({k: v for k, v in extra_headers.items() if k.lower() != "content-type"})

    sess = session or _build_session()

    temp_zip_path: Optional[Path] = None
    created_temp = False

    try:
        if src.is_file() and src.suffix.lower() == ".zip":
            zip_path = src
            presented_name = zip_name or src.name
        else:
            temp_zip_path = zip_folder_for_upload(src, ignore_globs=ignore_globs)
            created_temp = True
            presented_name = zip_name or f"{generate_ulid()}.zip"
            zip_path = temp_zip_path

        data = {
            "provider": provider,  # Curl sends with quotes!
            "resourceType": resource_type,  # Curl sends with quotes!
            # Note: cloudStoragePath may not be required, testing without it
            "cloudStoragePath": dated_path_local("lad_report/"),
        }

        logger.info(f"Uploading to {api_url} with data: {data}, zip: {presented_name}, headers keys: {list(merged_headers.keys())}")
        
        safe_auth = headers.get("Authorization", "")
        logger.info(f"Auth header startswith 'Bearer ': {safe_auth.startswith('Bearer ')} len={len(safe_auth)}")
        logger.info(f"Using URL: {api_url}")
        logger.info(f"Header keys: {list(headers.keys())}")

        with open(zip_path, "rb") as f:
            files = {"file": (presented_name, f, "application/zip")}
            
            resp = sess.post(
                api_url,
                headers=merged_headers,
                data=data,
                files=files,
                timeout=timeout,
            )

        if raise_for_status:
            try:
                resp.raise_for_status()
            except requests.HTTPError:
                body = None
                if "application/json" in resp.headers.get("Content-Type", ""):
                    try:
                        body = json.dumps(resp.json(), indent=2, ensure_ascii=False)
                    except Exception:
                        body = _safe_text(resp)  # fallback
                else:
                    body = _safe_text(resp)

                logger.error(
                    "Upload failed (JSON aware):\n"
                    f"URL: {resp.request.url}\n"
                    f"Status: {resp.status_code} {resp.reason}\n"
                    f"Headers: {dict(resp.headers)}\n"
                    f"Body:\n{body}"
                )
                raise
            if not resp.ok:
                logger.error(f"Upload failed with status {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        return resp

    finally:
        if created_temp and temp_zip_path and temp_zip_path.exists():
            try:
                temp_zip_path.unlink()
            except Exception:
                pass



def _redact_headers(h: dict) -> dict:
    if not h:
        return {}
    redacted = dict(h)
    for k in list(redacted.keys()):
        if k.lower() in ("authorization", "x-api-key"):
            v = str(redacted[k])
            if len(v) > 16:
                redacted[k] = v[:8] + "…" + v[-4:]
            else:
                redacted[k] = "***"
    return redacted

def _safe_text(resp: requests.Response, limit: int | None = None) -> str:
    # Try to decode, even for odd encodings
    try:
        text = resp.text
    except Exception:
        try:
            text = resp.content.decode(resp.encoding or "utf-8", errors="replace")
        except Exception:
            text = "<binary body>"
    if limit is not None and len(text) > limit:
        return text[:limit] + f"\n… (truncated, total {len(text)} bytes)"
    return text

def dated_path_local(base: str = "lad_report") -> str:
    """
    Single token based on the runtime env's local clock (no tz conversion).
    Example: lad_report_20251026_162355
    """
    now = datetime.now()                 # <-- runtime env timestamp
    ts  = now.strftime("%Y%m%d_%H%M%S")
    safe_base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    return f"{safe_base}_{ts}"