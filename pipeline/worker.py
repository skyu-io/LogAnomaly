from prefect import flow, get_run_logger, task
from datetime import datetime


@task
def install_packages() -> None:
    logger = get_run_logger()
    logger.info("Installing packages")


@flow
def execute_cloudwatch_log_ingestion() -> None:
    logger = get_run_logger()
    logger.info("Execute CloudWatch log download")


@flow
def download_config_yaml() -> None:
    logger = get_run_logger()
    logger.info("Fetch config YAML via curl from SkyU")


@task
def prepare_prerequisite() -> None:
    logger = get_run_logger()
    logger.info("Preparing prerequisites: logs + config")
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
    skip_install: bool = False,
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
