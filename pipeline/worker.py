from ast import Return
from datetime import datetime
import uuid
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Tuple, Literal

# Add the parent directory to Python path to find log_Injest module
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from prefect import flow, get_run_logger, task
from prefect.settings import temporary_settings, PREFECT_LOGGING_LEVEL

from post_process.result_analyse import build_template_data
from post_process.send_notification import send_email_notification
from constants import EMAIL_NOTIFICATION_URL, TO_EMAIL, TEMPLATE_NAME, USER_AGENT, TIMEOUT, CLUSTER_ENV_ID
from post_process.file_service_uploader import upload_folder_as_zip,build_headers

# Log group configuration - can be modified per pipeline run
LOG_GROUPS_CONFIG = [
    {"name": "lambda-app0", "logGroup": "/aws/lambda/musatest1", "uniqueLabel": ""},
    {"name": "lambda-app1", "logGroup": "/aws/lambda/cloudzero-connected-account-Disc-DiscoveryFunction-b2kdydG5QuEX", "uniqueLabel": ""},
    # {"name": "lambda-cluster0", "logGroup": "/aws/eks/skyu-sandbox-k8s-cluster/cluster", "uniqueLabel": "cluster"},
]

def get_log_groups_config() -> List[Dict[str, str]]:
    """Get the current log groups configuration. Can be overridden for different pipeline runs."""
    return LOG_GROUPS_CONFIG

def set_log_groups_config(config: List[Dict[str, str]]) -> None:
    """Set a new log groups configuration for the pipeline."""
    global LOG_GROUPS_CONFIG
    LOG_GROUPS_CONFIG = config

@flow
def upload_report(token: str , org_id: str, proj_id: str,app_id,resource_type,results_dir: str = "results") -> None:
    logger = get_run_logger()
    logger.info("Upload report via file-service")

       # Build headers using worker-provided fields; resource/env IDs come from constants in file_service_uploader
    headers = build_headers(
        project_id=proj_id,
        org_id=org_id,
        api_token=token,
        env_id=CLUSTER_ENV_ID,
        resource_id=app_id,
        # resource_id / environment_id defaulted inside build_headers via config/constants.py
    )

    # If you want a ULID file name inside the uploader, it's already defaulted there.
    RESULTS_DIR = parent_dir / "results"   # <-- your report folder

    try:
        # TEST: Use the exact same path as the working curl command
        resp = upload_folder_as_zip(
                folder_path=RESULTS_DIR,
                headers=headers,
                provider="aws",
                zip_name="LAD_report.zip",
                resource_type= resource_type,
                cloud_storage_path="lad_report",
                # extra_headers={"x-some-extra": "value"},  # optional
            )
        logger.info(f"Upload status: {resp.status_code}")
        
        try:
            logger.info(f"Upload response JSON: {resp.json()}")
        except Exception:
            logger.info(f"Upload response text: {resp.text}")

        if not resp.ok:
            logger.warning("File-service returned non-2xx status. Check headers, token, and payload.")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise

@task
def report_post_process(*,dry_run: bool,token: str, org_id: str, proj_id: str,app_id,resource_type) -> None:
    logger = get_run_logger()
    logger.info("Post-processing report (analyze → upload)")

    upload_report(token, org_id, proj_id,app_id,resource_type)

    logger.info('Upload complete in piepline')

    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    RESULTS_DIR   = PROJECT_ROOT / "results"

    template_data = build_template_data(
        summaries_dir=RESULTS_DIR,  # Directory containing summary JSON files
        pattern="*_summary.json",
        top_k=10,  # Top N threat indicators
        max_reports=25,  # Maximum number of reports to include
    )

    # 2) Send using constants
    total_reports = (template_data.get("aggregate") or {}).get("total_reports", 0)
    if total_reports == 0:
        logger.info("No summary files found or parsed; skipping notification email.")
        return 0, "NO_REPORTS", template_data

    if dry_run:
        logger.info("[dry_run] would send SIEM email", extra={"template_data": template_data})
        return 0, "DRY_RUN", template_data

    status, resp = send_email_notification(
        api_url=EMAIL_NOTIFICATION_URL,
        bearer_token=token,
        org_id=org_id,
        project_id=proj_id,
        payload=template_data,  # Changed from template_data to payload
        user_agent=USER_AGENT,
        timeout=TIMEOUT,
    )
    logger.info("Post-processing complete")

    # return status, resp, template_data
    

@flow(name="log-anomaly-workerpipeline")
def pipeline(
    run_id: str = datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
    skip_install: bool = True,
    dry_run: bool = False,
    log_level: Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"] = "INFO",
) -> None:

    with temporary_settings({PREFECT_LOGGING_LEVEL: log_level}):
        logger = get_run_logger()
        logger.info(f"Starting pipeline run_id={run_id} dry_run={dry_run}")

        logger.info(f"Using log groups config: {get_log_groups_config()}")

        # SKYU_PROJECT_ID    = "project_737bb615-33a7-44e6-af4b-f0c7a2b44bd4"                 # <-- hardcode here
        # SKYU_ORG_ID        = "org_60ec574a-0543-490d-b13b-20241932f98a"                    # <-- hardcode here
        # SKYU_DEV_API_TOKEN     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXJ2aWNlQWNjb3VudCI6dHJ1ZSwiYXV0aERhdGEiOnsib3JnXzYwZWM1NzRhLTA1NDMtNDkwZC1iMTNiLTIwMjQxOTMyZjk4YSI6eyJyb2xlcyI6WyJvd25lciJdLCJwcm9qZWN0cyI6e319fSwic2VydmljZUFjY291bnRJZCI6IjcwMDI5N2YzLTFkZjktNDkzMi1hYTAwLTJkZmRhYzhjZTRmNiIsInVzZXJJZCI6Ijk4NjExOWEyLTQzMDQtNGE1YS1iYThmLWU2OTJjMDJkMDFhOCIsImlhdCI6MTc2MDQzOTg1Mn0.joFnREZht-vBXDuWovdPETNXJ403ha5fQ2vJSj8zd8I"     # <-- hardcode here (no "Bearer " prefix)

         # ── Hardcode ONLY these in worker.py (per your request) ──
        SKYU_PROJECT_ID    = "project_737bb615-33a7-44e6-af4b-f0c7a2b44bd4"                 # <-- hardcode here
        SKYU_ORG_ID        = "org_60ec574a-0543-490d-b13b-20241932f98a"                    # <-- hardcode here
        SKYU_DEV_API_TOKEN     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXJ2aWNlQWNjb3VudCI6dHJ1ZSwiYXV0aERhdGEiOnsib3JnXzYwZWM1NzRhLTA1NDMtNDkwZC1iMTNiLTIwMjQxOTMyZjk4YSI6eyJyb2xlcyI6WyJvd25lciJdLCJwcm9qZWN0cyI6e319fSwic2VydmljZUFjY291bnRJZCI6IjcwMDI5N2YzLTFkZjktNDkzMi1hYTAwLTJkZmRhYzhjZTRmNiIsInVzZXJJZCI6Ijk4NjExOWEyLTQzMDQtNGE1YS1iYThmLWU2OTJjMDJkMDFhOCIsImlhdCI6MTc2MDQzOTg1Mn0.joFnREZht-vBXDuWovdPETNXJ403ha5fQ2vJSj8zd8I"     # <-- hardcode here
        SKYU_RESOURCE_TYPE = "anomaly-log-template"    # <-- hardcode here
        APP_ID    = 'app_771a94d7-0258-489c-a049-77a79eda2cb4'      # <-- hardcode here (or f"/loganomaly/{generate_ulid()}")



        # 3) Analyze + notifications process
        report_post_process(dry_run= dry_run,token=SKYU_DEV_API_TOKEN,org_id=SKYU_ORG_ID,proj_id=SKYU_PROJECT_ID,app_id=APP_ID,resource_type=SKYU_RESOURCE_TYPE)

        logger.info("Pipeline complete.")

if __name__ == "__main__":
    # Run locally: python worker.py
    # You can modify the LOG_GROUPS_CONFIG here before running
    # Example:
    # LOG_GROUPS_CONFIG = [
    #     {"name": "my-service", "logGroup": "/aws/lambda/my-service", "uniqueLabel": ""},
    #     {"name": "my-cluster", "logGroup": "/aws/eks/my-cluster/cluster", "uniqueLabel": "namespace"},
    # ]
    pipeline(skip_install=False)