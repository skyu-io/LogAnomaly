import os
import configparser
import shutil
import logging
from pathlib import Path
from tqdm import tqdm
from drain3 import TemplateMiner
from drain3.file_persistence import FilePersistence
from loganomaly import config as app_config

BASE_DIR = Path(__file__).parent


def setup_drain_config():
    drain_dir = Path(app_config.DRAIN3_LOG_DIR).parent
    drain_state_file = Path(app_config.DRAIN3_STATE_PATH)
    drain_logs_dir = Path(app_config.DRAIN3_LOG_DIR)
    drain_config_file = Path(app_config.DRAIN3_CONFIG_PATH)

    # Create drain3 folder if missing
    drain_dir.mkdir(parents=True, exist_ok=True)

    # Remove old state
    if drain_state_file.exists():
        drain_state_file.unlink()
    if drain_logs_dir.exists():
        shutil.rmtree(drain_logs_dir)

    # Create config
    config = configparser.ConfigParser()
    config["DEFAULT"] = {
        "snapshot_interval_minutes": "10",
        "snapshot_compress_state": "false",
        "snapshot_compress_state_min_size_kb": "500",
        "log_template_dir": str(drain_logs_dir),
    }

    with open(drain_config_file, "w") as configfile:
        config.write(configfile)

    drain_logs_dir.mkdir(parents=True, exist_ok=True)


def init_drain(use_persistence=False):
    # Set drain3 logger to ERROR level to reduce output
    logging.getLogger("drain3").setLevel(logging.ERROR)
    
    setup_drain_config()
    
    # Skip file persistence during mining for better performance
    persistence = FilePersistence(str(app_config.DRAIN3_STATE_PATH)) if use_persistence else None
    miner = TemplateMiner(persistence)

    if app_config.USE_DRAIN3_LIGHT:
        print("⚡️ Using Drain3 Light Mode (Fast, less precise)")
        miner.drain.depth = 3
        miner.drain.similarity_threshold = 0.5
    else:
        # Optimize default settings for speed
        miner.drain.depth = 4
        miner.drain.similarity_threshold = 0.4

    return miner


def mine_templates(df):
    """
    Add 'log_template' column to DataFrame.
    """
    # No persistence during mining = faster (no disk I/O)
    miner = init_drain(use_persistence=False)
    
    logs = df["log"].tolist()
    n_logs = len(logs)
    
    print(f"🔍 Mining log templates for {n_logs} logs...")
    
    # Process in batches for better progress display
    templates = []
    for log in tqdm(logs, desc="Template Mining", mininterval=0.5):
        result = miner.add_log_message(log)
        templates.append(result["template_mined"] if result else "Unknown")

    df["log_template"] = templates
    return df
