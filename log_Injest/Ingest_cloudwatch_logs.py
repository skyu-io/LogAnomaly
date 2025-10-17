from prefect import flow, get_run_logger
from typing import Optional, Union
from .client import SkyuClient
from pathlib import Path
from .constants import API_BASE_DEFAULT, OUT_DIR_DEFAULT

@flow(name="Fetch Skyu Logs")
def fetch_cloudwatch_logs(*,
    token: str,
    orgid: str,
    credential_id: str,
    project_id: Optional[str] = None,
    start: Optional[str] = None,   # e.g. "2025-10-14 07:02:54.939"
    end: Optional[str] = None,     # e.g. "2025-10-14 08:02:54.939"
) -> dict:
    logger = get_run_logger()
    client = SkyuClient(
        token=token,
        orgid=orgid,
        base_url=API_BASE_DEFAULT,
    )

    if project_id:
        result = client.fetch_logs_for_project(
            project_id=project_id,
            credential_id=credential_id,
            out_dir=Path(OUT_DIR_DEFAULT),
            start=start,
            end=end,
        )
        logger.info("Single-project fetch complete: project=%s, summary=%s",
                    project_id, result.get("logsSummary_acquired"))
    else:
        result = client.fetch_logs_for_all_projects(
            credential_id=credential_id,
            out_dir=Path(OUT_DIR_DEFAULT),
            start=start,
            end=end,
        )
        logger.info("Org-wide fetch complete: projects=%d, totalClusters=%d, summaries=%d",
                    len(result.get("apps", result.get("apps_info", {})).get(orgid, {})),
                    sum(len(v) for v in result.get("clusters", {}).values()) if "clusters" in result else
                    sum(len(v) for v in result.get("clusters_info", {}).values()),
                    len(result.get("logsSummary", result.get("logsSummary_acquired", []))),
                   )

    logger.info(f"Summary: {result}")
    return result

