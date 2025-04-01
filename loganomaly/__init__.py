"""LogAnomaly - Advanced Log Analysis with AI."""

from loganomaly.logging_config import setup_logging

# Set up logging configuration
setup_logging()

# Version of the loganomaly package
__version__ = "0.1.0"

# Import main components
from loganomaly.detectors import compute_lof_scores, mark_lof_anomalies
from loganomaly.llm_classifier import classify_log_llm, LLM_STATS
from loganomaly.workflow import WorkflowContext, LogAnalysisWorkflow, classify_log_with_pipeline

__all__ = [
    'compute_lof_scores',
    'mark_lof_anomalies',
    'classify_log_llm',
    'LLM_STATS',
    'LogAnalysisWorkflow',
    'WorkflowContext',
    'classify_log_with_pipeline'
]