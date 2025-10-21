# skyu_logs/skyu_api_service.py
from typing import Any, Dict, List
import requests
from prefect import get_run_logger

from .http_client import build_headers, request_json_and_trace, _to_curl
from .constants import HTTP_TIMEOUT


def get_org_info(session: requests.Session, url: str, token: str, orgid: str) -> Any:
    logger = get_run_logger()
    logger.debug(f"[get_org_info] started (orgid={orgid}, url={url})")

    resp = session.get(url, headers=build_headers(token, orgid, None), timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        logger.debug(f"[get_org_info] http {resp.status_code}")
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    logger.debug("[get_org_info] success")
    return data


def get_applications(session: requests.Session, url: str, token: str, orgid: str, projectid: str) -> Any:
    logger = get_run_logger()
    logger.debug(f"[get_applications] started (orgid={orgid}, projectid={projectid}, url={url})")

    headers = build_headers(
        token, orgid, projectid,
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
    resp = session.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        logger.debug(f"[get_applications] http {resp.status_code}")
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    logger.debug("[get_applications] success")
    return data


def get_clusters(session: requests.Session, url: str, token: str, orgid: str, projectid: str) -> Any:
    logger = get_run_logger()
    logger.info(f"[get_clusters] started (orgid={orgid}, projectid={projectid}, url={url})")

    headers = build_headers(
        token, orgid, projectid,
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
    
    # Perform request
    resp = session.get(url, headers=headers, timeout=HTTP_TIMEOUT)

    # Log exact cURL of the executed request
    try:
        curl_str = _to_curl(resp.request)
        logger.info("[get_clusters] cURL: %s", curl_str)
    except Exception as _:
        logger.info("[get_clusters] cURL: <failed to render>")

    # Log status and a safe preview of the response body
    body_preview = resp.text[:2000].replace("\n", "\\n") if resp.text else ""
    logger.info("[get_clusters] HTTP %s, preview: %s", resp.status_code, body_preview)

    if resp.status_code != 200:
        logger.error(f"[get_clusters] HTTP {resp.status_code}: {body_preview}")
        raise RuntimeError(f"HTTP {resp.status_code}: {body_preview}")

    # Parse JSON (log parse issues with a short preview)
    try:
        data = resp.json()
        logger.info(f"[get_clusters] JSON response: {data}")
    except Exception as e:
        logger.error("[get_clusters] JSON parse error: %s; body preview: %s", e, body_preview[:500])
        raise RuntimeError(f"Failed to parse JSON: {e}\nBody: {body_preview[:500]}")

    logger.info("[get_clusters] success")
    return data


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
    start: str | None,
    end: str | None,
    log_type: str,
    log_group: str,
    trace_steps: List[Dict[str, str]],
) -> Any:
    logger = get_run_logger()
    logger.debug(
        "[get_logs_query] started "
        f"(org={orgid}, project={projectid}, region={region}, cluster={cluster_name}, "
        f"ns={namespace}, provider={provider}, env={env_id}, app={app_id}, "
        f"log_type={log_type}, log_group={log_group})"
    )

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
        "labels[1][value]": app_id,
        "startDate": start,
        "endDate": end,
        "logType": log_type,
        "logGroup": log_group,
    }

    result = request_json_and_trace(session, url, headers, params, trace_steps, label="GET /logs/query")
    logger.debug("[get_logs_query] success")
    return result


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
    trace_steps: List[Dict[str, str]],
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
    return request_json_and_trace(session, url, headers, params, trace_steps, label="GET /logs/logs")
