import sys
import os
import subprocess
from pathlib import Path
from typing import List, Dict

# Add the parent directory to Python path to find log_Injest module
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from prefect import flow, get_run_logger, task
from datetime import datetime
# from log_Injest.Ingest_cloudwatch_logs import fetch_cloudwatch_logs
from yaml_extractor.yaml_config_fetcher import fetch_yaml_config
from loganomaly.processor import process_all_files
from log_Injest.prepare_jobs import main as prepare_jobs_main
from post_process.file_service_uploader import upload_folder_as_zip, generate_ulid


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


@task
def install_packages() -> None:
    logger = get_run_logger()
    logger.info("Installing packages")

# @task
# def create_fallback_test_data() -> None:
#     """Create fallback test data if log download fails"""
#     logger = get_run_logger()
#     logger.info("Creating fallback test data")
    
#     # Change to project root directory
#     original_cwd = os.getcwd()
#     project_root = Path(__file__).parent.parent
#     os.chdir(project_root)
    
#     try:
#         # Create test_data directory if it doesn't exist
#         test_data_dir = Path("log_Injest/test_data")
#         test_data_dir.mkdir(parents=True, exist_ok=True)
        
#         # Create a simple test log file
#         test_log_file = test_data_dir / "fallback_test.json"
#         test_data = [
#             {
#                 "@timestamp": "2025-10-06T10:00:00.000Z",
#                 "@message": {
#                     "time": "2025-10-06T10:00:00.000Z",
#                     "stream": "stdout",
#                     "_p": "F",
#                     "log": "Test log entry for fallback data",
#                     "data": {"level": "info", "message": "Test log entry"},
#                     "kubernetes": {
#                         "pod_name": "test-pod",
#                         "pod_id": "test-pod-id",
#                         "docker_id": "test-docker-id"
#                     }
#                 }
#             }
#         ]
        
#         with open(test_log_file, 'w') as f:
#             import json
#             json.dump(test_data, f, indent=2)
        
#         logger.info(f"Created fallback test data: {test_log_file}")
        
#     except Exception as e:
#         logger.error(f"Error creating fallback test data: {e}")
#     finally:
#         # Restore original working directory
#         os.chdir(original_cwd)

@task
def prepare_and_download_logs(start_time: str, end_time: str, region: str = "us-east-1") -> None:
    """Prepare jobs and download logs using prepare_jobs.py"""
    logger = get_run_logger()
    logger.info(f"Preparing jobs and downloading logs from {start_time} to {end_time}")
    
    # Change to log_Injest directory
    original_cwd = os.getcwd()
    log_injest_dir = Path(__file__).parent.parent / "log_Injest"
    os.chdir(log_injest_dir)
    
    try:
        # Call prepare_jobs with parameters
        args = {
            "start": start_time,
            "end": end_time,
            "region": region,
            "download": True,
            "transform": True,
            "jobs_file": "jobs.json"
        }
        
        logger.info("Calling prepare_jobs.py with parameters: " + str(args))
        prepare_jobs_main(args, config=get_log_groups_config())
        logger.info("Successfully prepared jobs and downloaded logs")
        
    except Exception as e:
        logger.error(f"Error in prepare_and_download_logs: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Don't raise the exception to prevent pipeline crash
        logger.warning("Continuing pipeline despite log download failure")
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

@task
def prepare_and_download_logs_safe(start_time: str, end_time: str, region: str = "us-east-1") -> bool:
    """Safe version that returns success/failure status instead of crashing"""
    logger = get_run_logger()
    logger.info(f"Preparing jobs and downloading logs from {start_time} to {end_time}")
    
    # Change to log_Injest directory
    original_cwd = os.getcwd()
    log_injest_dir = Path(__file__).parent.parent / "log_Injest"
    os.chdir(log_injest_dir)
    
    try:
        # Call prepare_jobs with parameters
        args = {
            "start": start_time,
            "end": end_time,
            "region": region,
            "download": True,
            "transform": True,
            "jobs_file": "jobs.json"
        }
        
        logger.info("Calling prepare_jobs.py with parameters: " + str(args))
        
        # Add some debugging
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Jobs file exists: {os.path.exists('jobs.json')}")
        if os.path.exists('jobs.json'):
            with open('jobs.json', 'r') as f:
                jobs_content = f.read()
                logger.info(f"Jobs file content: {jobs_content[:500]}...")
        
        prepare_jobs_main(args, config=get_log_groups_config())
        logger.info("Successfully prepared jobs and downloaded logs")
        return True
        
    except RuntimeError as e:
        logger.error(f"Runtime error in prepare_and_download_logs_safe: {e}")
        # Check if it's a download script failure
        if "Download script failed" in str(e):
            logger.error("Download script failed - this might be due to AWS permissions, network issues, or invalid log groups")
            logger.error("Continuing pipeline without downloaded logs")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in prepare_and_download_logs_safe: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

@task
def prepare_and_download_logs_subprocess(start_time: str, end_time: str, region: str = "us-east-1") -> None:
    """Alternative approach: Use subprocess to call prepare_jobs.py"""
    logger = get_run_logger()
    logger.info(f"Preparing jobs and downloading logs from {start_time} to {end_time} (subprocess method)")
    
    # Change to log_Injest directory
    original_cwd = os.getcwd()
    log_injest_dir = Path(__file__).parent.parent / "log_Injest"
    os.chdir(log_injest_dir)
    
    try:
        # Build command
        cmd = [
            "python", "prepare_jobs.py",
            "--start", start_time,
            "--end", end_time,
            "--region", region,
            "--download",
            "--transform",
            "--jobs-file", "jobs.json"
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        logger.info("Command output:")
        logger.info(result.stdout)
        if result.stderr:
            logger.warning("Command stderr:")
            logger.warning(result.stderr)
            
        logger.info("Successfully prepared jobs and downloaded logs")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return code {e.returncode}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error in prepare_and_download_logs_subprocess: {e}")
        raise
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

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
    
    # Use the new prepare_and_download_logs task
    prepare_and_download_logs(
        start_time="2025-10-17T02:27:40.015Z",
        end_time="2025-10-17T02:37:40.015Z",
        region="us-east-1"
    )
    
    # Keep the old fetch_cloudwatch_logs as backup if needed
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
    # execute_cloudwatch_log_ingestion()
    
    # Use safe version that won't crash the pipeline
    success = prepare_and_download_logs_safe(
        start_time="2025-10-06T00:00:00Z",
        end_time="2025-10-07T23:59:59Z",
        region="us-east-1"
    )
    
    if success:
        logger.info("Log download completed successfully")
    else:
        logger.warning("Log download failed, but continuing pipeline")
        # Create some test data if download failed
        # create_fallback_test_data()
    download_config_yaml()
    logger.info("Prerequisites complete")


@task
def execute_log_anomaly() -> None:
    """Execute log anomaly analysis using the loganomaly module"""
    logger = get_run_logger()
    logger.info("Execute log anomaly analysis")
    
    # Change to project root directory
    original_cwd = os.getcwd()
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    try:
        # Set up the environment for loganomaly
        input_folder = "log_Injest/test_data"  # Our downloaded logs
        output_folder = "results"
        config_file = "loganomly.yaml"
        
        logger.info(f"Input folder: {input_folder}")
        logger.info(f"Output folder: {output_folder}")
        logger.info(f"Config file: {config_file}")
        
        # Check if input folder exists and has files
        if not os.path.exists(input_folder):
            logger.error(f"Input folder not found: {input_folder}")
            return
            
        # Count log files
        supported_extensions = (".json", ".log", ".txt")
        log_files = [f for f in os.listdir(input_folder) if f.endswith(supported_extensions)]
        
        if not log_files:
            logger.warning(f"No supported log files found in {input_folder}")
            return
            
        logger.info(f"Found {len(log_files)} log files to process: {log_files}")
        
        # Temporarily modify the config to use our input folder
        from loganomaly import config as app_config
        original_input_folder = app_config.INPUT_FOLDER
        original_results_folder = app_config.RESULTS_FOLDER
        
        try:
            # Update config to use our folders
            app_config.INPUT_FOLDER = input_folder
            app_config.RESULTS_FOLDER = output_folder
            
            # Ensure output folder exists
            os.makedirs(output_folder, exist_ok=True)
            
            # Import and run the processor
            from loganomaly.processor import process_all_files
            logger.info("Starting log anomaly analysis...")
            process_all_files()
            logger.info("Log anomaly analysis completed successfully")
            
        finally:
            # Restore original config values
            app_config.INPUT_FOLDER = original_input_folder
            app_config.RESULTS_FOLDER = original_results_folder
            
    except Exception as e:
        logger.error(f"Error in execute_log_anomaly: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

@task
def execute_log_anomaly_subprocess() -> None:
    """Alternative approach: Execute log anomaly using subprocess (mimics CLI command)"""
    logger = get_run_logger()
    logger.info("Execute log anomaly analysis via subprocess")
    
    # Change to project root directory
    original_cwd = os.getcwd()
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    try:
        # Set up paths
        input_folder = "log_Injest/test_data"
        output_folder = "results"
        config_file = "loganomly.yaml"
        
        # Check if input folder exists
        if not os.path.exists(input_folder):
            logger.error(f"Input folder not found: {input_folder}")
            return
            
        # Ensure output folder exists
        os.makedirs(output_folder, exist_ok=True)
        
        # Build the command (mimics: python -m loganomaly --input testdata/cloudwatch --output results --config loganomly.yaml)
        cmd = [
            "python", "-m", "loganomaly",
            "--input", input_folder,
            "--output", output_folder,
            "--config", config_file
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        logger.info("Command output:")
        logger.info(result.stdout)
        if result.stderr:
            logger.warning("Command stderr:")
            logger.warning(result.stderr)
            
        logger.info("Log anomaly analysis completed successfully")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return code {e.returncode}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error in execute_log_anomaly_subprocess: {e}")
        raise
    finally:
        # Restore original working directory
        os.chdir(original_cwd)


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
def upload_report(results_dir: str = "results") -> None:
    logger = get_run_logger()
    logger.info("Upload report via file-service")

    # Pull creds/ids from env (set these in your runtime environment)
    api_url = os.getenv("SKYU_FILE_SERVICE_URL", "https://api.dev.skyu.io/file-service")
    headers = {
        "x-project-id": os.getenv("SKYU_PROJECT_ID", ""),           # e.g. project_efa7e65a-...
        "x-organization-id": os.getenv("SKYU_ORG_ID", ""),          # e.g. org_6de1b366-...
        "x-resource-id": os.getenv("SKYU_RESOURCE_ID", ""),         # e.g. app_23ee08b1-...
        "x-environment-id": os.getenv("SKYU_ENV_ID", ""),           # e.g. env_11f1dff0-...
        "Authorization": f"Bearer {os.getenv('SKYU_API_TOKEN', '')}",
    }

    # Optional: namespace uploads by run id / date
    run_ulid = generate_ulid()
    cloud_storage_path = os.getenv("SKYU_CLOUD_PATH", f"/loganomaly/{run_ulid}")

    try:
        resp = upload_folder_as_zip(
            results_dir,
            api_url=api_url,
            headers=headers,
            provider=os.getenv("SKYU_PROVIDER", "aws"),
            resource_type=os.getenv("SKYU_RESOURCE_TYPE", "infrastructure-cf-template"),
            cloud_storage_path=cloud_storage_path,
            # exclude noisy stuff if needed
            ignore_globs=["*.tmp", "__pycache__/", ".venv/", "node_modules/"],
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
def report_post_process(dry_run: bool) -> None:
    logger = get_run_logger()
    logger.info("Post-processing report (analyze → upload)")
    analyze_report(dry_run)
    upload_report()
    logger.info("Post-processing complete")


@flow(name="log-anomaly-workerpipeline")
def pipeline(
    run_id: str = datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
    skip_install: bool = True,
    dry_run: bool = False,
) -> None:
    logger = get_run_logger()
    logger.info(f"Starting pipeline run_id={run_id} dry_run={dry_run}")

    # Use the current log groups config
    logger.info(f"Using log groups config: {get_log_groups_config()}")

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


def run_pipeline_with_config(
    log_groups_config: List[Dict[str, str]],
    run_id: str = None,
    skip_install: bool = True,
    dry_run: bool = False,
) -> None:
    """Run pipeline with custom log groups configuration"""
    if run_id is None:
        run_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    
    # Set the custom config
    set_log_groups_config(log_groups_config)
    
    # Run the pipeline
    pipeline(run_id=run_id, skip_install=skip_install, dry_run=dry_run)

if __name__ == "__main__":
    # Run locally: python worker.py
    # You can modify the LOG_GROUPS_CONFIG here before running
    # Example:
    # LOG_GROUPS_CONFIG = [
    #     {"name": "my-service", "logGroup": "/aws/lambda/my-service", "uniqueLabel": ""},
    #     {"name": "my-cluster", "logGroup": "/aws/eks/my-cluster/cluster", "uniqueLabel": "namespace"},
    # ]
    
    pipeline()
