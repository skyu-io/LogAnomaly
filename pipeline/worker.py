from ast import Return
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Tuple, Literal

# Add the parent directory to Python path to find log_Injest module
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from log_Injest.prepare_jobs import main as prepare_jobs_main
from loganomaly.processor import process_all_files
from prefect import flow, get_run_logger, task
from prefect.settings import temporary_settings, PREFECT_LOGGING_LEVEL
from yaml_extractor.yaml_config_fetcher import fetch_yaml_config
from mistral_vm.instance_availability_checker import check_instance_or_exit

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
def install_packages(requirements_path: str = None,
                     upgrade: bool = False,
                     quiet: bool = False) -> Tuple[int, str]:
    logger = get_run_logger()
    logger.info("Installing packages")
    try:
        # If no path provided, use requirements.txt from the root directory
        if requirements_path is None:
            requirements_path = str(parent_dir / "requirements.txt")
        req = Path(requirements_path)
        if not req.is_file():
            return 1, f"[install_packages] Not found: {req.resolve()}"

        cmd = [sys.executable, "-m", "pip", "install", "-r", str(req)]
        
        if upgrade:
            cmd.append("--upgrade")
        if quiet:
            cmd.append("-q")

        try:
            proc = subprocess.run(cmd, text=True, capture_output=True, check=True)
            logger.debug(f"Running command: {' '.join(cmd)}")
            return 0, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.CalledProcessError as e:
            # pip returned a non-zero exit code; include both stdout/stderr for context
            return e.returncode or 1, (e.stdout or "") + (e.stderr or "")
    except KeyboardInterrupt:
        return 130, "[install_packages] Interrupted by user (KeyboardInterrupt)."
    except Exception as ex:
        # Covers unexpected issues (permissions, environment problems, etc.)
        return 1, f"[install_packages] Unexpected error: {ex}"


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
        args = {
            "start": start_time,
            "end": end_time,
            "region": region,
            "download": True,
            "transform": True,
            "jobs_file": "jobs.json"
        }
        
        logger.info("Calling prepare_jobs.py with parameters: " + str(args))
        logger.debug(f"Current working directory: {os.getcwd()}")
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
        if "Download script failed" in str(e):
            logger.error("Download script failed - possible AWS permissions/network/log group issues")
            logger.error("Continuing pipeline without downloaded logs")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in prepare_and_download_logs_safe: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    finally:
        os.chdir(original_cwd)

# @task
# def prepare_and_download_logs_subprocess(start_time: str, end_time: str, region: str = "us-east-1") -> None:
#     """Alternative approach: Use subprocess to call prepare_jobs.py"""
#     logger = get_run_logger()
#     logger.info(f"Preparing jobs and downloading logs from {start_time} to {end_time} (subprocess method)")
    
#     original_cwd = os.getcwd()
#     log_injest_dir = Path(__file__).parent.parent / "log_Injest"
#     os.chdir(log_injest_dir)
    
#     try:
#         cmd = [
#             "python", "prepare_jobs.py",
#             "--start", start_time,
#             "--end", end_time,
#             "--region", region,
#             "--download",
#             "--transform",
#             "--jobs-file", "jobs.json"
#         ]
        
#         logger.info(f"Running command: {' '.join(cmd)}")
#         result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
#         logger.info("Command output:")
#         logger.info(result.stdout)
#         if result.stderr:
#             logger.warning("Command stderr:")
#             logger.warning(result.stderr)
            
#         logger.info("Successfully prepared jobs and downloaded logs")
        
#     except subprocess.CalledProcessError as e:
#         logger.error(f"Command failed with return code {e.returncode}")
#         logger.error(f"stdout: {e.stdout}")
#         logger.error(f"stderr: {e.stderr}")
#         raise
#     except Exception as e:
#         logger.error(f"Error in prepare_and_download_logs_subprocess: {e}")
#         raise
#     finally:
#         os.chdir(original_cwd)

@flow
def config_mistral_server():
    logger = get_run_logger()
    logger.info("grab the mistral ami and config")
    public_ip = check_instance_or_exit("i-0793b8fd8e26328a2", region="us-east-1")
    if public_ip:
        return public_ip;
    else:
        logger.error("Mistral server is not available")
        raise Exception("Mistral server is not available")
@flow
def execute_cloudwatch_log_ingestion() -> None:
    logger = get_run_logger()
    logger.info("check for status up and running and continue the process")
    logger.info("Execute CloudWatch log download")
    
    prepare_and_download_logs(
        start_time="2025-10-17T02:27:40.015Z",
        end_time="2025-10-17T02:37:40.015Z",
        region="us-east-1"
    )
    
    transform_log__to_validated_schema()
    logger.info("save file in local")

@flow
def download_config_yaml(public_ip: str) -> None:
    logger = get_run_logger()
    logger.info("Fetch config YAML via SKY cone gitops repo")
    res = fetch_yaml_config(
        destination_config_dir="./config",
        app_id="myservice",  # or None to always use common
        # repo_url="https://github.com/skyu-io/oho-log-anomaly-skyu-gitops-446358f6.git",
        repo_url="https://github.com/salindaFinsighture/oho-log-anomaly-skyu-gitops-clone",
        config_root_rel="loganomaly/config",
        reuse_local_repo=None,
        overwrite=True,
        clean_destination_first=True,
    )
    logger.debug(f"copied={len(res.copied_files)} files → {res.destination}")

@task
def transform_log__to_validated_schema() -> None:
    logger = get_run_logger()
    logger.info("Convert logs to validate schema")

@task
def prepare_prerequisite(instance_id,) -> None:
    logger = get_run_logger()
    logger.info("Preparing prerequisites: logs + config")
    public_ip =config_mistral_server();
    success = prepare_and_download_logs_safe(
        start_time="2025-10-06T00:00:00Z",
        end_time="2025-10-07T23:59:59Z",
        region="us-east-1"
    )

    logger.info("Prerequisites complete")

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

        if not skip_install:
            install_packages()
        else:
            logger.info("skip_install=True → skipping install_packages()")

        # 1) Pull logs and configs
        prepare_prerequisite()

        logger.info("Pipeline complete.")

if __name__ == "__main__":
   
    pipeline()