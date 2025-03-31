import re

VALID_TAGS = [
    "Security", "Sensitive", "Operational", "Infrastructure",
    "Configuration Issue", "Dependency Failure", "Runtime Noise",
    "Stack Trace", "Resource Exhaustion", "Authorization Error",
    "Network Failure", "Database Error", "Service Timeout",
    "Process Crash", "Deployment Event", "Policy Violation",
    "Log Flood", "Anomaly", "Non-Anomaly", "Dependent Anomaly", "Unknown"
]


def clean_tags(tags, valid_tags):
    """
    Clean LLM tags to only include valid ones.
    """
    cleaned = []
    for tag in tags:
        tag_clean = re.sub(r"[^a-zA-Z\s\-]", "", tag).strip()
        if tag_clean in valid_tags and tag_clean not in cleaned:
            cleaned.append(tag_clean)
    return cleaned


def summarize_context_logs(context_logs, window_size=3, max_chars=300):
    """
    Simple summarizer: last N logs, trimmed to max_chars.
    """
    context_text = "\n".join([c["log"] for c in context_logs][-window_size:])
    return context_text[-max_chars:]


def build_llm_prompt(log_line, context_logs):
    """
    Build a generic LLM prompt.
    """
    context_summary = summarize_context_logs(context_logs)

    return f"""
You are an expert DevOps log anomaly detector. Analyze the following log line and summarized context logs.
Return a valid JSON object in this format:
{{
  "classification": "Anomaly | Non-Anomaly | Dependent Anomaly | Unknown",
  "reason": "short reason text",
  "tags": ["{', '.join(VALID_TAGS)}"]
}}
Use only the tags provided.

Context Logs Summary:
{context_summary}

Current Log Line:
{log_line}
"""
