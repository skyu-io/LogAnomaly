"""Prompt templates and utilities for LLM classification."""

import re
from typing import List

VALID_TAGS = [
    "Error", "Warning", "Info", "Debug",
    "Database", "Network", "Security", "Performance",
    "Configuration", "System", "Application", "API",
    "Authentication", "Authorization", "Validation",
    "Memory", "CPU", "Disk", "Cache", "Queue",
    "Timeout", "Retry", "Recovery", "Startup", "Shutdown",
    "Dependency", "Integration", "Migration", "Deployment",
    "Unknown"
]

def clean_tags(tags: List[str]) -> List[str]:
    """Clean and validate tags."""
    cleaned = []
    for tag in tags:
        tag = tag.strip().title()
        if tag in VALID_TAGS:
            cleaned.append(tag)
    return cleaned or ["Unknown"]

def summarize_context_logs(logs: List[str], max_logs=5) -> str:
    """Summarize context logs."""
    if not logs:
        return ""
    return f"\nContext ({len(logs)} logs):\n" + "\n".join(logs[:max_logs])

def build_llm_prompt(log_line: str, context_logs: List[str], enhanced_context: dict = None) -> str:
    """Build the prompt for log classification."""
    
    base_prompt = f"""Analyze this log line and classify it as anomaly or normal. Consider severity, patterns, and context.

Log line: {log_line}"""

    if enhanced_context:
        analysis = enhanced_context.get("log_analysis", {})
        context = enhanced_context.get("context_analysis", {})
        
        analysis_prompt = f"""

Analysis:
- Severity: {analysis.get('severity', 'unknown')}
- Component: {analysis.get('component', 'unknown')}
- Action: {analysis.get('action', 'unknown')}
- Error Type: {analysis.get('error_type', 'none')}
- Patterns: {', '.join(analysis.get('patterns', [])) or 'none'}

Context Analysis:
- Similar Log Count: {context.get('repetition_count', 0) if context else 'N/A'}
- Severity Distribution: {context.get('severity_distribution', {}) if context else 'N/A'}
- Related Components: {', '.join(context.get('related_components', [])) if context else 'N/A'}"""
        
        base_prompt += analysis_prompt

    if context_logs:
        base_prompt += summarize_context_logs(context_logs)

    base_prompt += """

Classify this log as:
1. Classification (one of): Normal Operation, Configuration Issue, Performance Problem, Security Issue, System Error, Network Issue, Database Error, Application Error, Resource Issue, Unknown
2. Reason: Brief explanation of the classification
3. Tags: [2-3 relevant tags from: Error, Warning, Info, Debug, Database, Network, Security, Performance, Configuration, System, Application, API, Authentication, Authorization, Validation, Memory, CPU, Disk, Cache, Queue, Timeout, Retry, Recovery, Startup, Shutdown, Dependency, Integration, Migration, Deployment, Unknown]

Format: Classification | Reason | [Tags]
Example: Network Issue | Connection timeout to database | [Error, Network, Database]

Classification:"""

    return base_prompt
