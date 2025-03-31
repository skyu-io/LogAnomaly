import os
import re
import json
import tempfile
import subprocess
from collections import Counter
from loganomaly import config as app_config

# === Default Security Leak Patterns ===
DEFAULT_SECURITY_PATTERNS = [
    {"name": "JWT Token", "pattern": r"eyJ[0-9a-zA-Z\-_.]+"},
    {"name": "Authorization Header", "pattern": r"Authorization: Bearer [a-zA-Z0-9\-_.]+"},
    {"name": "API Key", "pattern": r"API[_-]?KEY[:=\s][a-zA-Z0-9\-_.]+"}
]

# === Default Rule-Based Anomaly Patterns ===
DEFAULT_RULE_BASED_PATTERNS = [
    {"name": "Database Error", "pattern": r"(database|db).*error", "reason": "Database operation failed."},
    {"name": "Service Timeout", "pattern": r"(timeout|timed out|request timed out)", "reason": "Service call timed out."},
    {"name": "HTTP 500 Error", "pattern": r"status\s*[:=]\s*500", "reason": "HTTP 500 server error."},
    {"name": "Process Crash", "pattern": r"(process|service)\s*(exited|crashed|terminated)", "reason": "Process crash detected."},
    {"name": "Restart Detected", "pattern": r"(restart|restarting)", "reason": "Process or pod restart detected."},
    {"name": "Dependency Failure", "pattern": r"(dependency|service)\s*(unavailable|failed|error)", "reason": "Dependency failure detected."},
    {"name": "Configuration Issue", "pattern": r"(invalid|missing)\s*configuration", "reason": "Configuration issue."},
    {"name": "Resource Limit Issue", "pattern": r"(out of memory|OOM|cpu limit exceeded|quota exceeded)", "reason": "Resource limit breach."},
]

def load_custom_patterns():
    """
    Merge default patterns + additional patterns from YAML config.
    """
    rule_patterns = DEFAULT_RULE_BASED_PATTERNS.copy()
    security_patterns = DEFAULT_SECURITY_PATTERNS.copy()

    yaml_config = getattr(app_config, "YAML_CONFIG", {})

    # Add rule patterns
    extra_rules = yaml_config.get("rule_based_patterns", [])
    if extra_rules:
        rule_patterns.extend(extra_rules)

    # Add security patterns
    extra_security = yaml_config.get("security_patterns", [])
    if extra_security:
        security_patterns.extend(extra_security)

    return rule_patterns, security_patterns


def redact_security_leaks(log_line):
    redacted = re.sub(r"(Bearer|Token|Authorization)\s+[\w\-\.]+", r"\1 <REDACTED>", log_line, flags=re.IGNORECASE)
    redacted = re.sub(r"eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+", "<JWT_TOKEN>", redacted)
    redacted = re.sub(r"(API[_-]?KEY[:=\s])([a-zA-Z0-9\-_]+)", r"\1<REDACTED>", redacted, flags=re.IGNORECASE)
    return redacted


def find_security_leaks(df, security_patterns):
    leaks = []
    for idx, row in df.iterrows():
        log = row["log"]
        for pattern in security_patterns:
            if re.search(pattern["pattern"], log):
                redacted = redact_security_leaks(log)
                leaks.append({
                    "index": idx,
                    "timestamp": row["timestamp"],
                    "log": redacted,
                    "reason": f"Possible {pattern['name']} leakage."
                })
                break
    return leaks


def summarize_security_leaks(leaks):
    summary = {}
    for leak in leaks:
        summary[leak["reason"]] = summary.get(leak["reason"], 0) + 1
    return summary


def contains_secret_patterns(log_line):
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
        temp_file.write(log_line)
        temp_file_path = temp_file.name

    try:
        result = subprocess.run(
            [ "detect-secrets", "scan", temp_file_path, "--json"],
            capture_output=True,
            text=True
        )
        output = json.loads(result.stdout)
        has_secrets = len(output.get("results", {})) > 0
    except Exception:
        has_secrets = False

    os.remove(temp_file_path)
    return has_secrets


def clean_log_line(log_line):
    log_line = re.sub(r"\[.*?\]", "", log_line)
    log_line = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*?Z", "", log_line)
    log_line = re.sub(r"[a-f0-9\-]{32,}", "<ID>", log_line)
    log_line = re.sub(r"\d{1,3}(?:\.\d{1,3}){3}", "<IP>", log_line)
    log_line = re.sub(r"(Bearer|Token|APIKey|Secret)\s+\S+", "<SECRET>", log_line, flags=re.IGNORECASE)
    log_line = re.sub(r"\s+", " ", log_line).strip()
    return log_line


def short_reason(reason):
    max_length = app_config.MAX_REASON_LENGTH
    if max_length is None:
        return reason
    if len(reason) > max_length:
        return reason[:max_length].rstrip() + "..."
    return reason


def tag_label(label):
    tag_map = {
        "Sensitive Information Leak": "🔑 Sensitive Leak",
        "Possible Security Threat": "🚨 Security Threat",
        "Operational Error": "⚙️ Operational Error",
        "Routine": "✅ Routine",
        "Unknown": "❓ Unknown",
        "Error": "❗️ LLM Error"
    }
    return tag_map.get(label, "❓ Unknown")


def extract_tags(reply):
    try:
        result = json.loads(reply)

        label = result.get("classification", "Unknown")
        reason = result.get("reason", "Unknown")
        tags = result.get("tags", [])

        if "Routine" in tags or "Non-Anomaly" in tags:
            label = "Routine"
        elif "Possible Security Threat" in tags:
            label = "Possible Security Threat"
        elif "Operational Error" in tags:
            label = "Operational Error"
        elif "Sensitive Information Leak" in tags:
            label = "Sensitive Information Leak"
        elif "Configuration Issue" in tags:
            label = "Configuration Issue"
        else:
            label = "Unknown"

        return label, short_reason(reason), tags

    except Exception:
        return "Unknown", "Could not parse", ["Unknown"]


def is_non_anomalous(log_line, filename, non_anomalies_folder=None):
    non_anomalies_folder = non_anomalies_folder or app_config.NON_ANOMALIES_FOLDER
    non_anomalous_file = os.path.join(non_anomalies_folder, filename)
    if not os.path.exists(non_anomalous_file):
        return False

    try:
        with open(non_anomalous_file, "r") as f:
            data = json.load(f)
            for entry in data:
                if clean_log_line(entry.get("log", "")) == clean_log_line(log_line):
                    return True
    except Exception:
        return False

    return False


def summarize_log_levels(df):
    level_counts = {"debug": 0, "info": 0, "warn": 0, "error": 0}
    for log in df["log"]:
        log_lower = log.lower()
        if "debug" in log_lower:
            level_counts["debug"] += 1
        elif "info" in log_lower:
            level_counts["info"] += 1
        elif "warn" in log_lower or "warning" in log_lower:
            level_counts["warn"] += 1
        elif "error" in log_lower:
            level_counts["error"] += 1
    return level_counts


def summarize_tags(anomalies_df):
    tag_counter = Counter()
    if "tag" in anomalies_df.columns:
        for tags in anomalies_df["tag"]:
            for tag in tags:
                tag_counter[tag] += 1
    return dict(tag_counter)


def rule_based_classification(log_line, rule_based_patterns):
    for rule in rule_based_patterns:
        if re.search(rule["pattern"], log_line, re.IGNORECASE):
            return "Operational Error", rule["reason"], [rule["name"]]
    return None


def clean_tags(tags, valid_tags):
    cleaned = [tag for tag in tags if tag in valid_tags]
    dropped = list(set(tags) - set(cleaned))
    if dropped:
        print(f"⚠️ Dropped invalid tags: {dropped}")
    return cleaned
