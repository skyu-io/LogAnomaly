import click
import yaml
import os
import subprocess
from loganomaly import processor
from loganomaly import config as app_config


@click.command()
@click.option('--input', '-i', type=click.Path(exists=True), required=True, help='Input folder containing JSON log files.')
@click.option('--output', '-o', type=click.Path(), default='./results', help='Folder to save results.')
@click.option('--config', '-c', type=click.Path(exists=True), help='Optional YAML configuration file.')
@click.option('--max-logs', type=int, help='Maximum number of log lines to process.')
@click.option('--disable-llm', is_flag=True, help='Disable LLM classification step.')
@click.option('--summary-only', is_flag=True, help='Only print summary without saving anomaly details.')
@click.option('--llm', type=str, default=None, help='LLM model name (e.g. mistral, phi2).')
@click.option('--compliance-mode', is_flag=True, help='Enable compliance mode (limit logs).')
@click.option('--verbose', is_flag=True, help='Enable verbose output.')
@click.option('--show-results', is_flag=True, help='Launch Streamlit dashboard after analysis.')
def cli(input, output, config, max_logs, disable_llm, summary_only, llm, compliance_mode, verbose, show_results):
    """
    🚀 LogAnomaly - Semantic & Statistical Log Anomaly Detector
    """

    # === Load YAML config ===
    yaml_config = {}
    if config:
        with open(config, "r") as f:
            yaml_config = yaml.safe_load(f)
        click.echo(f"📄 Loaded config: {config}")

    # === Merge CLI + YAML ===
    app_config.INPUT_FOLDER = input
    app_config.RESULTS_FOLDER = output
    app_config.MAX_LOG_LINES = max_logs or yaml_config.get('max_logs', None)
    app_config.ENABLE_LLM = not disable_llm if disable_llm is not None else yaml_config.get('enable_llm', True)
    app_config.LLM_MODEL = llm or yaml_config.get('llm_model', app_config.LLM_MODEL)
    app_config.COMPLIANCE_MODE = compliance_mode or yaml_config.get('compliance_mode', False)
    app_config.SUMMARY_ONLY = summary_only
    app_config.VERBOSE = verbose

    # Optional LLM Configs from YAML
    if "anomaly_threshold" in yaml_config:
        app_config.ANOMALY_THRESHOLD = yaml_config["anomaly_threshold"]
    if "top_percent" in yaml_config:
        app_config.TOP_PERCENT = yaml_config["top_percent"]
    if "top_n_llm" in yaml_config:
        app_config.TOP_N_LLM = yaml_config["top_n_llm"]
    if "enable_spam_detection" in yaml_config:
        app_config.ENABLE_SPAM_DETECTION = yaml_config["enable_spam_detection"]
    if "spam_template_threshold" in yaml_config:
        app_config.SPAM_TEMPLATE_THRESHOLD = yaml_config["spam_template_threshold"]
    if "large_log_warning_threshold" in yaml_config:
        app_config.LARGE_LOG_WARNING_THRESHOLD = yaml_config["large_log_warning_threshold"]
    if "enable_dependent_anomaly_filter" in yaml_config:
        app_config.ENABLE_DEPENDENT_ANOMALY_FILTER = yaml_config["enable_dependent_anomaly_filter"]
    if "llm_config" in yaml_config:
        app_config.LLM_ENDPOINT = yaml_config["llm_config"].get("endpoint", app_config.LLM_ENDPOINT)
        app_config.LLM_MODEL = yaml_config["llm_config"].get("model", app_config.LLM_MODEL)
    if "additional_security_patterns" in yaml_config:
        app_config.ADDITIONAL_SECURITY_PATTERNS = yaml_config["additional_security_patterns"]

    if "additional_rule_based_patterns" in yaml_config:
        app_config.ADDITIONAL_RULE_BASED_PATTERNS = yaml_config["additional_rule_based_patterns"]
    
    
    click.echo(f"🔍 Starting analysis on → {input}")
    processor.process_all_files()
    click.echo(f"✅ Completed. Results saved in → {output}")

    # === Launch Dashboard if requested ===
    if show_results:
        click.echo(f"📊 Opening Dashboard...")
        subprocess.run(["streamlit", "run", "loganomaly/dashboard.py"])


if __name__ == "__main__":
    cli()
