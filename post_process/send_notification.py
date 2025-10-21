import json
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from prefect import task, get_run_logger

from .constants import (
    SKYU_DEV_API_TOKEN as SKYU_API_TOKEN,
    )

def _send_skyu_template_email(
    *,
    api_url: str,
    bearer_token: str,
    org_id: str,
    project_id: str,
    to_email: str,
    template_name: str,
    template_data: Dict,
    user_agent: str = "loganomaly-worker/1.0",
    timeout: int = 20,
) -> Tuple[int, str]:
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

    payload = {
        "to": to_email,
        "templateName": template_name,
        "data": template_data or {},
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    try:
        body = resp.json()
        logger.info(f"Email sent successfully. Body: {body}")
        body_text = json.dumps(body, ensure_ascii=False)
    except Exception:
        body_text = resp.text or ""

    return resp.status_code, body_text


@task
def analyze_reports_and_notify(
    results_dir: str = "results",
    *,
    # Trigger rule
    error_threshold: int = 5,              # fire when error_count >= threshold
    # SKYU API config
    api_url: str = "https://api.dev.skyu.io/notifications-service/emails/sendTemplate",
    bearer_token: Optional[str] = SKYU_API_TOKEN,    # put token in an env var and pass it in!
    org_id: str = "org_60ec574a-0543-490d-b13b-20241932f98a",
    project_id: str = "project_15db1623-90a0-4bb7-b515-f5d657c75587",
    to_email: str = "salinda.f@insighture.com",
    template_name: str = "invite",
    template_data: Optional[Dict] = None,  # {"email": "...", "fullName": "...", ...}
) -> None:
    """
    Find *summary.json reports in `results_dir`, read error_count, and, if >= error_threshold,
    send a SKYU template email.

    Example call:
        analyze_reports_and_notify(
            results_dir="results",
            bearer_token=os.environ["SKYU_API_TOKEN"],
            template_data={
                "email": "salinda.f@insighture.com",
                "fullName": "thameera",
                "orgDesignation": "orgDesignation",
                "orgName": "orgName",
            },
        )
    """
    log = get_run_logger()

    if not bearer_token:
        log.error("No bearer_token supplied. Aborting notification step.")
        return

    # Make results_dir relative to project root if it's a relative path
    if not Path(results_dir).is_absolute():
        # Get the project root (parent of post_process folder)
        project_root = Path(__file__).parent.parent
        results_path = project_root / results_dir
    else:
        results_path = Path(results_dir)
    if not results_path.is_dir():
        log.warning(f"Results folder not found: {results_path.resolve()}")
        return

    # Default template data if none provided
    if template_data is None:
        template_data = {
            "email": to_email,
            "fullName": "thameera",
            "orgDesignation": "orgDesignation",
            "orgName": "orgName",
        }

    # Find all *_summary.json reports
    summary_files = sorted(results_path.glob("*_summary.json"))
    if not summary_files:
        log.info(f"No summary files found in {results_path.resolve()}")
        return

    log.info(f"Scanning {len(summary_files)} summary files in '{results_dir}'")

    # Process each summary and trigger notifications as needed
    for summary_file in summary_files:
        app_name = summary_file.name.replace("_summary.json", "")
        try:
            with summary_file.open("r", encoding="utf-8") as f:
                summary = json.load(f)
        except Exception as ex:
            log.error(f"Failed to read {summary_file.name}: {ex}")
            continue

        # Navigate to operational_metrics.system_health.error_count
        try:
            op = summary.get("operational_metrics", {})
            sys_health = op.get("system_health", {})
            error_count = int(sys_health.get("error_count", 0))
        except Exception:
            error_count = 0

        log.info(f"[{app_name}] error_count={error_count}")

        # Trigger rule: >= threshold (change to == if you want exact match)
        if error_count >= error_threshold:
            log.warning(f"[{app_name}] error_count >= {error_threshold} → sending notification")
            status, body_text = _send_skyu_template_email(
                api_url=api_url,
                bearer_token=bearer_token,
                org_id=org_id,
                project_id=project_id,
                to_email=to_email,
                template_name=template_name,
                template_data=template_data,
            )
            log.info(f"[{app_name}] Notification response {status}: {body_text[:500]}")
            if status >= 400:
                log.warning(f"[{app_name}] Notification returned non-2xx status ({status}).")
        else:
            log.debug(f"[{app_name}] Below threshold ({error_threshold}); no notification sent.")
