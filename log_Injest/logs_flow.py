# skyu_logs/logs_flow.py
from typing import Any, Dict, List, Optional
from pathlib import Path
from prefect import get_run_logger
import requests

from .http_client import build_headers, request_json_and_trace
from .constants import HTTP_TIMEOUT


def retrieve_app_logs_for_cluster(
    *,
    session: requests.Session,
    logs_query_url: str,
    logs_result_url: str,
    token: str,
    orgid: str,
    project_id: str,
    credential_id: str,
    region: str,
    cluster_name: str,
    env_id: str,
    app_id: str,
    namespace: str,
    log_group: str,
    out_dir: Path,
    logs_aggregated: List[Dict[str, Any]],
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the logs query and fetch process for a specific app/cluster pair."""
    logger = get_run_logger()
    logger.debug(f"[retrieve_app_logs_for_cluster] started for app={app_id}, cluster={cluster_name}")
    
    try:
        # Step 1: Query logs using GET with query parameters (as shown in curl example)
        query_params = {
            "region": region,
            "clusterName": cluster_name,
            "namespace": namespace,
            "provider": "aws",
            "labels[0][key]": "environmentId",
            "labels[0][value]": env_id,
            "labels[1][key]": "applicationId", 
            "labels[1][value]": app_id,
            "startDate": start,
            "endDate": end,
            "logType": "application",
            "logGroup": log_group
        }
        
        # Build headers with additional required headers from curl example
        headers = build_headers(token, orgid, project_id)
        headers.update({
            "x-credential-id": credential_id,
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        })
        
        query_response = session.get(
            logs_query_url,
            headers=headers,
            params=query_params,
            timeout=HTTP_TIMEOUT
        )
        
        logger.info(f"[retrieve_app_logs_for_cluster] query response status: {query_response.status_code}")
        logger.info(f"[retrieve_app_logs_for_cluster] query response text: {query_response.text[:500]}")
        
        if query_response.status_code != 200:
            logger.error(f"[retrieve_app_logs_for_cluster] query failed with status {query_response.status_code}: {query_response.text[:500]}")
            return {"status": "failed", "reason": f"query_http_{query_response.status_code}"}
        
        try:
            query_data = query_response.json()
        except Exception as e:
            logger.error(f"[retrieve_app_logs_for_cluster] failed to parse query response JSON: {e}")
            return {"status": "failed", "reason": "query_json_parse_error"}
        
        if not query_data or 'data' not in query_data:
            logger.warning(f"[retrieve_app_logs_for_cluster] no queryId in response for app={app_id}")
            return {"status": "failed", "reason": "no_query_id"}
        
        query_id = query_data['data']
        logger.debug(f"[retrieve_app_logs_for_cluster] got queryId={query_id}")
        
        # Step 2: Fetch logs using GET with query parameters
        logs_params = {
            "queryId": query_id,
            "region": region,
            "logType": "application"
        }
        
        logs_response = session.get(
            logs_result_url,
            headers=headers,
            params=logs_params,
            timeout=HTTP_TIMEOUT
        )
        
        logger.info(f"[retrieve_app_logs_for_cluster] logs response status: {logs_response.status_code}")
        logger.info(f"[retrieve_app_logs_for_cluster] logs response text: {logs_response.text[:500]}")
        
        if logs_response.status_code != 200:
            logger.error(f"[retrieve_app_logs_for_cluster] logs fetch failed with status {logs_response.status_code}: {logs_response.text[:500]}")
            return {"status": "failed", "reason": f"logs_http_{logs_response.status_code}"}
        
        try:
            logs_data = logs_response.json()
        except Exception as e:
            logger.error(f"[retrieve_app_logs_for_cluster] failed to parse logs response JSON: {e}")
            return {"status": "failed", "reason": "logs_json_parse_error"}
        
        if not logs_data:
            logger.warning(f"[retrieve_app_logs_for_cluster] no logs response for queryId={query_id}")
            return {"status": "failed", "reason": "no_logs_response"}
        
        # Check if there are actual log results to save
        results = logs_data.get('results', [])
        if not results or len(results) == 0:
            logger.info(f"[retrieve_app_logs_for_cluster] no log data found for app={app_id}, cluster={cluster_name} - skipping file creation")
            return {
                "status": "success",
                "queryId": query_id,
                "logFile": None,
                "logCount": 0
            }
        
        # Step 3: Save logs to file and add to aggregated results (only if there's data)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_file = out_dir / f"logs_{app_id}_{cluster_name}.json"
        
        with open(log_file, 'w') as f:
            import json
            json.dump(logs_data, f, indent=2)
        
        logger.info(f"[retrieve_app_logs_for_cluster] saved logs to {log_file} (found {len(results)} log entries)")
        
        # Add to aggregated results
        logs_aggregated.append({
            "projectId": project_id,
            "cluster": cluster_name,
            "appId": app_id,
            "results": results
        })
        
        return {
            "status": "success",
            "queryId": query_id,
            "logFile": str(log_file),
            "logCount": len(results)
        }
        
    except Exception as e:
        logger.error(f"[retrieve_app_logs_for_cluster] error for app={app_id}, cluster={cluster_name}: {e}")
        return {"status": "error", "reason": str(e)}
