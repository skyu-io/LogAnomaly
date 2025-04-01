"""Tools for enhancing LLM-based log analysis."""

import re
from typing import Dict, List, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)

def think_about_log(log_line: Union[str, Dict], context_logs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Analyze a log line and extract key information."""
    # Handle dict input
    if isinstance(log_line, dict):
        log_line = log_line.get("log", "") if isinstance(log_line, dict) else str(log_line)
    
    # Ensure context_logs is a list of strings
    if context_logs is None:
        context_logs = []
    context_logs = [str(log) if isinstance(log, dict) else log for log in context_logs]
    
    analysis = {
        "severity": "unknown",
        "component": "unknown",
        "action": "unknown",
        "error_type": "none",
        "patterns": []
    }
    
    # Extract severity
    if re.search(r"\b(error|fail|exception|critical)\b", log_line.lower()):
        analysis["severity"] = "error"
    elif re.search(r"\b(warn|warning)\b", log_line.lower()):
        analysis["severity"] = "warning"
    elif re.search(r"\b(info|notice)\b", log_line.lower()):
        analysis["severity"] = "info"
    elif re.search(r"\b(debug|trace)\b", log_line.lower()):
        analysis["severity"] = "debug"
        
    # Extract component
    component_match = re.match(r"^\[?([a-zA-Z0-9_.-]+)\]?[:|\s]", log_line)
    if component_match:
        analysis["component"] = component_match.group(1)
        
    # Detect action
    action_words = ["started", "stopped", "created", "deleted", "updated", "failed", "connected", "disconnected"]
    for word in action_words:
        if word in log_line.lower():
            analysis["action"] = word
            break
            
    # Detect error type
    error_patterns = {
        "timeout": r"\b(timeout|timed?\s*out)\b",
        "connection": r"\b(connection|connect)\s*(error|fail|refused)\b",
        "permission": r"\b(permission|access)\s*(denied|error)\b",
        "validation": r"\b(invalid|validation)\s*(error|fail)\b",
        "resource": r"\b(memory|disk|cpu|resource)\s*(error|exhausted|full)\b"
    }
    
    for error_type, pattern in error_patterns.items():
        if re.search(pattern, log_line.lower()):
            analysis["error_type"] = error_type
            break
            
    # Extract patterns
    patterns = []
    if re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", log_line):
        patterns.append("ip_address")
    if re.search(r"[a-fA-F0-9]{32}", log_line):
        patterns.append("hash")
    if re.search(r"\d{4}-\d{2}-\d{2}", log_line):
        patterns.append("date")
    if re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+/\S+", log_line):
        patterns.append("http_request")
        
    analysis["patterns"] = patterns
    return analysis

def analyze_context(context_logs: List[Union[str, Dict]]) -> Dict[str, Any]:
    """Analyze context logs for patterns and relationships."""
    # Convert dict logs to strings
    logs = [log.get("log", "") if isinstance(log, dict) else str(log) for log in context_logs]
    
    analysis = {
        "repetition_count": 0,
        "severity_distribution": {"error": 0, "warning": 0, "info": 0, "debug": 0},
        "related_components": set(),
        "patterns": []
    }
    
    if not logs:
        return analysis
        
    # Count similar logs
    from collections import Counter
    log_counter = Counter(logs)
    analysis["repetition_count"] = max(log_counter.values())
    
    # Analyze each log
    for log in logs:
        log_analysis = think_about_log(log)
        
        # Update severity distribution
        severity = log_analysis["severity"]
        analysis["severity_distribution"][severity] = analysis["severity_distribution"].get(severity, 0) + 1
        
        # Track components
        if log_analysis["component"] != "unknown":
            analysis["related_components"].add(log_analysis["component"])
            
        # Collect patterns
        analysis["patterns"].extend(log_analysis["patterns"])
        
    # Convert sets to lists for JSON serialization
    analysis["related_components"] = list(analysis["related_components"])
    analysis["patterns"] = list(set(analysis["patterns"]))
    
    return analysis
