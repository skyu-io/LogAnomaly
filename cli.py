import click
import yaml
import os
import subprocess
from loganomaly import processor
from loganomaly import config as app_config


@click.command()
@click.option('--input', '-i', type=click.Path(exists=True), required=True, help='Input folder containing log files.')
@click.option('--output', '-o', type=click.Path(), default='./results', help='Folder to save results.')
@click.option('--config', '-c', type=click.Path(exists=True), help='Optional YAML configuration file.')
@click.option('--max-logs', type=int, help='Maximum number of log lines to process.')
@click.option('--disable-llm', is_flag=True, help='Disable LLM classification step.')
@click.option('--summary-only', is_flag=True, help='Only print summary without saving anomaly details.')
@click.option('--llm', type=str, default=None, help='LLM model name (e.g. mistral, phi2).')
@click.option('--compliance-mode', is_flag=True, help='Enable compliance mode (limit logs).')
@click.option('--verbose', is_flag=True, help='Enable verbose output.')
@click.option('--show-results', is_flag=True, help='Launch Streamlit dashboard after analysis.')
@click.option('--enable-lof', is_flag=True, default=None, help='Enable Local Outlier Factor Detection.')
@click.option('--lof-n-neighbors', type=int, default=None, help='Number of neighbors for LOF.')
@click.option('--lof-contamination', type=float, default=None, help='Contamination ratio for LOF.')
@click.option('--enable-rolling-window', is_flag=True, default=None, help='Enable Rolling Window Flood Detection.')
@click.option('--rolling-window-size', type=int, default=None, help='Rolling window size.')
@click.option('--rolling-window-threshold', type=float, default=None, help='Flood detection threshold in window.')
def cli(
    input, output, config, max_logs, disable_llm, summary_only, llm, compliance_mode, verbose, show_results,
    enable_lof, lof_n_neighbors, lof_contamination, enable_rolling_window, rolling_window_size, rolling_window_threshold
):
    """
    🚀 LogAnomaly - Semantic, Statistical & Rule-Based Log Anomaly Detector
    """

    # === Load YAML config ===
    yaml_config = {}
    if config:
        with open(config, "r") as f:
            yaml_config = yaml.safe_load(f)
        app_config.YAML_CONFIG = yaml_config  # Store in config
        click.echo(f"📄 Loaded config: {config}")

    # === Merge CLI + YAML + Defaults ===
    app_config.INPUT_FOLDER = input
    app_config.RESULTS_FOLDER = output
    app_config.MAX_LOG_LINES = max_logs or yaml_config.get('max_log_lines', app_config.MAX_LOG_LINES)
    app_config.ENABLE_LLM = not disable_llm if disable_llm else yaml_config.get('enable_llm', app_config.ENABLE_LLM)
    app_config.LLM_MODEL = llm or yaml_config.get('llm_model', app_config.LLM_MODEL)
    app_config.COMPLIANCE_MODE = compliance_mode or yaml_config.get('compliance_mode', app_config.COMPLIANCE_MODE)
    app_config.SUMMARY_ONLY = summary_only
    app_config.VERBOSE = verbose

    # Optional YAML Config
    app_config.ANOMALY_THRESHOLD = yaml_config.get('anomaly_threshold', app_config.ANOMALY_THRESHOLD)
    app_config.TOP_PERCENT = yaml_config.get('top_percent', app_config.TOP_PERCENT)
    app_config.TOP_N_LLM = yaml_config.get('top_n_llm', app_config.TOP_N_LLM)
    app_config.ENABLE_SPAM_DETECTION = yaml_config.get('enable_spam_detection', app_config.ENABLE_SPAM_DETECTION)
    app_config.SPAM_TEMPLATE_THRESHOLD = yaml_config.get('spam_template_threshold', app_config.SPAM_TEMPLATE_THRESHOLD)
    app_config.LARGE_LOG_WARNING_THRESHOLD = yaml_config.get('large_log_warning_threshold', app_config.LARGE_LOG_WARNING_THRESHOLD)
    app_config.ENABLE_DEPENDENT_ANOMALY_FILTER = yaml_config.get('enable_dependent_anomaly_filter', app_config.ENABLE_DEPENDENT_ANOMALY_FILTER)

    # LLM config
    llm_cfg = yaml_config.get('llm', {})
    app_config.LLM_PROVIDER = llm_cfg.get('provider', app_config.LLM_PROVIDER)
    app_config.LLM_ENDPOINT = llm_cfg.get('endpoint', app_config.LLM_ENDPOINT)
    app_config.LLM_MODEL = llm_cfg.get('model', app_config.LLM_MODEL)
    app_config.TIMEOUT = llm_cfg.get('timeout', app_config.TIMEOUT)
    app_config.MAX_RETRIES = llm_cfg.get('max_retries', getattr(app_config, 'MAX_RETRIES', 3))

    app_config.ADDITIONAL_SECURITY_PATTERNS = yaml_config.get("additional_security_patterns", [])
    app_config.ADDITIONAL_RULE_BASED_PATTERNS = yaml_config.get("additional_rule_based_patterns", [])

    # Detectors config
    detectors_cfg = yaml_config.get('detectors', {})
    
    # LOF config
    lof_cfg = detectors_cfg.get('lof', {})
    app_config.ENABLE_LOF = enable_lof if enable_lof is not None else lof_cfg.get('enabled', yaml_config.get("enable_lof", app_config.ENABLE_LOF))
    app_config.LOF_N_NEIGHBORS = lof_n_neighbors or lof_cfg.get('neighbors', yaml_config.get("lof_n_neighbors", app_config.LOF_N_NEIGHBORS))
    app_config.LOF_CONTAMINATION = lof_contamination or lof_cfg.get('contamination', yaml_config.get("lof_contamination", app_config.LOF_CONTAMINATION))

    # Rolling Window config
    rolling_window_cfg = detectors_cfg.get('rolling_window', {})
    app_config.ENABLE_ROLLING_WINDOW = enable_rolling_window if enable_rolling_window is not None else rolling_window_cfg.get('enabled', yaml_config.get("enable_rolling_window", app_config.ENABLE_ROLLING_WINDOW))
    app_config.ROLLING_WINDOW_SIZE = rolling_window_size or rolling_window_cfg.get('window_size', yaml_config.get("rolling_window_size", app_config.ROLLING_WINDOW_SIZE))
    app_config.ROLLING_WINDOW_THRESHOLD = rolling_window_threshold or rolling_window_cfg.get('repetition_threshold', yaml_config.get("rolling_window_threshold", app_config.ROLLING_WINDOW_THRESHOLD))

    # === Run ===
    click.echo(f"🔍 Starting analysis on → {input}")
    processor.process_all_files()
    click.echo(f"✅ Completed. Results saved in → {output}")

    # === Dashboard ===
    if show_results:
        click.echo(f"📊 Opening Dashboard...")
        subprocess.run(["streamlit", "run", "loganomaly/dashboard.py"])


if __name__ == "__main__":
    cli()
