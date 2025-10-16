#!/usr/bin/env python3
import sys
import json
import uuid
import argparse
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- Constants ----------------
API_BASE_DEFAULT = "https://api.skyu.io/"
ORGANIZATIONS_ENDPOINT = "resource-service/organizations/find?populate=true"
APPLICATIONS_ENDPOINT = "resource-service/applications/findApplications?populate=true"
HTTP_TIMEOUT = 30  # seconds

# ---------------- CLI ----------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch Skyu application IDs.\n"
            "If --projectid is provided, fetch that project's app IDs directly.\n"
            "Otherwise, list projects from org and fetch each project's app IDs."
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
    projectid: Optional[str],
) -> Any:
    headers = build_headers(token, orgid, projectid)
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
            # fallback single-record shape
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
    {
      "success": true,
      "data": {
        ...,
        "projects": [ { "id": "...", "name": "...", "applications": [...] }, ... ]
      }
    }
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
    # Fallback (very defensive) – not expected for your shape, but safe to keep:
    if not projects:
        projects = extract_projects_best_effort(payload)
    return projects

def extract_projects_best_effort(payload: Any) -> List[Tuple[str, str]]:
    """
    Very defensive recursive fallback if the org payload shape changes.
    """
    results: List[Tuple[str, str]] = []
    seen = set()

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            pid = node.get("id") or node.get("_id") or node.get("projectId") or node.get("project_id")
            pname = node.get("name") or node.get("projectName") or node.get("title") or node.get("displayName")
            if pid and pname:
                pair = (str(pid), str(pname))
                if pair not in seen:
                    seen.add(pair)
                    results.append(pair)
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for it in node:
                collect(it)

    collect(payload)
    return results

# -------------- Main -----------------
def main():
    args = parse_args()

    base_url = args.base_url or API_BASE_DEFAULT
    org_url = build_url(base_url, ORGANIZATIONS_ENDPOINT)
    applications_url = build_url(base_url, APPLICATIONS_ENDPOINT)

    session = new_session()

    mapping: Dict[str, Dict[str, List[str]]] = {args.orgid: {}}

    if args.projectid:
        # FAST PATH: user provided project → fetch just that project's app IDs
        try:
            apps_payload = get_applications(
                session=session,
                url=applications_url,
                token=args.token,
                orgid=args.orgid,
                projectid=args.projectid,
            )
            app_ids = extract_application_ids(apps_payload)
            mapping[args.orgid][args.projectid] = app_ids
        except Exception as e:
            print(f"[ERROR] applications request failed for project {args.projectid}: {e}", file=sys.stderr)
            sys.exit(2)

        print(json.dumps(mapping, indent=2))
        return

    # SLOW PATH: no project provided → fetch org to discover projects, then fetch each project's apps
    try:
        org_payload = get_org_info(
            session=session,
            url=org_url,
            token=args.token,
            orgid=args.orgid,
            projectid=None,
        )
    except Exception as e:
        print(f"[ERROR] org request failed: {e}", file=sys.stderr)
        sys.exit(2)

    projects = list_projects_from_org_payload(org_payload)
    if not projects:
        # No projects found – produce empty mapping per requirement
        print(json.dumps(mapping, indent=2))
        return

    for project_id, _project_name in projects:
        try:
            apps_payload = get_applications(
                session=session,
                url=applications_url,
                token=args.token,
                orgid=args.orgid,
                projectid=project_id,
            )
            app_ids = extract_application_ids(apps_payload)
            mapping[args.orgid][project_id] = app_ids
        except Exception as e:
            # Continue other projects, but log the failure
            print(f"[WARN] applications request failed for project {project_id}: {e}", file=sys.stderr)
            continue

    print(json.dumps(mapping, indent=2))

if __name__ == "__main__":
    main()
