#!/usr/bin/env python3
import os
import sys
import json
import uuid
import time
import csv
import argparse
from getpass import getpass
from typing import Any, Dict, List, Optional, Iterable, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SKYU_BASE_URL = os.getenv("SKYU_BASE_URL", "https://api.skyu.io")
API_URL_DEFAULT = f"{SKYU_BASE_URL}/resource-service/organizations/find?populate=true"

# ---------------- CLI ----------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch organization data from Skyu and extract {orgId, projectName, appId} rows."
    )
    p.add_argument("--token", help="Bearer token (required, will prompt if not provided).")
    p.add_argument("--orgid", help="Organization ID ,Based on orgid log anomaly will be enabled.")
    p.add_argument("--projectid", help="Based on projectId log anomaly will be enabled.")
    p.add_argument("--appid", help="Based on applicationId log anomaly will be enabled.")
    p.add_argument("--csv", help="Optional path to write CSV output.")
    p.add_argument("--url", default=API_URL_DEFAULT, help=f"API URL (default: {API_URL_DEFAULT}, base URL can be set via SKYU_BASE_URL env var)")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds (default: 30).")
    p.add_argument("--raw-dump", action="store_true",
                   help="If no appIds extracted, dump raw JSON to a timestamped file.")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logs.")
    return p.parse_args()

# -------------- HTTP -----------------

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

def make_request(session: requests.Session, url: str, token: str, orgid: str, timeout: int, verbose: bool=False) -> Any:
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "cache-control": "no-cache",
        "origin": "https://console.skyu.io",
        "pragma": "no-cache",
        "referer": "https://console.skyu.io/",
        "user-agent": "python-requests",
        "x-organization-id": orgid,
        "x-trace-id": str(uuid.uuid4()),
    }
    
    # Log equivalent curl command
    curl_headers = []
    for key, value in headers.items():
        curl_headers.append(f'-H "{key}: {value}"')
    
    curl_cmd = f'curl -X GET "{url}" \\\n  {" \\\n  ".join(curl_headers)}'
    print(f"[CURL] Equivalent command:\n{curl_cmd}\n", file=sys.stderr)
    
    if verbose:
        print(f"[INFO] GET {url} (orgid={orgid})", file=sys.stderr)
    resp = session.get(url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON: {e}\nBody starts with: {resp.text[:500]}")

# -------- Flexible extractors (schema-light) --------

def guess_project_name(d: Dict[str, Any]) -> Optional[str]:
    for k in ("projectName", "name", "title", "project_name", "project"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def extract_app_id_from_obj(d: Dict[str, Any]) -> Iterable[str]:
    for k in ("appId", "app_id", "id", "appID"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            yield v.strip()
    if "identifier" in d and isinstance(d["identifier"], str):
        yield d["identifier"].strip()

def walk_for_projects_and_apps(node: Any, current_project: Optional[str] = None) -> Iterable[Tuple[str, str]]:
    """
    Recursively traverse any JSON structure and yield (projectName, appId).
    Heuristics:
      - A dict containing an 'apps' key defines a likely project scope.
      - If 'appIds' array exists, treat parent as project.
      - Otherwise, keep current project context while descending.
    """
    if isinstance(node, dict):
        project_here = current_project
        if "apps" in node and isinstance(node["apps"], (list, dict)):
            project_here = guess_project_name(node) or current_project
        if "appIds" in node and isinstance(node["appIds"], list):
            project_here = guess_project_name(node) or current_project
            for v in node["appIds"]:
                if isinstance(v, str) and v.strip() and project_here:
                    yield (project_here, v.strip())

        if project_here:
            for app_id in extract_app_id_from_obj(node):
                yield (project_here, app_id)

        for k, v in node.items():
            if k == "apps" and isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        for app_id in extract_app_id_from_obj(item):
                            if (current_project or project_here):
                                yield ((project_here or current_project), app_id)
                        yield from walk_for_projects_and_apps(item, project_here)
                return
            if k.lower().startswith("project"):
                pn = guess_project_name(node) or current_project
                yield from walk_for_projects_and_apps(v, pn)
            else:
                yield from walk_for_projects_and_apps(v, project_here)

    elif isinstance(node, list):
        for item in node:
            yield from walk_for_projects_and_apps(item, current_project)

def build_rows(data: Any, orgid: str) -> List[Dict[str, str]]:
    pairs = list(walk_for_projects_and_apps(data, None))
    rows: List[Dict[str, str]] = []
    seen = set()
    for project_name, app_id in pairs:
        if not project_name or not app_id:
            continue
        key = (project_name, app_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"orgId": orgid, "projectName": project_name, "appId": app_id})
    return rows

def select_project_subtrees(data: Any, projectid: Optional[str]) -> Any:
    """
    Return a pruned structure containing only elements that belong to the matching project.
    Matching rules are flexible:
      - If project's human-friendly name matches `projectid` (via guess_project_name)
      - Or if an explicit key like 'projectId' equals `projectid`
    If nothing matches, return the original data to avoid false negatives.
    """
    if not projectid:
        return data

    target = projectid.strip()

    def node_matches(dct: Dict[str, Any]) -> bool:
        if not isinstance(dct, dict):
            return False
        if guess_project_name(dct) == target:
            return True
        pid = dct.get("projectId") or dct.get("project_id") or dct.get("id")
        if isinstance(pid, str) and pid.strip() == target:
            return True
        return False

    matches: List[Any] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            if node_matches(node):
                matches.append(node)
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(data)
    if matches:
        return matches
    return data

def filter_rows_by_projectid(rows: List[Dict[str, str]], projectid: Optional[str]) -> List[Dict[str, str]]:
    if not projectid:
        return rows
    pid = projectid.strip()
    return [r for r in rows if r.get("projectName") == pid]

def filter_rows_by_appid(rows: List[Dict[str, str]], appid: Optional[str]) -> List[Dict[str, str]]:
    if not appid:
        return rows
    aid = appid.strip()
    return [r for r in rows if r.get("appId") == aid]

def print_json(rows: List[Dict[str, str]]) -> None:
    print(json.dumps(rows, indent=2))

def maybe_write_csv(rows: List[Dict[str, str]], path: Optional[str]) -> None:
    if not path:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["orgId", "projectName", "appId"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n[INFO] Saved CSV: {path}", file=sys.stderr)

# -------------- IO Flow -----------------

def resolve_token_and_orgid(args: argparse.Namespace) -> Tuple[str, str]:
    token = args.token
    orgid = args.orgid or os.environ.get("SKYU_ORG_ID")

    if not token:
        token = getpass("Enter Bearer TOKEN (input hidden): ").strip()
    if not orgid:
        orgid = input("Enter ORGID (e.g., org_xxx... or UUID): ").strip()

    if not token or not orgid:
        print("TOKEN and ORGID are required.", file=sys.stderr)
        sys.exit(1)
    return token, orgid

def main():
    args = parse_args()
    token, orgid = resolve_token_and_orgid(args)
    session = new_session()

    try:
        data = make_request(session, args.url, token, orgid, args.timeout, args.verbose)
    except Exception as e:
        print(f"[ERROR] Request failed: {e}", file=sys.stderr)
        sys.exit(2)

    # If projectId provided, narrow data to that project before extraction
    narrowed = select_project_subtrees(data, args.projectid)
    rows = build_rows(narrowed, orgid)
    # If appId provided, return only that appId as final data
    rows = filter_rows_by_appid(rows, args.appid)
    if not rows:
        msg = "No appIds were extracted."
        if args.raw_dump:
            dump_path = f"skyu_raw_{int(time.time())}.json"
            with open(dump_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[WARN] {msg} Saved raw response for inspection: {dump_path}", file=sys.stderr)
        else:
            print(f"[WARN] {msg} (use --raw-dump to save the raw response)", file=sys.stderr)
        sys.exit(3)

    print_json(rows)
    maybe_write_csv(rows, args.csv)

if __name__ == "__main__":
    main()
