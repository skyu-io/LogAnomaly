import sys
import os
from pathlib import Path

# Add the parent directory to Python path to find log_Injest module
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from prefect import flow, get_run_logger, task
from datetime import datetime
from mistral_vllm.run_launcher import run_launcher, LaunchResult

# from log_Injest.Ingest_cloudwatch_logs import fetch_cloudwatch_logs

@task
def install_packages() -> None:
    logger = get_run_logger()
    logger.info("Installing packages")

@flow
def config_mistral_server():
    logger = get_run_logger()

    base = Path(__file__).parent.parent  # repo root
    env_file = base / "mistral_vllm" / "mistral.env"
    script = base / "mistral_vllm" / "test.sh"   

    print("ENV:", env_file.resolve())
    print("SCRIPT:", script.resolve())  

    result = run_launcher(
        env_file=str(env_file),
        script_path=str(script),
        extra_env={
                "AWS_PROFILE": "prod",
                "INSTANCE_WAIT_SECS": "2400",   # 40 min ceiling for EC2 to be running
                "STATUS_OK_WAIT_SECS": "2400",  # 40 min for status checks
                "HEALTH_WAIT_SECS": "1500",     # 25 min for vLLM to come up
            },
            timeout_sec=60 * 60,   # 1 hour hard cap for the whole run
            stream=True            # get live logs from bash
            )
    print("Instance:", result.instance_id)
    print("API URL:", result.api_url)
    logger.info("grab the ip ")


@flow
def execute_cloudwatch_log_ingestion() -> None:
    logger = get_run_logger()
    logger.info("check for status up and running and continue the process")
    logger.info("Execute CloudWatch log download")
    # fetch_cloudwatch_logs(
    #     token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXJ2aWNlQWNjb3VudCI6dHJ1ZSwiYXV0aERhdGEiOnsib3JnXzYwZWM1NzRhLTA1NDMtNDkwZC1iMTNiLTIwMjQxOTMyZjk4YSI6eyJyb2xlcyI6WyJvd25lciJdLCJwcm9qZWN0cyI6e319fSwic2VydmljZUFjY291bnRJZCI6IjcwMDI5N2YzLTFkZjktNDkzMi1hYTAwLTJkZmRhYzhjZTRmNiIsInVzZXJJZCI6Ijk4NjExOWEyLTQzMDQtNGE1YS1iYThmLWU2OTJjMDJkMDFhOCIsImlhdCI6MTc2MDQzOTg1Mn0.joFnREZht-vBXDuWovdPETNXJ403ha5fQ2vJSj8zd8I",
    #     orgid="org_60ec574a-0543-490d-b13b-20241932f98a",
    #     credential_id="credential_5c8982b5-a4cc-4329-a60f-6fdcb67b01da",
    #     project_id="project_15db1623-90a0-4bb7-b515-f5d657c75587",
    #     start="2025-10-17 02:27:40.015",
    #     end="2025-10-17 02:37:40.015"
    #     )
    transform_log__to_validated_schema()
    logger.info("save file in local")


@flow
def download_config_yaml() -> None:
    logger = get_run_logger()
    logger.info("Fetch config YAML via curl from SkyU")
    logger.info("Edit the yaml file with updated configs from mistral server")

@task
def transform_log__to_validated_schema() -> None:
    logger = get_run_logger()
    logger.info("Convert logs to validate schema")

@task
def prepare_prerequisite() -> None:
    logger = get_run_logger()
    logger.info("Preparing prerequisites: logs + config")
    config_mistral_server()
    execute_cloudwatch_log_ingestion()
    download_config_yaml()
    logger.info("Prerequisites complete")


@task
def execute_log_anomaly() -> None:
    logger = get_run_logger()
    logger.info("Execute log anomaly binary")


@flow
def send_notification_emails() -> None:
    logger = get_run_logger()
    logger.info("Send notification emails")


@flow
def analyze_report(dry_run: bool) -> None:
    logger = get_run_logger()
    logger.info("Analyze reports locally and decide what to notify/email")
    if not dry_run:
        logger.info("dry_run=False → sending notifications")
        send_notification_emails()
    else:
        logger.info("Dry-run enabled: skipping send_notification_emails()")


@flow
def upload_report() -> None:
    logger = get_run_logger()
    logger.info("Upload report via file-service")


@task
def report_post_process(dry_run: bool) -> None:
    logger = get_run_logger()
    logger.info("Post-processing report (analyze → upload)")
    analyze_report(dry_run)
    upload_report()
    logger.info("Post-processing complete")


@flow(name="log-anomaly-pipeline")
def pipeline(
    run_id: str = datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
    skip_install: bool = True,
    dry_run: bool = False,
) -> None:
    logger = get_run_logger()
    logger.info(f"Starting pipeline run_id={run_id} dry_run={dry_run}")

    if not skip_install:
        install_packages()
    else:
        logger.info("skip_install=True → skipping install_packages()")

    # 1) Pull logs and configs
    prepare_prerequisite()

    # 2) Run anomaly detection
    execute_log_anomaly()

    # 3) Analyze + notifications process
    report_post_process(dry_run)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    # Run locally: python worker.py
    pipeline()
