"""Rolling window detector for log flood detection and chunking."""

import pandas as pd
import numpy as np
from collections import defaultdict
import logging
from typing import Tuple, List, Dict
import re

logger = logging.getLogger(__name__)

def compute_template_similarity(template1: str, template2: str) -> float:
    """Compute similarity between two log templates."""
    words1 = set(template1.split())
    words2 = set(template2.split())
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0

def analyze_flood_pattern(logs: List[str], templates: List[str]) -> Dict[str, any]:
    """Analyze pattern in a flood of similar logs."""
    pattern = {
        "template": max(set(templates), key=templates.count),
        "variable_parts": [],
        "severity": "unknown",
        "components": set()
    }
    
    # Extract variable parts by comparing logs
    template_words = pattern["template"].split()
    for log in logs:
        log_words = log.split()
        if len(log_words) == len(template_words):
            for i, (t_word, l_word) in enumerate(zip(template_words, log_words)):
                if t_word != l_word and l_word not in pattern["variable_parts"]:
                    pattern["variable_parts"].append(l_word)
                    
        # Extract severity and components
        if "error" in log.lower():
            pattern["severity"] = "error"
        elif "warn" in log.lower() and pattern["severity"] != "error":
            pattern["severity"] = "warning"
        
        comp_match = re.match(r"^\[?([a-zA-Z0-9_.-]+)\]?[:|\s]", log)
        if comp_match:
            pattern["components"].add(comp_match.group(1))
    
    pattern["components"] = list(pattern["components"])
    return pattern

def rolling_window_chunking(df: pd.DataFrame, window_size: int = 1000, 
                          repetition_threshold: float = 0.75) -> pd.DataFrame:
    """
    Detect and chunk repeated log patterns within a rolling window.
    
    Args:
        df: DataFrame with logs
        window_size: Size of rolling window
        repetition_threshold: Threshold for considering logs as repeated (0-1)
        
    Returns:
        DataFrame with chunked logs and flood information
    """
    logger.info(f"🌀 Rolling Window Chunking → Window Size: {window_size}, Threshold: {repetition_threshold}")
    
    if len(df) <= window_size:
        return df
        
    result_logs = []
    i = 0
    
    while i < len(df):
        window = df.iloc[i:i + window_size]
        templates = window["log_template"].tolist()
        template_counts = defaultdict(int)
        
        # Count template occurrences
        for template in templates:
            template_counts[template] += 1
            
        # Find templates that exceed threshold
        flood_templates = {
            t: c for t, c in template_counts.items()
            if c / window_size >= repetition_threshold
        }
        
        if flood_templates:
            # Found flood pattern
            dominant_template = max(flood_templates.items(), key=lambda x: x[1])[0]
            
            # Find extent of flood
            j = i + window_size
            while j < len(df) and compute_template_similarity(df.iloc[j]["log_template"], dominant_template) > 0.8:
                j += 1
                
            flood_logs = df.iloc[i:j]
            flood_info = analyze_flood_pattern(
                flood_logs["log"].tolist(),
                flood_logs["log_template"].tolist()
            )
            
            # Create summary log
            summary_row = pd.Series({
                "log": f"[LOG FLOOD] {j-i} occurrences of similar logs: {flood_info['template']}",
                "log_template": f"[LOG FLOOD] <count> occurrences of similar logs: {flood_info['template']}",
                "is_anomaly": 1 if flood_info["severity"] == "error" else 0,
                "anomaly_source": "FLOOD",
                "flood_info": flood_info
            })
            
            result_logs.append(summary_row)
            i = j
            
        else:
            # No flood pattern, keep original log
            result_logs.append(df.iloc[i])
            i += 1
            
    return pd.DataFrame(result_logs)
