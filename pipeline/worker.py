from ast import Return
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional, Literal,Iterable

# Add the parent directory to Python path to find log_Injest module
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
# Paths based on this file's location
HERE = Path(__file__).resolve()
PIPELINE_DIR = HERE.parent                   # .../loganomaly/pipeline
PROJECT_ROOT = PIPELINE_DIR.parent  

from loganomaly.processor import process_all_files

from prefect import flow, get_run_logger, task
from prefect.settings import temporary_settings, PREFECT_LOGGING_LEVEL
from yaml_extractor.repo_config_handler import build_configs_from_repo, BuildResult
from constants import LOG_COLLECTION_DIR,LAD_RESULT_OUTPUT_DIR, OUT_DIR_DEFAULT,GITOPS_CONFIG_REPO

root_str = str(PROJECT_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

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

def generate_configs_clone_per_run(
    *,
    appids: Optional[Iterable[str]],
    ip: str,
    workdir: str,
    branch: str | None = "main",
    tmp_dir: str = "tmp_config",
    out_dir: str = "config",
    array_policy: str = "replace",   # or "extend"
) -> List[BuildResult]:

    """
    Clone once (or refresh) into a persistent workspace and build configs for the given app IDs.
    Reuses the clone across calls. On Windows, consider NOT removing the workspace immediately.
    """
    # REPO_URL = "https://github.com/salindaFinsighture/oho-log-anomaly-skyu-gitops-clone"

    # Build from the existing clone
    results = build_configs_from_repo(
        repo_url=GITOPS_CONFIG_REPO,
        appids=list(appids) if appids else None,
        ip=ip,
        branch=branch,
        workdir=workdir,
        tmp_dir=tmp_dir,
        out_dir=out_dir,
        array_policy=array_policy,
        verbose=True,
    )
    # Optional: ws.cleanup(remove=True)
    return results

@flow
def download_prep_config_yaml(public_ip: str) -> None:
    logger = get_run_logger()

    logger.info("Fetch config YAML via SKY cone gitops repo")
  
    REPO_URL = "https://github.com/salindaFinsighture/oho-log-anomaly-skyu-gitops-clone"

    results = generate_configs_clone_per_run(
            appids=["orders-service", "billing", "inventory"],   # pass None/[] to use "default"
            ip=public_ip,                                       # becomes http://10.1.2.3:11434/api/generate
            workdir= str(PIPELINE_DIR),
            branch="main",                                       # optional
            tmp_dir="tmp_config",
            out_dir="config",
        )

    for r in results:
        print(f"[{r.appid}] mode={r.mode}")
        print(f"  -> wrote: {r.out_path}")
        for f in r.suffix_files_used:
            print(f"     used: {f}")


@task
def prepare_prerequisite(public_ip) -> None:
    logger = get_run_logger()
    logger.info("Preparing prerequisites: logs + config")
    
    download_prep_config_yaml(public_ip)
    logger.info("Prerequisites complete")

@task
def execute_log_anomaly(
    input_folder: str = "testdata",     # == --input
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
        public_ip = '3.85.137.215'
        prepare_prerequisite(public_ip)

        # 2) Run anomaly detection
        execute_log_anomaly(
                input_folder=LOG_COLLECTION_DIR,          # or "log_Injest/test_data"
                output_folder=LAD_RESULT_OUTPUT_DIR,
                config_file="config",            # (fix the earlier "loganomly.yaml" typo)
                show_results=True
            )

        logger.info("Pipeline complete.")

if __name__ == "__main__":

    pipeline(skip_install=False)