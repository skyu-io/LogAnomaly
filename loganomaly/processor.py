### processor.py (fully fixed, full version)

import os
import json
import pandas as pd
import asyncio
from tqdm import tqdm
from collections import Counter
import math
import re

from loganomaly import config as app_config
from loganomaly.utils import (
    summarize_log_levels, is_non_anomalous,
    find_security_leaks, summarize_tags, rule_based_classification,
    redact_security_leaks, load_custom_patterns, evaluate_behavioral_rules
)
from loganomaly.pattern_miner import mine_templates
from loganomaly.detectors.anomaly_detector import detect_knn_anomalies as knn_detect
from loganomaly.detectors.lof_detector import detect_anomalies_lof
from loganomaly.detectors.rolling_window_detector import rolling_window_chunking
from loganomaly.llm_classifier import classify_anomalies, apply_dependent_anomaly_filter


# === Load dynamic patterns ===
custom_rule_patterns, custom_security_patterns = load_custom_patterns()

def save_llm_candidates(anomalies_df, filename):
    """
    Save anomalies that should be sent to the LLM into a JSONL file.
    """
    if anomalies_df is None or anomalies_df.empty:
        return None

    base = os.path.splitext(filename)[0]
    path = os.path.join(app_config.RESULTS_FOLDER, f"{base}_llm_candidates.jsonl")

    # Keep the columns we need for LLM
    cols = ["timestamp", "log", "context_logs", "anomaly_score", "source_file"]
    cols = [c for c in cols if c in anomalies_df.columns]

    anomalies_df[cols].to_json(path, orient="records", lines=True, force_ascii=False)
    print(f"💾 Saved LLM candidates to {path}")
    return path


def load_logs(filepath):
    filename = os.path.basename(filepath)
    log_lines = []

    try:
        if filepath.endswith(".json"):
            with open(filepath, "r") as f:
                data = json.load(f)
                for record in data:
                    # Extract message from various possible fields
                    message = ""
                    if "@message" in record and isinstance(record["@message"], dict):
                        message = record["@message"].get("log", "").strip()
                    elif "message" in record:
                        message = record["message"].strip() if isinstance(record["message"], str) else ""
                    elif "log" in record:
                        message = record["log"].strip() if isinstance(record["log"], str) else ""
                    elif "@message" in record and isinstance(record["@message"], str):
                        message = record["@message"].strip()
                    
                    if message:
                        # Extract timestamp from various possible fields
                        timestamp = ""
                        timestamp_fields = ["@timestamp", "timestamp", "time", "@time", "datetime", "date"]
                        for field in timestamp_fields:
                            if field in record and record[field]:
                                timestamp = str(record[field])
                                break
                        
                        log_lines.append({
                            "timestamp": timestamp,
                            "log": message,
                            "source_file": filename
                        })
        else:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(" ", 1)
                    timestamp = parts[0] if len(parts) > 1 else ""
                    log_msg = parts[1] if len(parts) > 1 else parts[0]
                    log_lines.append({
                        "timestamp": timestamp,
                        "log": log_msg,
                        "source_file": filename
                    })

    except Exception as e:
        print(f"❌ Failed to load {filename}: {e}")
        return None, 0

    original_count = len(log_lines)

    if app_config.MAX_LOG_LINES:
        print(f"⚠️ Sampling first {app_config.MAX_LOG_LINES} logs (Compliance Mode)")
        log_lines = log_lines[:app_config.MAX_LOG_LINES]

    if len(log_lines) > app_config.LARGE_LOG_WARNING_THRESHOLD:
        print(f"⚠️ Large log file detected: {len(log_lines)} lines. Processing may take longer.")

    return pd.DataFrame(log_lines) if log_lines else None, original_count


def detect_volume_anomalies(df):
    if not app_config.ENABLE_SPAM_DETECTION:
        return [], False, []

    if "log_template" not in df.columns:
        return [], False, []

    template_counts = Counter(df["log_template"])
    total_logs = len(df)
    volume_stats = []
    flood_templates = []

    for template, count in template_counts.items():
        ratio = count / total_logs
        entry = {
            "template": template,
            "count": count,
            "ratio": round(ratio, 2)
        }
        volume_stats.append(entry)

        if ratio >= app_config.SPAM_TEMPLATE_THRESHOLD:
            flood_templates.append(entry)

    volume_stats = sorted(volume_stats, key=lambda x: x["count"], reverse=True)[:5]
    flood_detected = len(flood_templates) > 0
    return volume_stats, flood_detected, flood_templates


def get_context_logs(df, index, window=5):
    start = max(index - window, 0)
    end = min(index + window + 1, len(df))
    
    # Determine which columns are available
    available_columns = []
    if "timestamp" in df.columns:
        available_columns.append("timestamp")
    if "log" in df.columns:
        available_columns.append("log")
    
    # If no required columns exist, return empty list
    if not available_columns:
        return []
    
    # Extract context with available columns
    context = df.iloc[start:end][available_columns].to_dict(orient="records")
    
    # Filter out malformed or incomplete log entries
    filtered_context = []
    target_timestamp = None
    
    # Find the target log's timestamp for time-based filtering (if timestamp column exists)
    if "timestamp" in df.columns:
        for log_entry in context:
            if log_entry.get("timestamp") == df.iloc[index].get("timestamp"):
                ts_value = log_entry.get("timestamp", "")
                # Convert to string safely (handle float, NaN, None)
                if ts_value is None or (isinstance(ts_value, float) and pd.isna(ts_value)):
                    target_timestamp = ""
                else:
                    target_timestamp = str(ts_value).strip()
                break
    
    for log_entry in context:
        log_text = log_entry.get("log", "").strip()
        ts_value = log_entry.get("timestamp", "")
        # Convert to string safely (handle float, NaN, None)
        if ts_value is None or (isinstance(ts_value, float) and pd.isna(ts_value)):
            timestamp = ""
        else:
            timestamp = str(ts_value).strip()
        
        # Basic log text validation (always required)
        if len(log_text) < 5 or len(log_text.split()) < 2:
            continue
        
        # Skip entries that look like fragments or incomplete logs
        if (
            log_text.startswith("'") and log_text.endswith("'") and len(log_text) < 50 or  # Short quoted fragments
            log_text.count("/") > 3 and len(log_text) < 100 or  # Path fragments
            "..." in log_text or  # Truncated content
            log_text.startswith("(") and log_text.endswith(")") and len(log_text) < 100  # Parenthetical fragments
        ):
            continue
        
        # Timestamp validation (only if timestamp column exists)
        if "timestamp" in df.columns and timestamp:
            if (
                len(timestamp) < 3 or
                timestamp.startswith("(") or  # Parenthetical timestamps (fragments)
                timestamp.startswith("'") or  # Quote-prefixed timestamps (fragments)
                timestamp.startswith("+") or  # Command prefixes
                not any(c.isdigit() for c in timestamp)  # No digits in timestamp (likely not a real timestamp)
            ):
                continue
        
        # Time-based filtering: exclude logs from different days if target timestamp is available
        if target_timestamp and len(timestamp) >= 10 and len(target_timestamp) >= 10:
            try:
                target_date = target_timestamp[:10]  # Extract YYYY-MM-DD
                log_date = timestamp[:10]
                if target_date != log_date:  # Different day
                    continue
            except:
                pass  # If parsing fails, include the log
            
        filtered_context.append(log_entry)
    
    return filtered_context


def is_security_related_anomaly(row, security_patterns):
    """
    Determine if an anomaly is security-related based on various indicators.
    """
    log_text = row.get("log", "").lower()
    classification = row.get("classification", "").lower()
    tags = row.get("tag", [])
    reason = row.get("reason", "").lower()
    
    # Check if it's a security leak
    for pattern in security_patterns:
        if re.search(pattern["pattern"], row.get("log", ""), re.IGNORECASE):
            return True
    
    # Check classification and reason for security keywords
    security_keywords = [
        "security", "breach", "unauthorized", "authentication", "auth", "login", "password",
        "token", "credential", "privilege", "permission", "access", "intrusion", "attack",
        "malicious", "suspicious", "threat", "vulnerability", "exploit", "injection",
        "xss", "csrf", "sql injection", "brute force", "ddos", "dos", "phishing",
        "malware", "virus", "trojan", "ransomware", "backdoor", "rootkit", "keylogger",
        "firewall", "blocked", "denied", "forbidden", "failed login", "invalid user",
        "certificate", "ssl", "tls", "encryption", "decrypt", "hash", "signature",
        "audit", "compliance", "policy violation", "data leak", "exposure", "breach"
    ]
    
    # Check in classification
    if any(keyword in classification for keyword in security_keywords):
        return True
    
    # Check in reason
    if any(keyword in reason for keyword in security_keywords):
        return True
    
    # Check in tags
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and any(keyword in tag.lower() for keyword in security_keywords):
                return True
    
    # Check for specific log patterns that indicate security issues
    security_log_patterns = [
        r"failed.*login",
        r"invalid.*user",
        r"authentication.*failed",
        r"access.*denied",
        r"permission.*denied",
        r"unauthorized.*access",
        r"security.*violation",
        r"blocked.*request",
        r"suspicious.*activity",
        r"malicious.*request",
        r"sql.*injection",
        r"xss.*attack",
        r"csrf.*token",
        r"brute.*force",
        r"ddos.*attack",
        r"firewall.*block",
        r"intrusion.*detect",
        r"virus.*detect",
        r"malware.*detect",
        r"certificate.*error",
        r"ssl.*error",
        r"encryption.*failed",
        r"audit.*failure",
        r"compliance.*violation",
        r"data.*breach",
        r"information.*leak",
        r"privilege.*escalation",
        r"buffer.*overflow",
        r"code.*injection",
        r"path.*traversal",
        r"directory.*traversal"
    ]
    
    for pattern in security_log_patterns:
        if re.search(pattern, log_text, re.IGNORECASE):
            return True
    
    return False


def apply_rule_based_classification(row):
    result = rule_based_classification(row["log"], custom_rule_patterns)
    if result:
        label, reason, tags = result
        row["classification"] = label
        row["reason"] = reason
        row["tag"] = tags
        row["is_rule_based"] = True
        row["is_anomaly"] = 1
        row["anomaly_source"] = "Rule-Based"
        row["is_security_related"] = is_security_related_anomaly(row, custom_security_patterns)
    else:
        row["is_rule_based"] = False
        row["is_security_related"] = False
    return row


def process_file(filepath):
    filename = os.path.basename(filepath)
    llm_phase = getattr(app_config, "LLM_PHASE", "full")
    
    print(f"\n🔍 Processing {filename} (LLM phase={llm_phase})")

    df, original_count = load_logs(filepath)
    if df is None or len(df) == 0:
        return

    # === DEBUG: Check what fields are available ===
    print(f"📊 DataFrame columns: {df.columns.tolist()}")
    if len(df) > 0:
        print(f"📋 Sample row fields:")
        sample_row = df.iloc[0]
        for col in df.columns:
            print(f"   - {col}: {sample_row[col]}")

    # === Extract client-specific fields ===
    from loganomaly.utils import extract_client_fields
    
    # Check if this file has a specific config in FILE_CONFIG_MAP
    client_config_file = getattr(app_config, "CLIENT_CONFIG_FILE", None)
    file_config_map = getattr(app_config, "FILE_CONFIG_MAP", {})
    
    if filename in file_config_map:
        # Use per-file config
        client_config_file = file_config_map[filename]
        print(f"🎯 Using file-specific config for {filename}: {client_config_file}")
    
    if client_config_file:
        df = extract_client_fields(df, client_config_file)
        print(f"📊 New DataFrame columns after client extraction: {df.columns.tolist()}")

    # Initialize behavioral detection columns
    if 'is_behavioral' not in df.columns:
        df['is_behavioral'] = False
    if 'behavioral_rule' not in df.columns:
        df['behavioral_rule'] = None
    
    df = mine_templates(df)

    # Always calculate volume stats, even if empty
    volume_stats, flood_detected, flood_templates = detect_volume_anomalies(df)
    
    # Calculate template diversity metrics
    template_diversity = {
        "unique_templates": 0,
        "template_entropy": 0.0,
        "top_template_ratio": 0.0
    }
    
    if "log_template" in df.columns:
        template_counts = Counter(df["log_template"])
        total_logs = len(df)
        unique_templates = len(template_counts)
        
        # Calculate Shannon entropy for template distribution
        entropy = 0.0
        for template, count in template_counts.items():
            p = count / total_logs
            entropy -= p * (math.log2(p) if p > 0 else 0)
            
        # Get ratio of most common template
        most_common = template_counts.most_common(1)
        top_ratio = most_common[0][1] / total_logs if most_common else 0
        
        template_diversity = {
            "unique_templates": unique_templates,
            "template_entropy": round(entropy, 2),
            "top_template_ratio": round(top_ratio, 3)
        }
    
    if app_config.ENABLE_ROLLING_WINDOW:
        df = rolling_window_chunking(
            df,
            window_size=app_config.ROLLING_WINDOW_SIZE,
            repetition_threshold=app_config.ROLLING_WINDOW_THRESHOLD
        )

    df = knn_detect(df, app_config.TOP_PERCENT)

    if app_config.ENABLE_LOF:
        df = detect_anomalies_lof(df, app_config.TOP_PERCENT, n_neighbors=app_config.LOF_N_NEIGHBORS)

    df = df.apply(apply_rule_based_classification, axis=1)
    rule_based_count = df["is_rule_based"].sum()

    max_score = df["anomaly_score"].max() if "anomaly_score" in df.columns else 0
    print(f"🔎 Max Anomaly Score: {max_score:.4f}")

    skipped_non_anomalies = 0
    llm_classification_done = False
    security_leaks = find_security_leaks(df, custom_security_patterns)

    anomalies_df = df[(df["is_anomaly"] == 1) & (df["is_rule_based"] == False)].copy()

    if max_score < app_config.ANOMALY_THRESHOLD or anomalies_df.empty:
        print(f"✅ No significant LLM anomalies in {filename}")
        llm_stats = {}
    else:
        if app_config.ENABLE_LLM:
            anomalies_df = anomalies_df.head(app_config.TOP_N_LLM)

            filtered = []
            for idx, row in anomalies_df.iterrows():
                if is_non_anomalous(row["log"], filename, app_config.NON_ANOMALIES_FOLDER):
                    skipped_non_anomalies += 1
                    continue
                row = row.copy()
                row["context_logs"] = get_context_logs(df, idx)
                filtered.append(row)

            anomalies_df = pd.DataFrame(filtered)

            if anomalies_df.empty:
                llm_stats = {}               
            else:
                llm_phase = getattr(app_config, "LLM_PHASE", "full")

                if llm_phase == "prepare":
                    # 🔹 CPU-only phase: just save candidates and skip the LLM call
                    save_llm_candidates(anomalies_df, filename)
                    llm_stats = {}
                    llm_classification_done = False

                elif llm_phase == "full":
                    print(f"\n🤖 Classifying {len(anomalies_df)} anomalies (LLM)...")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    classifications, reasons, cleaned_logs, tags_list, llm_stats = loop.run_until_complete(
                        classify_anomalies(anomalies_df)
                    )

                    print(f"📊 LLM Usage → {llm_stats['total_calls']} calls, "
                          f"{llm_stats['total_tokens']} tokens, "
                          f"Avg time: {llm_stats['total_time']/max(llm_stats['total_calls'],1):.2f}s, "
                          f"Errors: {llm_stats['errors']}")

                    anomalies_df["classification"] = classifications
                    anomalies_df["reason"] = reasons
                    anomalies_df["tag"] = tags_list
                    anomalies_df["cleaned_log"] = cleaned_logs
                    anomalies_df["is_llm_anomaly"] = True
                    anomalies_df["anomaly_source"] = "LLM"
                    anomalies_df["is_security_related"] = anomalies_df.apply(
                        lambda row: is_security_related_anomaly(row, custom_security_patterns), axis=1
                    )

                    if app_config.ENABLE_DEPENDENT_ANOMALY_FILTER:
                        anomalies_df = anomalies_df.apply(apply_dependent_anomaly_filter, axis=1)

                    llm_classification_done = True
                else:
                    # llm_phase == "classify": nothing to do here in this pass
                    llm_stats = {}
        else:
            llm_stats = {}

    # Remove logs that LLM classified as non-anomalous or uncertain
    if "classification" in anomalies_df.columns:
        normal_indices = anomalies_df[anomalies_df["classification"].isin(["Routine", "Normal", "unknown"])].index
        anomalies_df.loc[normal_indices, "is_anomaly"] = 0

    if not app_config.ENABLE_LLM:
        context_logs = []
        for idx in anomalies_df.index:
            context = get_context_logs(df, idx)
            context_logs.append(context)
        anomalies_df["context_logs"] = context_logs
        
        # Add security classification for non-LLM anomalies if not already set
        if "is_security_related" not in anomalies_df.columns:
            anomalies_df["is_security_related"] = anomalies_df.apply(
                lambda row: is_security_related_anomaly(row, custom_security_patterns), axis=1
            )

    df["log"] = df["log"].apply(redact_security_leaks)

    # === Behavioral anomaly detection ===
    from loganomaly.utils import load_behavioral_rules
    
    # Load behavioral rules from inline config or external file
    behavioral_rules = []
    if getattr(app_config, "ENABLE_BEHAVIORAL_DETECTION", False):
        # First, try to load from per-file config (file-config-map)
        if client_config_file and os.path.exists(client_config_file):
            behavioral_rules = load_behavioral_rules(client_config_file)
        # Second, try global behavioral rules file
        elif getattr(app_config, "BEHAVIORAL_RULES_FILE", None):
            behavioral_rules = load_behavioral_rules(app_config.BEHAVIORAL_RULES_FILE)
        else:
            # Fall back to inline behavioral rules from config
            behavioral_rules = getattr(app_config, "BEHAVIORAL_RULES", [])
    if behavioral_rules:
        print(f"🧠 Evaluating {len(behavioral_rules)} behavioral rules...")
        behavioral_anomalies = evaluate_behavioral_rules(df, behavioral_rules)
        
        print(f"📊 Found {len(behavioral_anomalies)} behavioral anomalies")

        if behavioral_anomalies:
            for anomaly in behavioral_anomalies:
                matched = anomaly.get("matched_indices", []) or []
                rule_name = anomaly.get("rule", "Unknown")
                reason = anomaly.get("reason", "Behavioral rule triggered")
                
                print(f"🔧 Applying behavioral rule '{rule_name}' to {len(matched)} log entries")
                
                for idx in matched:
                    if idx in df.index:
                        # Mark as behavioral anomaly
                        df.loc[idx, "is_behavioral"] = True
                        df.loc[idx, "behavioral_rule"] = rule_name
                        df.loc[idx, "is_anomaly"] = 1
                        df.loc[idx, "anomaly_source"] = "Behavioral"
                        
                        # Set classification and reason if not already set
                        if "classification" not in df.columns or pd.isna(df.loc[idx, "classification"]):
                            df.loc[idx, "classification"] = "Behavioral Anomaly"
                        
                        # if "reason" not in df.columns or not df.loc[idx].get("reason"):
                        if "reason" not in df.columns or pd.isna(df.loc[idx, "reason"]):

                            df.loc[idx, "reason"] = reason
                        
                        # Set tag
                        tag_str = rule_name.lower().replace(" ", "_")
                        if "tag" not in df.columns or not isinstance(df.loc[idx, "tag"], list):
                            df.loc[idx, "tag"] = ["behavioral_" + tag_str]
                        else:
                            df.loc[idx, "tag"].append("behavioral_" + tag_str)


    # Create final anomalies dataframe by combining all types
    anomaly_sources = []

    # 1. Rule-based anomalies
    if "is_rule_based" in df.columns:
        rule_based_anomalies = df[df["is_rule_based"] == True]
        if not rule_based_anomalies.empty:
            anomaly_sources.append(rule_based_anomalies)

    # 2. LLM/Statistical anomalies (only when not in prepare phase)
    llm_phase = getattr(app_config, "LLM_PHASE", "full")
    if llm_phase != "prepare" and not anomalies_df.empty:
        llm_anomalies = anomalies_df[anomalies_df["is_anomaly"] == 1]
        if not llm_anomalies.empty:
            anomaly_sources.append(llm_anomalies)

    # 3. Behavioral anomalies 
    if "is_behavioral" in df.columns:
        behavioral_anomalies = df[df["is_behavioral"] == True].copy() 
        print(f"📊 Found {len(behavioral_anomalies)} behavioral anomalies to include in final output")
        if not behavioral_anomalies.empty:
            # Ensure behavioral anomalies have required columns
            for col in ['classification', 'reason', 'tag']:
                if col not in behavioral_anomalies.columns:
                    behavioral_anomalies[col] = None
            if 'anomaly_source' not in behavioral_anomalies.columns:
                behavioral_anomalies['anomaly_source'] = 'Behavioral'
            
            # Ensure is_anomaly is set to 1 for behavioral anomalies
            behavioral_anomalies['is_anomaly'] = 1  # ← Added this line

            # Convert timestamp to string to avoid JSON serialization issues
        if "timestamp" in behavioral_anomalies.columns:
            behavioral_anomalies["timestamp"] = pd.to_datetime(
                behavioral_anomalies["timestamp"], errors='coerce'
            ).dt.strftime('%Y-%m-%d %H:%M:%S.%f').str.slice(0, 23)
            
            anomaly_sources.append(behavioral_anomalies)

    # Combine all anomaly types
    if anomaly_sources:
        final_anomalies_df = pd.concat(anomaly_sources, ignore_index=True)
    else:
        final_anomalies_df = pd.DataFrame()

    print(f"🎯 Final anomalies breakdown:")
    print(f"   - Rule-based: {len(rule_based_anomalies) if 'rule_based_anomalies' in locals() else 0}")
    print(f"   - LLM/Statistical: {len(llm_anomalies) if 'llm_anomalies' in locals() else 0}")
    print(f"   - Behavioral: {len(behavioral_anomalies) if 'behavioral_anomalies' in locals() else 0}")


    out_file = os.path.join(app_config.RESULTS_FOLDER, f"{os.path.splitext(filename)[0]}_anomalies.jsonl")
    
    def clean_json_value(value):
        """Convert non-serializable values to JSON-serializable ones."""
        if pd.isna(value) or value in ('NaN', 'None', 'nan', None):
            return None
        try:
            # Handle numpy types and other non-serializable values
            if hasattr(value, 'item') and not isinstance(value, (str, bytes)):
                return value.item()
            return value
        except (TypeError, ValueError):
            return str(value)
    
    with open(out_file, "w") as f:
        for _, row in final_anomalies_df.iterrows():
            try:
                # Get basic record data
                record = row.to_dict()
                
                # Add record_id
                timestamp = str(record.get("timestamp", "")).strip()

                if timestamp:
                # Replace 'T' with space if it exists
                    timestamp = timestamp.replace("T", " ")
                    
                    # Ensure milliseconds only (3 digits)
                    if '.' in timestamp:
                        # Keep exactly 3 digits for milliseconds
                        ts_main, ts_fraction = timestamp.split('.')
                        timestamp = f"{ts_main}.{ts_fraction[:3]}"
                    else:
                        # If no fractional seconds, add .000
                        timestamp = f"{timestamp}.000"

                record["timestamp"] = timestamp
                log_content = str(record.get("log", "")).strip()
                log_hash = str(hash(log_content))[-8:]
                record["record_id"] = f"{timestamp}_{log_hash}"
                
                # Clean all values in the record
                clean_record = {}
                for key, value in record.items():
                    if isinstance(value, (list, tuple)):
                        clean_record[key] = [clean_json_value(v) for v in value]
                    elif isinstance(value, dict):
                        clean_record[key] = {k: clean_json_value(v) for k, v in value.items()}
                    else:
                        clean_record[key] = clean_json_value(value)
                
                # Write as a single line of JSON
                json_line = json.dumps(
                    clean_record,
                    ensure_ascii=False,
                    default=str,
                    separators=(',', ':')
                )
                f.write(json_line + "\n")
                
            except Exception as e:
                print(f"⚠️ Error processing record: {e}")
                continue

    print(f"✅ Saved anomalies to {out_file} ({len(final_anomalies_df)} anomalies)")

    severity_summary = summarize_log_levels(df)
    tag_summary = summarize_tags(final_anomalies_df)

    # Calculate time-based metrics if timestamp is available
    time_metrics = {"available": False}
    if "timestamp" in df.columns and len(df) > 0:
        try:
            # Convert to datetime if not already
            if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
                df = df.copy()  # Create a copy to avoid SettingWithCopyWarning
                df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", errors="coerce")
                
            # Filter out invalid timestamps
            valid_times = df[pd.notna(df["timestamp"])].copy()  # Create a copy to avoid SettingWithCopyWarning
            
            if len(valid_times) > 0:
                # Calculate time span and log rate
                start_time = valid_times["timestamp"].min()
                end_time = valid_times["timestamp"].max()
                time_span_seconds = (end_time - start_time).total_seconds()
                
                if time_span_seconds > 0:
                    logs_per_second = len(valid_times) / time_span_seconds
                    logs_per_minute = logs_per_second * 60
                    logs_per_hour = logs_per_minute * 60
                    
                    # Find peak log rate (logs per minute in the busiest minute)
                    valid_times.loc[:, "minute"] = valid_times["timestamp"].dt.floor("min")  # Use .loc to avoid SettingWithCopyWarning
                    logs_per_min = valid_times.groupby("minute").size()
                    peak_rate = logs_per_min.max() if not logs_per_min.empty else 0
                    
                    # Calculate error rate over time
                    error_logs = valid_times[valid_times["log"].str.contains("error|exception|fail", case=False, regex=True)]
                    error_rate = len(error_logs) / len(valid_times) if len(valid_times) > 0 else 0
                    
                    time_metrics = {
                        "available": True,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "time_span_seconds": round(time_span_seconds, 2),
                        "logs_per_second": round(logs_per_second, 2),
                        "logs_per_minute": round(logs_per_minute, 2),
                        "logs_per_hour": round(logs_per_hour, 2),
                        "peak_rate_per_minute": int(peak_rate),
                        "error_rate": round(error_rate, 4)
                    }
        except Exception as e:
            print(f"⚠️ Could not calculate time metrics: {str(e)}")
            time_metrics = {"available": False, "error": str(e)}

    # Calculate component metrics
    component_metrics = {"available": False}
    try:
        # Extract components from log lines (assuming format like [COMPONENT] or component: )
        component_pattern = r'\[([^\]]+)\]|(\w+):'
        components = []
        
        for log in df["log"]:
            matches = re.findall(component_pattern, log)
            for match in matches:
                component = match[0] if match[0] else match[1]
                if component and len(component) < 30:  # Avoid false positives
                    components.append(component)
        
        if components:
            component_counts = Counter(components)
            top_components = component_counts.most_common(5)
            
            component_metrics = {
                "available": True,
                "unique_components": len(component_counts),
                "top_components": [{"name": comp, "count": count} for comp, count in top_components]
            }
    except Exception as e:
        print(f"⚠️ Could not calculate component metrics: {str(e)}")
        component_metrics = {"available": False, "error": str(e)}

    leak_summary = {
        "leak_count": len(security_leaks),
        "examples": [leak["log"] for leak in security_leaks[:3]]
    }

    # Calculate SIEM-specific metrics
    # critical_anomalies = len(final_anomalies_df[final_anomalies_df["is_anomaly"] == 1])
    if "is_anomaly" in final_anomalies_df.columns:
        critical_anomalies = len(final_anomalies_df[final_anomalies_df["is_anomaly"] == 1])
    else:
        critical_anomalies = 0

    security_incidents = len(security_leaks) + int(rule_based_count)
    
    # Risk assessment
    risk_level = "LOW"
    if security_incidents > 5 or critical_anomalies > 10:
        risk_level = "HIGH"
    elif security_incidents > 2 or critical_anomalies > 5:
        risk_level = "MEDIUM"
    
    # Threat indicators
    threat_indicators = []
    if flood_detected:
        threat_indicators.append("LOG_FLOODING")
    if len(security_leaks) > 0:
        threat_indicators.append("DATA_EXPOSURE")
    if rule_based_count > 0:
        threat_indicators.append("RULE_VIOLATIONS")
    if time_metrics.get("error_rate", 0) > 0.1:
        threat_indicators.append("HIGH_ERROR_RATE")
    
    summary = {
        # === SIEM EXECUTIVE SUMMARY ===
        "siem_report": {
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            "source_file": filename,
            "risk_level": risk_level,
            "security_incidents": security_incidents,
            "critical_anomalies": critical_anomalies,
            "threat_indicators": threat_indicators,
            "analysis_period": {
                "start_time": time_metrics.get("start_time", "Unknown"),
                "end_time": time_metrics.get("end_time", "Unknown"),
                "duration_hours": round(time_metrics.get("time_span_seconds", 0) / 3600, 2)
            }
        },
        
        # === SECURITY ANALYSIS ===
        "security_assessment": {
            "data_exposure_incidents": {
                "count": len(security_leaks),
                "examples": [leak["log"] for leak in security_leaks[:3]],
                "types_detected": list(set([leak.get("type", "Unknown") for leak in security_leaks]))
            },
            "rule_based_violations": {
                "count": int(rule_based_count),
                "severity": "HIGH" if rule_based_count > 3 else "MEDIUM" if rule_based_count > 0 else "LOW"
            },
            "anomalous_behavior": {
                "statistical_anomalies": critical_anomalies,
                "ai_verified_threats": len(final_anomalies_df[
                    (final_anomalies_df["is_anomaly"] == 1) & 
                    (final_anomalies_df["classification"] == "Anomaly")
                ]) if "classification" in final_anomalies_df.columns else 0,
                "false_positives_filtered": skipped_non_anomalies
            }
        },
        
        # === OPERATIONAL INTELLIGENCE ===
        "operational_metrics": {
            "log_volume": {
                "total_events": original_count,
                "processed_events": len(df),
                "events_per_hour": round(time_metrics.get("logs_per_hour", 0), 2),
                "peak_rate_per_minute": time_metrics.get("peak_rate_per_minute", 0)
            },
            "system_health": {
                "error_rate": round(time_metrics.get("error_rate", 0) * 100, 2),
                "warning_count": severity_summary.get("warn", 0),
                "error_count": severity_summary.get("error", 0),
                "flood_detection": {
                    "detected": flood_detected,
                    "affected_templates": len(flood_templates)
                }
            },
            "component_analysis": component_metrics
        },
        
        # === TECHNICAL DETAILS ===
        "technical_analysis": {
            "template_diversity": template_diversity,
            "top_log_patterns": volume_stats,
            "ai_analysis": {
                "llm_classification_enabled": llm_classification_done,
                "total_llm_calls": llm_stats.get("total_calls", 0),
                "average_response_time": round(llm_stats.get("total_time", 0) / max(llm_stats.get("total_calls", 1), 1), 2),
                "classification_errors": llm_stats.get("errors", 0)
            }
        },
        
        # === OUTPUTS ===
        "report_outputs": {
            "anomaly_details_file": out_file,
            "processing_limits": {
                "max_logs_analyzed": app_config.MAX_LOG_LINES,
                "compliance_mode": app_config.MAX_LOG_LINES is not None
            }
        }
    }

    summary_file = os.path.join(app_config.RESULTS_FOLDER, f"{os.path.splitext(filename)[0]}_summary.jsonl")
    with open(summary_file, "w", encoding="utf-8") as f:
        # Write the summary as a single line in JSONL format
        json.dump(summary, f, ensure_ascii=False)
        f.write('\n')  # Add newline for JSONL format
    print(f"📄 Summary saved to {summary_file}")


def process_all_files():
    llm_phase = getattr(app_config, "LLM_PHASE", "full")
    print(f"🚀 Starting log anomaly processing (LLM phase={llm_phase})")
    
        # 🔹 LLM-only mode: operate on saved candidates, ignore raw logs
    if llm_phase == "classify":
        results_folder = app_config.RESULTS_FOLDER

        if not os.path.exists(results_folder):
            print(f"⚠️ Results folder not found: {results_folder}")
            return

        candidates_files = [
            os.path.join(results_folder, f)
            for f in os.listdir(results_folder)
            if f.endswith("_llm_candidates.jsonl")
        ]

        if not candidates_files:
            print(f"⚠️ No *_llm_candidates.jsonl files found in {results_folder}")
            return

        print(f"🤖 Found {len(candidates_files)} candidate files for LLM classification")
        for path in tqdm(candidates_files, desc="LLM-only classification"):
            run_llm_only_on_candidates(path)

        print("✅ LLM-only phase complete.")
        return

    # 🔹 Otherwise: existing behavior (full / prepare)
    
    input_folder = app_config.INPUT_FOLDER

    if not os.path.exists(input_folder):
        print(f"⚠️ Input folder not found: {input_folder}")
        return

    supported_extensions = (".json", ".log", ".txt")
    files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.endswith(supported_extensions)]

    if not files:
        print(f"⚠️ No supported log files (.json, .log, .txt) found in {input_folder}")
        return

    print(f"🔍 Found {len(files)} log files to process")
    for file in tqdm(files, desc="Processing Log Files"):
        process_file(file)

    print(f"✅ Completed. Results saved in → {app_config.RESULTS_FOLDER}")


def run_llm_only_on_candidates(candidates_file: str):
    """
    LLM-only stage: load previously saved candidates, classify with LLM, and write result file.
    """
    print(f"🔎 LLM-only classification for {candidates_file}")
    df_candidates = pd.read_json(candidates_file, lines=True)

    if df_candidates.empty:
        print("⚠️ No candidates in file, skipping.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    classifications, reasons, cleaned_logs, tags_list, llm_stats = loop.run_until_complete(
        classify_anomalies(df_candidates)
    )

    df_candidates["classification"] = classifications
    df_candidates["reason"] = reasons
    df_candidates["tag"] = tags_list
    df_candidates["cleaned_log"] = cleaned_logs
    df_candidates["is_llm_anomaly"] = True
    df_candidates["anomaly_source"] = "LLM"
    df_candidates["is_anomaly"] = 1

    out_file = candidates_file.replace("_llm_candidates", "_llm_results")
    df_candidates.to_json(out_file, orient="records", lines=True, force_ascii=False)

    print(f"✅ Saved LLM classification results to {out_file}")
    print(f"📊 LLM stats: {llm_stats}")
    
     # 🧹 Always delete the candidates file after successful classify
    try:
        os.remove(candidates_file)
        print(f"🧹 Deleted LLM candidate file: {candidates_file}")
    except OSError as e:
        print(f"⚠️ Could not delete candidates file {candidates_file}: {e}")