import json
import uuid
import requests
from prefect import get_run_logger

def send_email_notification(
    *,
    api_url: str,
    bearer_token: str,
    org_id: str,
    project_id: str,
    user_agent: str = "loganomaly-worker/1.0",
    timeout: int = 20,
    payload
) :
    """
    Low-level helper: sends a single template email via SKYU Notifications service.
    Returns (status_code, text_or_json_string).
    """
    logger = get_run_logger()
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "accept": "application/json, text/plain, */*",
        "x-organization-id": org_id,
        "x-project-id": project_id,
        "x-trace-id": str(uuid.uuid4()),
        "x-auth-by": "sa",  # keep if your backend expects it
        "User-Agent": user_agent,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    try:
        body = resp.json()
        body_text = json.dumps(body, ensure_ascii=False)
        logger.info("Email sent.", extra={"status": resp.status_code, "body": body})
    except Exception:
        body_text = resp.text or ""
        logger.info("Email sent.", extra={"status": resp.status_code, "body_text": body_text[:500]})
    return resp.status_code, body_text
