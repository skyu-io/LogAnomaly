#!/usr/bin/env python3
import sys
import json
import uuid
import argparse
import re
import shlex
from pathlib import Path
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
LOGS_QUERY_ENDPOINT = "credential-service/kubernetes/clusters/logs/query"
LOGS_RESULT_ENDPOINT = "credential-service/kubernetes/clusters/logs/logs"
HTTP_TIMEOUT = 30  # seconds

# ---------------- CLI ----------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch Skyu application IDs, cluster info, and application logs.\n"
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

    # Logs-specific inputs
    p.add_argument("--credential-id", dest="credential_id", required=True,
                   help="Credential ID to use for logs endpoints (x-credential-id header)")
    p.add_argument("--start", help='Start datetime for logs (e.g. "2025-10-14 07:02:54.939")')
    p.add_argument("--end", help='End datetime for logs (e.g. "2025-10-14 08:02:54.939")')
    p.add_argument("--out_dir", default="./logs_out", help="Directory to save raw JSON responses")
    p.add_argument("--namespace", help="K8s namespace override (optional)")
    p.add_argument("--log-group", help="CloudWatch log group override (optional)")
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

def _to_curl(req: requests.PreparedRequest) -> str:
    parts = ["curl", "-X", shlex.quote(req.method)]
    for k, v in req.headers.items():
        # redact token if present
        if k.lower() == "authorization" and isinstance(v, str) and v.startswith("Bearer "):
            v = "Bearer " + v[len("Bearer "):][:8] + "...redacted"
        parts += ["-H", shlex.quote(f"{k}: {v}")]
    if req.body:
        body = req.body.decode("utf-8", "replace") if isinstance(req.body, bytes) else str(req.body)
        parts += ["--data-binary", shlex.quote(body)]
    parts += ["--compressed", shlex.quote(req.url)]
    return " ".join(parts)

def perform_get_with_params(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    params: Dict[str, Any],
) -> Any:
    resp = session.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)

    # print(f"[DEBUG] HTTP response ({resp.status_code}) body (first 800 chars): {resp.text[:800]}")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON: {e}\nBody starts with: {resp.text[:500]}")

# -------------- API wrappers -----------------
def get_org_info(session: requests.Session, url: str, token: str, orgid: str) -> Any:
    # Organization lookup must NOT be scoped to a project
    headers = build_headers(token, orgid, None)
    return perform_get(session, url, headers)

def get_applications(session: requests.Session, url: str, token: str, orgid: str, projectid: str) -> Any:
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

def get_clusters(session: requests.Session, url: str, token: str, orgid: str, projectid: str) -> Any:
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

def get_logs_query(
    session: requests.Session,
    url: str,
    token: str,
    orgid: str,
    projectid: str,
    credential_id: str,
    *,
    region: str,
    cluster_name: str,
    namespace: str,
    provider: str,
    env_id: str,
    app_id: str,
    start: Optional[str],
    end: Optional[str],
    log_type: str,
    log_group: str,
) -> Any:
    headers = build_headers(
        token, orgid, projectid,
        extra={
            "x-credential-id": credential_id,
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "user-agent": "Mozilla/5.0",
        }
    )
    params = {
        "region": region,
        "clusterName": cluster_name,
        "namespace": namespace,
        "provider": provider,
        "labels[0][key]": "environmentId",
        "labels[0][value]": env_id,
        "labels[1][key]": "applicationId",
        "labels[1][value]": app_id,  # use param, not hard-coded
        "startDate": start,
        "endDate": end,
        "logType": log_type,
        "logGroup": log_group,
    }
    # Optional: print a reproducible curl for /logs/query (token redacted)
    try:
        redacted_token = (token[:8] + "...redacted") if token else ""
        q_url = url
        curl_cmd_parts = [
            "curl", "-sS", "-G", q_url,
            "-H", "accept: application/json, text/plain, */*",
            "-H", "content-type: application/json",
            "-H", f"authorization: Bearer {redacted_token}",
            "-H", f"x-organization-id: {orgid}",
            "-H", f"x-project-id: {projectid}",
            "-H", f"x-credential-id: {credential_id}",
        ]
        for k, v in params.items():
            if v is None:
                continue
            curl_cmd_parts += ["--data-urlencode", f"{k}={v}"]
        # print(" ".join(shlex.quote(str(p)) for p in curl_cmd_parts))
    except Exception:
        pass

    return perform_get_with_params(session, url, headers, params)

def get_logs_result(
    session: requests.Session,
    url: str,
    token: str,
    orgid: str,
    projectid: str,
    credential_id: str,
    *,
    region: str,
    query_id: str,
    log_type: str,
) -> Any:
    headers = build_headers(
        token, orgid, projectid,
        extra={
            "x-credential-id": credential_id,
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "user-agent": "Mozilla/5.0",
        }
    )
    params = {"queryId": query_id, "region": region, "logType": log_type}
    # Print a reproducible curl for /logs/logs (token redacted)
    try:
        redacted_token = (token[:8] + "...redacted") if token else ""
        curl_parts = [
            "curl", "--location", f"{url}?queryId={query_id}&region={region}&logType={log_type}",
            "--header", "accept: application/json, text/plain, */*",
            "--header", "accept-language: en-GB,en-US;q=0.9,en;q=0.8",
            "--header", f"authorization: Bearer {redacted_token}",
            "--header", "cache-control: no-cache",
            "--header", "origin: https://console.skyu.io",
            "--header", "pragma: no-cache",
            "--header", "referer: https://console.skyu.io/",
            "--header", "user-agent: Mozilla/5.0",
            "--header", f"x-credential-id: {credential_id}",
            "--header", f"x-organization-id: {orgid}",
            "--header", f"x-project-id: {projectid}",
            "--header", f"x-trace-id: {str(uuid.uuid4())}",
            "--header", "x-auth-by: sa",
        ]

    except Exception:
        pass

    return perform_get_with_params(session, url, headers, params)

# -------------- Extraction helpers -----------------
def extract_application_ids(payload: Any) -> List[str]:
    """Extract app IDs from common shapes: list, or dict with data/items/applications."""
    records: List[Any] = []
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        # Look for a list under known keys
        for key in ("data", "items", "applications"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        # If nothing matched, fall back to treating the payload as a single record
        if not records:
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

def _short(text: str, max_len: int = 200) -> str:
    """Trim long strings for debug logs."""
    return text if len(text) <= max_len else text[:max_len] + "...<truncated>"

def extract_query_id_from_query_resp(obj: Any) -> Optional[str]:
    # If it's a JSON string, try to parse; if parsing fails, treat raw string as the id
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            s = obj.strip()
            if s:
                print(f"[extract] id via raw string")
                return s
            print("[extract] id not found (empty string)")
            return None

    if not isinstance(obj, dict):
        print("[extract] id not found (not a dict)")
        return None

    # {"data": {"id": "..."}}
    data = obj.get("data")
    if isinstance(data, dict):
        qid = data.get("id")
        if isinstance(qid, str) and qid:
            print("[extract] id via data.id")
            return qid

    # {"data": "..."}
    if isinstance(data, str) and data:
        print("[extract] id via data (string)")
        return data

    # {"data": [{"id": "..."}]}
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                print(f"[extract] id via data[{i}].id")
                return item["id"]

    # {"id": "..."}
    top_id = obj.get("id")
    if isinstance(top_id, str) and top_id:
        print("[extract] id via top-level id")
        return top_id

    print("[extract] id not found")
    return None

def extract_logs_results(obj: Any) -> List[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    data = obj.get("data")
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
    return []

def safe_slug(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', s or "")

# -------------- Main -----------------
def main():
    args = parse_args()

    base_url = args.base_url or API_BASE_DEFAULT
    org_url = build_url(base_url, ORGANIZATIONS_ENDPOINT)
    applications_url = build_url(base_url, APPLICATIONS_ENDPOINT)
    clusters_url = build_url(base_url, CLUSTERS_ENDPOINT)
    logs_query_url = build_url(base_url, LOGS_QUERY_ENDPOINT)
    logs_result_url = build_url(base_url, LOGS_RESULT_ENDPOINT)

    out_dir = Path(args.out_dir or "./logs_out")
    out_dir.mkdir(parents=True, exist_ok=True)

    session = new_session()

    # Final output containers
    apps_mapping: Dict[str, Dict[str, List[str]]] = {args.orgid: {}}
    clusters_by_project: Dict[str, List[Dict[str, Any]]] = {}
    logs_aggregated: List[Dict[str, Any]] = []

    def run_logs_pair(project_id: str, cluster_summary: Dict[str, Any], app_id: str) -> None:

        # If cluster summary is missing or incomplete, just print and skip (as requested)
        if not cluster_summary or not isinstance(cluster_summary, dict):
            print(f"No clusters available for this app: {app_id} (project {project_id})")
            return

        region = (cluster_summary.get("aws") or {}).get("region")
        cluster_name = cluster_summary.get("name")
        env_id = cluster_summary.get("envId")

        if not region or not cluster_name or not env_id:
            print(f"No clusters available for this app: {app_id} (project {project_id})")
            return

        namespace = args.namespace or f"project-{project_id.split('_', 1)[-1]}-prod"
        log_group = args.log_group or f"/aws/containerinsights/{cluster_name}/application"

        # --- Step 1: /logs/query ---
        try:
            q_json = get_logs_query(
                session=session,
                url=logs_query_url,
                token=args.token,
                orgid=args.orgid,
                projectid=project_id,
                credential_id=args.credential_id,
                region=region,
                cluster_name=cluster_name,
                namespace=namespace,
                provider="aws",
                env_id=env_id,
                app_id=app_id,
                start=args.start,
                end=args.end,
                log_type="application",
                log_group=log_group,
            )
        except Exception as e:
            print(f"[WARN] /logs/query failed for project {project_id}, cluster {cluster_name}, app {app_id}: {e}",
                  file=sys.stderr)
            return

        query_id = extract_query_id_from_query_resp(q_json)
        if not query_id:
            print(
                f"[WARN] logs query missing queryId for project {project_id}, cluster {cluster_name}, app {app_id}",
                file=sys.stderr,
            )
            return

        # Print the appId=queryId mapping
        print(f"appId={app_id} queryId={query_id}")

        # --- Step 2: /logs/logs ---
        try:
            logs_json = get_logs_result(
                session=session,
                url=logs_result_url,
                token=args.token,
                orgid=args.orgid,
                projectid=project_id,
                credential_id=args.credential_id,
                region=region,
                query_id=query_id,
                log_type="application",
            )
        except Exception as e:
            print(f"[WARN] /logs/logs failed for project {project_id}, cluster {cluster_name}, app {app_id}: {e}",
                  file=sys.stderr)
            return

        # Save the /logs/logs response as the main output file
        output_fname = f"{safe_slug(project_id)}__{safe_slug(cluster_name)}__{safe_slug(app_id)}__logs.json"
        (out_dir / output_fname).write_text(json.dumps(logs_json, indent=2))

        # Keep the aggregated summary in-memory if you still need it later
        results = extract_logs_results(logs_json)
        logs_aggregated.append({
            "projectId": project_id,
            "cluster": cluster_name,
            "appId": app_id,
            "results": results
        })

    # ======== Data discovery ========
    if args.projectid:
        project_id = args.projectid

        # Apps
        try:
            apps_payload = get_applications(session, applications_url, args.token, args.orgid, project_id)
            app_ids = extract_application_ids(apps_payload)
            apps_mapping[args.orgid][project_id] = app_ids
        except Exception as e:
            print(f"[ERROR] applications request failed for project {project_id}: {e}", file=sys.stderr)
            sys.exit(2)

        # Clusters
        try:
            cl_payload = get_clusters(session, clusters_url, args.token, args.orgid, project_id)
            clusters = summarize_clusters(cl_payload)
            clusters_by_project[project_id] = clusters
        except Exception as e:
            print(f"[ERROR] clusters request failed for project {project_id}: {e}", file=sys.stderr)
            clusters_by_project[project_id] = []

        # If NO clusters, just print per-app message and do not continue to logs calls
        if not clusters_by_project.get(project_id):
            for app_id in apps_mapping[args.orgid].get(project_id, []):
                print(f"No clusters available for this app: {app_id} (project {project_id})")
        else:
            # Logs per cluster x app
            for cs in clusters_by_project.get(project_id, []):
                for app_id in apps_mapping[args.orgid].get(project_id, []):
                    run_logs_pair(project_id, cs, app_id)

        print(json.dumps({
            "apps": apps_mapping,
            "clusters": clusters_by_project,
            "logsSummary": [
                {"projectId": it["projectId"], "cluster": it["cluster"], "appId": it["appId"], "count": len(it["results"])}
                for it in logs_aggregated
            ]
        }, indent=2))
        return

    # Discover all projects
    try:
        org_payload = get_org_info(session, org_url, args.token, args.orgid)
    except Exception as e:
        print(f"[ERROR] org request failed: {e}", file=sys.stderr)
        sys.exit(2)

    projects = list_projects_from_org_payload(org_payload)
    if not projects:
        print(json.dumps({
            "apps": apps_mapping,
            "clusters": {},
            "logsSummary": []
        }, indent=2))
        return

    for project_id, _project_name in projects:
        print(f"{project_id} - {_project_name}")
        clusters_by_project.setdefault(project_id, [])

        # Apps
        try:
            apps_payload = get_applications(session, applications_url, args.token, args.orgid, project_id)
            apps_mapping[args.orgid][project_id] = extract_application_ids(apps_payload)
        except Exception as e:
            print(f"[WARN] applications request failed for project {project_id}: {e}", file=sys.stderr)
            apps_mapping[args.orgid][project_id] = []

        # Clusters
        try:
            cl_payload = get_clusters(session, clusters_url, args.token, args.orgid, project_id)
            summaries = summarize_clusters(cl_payload)
            clusters_by_project[project_id].extend(summaries)
        except Exception as e:
            print(f"[WARN] clusters request failed for project {project_id}: {e}", file=sys.stderr)

        # If no clusters, print message per app and skip logs calls
        if not clusters_by_project.get(project_id):
            for app_id in apps_mapping[args.orgid].get(project_id, []):
                print(f"No clusters available for this app: {app_id} (project {project_id})")
            continue

        # Otherwise, run logs per cluster x app
        for cs in clusters_by_project.get(project_id, []):
            for app_id in apps_mapping[args.orgid].get(project_id, []):
                run_logs_pair(project_id, cs, app_id)

    # Final print (aggregate only)
    print(json.dumps({
        "apps": apps_mapping,
        "clusters": clusters_by_project,
        "logsSummary": [
            {"projectId": it["projectId"], "cluster": it["cluster"], "appId": it["appId"], "count": len(it["results"])}
            for it in logs_aggregated
        ]
    }, indent=2))

if __name__ == "__main__":
    main()
