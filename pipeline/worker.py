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
from mistral_vm.instance_availability_checker import check_instance_or_exit
from post_process.file_service_uploader import (
    build_headers,
    generate_ulid,
    upload_folder_as_zip,
)
from prefect import flow, get_run_logger, task
from prefect.settings import temporary_settings, PREFECT_LOGGING_LEVEL
from yaml_extractor.yaml_config_fetcher import fetch_yaml_config
from post_process.send_notification import analyze_reports_and_notify



# (Optional) If you want to pass API URL / provider explicitly from constants:
# from config.constants import API_URL as DEFAULT_API_URL, PROVIDER as DEFAULT_PROVIDER

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

@task
def prepare_and_download_logs_subprocess(start_time: str, end_time: str, region: str = "us-east-1") -> None:
    """Alternative approach: Use subprocess to call prepare_jobs.py"""
    logger = get_run_logger()
    logger.info(f"Preparing jobs and downloading logs from {start_time} to {end_time} (subprocess method)")
    
    original_cwd = os.getcwd()
    log_injest_dir = Path(__file__).parent.parent / "log_Injest"
    os.chdir(log_injest_dir)
    
    try:
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
        os.chdir(original_cwd)

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
def prepare_prerequisite() -> None:
    logger = get_run_logger()
    logger.info("Preparing prerequisites: logs + config")
    public_ip =config_mistral_server();
    success = prepare_and_download_logs_safe(
        start_time="2025-10-06T00:00:00Z",
        end_time="2025-10-07T23:59:59Z",
        region="us-east-1"
    )
    
    if success:
        logger.info("Log download completed successfully")
    else:
        logger.warning("Log download failed, but continuing pipeline")
    download_config_yaml(public_ip)
    logger.info("Prerequisites complete")

@task
def execute_log_anomaly(
    input_folder: str = "testdata/big",     # == --input
    output_folder: str = "results",         # == --output
    config_file: str = "config.yaml",       # == --config
    show_results: bool = True               # == --show-results
) -> None:
    """
    Run loganomaly in-process by setting loganomaly.config for this task,
    then calling processor.process_all_files().
    """
    logger = get_run_logger()
    logger.info("Execute log anomaly analysis (in-process)")

    # Ensure we run from repo root (so relative paths in your code/config work)
    original_cwd = os.getcwd()
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    try:
        # Sanity checks
        if not Path(input_folder).exists():
            logger.error(f"Input folder not found: {input_folder}")
            return
        Path(output_folder).mkdir(parents=True, exist_ok=True)

        # Import here so the CWD change applies to any relative imports
        from loganomaly import config as app_config
        from loganomaly.processor import process_all_files

        # Snapshot current config to restore later
        orig = {
            "INPUT_FOLDER":     getattr(app_config, "INPUT_FOLDER", None),
            "RESULTS_FOLDER":   getattr(app_config, "RESULTS_FOLDER", None),
            "CONFIG_FILE":      getattr(app_config, "CONFIG_FILE", None),
            "SHOW_RESULTS":     getattr(app_config, "SHOW_RESULTS", None),
        }

        # Set per-run config
        app_config.INPUT_FOLDER   = input_folder
        app_config.RESULTS_FOLDER = output_folder

        # Only set these if your codebase uses them elsewhere (e.g., loaders or renderers).
        # processor.py you shared doesn’t read them directly, but other modules might.
        app_config.CONFIG_FILE    = config_file
        app_config.SHOW_RESULTS   = show_results

        logger.info(f"Input:  {app_config.INPUT_FOLDER}")
        logger.info(f"Output: {app_config.RESULTS_FOLDER}")
        logger.info(f"Config: {app_config.CONFIG_FILE}")
        logger.info(f"Show results: {app_config.SHOW_RESULTS}")

        # Run the pipeline
        process_all_files()

        logger.info("Log anomaly analysis completed successfully")

    except Exception as e:
        logger.error(f"Error in execute_log_anomaly: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    finally:
        # Restore config so other tasks/flows aren’t affected
        try:
            app_config.INPUT_FOLDER   = orig["INPUT_FOLDER"]
            app_config.RESULTS_FOLDER = orig["RESULTS_FOLDER"]
            app_config.CONFIG_FILE    = orig["CONFIG_FILE"]
            app_config.SHOW_RESULTS   = orig["SHOW_RESULTS"]
        except Exception:
            pass
        os.chdir(original_cwd)
# def execute_log_anomaly() -> None:
#     """Execute log anomaly analysis using the loganomaly module"""
#     logger = get_run_logger()
#     logger.info("Execute log anomaly analysis")
    
#     original_cwd = os.getcwd()
#     project_root = Path(__file__).parent.parent
#     os.chdir(project_root)
    
#     try:
#         input_folder = "log_Injest/test_data"  # Our downloaded logs
#         output_folder = "results"
#         config_file = "loganomly.yaml"
        
#         logger.info(f"Input folder: {input_folder}")
#         logger.info(f"Output folder: {output_folder}")
#         logger.info(f"Config file: {config_file}")
        
#         if not os.path.exists(input_folder):
#             logger.error(f"Input folder not found: {input_folder}")
#             return
            
#         supported_extensions = (".json", ".log", ".txt")
#         log_files = [f for f in os.listdir(input_folder) if f.endswith(supported_extensions)]
        
#         if not log_files:
#             logger.warning(f"No supported log files found in {input_folder}")
#             return
            
#         logger.info(f"Found {len(log_files)} log files to process: {log_files}")
        
#         from loganomaly import config as app_config
#         original_input_folder = app_config.INPUT_FOLDER
#         original_results_folder = app_config.RESULTS_FOLDER
        
#         try:
#             app_config.INPUT_FOLDER = input_folder
#             app_config.RESULTS_FOLDER = output_folder
#             os.makedirs(output_folder, exist_ok=True)
#             from loganomaly.processor import process_all_files
#             logger.info("Starting log anomaly analysis...")
#             process_all_files()
#             logger.info("Log anomaly analysis completed successfully")
#         finally:
#             app_config.INPUT_FOLDER = original_input_folder
#             app_config.RESULTS_FOLDER = original_results_folder
            
#     except Exception as e:
#         logger.error(f"Error in execute_log_anomaly: {e}")
#         import traceback
#         logger.error(f"Traceback: {traceback.format_exc()}")
#         raise
#     finally:
#         os.chdir(original_cwd)

# @task
# def execute_log_anomaly_subprocess() -> None:
#     """Alternative approach: Execute log anomaly using subprocess (mimics CLI command)"""
#     logger = get_run_logger()
#     logger.info("Execute log anomaly analysis via subprocess")
    
#     original_cwd = os.getcwd()
#     project_root = Path(__file__).parent.parent
#     os.chdir(project_root)
    
#     try:
#         input_folder = "log_Injest/test_data"
#         output_folder = "results"
#         config_file = "loganomly.yaml"
        
#         if not os.path.exists(input_folder):
#             logger.error(f"Input folder not found: {input_folder}")
#             return
            
#         os.makedirs(output_folder, exist_ok=True)
        
#         cmd = [
#             "python", "-m", "loganomaly",
#             "--input", input_folder,
#             "--output", output_folder,
#             "--config", config_file
#         ]
        
#         logger.info(f"Running command: {' '.join(cmd)}")
#         result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
#         logger.info("Command output:")
#         logger.info(result.stdout)
#         if result.stderr:
#             logger.warning("Command stderr:")
#             logger.warning(result.stderr)
            
#         logger.info("Log anomaly analysis completed successfully")
        
#     except subprocess.CalledProcessError as e:
#         logger.error(f"Command failed with return code {e.returncode}")
#         logger.error(f"stdout: {e.stdout}")
#         logger.error(f"stderr: {e.stderr}")
#         raise
#     except Exception as e:
#         logger.error(f"Error in execute_log_anomaly_subprocess: {e}")
#         raise
#     finally:
#         os.chdir(original_cwd)

@task
def send_notification_emails() -> None:
    logger = get_run_logger()
    logger.info("Send notification emails");
    analyze_reports_and_notify(
        results_dir="results",
        org_id= "org_6de1b366-9da6-4d55-b363-f5a2c4382016",
        project_id= "project_c68bc2f1-5cb8-402c-b52f-721d2b091574",
        to_email= "salinda.f@insighture.com",
        # Optionally override threshold, recipient or template data:
        # error_threshold=5,
        # to_email="alerts@yourorg.com",
        # template_data={"email": "...", "fullName": "...", ...},
       
    )

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

    # ── Hardcode ONLY these in worker.py (per your request) ──
    SKYU_PROJECT_ID    = "project_c68bc2f1-5cb8-402c-b52f-721d2b091574"                 # <-- hardcode here
    SKYU_ORG_ID        = "org_6de1b366-9da6-4d55-b363-f5a2c4382016"                    # <-- hardcode here
    SKYU_DEV_API_TOKEN     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXJ2aWNlQWNjb3VudCI6dHJ1ZSwiYXV0aERhdGEiOnsib3JnXzZkZTFiMzY2LTlkYTYtNGQ1NS1iMzYzLWY1YTJjNDM4MjAxNiI6eyJwcm9qZWN0cyI6eyJwcm9qZWN0X2M2OGJjMmYxLTVjYjgtNDAyYy1iNTJmLTcyMWQyYjA5MTU3NCI6eyJyb2xlcyI6WyJvd25lciJdLCJlbnZpcm9ubWVudHMiOnt9fX19fSwic2VydmljZUFjY291bnRJZCI6IjJjMzUyODE0LTUwY2EtNDJkZC05ZmE4LTFiMDM1NDc1OTNmZSIsInVzZXJJZCI6IjQ0YjhkNDk4LTYwYzEtNzBlNy03OWZlLTg5MThmNDdiNDJjMSIsImlhdCI6MTc2MTAxNzQ3NH0.dmx3WF8PekDWigeYQJsGnDJ81MiKroONmkGlO9igpEQ"     # <-- hardcode here
    SKYU_RESOURCE_TYPE = "infrastructure-cf-template"    # <-- hardcode here
    SKYU_CLOUD_PATH    = "/dev-LAD-report/"      # <-- hardcode here (or f"/loganomaly/{generate_ulid()}")
    SKYU_ENV_ID = "env_ad855eb0-f137-4258-9236-79be5f6772ea"

    # Build headers using worker-provided fields; resource/env IDs come from constants in file_service_uploader
    headers = build_headers(
        project_id=SKYU_PROJECT_ID,
        org_id=SKYU_ORG_ID,
        api_token=SKYU_DEV_API_TOKEN,
        env_id=SKYU_ENV_ID,
        # resource_id / environment_id defaulted inside build_headers via config/constants.py
    )

    # If you want a ULID file name inside the uploader, it's already defaulted there.

    try:
        # resp = upload_folder_as_zip(
        #     results_dir,
        #     # api_url, provider default from config/constants.py; pass explicitly if you prefer:
        #     # api_url=DEFAULT_API_URL,
        #     # provider=DEFAULT_PROVIDER,
        #     headers=headers,
        #     resource_type=SKYU_RESOURCE_TYPE,
        #     cloud_storage_path=SKYU_CLOUD_PATH,
        #     ignore_globs=["*.tmp", "__pycache__/", ".venv/", "node_modules/"],
        # )
        resp = upload_folder_as_zip(
                r"C:\Users\salinda.fernando\Downloads\file_service_uploader.zip",
                api_url="https://api.dev.skyu.io/file-service",
                headers=headers,
                provider="aws",
                zip_name="LAD_report.zip",
                resource_type="anomaly-log-template",
                cloud_storage_path="/LAD_reports/dev_test/1_",
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

        # 2) Run anomaly detection
        execute_log_anomaly(
                input_folder="testdata/cloudwatch",          # or "log_Injest/test_data"
                output_folder="results",
                config_file="loganomly.yaml",            # (fix the earlier "loganomly.yaml" typo)
                show_results=True
            )


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
    
    set_log_groups_config(log_groups_config)
    pipeline(run_id=run_id, skip_install=skip_install, dry_run=dry_run)

if __name__ == "__main__":
    # Run locally: python worker.py
    # You can modify the LOG_GROUPS_CONFIG here before running
    # Example:
    # LOG_GROUPS_CONFIG = [
    #     {"name": "my-service", "logGroup": "/aws/lambda/my-service", "uniqueLabel": ""},
    #     {"name": "my-cluster", "logGroup": "/aws/eks/my-cluster/cluster", "uniqueLabel": "namespace"},
    # ]
    pipeline(skip_install=False)
