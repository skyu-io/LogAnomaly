"""LogAnomaly - Advanced Log Analysis with AI."""

from loganomaly.logging_config import setup_logging

# Set up logging configuration
setup_logging()

# Version of the loganomaly package
__version__ = "0.1.0"

# Import main components
from loganomaly.detectors import LOFDetector, RollingWindowDetector
from loganomaly.llm_classifier import classify_log_llm, LLM_STATS
from loganomaly.workflow import Pipeline, WorkflowContext, classify_log_with_pipeline

__all__ = [
    'LOFDetector',
    'RollingWindowDetector',
    'classify_log_llm',
    'LLM_STATS',
    'Pipeline',
    'WorkflowContext',
    'classify_log_with_pipeline'
]