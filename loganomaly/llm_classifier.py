import aiohttp
import asyncio
import time
import tiktoken
import random
import logging
import os
from tqdm import tqdm
from typing import Dict, Any, List

from loganomaly.utils import contains_secret_patterns, short_reason, clean_log_line, extract_tags
from loganomaly.prompt import build_llm_prompt, summarize_context_logs, clean_tags, VALID_TAGS
from loganomaly.llm_provider import get_llm_provider
from loganomaly.workflow import LogAnalysisWorkflow
from loganomaly import config as app_config

LLM_STATS = {
    "total_calls": 0,
    "total_time": 0.0,
    "errors": 0,
    "total_tokens": 0,
    "context_trimmed": 0
}

tokenizer = tiktoken.get_encoding("cl100k_base")
MAX_RETRIES = 3
MAX_TOTAL_TOKENS = 2048

logging.basicConfig(filename='error.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

os.environ["TOKENIZERS_PARALLELISM"] = "false"


def apply_dependent_anomaly_filter(row):
    if not app_config.ENABLE_DEPENDENT_ANOMALY_FILTER:
        return row

    log_line = row.get("log", "")
    classification = row.get("classification", "")

    if classification == "Unknown" and log_line.strip().startswith("at "):
        row["classification"] = "Dependent Anomaly"
        row["reason"] = "Stack trace line, follows an actual error."
        row["is_anomaly"] = 0

    return row


class LLMClassifier:
    """LLM-based log anomaly classifier."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the classifier."""
        self.config = config
        self.context_window = 5  # Number of logs before/after to include as context
        
    async def classify(self, logs: List[str]) -> List[Dict[str, Any]]:
        """Classify logs as normal or anomalous."""
        results = []
        
        for i, log in enumerate(logs):
            # Skip empty logs
            if not log or not log.strip():
                continue
                
            # Get context logs
            start_idx = max(0, i - self.context_window)
            end_idx = min(len(logs), i + self.context_window + 1)
            context = logs[start_idx:i] + logs[i+1:end_idx]
            
            # Process results
            result = {
                'log': log,
                'classification': None,
                'reason': None,
                'tags': []
            }
            
            try:
                from loganomaly.workflow import LogAnalysisWorkflow
                pipeline = LogAnalysisWorkflow(self.config)
                workflow_result = await pipeline.execute(log)
                
                if workflow_result and workflow_result.get('llm_response'):
                    response = workflow_result['llm_response'].strip()
                    label, reason, tags = extract_tags(response)
                    
                    result['classification'] = label
                    result['reason'] = reason
                    result['tags'] = clean_tags(tags)
                    
                    # Update stats
                    LLM_STATS["total_calls"] += 1
                    
                else:
                    # Handle empty or invalid response
                    result['classification'] = 'unknown'
                    result['reason'] = 'Empty or invalid LLM response'
                    
            except Exception as e:
                logger.error(f"Error in LLM classification: {str(e)}")
                LLM_STATS["errors"] += 1
                result['classification'] = 'unknown'
                
            results.append(result)
            
        return results


async def classify_log_llm(session, log_line, context_logs):
    """Classify a log line using LLM."""
    global LLM_STATS
    start_time = time.time()

    try:
        if len(log_line) > app_config.MAX_LOG_LENGTH:
            log_line = log_line[:app_config.MAX_LOG_LENGTH] + "..."

        if contains_secret_patterns(log_line):
            LLM_STATS["total_calls"] += 1
            LLM_STATS["total_time"] += time.time() - start_time
            return "Sensitive Information Leak", "Contains possible secret/token.", ["Sensitive", "Security Threat"]

        # Use workflow pipeline for classification
        from loganomaly.workflow import LogAnalysisWorkflow
        pipeline = LogAnalysisWorkflow({}, session=session)
        results = await pipeline.execute(log_line)
        
        if results.get("errors"):
            error_msg = "; ".join(results["errors"].values()) if isinstance(results["errors"], dict) else str(results["errors"])
            logger.error(f"LLM Error: {error_msg}")
            return "Error", f"LLM Error: {error_msg}", ["Unknown"]
            
        reply = results.get("llm_response", "")
        if not reply:
            logger.error(f"Empty reply from LLM for log: {log_line}")
            return "Unknown", "Empty reply from LLM", ["Unknown"]
            
        label, reason, tags = extract_tags(reply)
        
        # Update stats
        LLM_STATS["total_calls"] += 1
        LLM_STATS["total_time"] += time.time() - start_time
        
        return label, reason, clean_tags(tags)
        
    except Exception as e:
        logger.error(f"Error classifying log: {str(e)}")
        LLM_STATS["errors"] += 1
        return "Error", f"Classification error: {str(e)}", ["Unknown"]


async def classify_anomalies(anomalies_df):
    global LLM_STATS

    classifications = []
    reasons = []
    cleaned_logs = []
    tags_list = []

    semaphore = asyncio.Semaphore(app_config.CONCURRENCY)

    connector = aiohttp.TCPConnector(limit=app_config.CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        
        async def bounded_classify(log_line, context_logs, pbar):
            async with semaphore:
                result = await classify_log_llm(session, log_line, context_logs)
                pbar.update(1)
                return result

        tasks = []
        with tqdm(total=len(anomalies_df), desc="LLM Classification") as pbar:
            for _, row in anomalies_df.iterrows():
                log_line = row["log"]
                context_logs = row.get("context_logs", [])
                tasks.append(bounded_classify(log_line, context_logs, pbar))

            results = await asyncio.gather(*tasks)

        for idx, (label, reason, tags) in enumerate(results):
            classifications.append(label)
            reasons.append(reason)
            tags_list.append(tags)
            cleaned_logs.append(clean_log_line(anomalies_df.iloc[idx]["log"]))

    return classifications, reasons, cleaned_logs, tags_list, LLM_STATS
