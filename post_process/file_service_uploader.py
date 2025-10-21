# utils/file_service_uploader.py
from __future__ import annotations
import os, zipfile, tempfile, secrets, time, fnmatch
from pathlib import Path
from typing import Optional, Iterable, Dict
import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urljoin


from .constants import (
    DEFAULT_API_URL as API_URL,
    SKYU_FILE_SERVICE_URL ,
    DEFAULT_PROVIDER as PROVIDER,
    DEFAULT_RESOURCE_ID
    )

FILE_SERVICE_API_URL = urljoin(API_URL, SKYU_FILE_SERVICE_URL.lstrip("/"))


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

# ----- upload -----
# def upload_folder_as_zip(
#     folder_path: str | Path,
#     *,
#     api_url: str = API_URL,
#     headers: Optional[Dict[str, str]] = None,
#     provider: str = PROVIDER,
#     resource_type: str,
#     cloud_storage_path: str,
#     zip_name: Optional[str] = None,
#     timeout: tuple = (10, 180),
#     ignore_globs: Optional[Iterable[str]] = None,
#     session: Optional[requests.Session] = None,
# ) -> requests.Response:
#     """
#     NOTE: resource_type and cloud_storage_path are required (passed from worker).
#     """
#     src = Path(folder_path).resolve()
#     if headers is None:
#         headers = {}
#     headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
#     print("headers")
#     print(headers)

#     sess = session or _build_session()

#     temp_zip_path: Optional[Path] = None
#     created_temp = False
#     try:
#         if src.is_file() and src.suffix.lower() == ".zip":
#             zip_path = src
#             presented_name = zip_name or src.name
#         else:
#             temp_zip_path = zip_folder_for_upload(src, ignore_globs=ignore_globs)
#             created_temp = True
#             presented_name = zip_name or f"{generate_ulid()}.zip"
#             zip_path = temp_zip_path

#         data = {
#             "provider": provider,
#             "resourceType": resource_type,
#             "cloudStoragePath": cloud_storage_path,
#         }
#         with open(zip_path, "rb") as f:
#             files = {"file": (presented_name, f, "application/zip")}
#             return sess.post(api_url, headers=headers, data=data, files=files, timeout=timeout)
#     finally:
#         if created_temp and temp_zip_path and temp_zip_path.exists():
#             try:
#                 temp_zip_path.unlink()
#             except Exception:
#                 pass


def upload_folder_as_zip(
    folder_path: str | Path,
    *,
    api_url: str,
    headers: Dict[str, str],                  # <- pass build_headers(...) output here
    provider: str,
    resource_type: str,
    cloud_storage_path: str,
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
            "provider": provider,
            "resourceType": resource_type,
            "cloudStoragePath": cloud_storage_path,
        }

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
            resp.raise_for_status()
        return resp

    finally:
        if created_temp and temp_zip_path and temp_zip_path.exists():
            try:
                temp_zip_path.unlink()
            except Exception:
                pass
