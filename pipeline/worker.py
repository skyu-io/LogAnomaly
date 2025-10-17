import sys
import os
from pathlib import Path

# Add the parent directory to Python path to find log_Injest module
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from prefect import flow, get_run_logger, task
from datetime import datetime
from log_Injest.Ingest_cloudwatch_logs import fetch_cloudwatch_logs
from yaml_extractor.yaml_config_fetcher import fetch_yaml_config

@task
def install_packages() -> None:
    logger = get_run_logger()
    logger.info("Installing packages")

@flow
def config_mistral_server():
    logger = get_run_logger()
    logger.info("grab the mistral ami and config")
    logger.info("start mistral server")
    logger.info("grab the ip ")


@flow
def execute_cloudwatch_log_ingestion() -> None:
    logger = get_run_logger()
    logger.info("check for status up and running and continue the process")
    logger.info("Execute CloudWatch log download")
    fetch_cloudwatch_logs(
        token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXJ2aWNlQWNjb3VudCI6dHJ1ZSwiYXV0aERhdGEiOnsib3JnXzYwZWM1NzRhLTA1NDMtNDkwZC1iMTNiLTIwMjQxOTMyZjk4YSI6eyJyb2xlcyI6WyJvd25lciJdLCJwcm9qZWN0cyI6e319fSwic2VydmljZUFjY291bnRJZCI6IjcwMDI5N2YzLTFkZjktNDkzMi1hYTAwLTJkZmRhYzhjZTRmNiIsInVzZXJJZCI6Ijk4NjExOWEyLTQzMDQtNGE1YS1iYThmLWU2OTJjMDJkMDFhOCIsImlhdCI6MTc2MDQzOTg1Mn0.joFnREZht-vBXDuWovdPETNXJ403ha5fQ2vJSj8zd8I",
        orgid="org_60ec574a-0543-490d-b13b-20241932f98a",
        credential_id="credential_5c8982b5-a4cc-4329-a60f-6fdcb67b01da",
        project_id="project_15db1623-90a0-4bb7-b515-f5d657c75587",
        start="2025-10-17 02:27:40.015",
        end="2025-10-17 02:37:40.015"
        )
    transform_log__to_validated_schema()
    logger.info("save file in local")


@flow
def download_config_yaml() -> None:
    logger = get_run_logger()
    logger.info("Fetch config YAML via SKY cone gitops repo")
    res = fetch_yaml_config(
        destination_config_dir="./config",
        app_id="myservice",  # or None to always use common
        # repo_url="https://github.com/skyu-io/oho-log-anomaly-skyu-gitops-446358f6.git",
        repo_url="https://github.com/salindaFinsighture/oho-log-anomaly-skyu-gitops-clone",
        config_root_rel="loganomaly/config",
        reuse_local_repo=None,  # set to a local repo path to skip cloning
        overwrite=True,
        clean_destination_first=True,
    )
    logger.debug(f"copied={len(res.copied_files)} files → {res.destination}")

@task
def transform_log__to_validated_schema() -> None:
    logger = get_run_logger()
    logger.info("Convert logs to validate schema")

@task
def prepare_prerequisite() -> None:
    logger = get_run_logger()
    logger.info("Preparing prerequisites: logs + config")
    # config_mistral_server()
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
