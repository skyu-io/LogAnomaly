#!/usr/bin/env python3
import sys
import json
import uuid
import argparse
from typing import Any, Dict, Optional, List, Tuple, Iterable
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- Constants ----------------
API_BASE_DEFAULT = "https://api.skyu.io/"
ORGANIZATIONS_ENDPOINT = "resource-service/organizations/find?populate=true"
APPLICATIONS_ENDPOINT = "resource-service/applications/findApplications?populate=true"
CLUSTERS_ENDPOINT = "cluster-service/cluster"
HTTP_TIMEOUT = 30  # seconds

# ---------------- CLI ----------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch Skyu application IDs and cluster info.\n"
            "If --projectid is provided, fetch only that project's data; "
            "otherwise, fetch for all projects in the org."
        )
    )
    p.add_argument("--token", required=True, help="Bearer token")
    p.add_argument("--orgid", required=True, help="Organization ID")
    p.add_argument("--projectid", help="Project ID (optional)")
    p.add_argument(
        "--url",
        dest="base_url",
        default=API_BASE_DEFAULT,
        help=f"API base URL (default: {API_BASE_DEFAULT})",
    )
    return p.parse_args()

# -------------- HTTP -----------------
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
        "x-auth-by": "sa",  # service user
    }
    if projectid:
        headers["x-project-id"] = projectid
    if extra:
        headers.update(extra)
    return headers

def perform_get(session: requests.Session, url: str, headers: Dict[str, str]) -> Any:
    resp = session.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON: {e}\nBody starts with: {resp.text[:500]}")

# -------------- API wrappers -----------------
def get_org_info(
    session: requests.Session,
    url: str,
    token: str,
    orgid: str,
) -> Any:
    headers = build_headers(token, orgid, None)
    return perform_get(session, url, headers)

def get_applications(
    session: requests.Session,
    url: str,
    token: str,
    orgid: str,
    projectid: str,
) -> Any:
    headers = build_headers(
        token,
        orgid,
        projectid,
        extra={
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0",
        },
    )
    return perform_get(session, url, headers)

def get_clusters(
    session: requests.Session,
    url: str,
    token: str,
    orgid: str,
    projectid: str,
) -> Any:
    # Same header model as your cURL (x-project-id is critical for scoping)
    headers = build_headers(
        token,
        orgid,
        projectid,
        extra={
            "accept-language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0",
        },
    )
    return perform_get(session, url, headers)

# -------------- Extraction helpers -----------------
def extract_application_ids(payload: Any) -> List[str]:
    """
    Accepts the applications response like: {"data": [ { "id": ...}, ... ]}
    Returns a list of string app IDs.
    """
    records: List[Any] = []
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("data", "items", "applications"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        else:
            records = [payload]

    ids: List[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        for candidate_key in ("id", "_id", "applicationId"):
            candidate = record.get(candidate_key)
            if candidate is not None:
                ids.append(str(candidate))
                break
    return ids

def list_projects_from_org_payload(payload: Any) -> List[Tuple[str, str]]:
    """
    Parse projects from the get_org_info response you showed:
      payload["data"]["projects"] -> [{ "id": "...", "name": "..." }, ...]
    Returns [(project_id, project_name), ...]
    """
    projects: List[Tuple[str, str]] = []
    try:
        data = payload.get("data") if isinstance(payload, dict) else None
        items = data.get("projects") if isinstance(data, dict) else None
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "id" in item and "name" in item:
                    projects.append((str(item["id"]), str(item["name"])))
    except Exception:
        pass
    return projects

def summarize_clusters(payload: Any) -> List[Dict[str, Any]]:
    """
    Input: cluster-service response (expected to be a list of cluster objects).
    Output: list of dicts with {projectId, name, aws, envId} ONLY for clusters that have env 'prod'.
    If multiple 'prod' env entries appear, the first match is used for envId.
    """
    clusters: Iterable[Any] = payload if isinstance(payload, list) else (payload or [])
    out: List[Dict[str, Any]] = []
    for c in clusters:
        if not isinstance(c, dict):
            continue
        env_id = None
        envs = c.get("envs") or []
        if isinstance(envs, list):
            for e in envs:
                if isinstance(e, dict) and e.get("name") == "prod" and "id" in e:
                    env_id = str(e["id"])
                    break
        if env_id is None:
            # Skip clusters that don't have a 'prod' env
            continue
        aws_obj = c.get("aws")
        aws_slim = None
        if isinstance(aws_obj, dict):
            region = aws_obj.get("region")
            cred = aws_obj.get("credentialId")
            aws_slim = {"region": region, "credentialId": cred}
        out.append(
            {
                "projectId": c.get("projectId"),
                "name": c.get("name"),
                "aws": aws_slim,
                "envId": env_id,
            }
        )
    return out

# -------------- Main -----------------
def main():
    args = parse_args()

    base_url = args.base_url or API_BASE_DEFAULT
    org_url = build_url(base_url, ORGANIZATIONS_ENDPOINT)
    applications_url = build_url(base_url, APPLICATIONS_ENDPOINT)
    clusters_url = build_url(base_url, CLUSTERS_ENDPOINT)

    session = new_session()

    # Final output containers
    apps_mapping: Dict[str, Dict[str, List[str]]] = {args.orgid: {}}
    clusters_by_project: Dict[str, List[Dict[str, Any]]] = {}

    if args.projectid:
        # FAST PATH: just the specified project
        project_id = args.projectid

        # Apps
        try:
            apps_payload = get_applications(session, applications_url, args.token, args.orgid, project_id)
            apps_mapping[args.orgid][project_id] = extract_application_ids(apps_payload)
        except Exception as e:
            print(f"[ERROR] applications request failed for project {project_id}: {e}", file=sys.stderr)
            sys.exit(2)

        # Clusters
        try:
            cl_payload = get_clusters(session, clusters_url, args.token, args.orgid, project_id)
            summaries = summarize_clusters(cl_payload)
            if summaries:
                clusters_by_project[project_id] = summaries
        except Exception as e:
            print(f"[ERROR] clusters request failed for project {project_id}: {e}", file=sys.stderr)
            # still print apps result
        print(json.dumps({"apps": apps_mapping, "clusters": clusters_by_project}, indent=2))
        return

    # SLOW PATH: discover projects then fetch per-project
    try:
        org_payload = get_org_info(session, org_url, args.token, args.orgid)
    except Exception as e:
        print(f"[ERROR] org request failed: {e}", file=sys.stderr)
        sys.exit(2)

    projects = list_projects_from_org_payload(org_payload)
    if not projects:
        print(json.dumps({"apps": apps_mapping, "clusters": clusters_by_project}, indent=2))
        return

    for project_id, _project_name in projects:
        # Apps for project
        try:
            apps_payload = get_applications(session, applications_url, args.token, args.orgid, project_id)
            apps_mapping[args.orgid][project_id] = extract_application_ids(apps_payload)
        except Exception as e:
            print(f"[WARN] applications request failed for project {project_id}: {e}", file=sys.stderr)

        # Clusters for project
        try:
            cl_payload = get_clusters(session, clusters_url, args.token, args.orgid, project_id)
            summaries = summarize_clusters(cl_payload)
            if summaries:
                clusters_by_project[project_id] = summaries
        except Exception as e:
            print(f"[WARN] clusters request failed for project {project_id}: {e}", file=sys.stderr)

    print(json.dumps({"apps": apps_mapping, "clusters": clusters_by_project}, indent=2))

if __name__ == "__main__":
    main()
