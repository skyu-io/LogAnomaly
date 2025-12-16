import os
import re
import json
import tempfile
import subprocess
import yaml
from collections import Counter
from loganomaly import config as app_config
from datetime import datetime, timedelta
import pandas as pd

# === Default Security Leak Patterns ===
DEFAULT_SECURITY_PATTERNS = [
    {"name": "JWT Token", "pattern": r"eyJ[0-9a-zA-Z\-_.]+"},
    {"name": "Authorization Header", "pattern": r"Authorization: Bearer [a-zA-Z0-9\-_.]+"},
    {"name": "API Key", "pattern": r"API[_-]?KEY[:=\s][a-zA-Z0-9\-_.]+"}
]

# === Default Rule-Based Anomaly Patterns ===
# Note: Use non-capturing groups (?:...) instead of (...) to avoid pandas warnings
DEFAULT_RULE_BASED_PATTERNS = [
    {"name": "Database Error", "pattern": r"(?:database|db).*error", "reason": "Database operation failed."},
    {"name": "Service Timeout", "pattern": r"(?:timeout|timed out|request timed out)", "reason": "Service call timed out."},
    {"name": "HTTP 500 Error", "pattern": r"status\s*[:=]\s*500", "reason": "HTTP 500 server error."},
    {"name": "Process Crash", "pattern": r"(?:process|service)\s*(?:exited|crashed|terminated)", "reason": "Process crash detected."},
    {"name": "Restart Detected", "pattern": r"(?:restart|restarting)", "reason": "Process or pod restart detected."},
    {"name": "Dependency Failure", "pattern": r"(?:dependency|service)\s*(?:unavailable|failed|error)", "reason": "Dependency failure detected."},
    {"name": "Configuration Issue", "pattern": r"(?:invalid|missing)\s*configuration", "reason": "Configuration issue."},
    {"name": "Resource Limit Issue", "pattern": r"(?:out of memory|OOM|cpu limit exceeded|quota exceeded)", "reason": "Resource limit breach."},
]

def load_custom_patterns():
    """
    Merge default rule & security patterns with additional patterns from config.
    """
    rule_patterns = DEFAULT_RULE_BASED_PATTERNS.copy()
    security_patterns = DEFAULT_SECURITY_PATTERNS.copy()

    # Add additional patterns from config
    extra_rules = getattr(app_config, "ADDITIONAL_RULE_BASED_PATTERNS", [])
    extra_security = getattr(app_config, "ADDITIONAL_SECURITY_PATTERNS", [])

    if extra_rules:
        rule_patterns.extend(extra_rules)
        print(f"🔧 Loaded {len(extra_rules)} additional rule patterns")

    if extra_security:
        security_patterns.extend(extra_security)
        print(f"🔐 Loaded {len(extra_security)} additional security patterns")

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
        # First try to parse as JSON (in case the LLM returns JSON)
        try:
            result = json.loads(reply)
            label = result.get("classification", "Unknown")
            reason = result.get("reason", "Unknown")
            tags = result.get("tags", [])
            
            # Return early if we successfully parsed JSON
            return label, short_reason(reason), tags
        except json.JSONDecodeError:
            # Not JSON, continue with text parsing
            pass
        
        # Extract classification using regex
        classification_match = re.search(r"(?i)classification:\s*(\w+)", reply)
        label = classification_match.group(1).strip() if classification_match else "Unknown"
        
        # Convert classification to standard format
        if label.lower() == "normal":
            label = "Normal"
        elif label.lower() in ["anomaly", "anomalous"]:
            label = "Anomaly"
        elif label.lower() == "error":
            label = "Error"
            
        # Extract reason using regex
        reason_match = re.search(r"(?i)reason:\s*(.+?)(?=\n|tags:|$)", reply)
        reason = reason_match.group(1).strip() if reason_match else reply
        
        # Extract tags using regex
        tags_match = re.search(r"(?i)tags:\s*(.+?)(?=\n|$)", reply)
        if tags_match:
            tags_str = tags_match.group(1).strip()
            tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
        else:
            tags = ["Unknown"]
            
        # Apply tag-based classification logic
        if "routine" in [t.lower() for t in tags] or "non-anomaly" in [t.lower() for t in tags]:
            label = "Normal"
        elif any(security in [t.lower() for t in tags] for security in ["security", "sensitive", "leak"]):
            label = "Security"
            
        return label, short_reason(reason), tags
        
    except Exception as e:
        print(f"Error extracting tags: {str(e)}")
        return "Unknown", reply, ["Unknown"]


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
            if isinstance(tags, list):  # Added type checking
                for tag in tags:
                    tag_counter[tag] += 1
            elif isinstance(tags, str):  # Handle string tags
                tag_counter[tags] += 1
            # Skip None, NaN, or other non-iterable values
    return dict(tag_counter)


def rule_based_classification(log_line, rule_based_patterns):
    for rule in rule_based_patterns:
        if re.search(rule["pattern"], log_line, re.IGNORECASE):
            return "Operational Error", rule["reason"], [rule["name"]]
    return None


def apply_rule_based_classification_vectorized(df, rule_patterns, security_patterns):
    """
    Vectorized rule-based classification - much faster than row-by-row apply.
    
    Args:
        df: DataFrame with 'log' column
        rule_patterns: List of rule pattern dicts with 'pattern', 'reason', 'name'
        security_patterns: List of security pattern dicts for security-related check
    
    Returns:
        DataFrame with classification columns added
    """
    n_rows = len(df)
    
    # Initialize columns with default values
    df["is_rule_based"] = False
    df["is_security_related"] = False
    df["classification"] = None
    df["reason"] = None
    df["tag"] = [[] for _ in range(n_rows)]  # List of empty lists
    df["anomaly_source"] = None
    
    # Ensure is_anomaly exists
    if "is_anomaly" not in df.columns:
        df["is_anomaly"] = 0
    
    # Track which rows have been classified (first match wins)
    classified_mask = pd.Series([False] * n_rows, index=df.index)
    
    def convert_to_non_capturing(pattern):
        """Convert capturing groups (...) to non-capturing (?:...) to avoid pandas warnings."""
        # Match ( not preceded by \ and not followed by ? (which would be (?:, (?=, etc.)
        return re.sub(r'(?<!\\)\((?!\?)', '(?:', pattern)
    
    for rule in rule_patterns:
        pattern = rule["pattern"]
        reason = rule.get("reason", "Rule-based detection")
        name = rule.get("name", "Unknown Rule")
        
        # Convert any capturing groups to non-capturing for str.contains()
        safe_pattern = convert_to_non_capturing(pattern)
        
        # Vectorized regex matching - only on unclassified rows
        try:
            match_mask = (
                ~classified_mask & 
                df["log"].str.contains(safe_pattern, case=False, regex=True, na=False)
            )
        except re.error as e:
            print(f"⚠️ Invalid regex pattern '{pattern}': {e}")
            continue
        
        if match_mask.any():
            matched_indices = df.index[match_mask]
            
            df.loc[matched_indices, "classification"] = "Operational Error"
            df.loc[matched_indices, "reason"] = reason
            df.loc[matched_indices, "is_rule_based"] = True
            df.loc[matched_indices, "is_anomaly"] = 1
            df.loc[matched_indices, "anomaly_source"] = "Rule-Based"
            
            # Set tags (need to do this row by row due to list type)
            for idx in matched_indices:
                df.at[idx, "tag"] = [name]
            
            # Mark as classified
            classified_mask = classified_mask | match_mask
    
    # Vectorized security-related check for classified rows
    if classified_mask.any() and security_patterns:
        rule_based_indices = df.index[classified_mask]
        
        for pattern_info in security_patterns:
            pattern = pattern_info["pattern"]
            safe_pattern = convert_to_non_capturing(pattern)
            try:
                security_mask = df.loc[rule_based_indices, "log"].str.contains(
                    safe_pattern, case=False, regex=True, na=False
                )
                if security_mask.any():
                    matched_security_indices = rule_based_indices[security_mask]
                    df.loc[matched_security_indices, "is_security_related"] = True
            except re.error:
                continue
    
    return df


def clean_tags(tags, valid_tags):
    cleaned = [tag for tag in tags if tag in valid_tags]
    dropped = list(set(tags) - set(cleaned))
    if dropped:
        print(f"⚠️ Dropped invalid tags: {dropped}")
    return cleaned


def evaluate_behavioral_rules(df, behavioral_rules):
    """
    Evaluate behavioral rules against the logs DataFrame.
    df: pandas.DataFrame with at least columns: 'timestamp', 'log', plus any fields referred by rules
       - timestamp should be parsable to datetime or already datetime dtype
       - other fields (like 'user', 'organization_id', 'application') should exist if rules use them
    behavioral_rules: list of dicts with supported keys:
       - name, type (count|distinct_count|ratio), group_by, window_minutes, threshold,
         field (for distinct_count), pattern (optional regex), threshold_ratio (for ratio)
    Returns: list of anomaly dicts: {"rule": name, "group": group_key, "count": n, "reason": reason, "matched_logs": [indices...]}
    """
    anomalies = []

    if df.empty or not behavioral_rules:
        return anomalies

    if "timestamp" not in df.columns:
        print("⚠️ Behavioral rule evaluation skipped: 'timestamp' column is missing in the logs dataframe.")
        return anomalies

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        try:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        except Exception:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    for rule in behavioral_rules:
        name = rule.get("name", "Unnamed Rule")
        rtype = rule.get("type", "count")
        group_by = rule.get("group_by", None)
        window_minutes = rule.get("window_minutes", 60)  # default 1 hour
        threshold = rule.get("threshold", None)
        field = rule.get("field", None)  # used for distinct_count
        pattern = rule.get("pattern", None)
        threshold_ratio = rule.get("threshold_ratio", None)

        # Pattern filter: restrict rows to those that match rule.pattern if provided
        def pattern_filter_series(series):
            if not pattern:
                return series
            mask = series["log"].str.contains(pattern, flags=re.IGNORECASE, regex=True, na=False)
            return series[mask]

        filtered = pattern_filter_series(df)

        # fallback group_by -> single group
        if group_by and group_by in filtered.columns:
            groups = filtered.groupby(group_by)
        else:
            # use a single synthetic group
            groups = [ (None, filtered) ]

        for group_key, group_df in groups:
            # sort for sliding window
            g = group_df.sort_values("timestamp").reset_index()
            timestamps = g["timestamp"].tolist()
            
            print(f"\n🔍 Evaluating rule: {name}")
            print(f"Group by: {group_by}, Group value: {group_key}")
            print(f"Log entries in group: {len(g)}")
            print(f"Pattern matching: {pattern}")
            
            if rtype == "count":
                print(f"Looking for {threshold} occurrences within {window_minutes} minutes")
                # sliding window count: for each event, count events within window ending at that timestamp
                window_td = timedelta(minutes=window_minutes)
                left = 0
                for i, ts in enumerate(timestamps):
                    if pd.isna(ts):
                        continue
                    # move left pointer forward while outside window
                    while left <= i and timestamps[left] < ts - window_td:
                        left += 1
                    cnt = i - left + 1
                    print(f"Window from {timestamps[left]} to {ts}: Found {cnt} events")
                    if threshold is not None and cnt >= threshold:
                        matched_indices = g.loc[left:i, "index"].tolist()
                        print(f"🎯 Threshold reached! Count: {cnt} >= {threshold}")
                        anomalies.append({
                            "rule": name,
                            "group": group_key,
                            "count": cnt,
                            "matched_indices": matched_indices,
                            "reason": rule.get("reason", f"{name} triggered by count >= {threshold}")
                        })
                        # break to avoid duplicates for same group (you can change this to keep all occurrences)
                        break

            elif rtype == "distinct_count":
                # distinct values of `field` seen for this group within window
                # We'll do a sliding window and check distinct count over window
                if not field or field not in g.columns:
                    continue
                window_td = timedelta(minutes=window_minutes)
                left = 0
                values = g[field].tolist()
                for i, ts in enumerate(timestamps):
                    if pd.isna(ts):
                        continue
                    while left <= i and timestamps[left] < ts - window_td:
                        left += 1
                    window_values = values[left:i+1]
                    distinct_count = len(set([v for v in window_values if pd.notna(v)]))
                    if threshold is not None and distinct_count >= threshold:
                        matched_indices = g.loc[left:i, "index"].tolist()
                        anomalies.append({
                            "rule": name,
                            "group": group_key,
                            "distinct_count": distinct_count,
                            "matched_indices": matched_indices,
                            "reason": rule.get("reason", f"{name} triggered by distinct_count >= {threshold}")
                        })
                        break

            elif rtype == "ratio":
                # ratio of matching events / total events in a sliding window
                if threshold_ratio is None:
                    continue
                window_td = timedelta(minutes=window_minutes)

                # For ratio we need:
                # - numerator: events matching the rule (g)
                # - denominator: all events in same group (from original df)
                if group_by and group_by in df.columns and group_key is not None:
                    all_group = df[df[group_by] == group_key].sort_values("timestamp").reset_index()
                else:
                    all_group = df.sort_values("timestamp").reset_index()

                times_all = all_group["timestamp"].tolist()
                left_all = 0

                for i_all, ts_all in enumerate(times_all):
                    if pd.isna(ts_all):
                        continue
                    while left_all <= i_all and times_all[left_all] < ts_all - window_td:
                        left_all += 1
                    total_count = i_all - left_all + 1

                    # matched events in the same window (from filtered set g)
                    window_start = times_all[left_all]
                    window_end = ts_all
                    mask = (g["timestamp"] >= window_start) & (g["timestamp"] <= window_end)
                    matched_count = int(mask.sum())
                    ratio = matched_count / float(total_count) if total_count > 0 else 0.0

                    if ratio >= float(threshold_ratio):
                        matched_indices = g.loc[mask, "index"].tolist()
                        anomalies.append({
                            "rule": name,
                            "group": group_key,
                            "ratio": ratio,
                            "matched_indices": matched_indices,
                            "reason": rule.get("reason", f"{name} triggered by ratio >= {threshold_ratio}")
                        })
                        break

            else:
                # unknown rule type
                print(f"⚠️ Unknown behavioral rule type {rtype} for rule {name}")

    return anomalies

def extract_client_fields(df, client_config_file=None):
    """
    Extract client-specific fields based on external configuration.
    Optimized with vectorized operations for much better performance.
    
    Returns DataFrame with additional fields.
    """
    if not client_config_file or not os.path.exists(client_config_file):
        return df
    
    try:
        with open(client_config_file, 'r') as f:
            client_config = yaml.safe_load(f)
        
        if client_config is None:
            print(f"⚠️ Config file is empty: {client_config_file}")
            return df
        
        field_configs = client_config.get('field_extraction', [])
        
        if not field_configs:
            return df
        
        # === OPTIMIZATION: Parse all JSON logs once ===
        def safe_json_parse(log):
            """Safely parse JSON, return empty dict on failure."""
            if not isinstance(log, str):
                return {}
            try:
                result = json.loads(log)
                return result if isinstance(result, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        
        # Parse all logs at once (vectorized)
        parsed_logs = df["log"].apply(safe_json_parse)
        
        for field_config in field_configs:
            field_name = field_config['name']
            extractors = field_config.get('extractors', [])
            regex_pattern = field_config.get('regex')
            
            # Initialize the field
            df[field_name] = None
            
            # === Method 1: Extract from parsed JSON (vectorized) ===
            def extract_from_json(parsed_dict):
                """Extract field value from parsed JSON dict."""
                for extractor in extractors:
                    if extractor in parsed_dict and parsed_dict[extractor]:
                        return parsed_dict[extractor]
                return None
            
            df[field_name] = parsed_logs.apply(extract_from_json)
            
            # === Method 2: Check existing columns (vectorized) ===
            # Only for rows still missing the field
            missing_mask = df[field_name].isna()
            
            if missing_mask.any():
                for extractor in extractors:
                    if extractor in df.columns:
                        # Fill missing values from existing column
                        fill_mask = missing_mask & df[extractor].notna() & (df[extractor] != "")
                        if fill_mask.any():
                            df.loc[fill_mask, field_name] = df.loc[fill_mask, extractor]
                            missing_mask = df[field_name].isna()
                            if not missing_mask.any():
                                break
            
            # === Method 3: Regex extraction (vectorized) ===
            if regex_pattern and missing_mask.any():
                try:
                    # Use str.extract for vectorized regex extraction
                    # Check if pattern has capture group
                    if '(' in regex_pattern and ')' in regex_pattern:
                        extracted = df.loc[missing_mask, "log"].str.extract(
                            regex_pattern, flags=re.IGNORECASE, expand=False
                        )
                    else:
                        # Wrap pattern in capture group for extraction
                        extracted = df.loc[missing_mask, "log"].str.extract(
                            f"({regex_pattern})", flags=re.IGNORECASE, expand=False
                        )
                    
                    # Fill in extracted values
                    if extracted is not None and not extracted.empty:
                        # Handle both Series and DataFrame returns
                        if isinstance(extracted, pd.DataFrame):
                            extracted = extracted.iloc[:, 0]
                        
                        valid_extracts = extracted.notna() & (extracted != "")
                        if valid_extracts.any():
                            df.loc[missing_mask & valid_extracts.reindex(df.index, fill_value=False), field_name] = extracted[valid_extracts]
                            
                except re.error as e:
                    print(f"⚠️ Invalid regex pattern for {field_name}: {e}")
        
        # Count extracted values for reporting
        extracted_counts = {fc['name']: df[fc['name']].notna().sum() for fc in field_configs}
        print(f"✅ Extracted {len(field_configs)} client-specific fields from {client_config_file}")
        for name, count in extracted_counts.items():
            if count > 0:
                print(f"   📌 {name}: {count} values extracted")
        
        return df
        
    except Exception as e:
        print(f"❌ Failed to extract client fields: {e}")
        return df



def load_behavioral_rules(rules_file_path=None):
    """Load behavioral rules from external YAML file."""
    if not rules_file_path:
        return []
    
    try:
        with open(rules_file_path, 'r') as f:
            config = yaml.safe_load(f)
            behavioral_rules = config.get('behavioral_rules', [])
            print(f"✅ Loaded {len(behavioral_rules)} behavioral rules from {rules_file_path}")
            return behavioral_rules
    except Exception as e:
        print(f"❌ Failed to load behavioral rules from {rules_file_path}: {e}")
        return []