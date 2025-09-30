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
    tag_label, summarize_log_levels, is_non_anomalous,
    find_security_leaks, summarize_tags, rule_based_classification,
    redact_security_leaks, load_custom_patterns
)
from loganomaly.pattern_miner import mine_templates
from loganomaly.detectors.anomaly_detector import detect_knn_anomalies as knn_detect
from loganomaly.detectors.lof_detector import detect_anomalies_lof
from loganomaly.detectors.rolling_window_detector import rolling_window_chunking
from loganomaly.llm_classifier import classify_anomalies, apply_dependent_anomaly_filter

# === Load dynamic patterns ===
custom_rule_patterns, custom_security_patterns = load_custom_patterns()


def load_logs(filepath):
    filename = os.path.basename(filepath)
    log_lines = []

    try:
        if filepath.endswith(".json"):
            with open(filepath, "r") as f:
                data = json.load(f)
                for record in data:
                    message = record.get("@message", {}).get("log", "").strip()
                    if message:
                        log_lines.append({
                            "timestamp": record.get("@timestamp", ""),
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
    context = df.iloc[start:end][["timestamp", "log"]].to_dict(orient="records")
    
    # Filter out malformed or incomplete log entries
    filtered_context = []
    for log_entry in context:
        log_text = log_entry.get("log", "").strip()
        timestamp = log_entry.get("timestamp", "").strip()
        
        # Skip entries that look like fragments or incomplete logs
        if (
            len(log_text) < 5 or  # Too short to be meaningful
            len(log_text.split()) < 2 or  # Single word entries (likely fragments)
            not timestamp or len(timestamp) < 3 or  # Missing or too short timestamps
            timestamp.startswith("(") or  # Parenthetical timestamps (fragments)
            timestamp.startswith("'") or  # Quote-prefixed timestamps (fragments)
            timestamp.startswith("+") or  # Command prefixes
            not any(c.isdigit() for c in timestamp) or  # No digits in timestamp (likely not a real timestamp)
            log_text.startswith("'") and log_text.endswith("'") and len(log_text) < 50 or  # Short quoted fragments
            log_text.count("/") > 3 and len(log_text) < 100 or  # Path fragments
            "..." in log_text or  # Truncated content
            log_text.startswith("(") and log_text.endswith(")") and len(log_text) < 100  # Parenthetical fragments
        ):
            continue
            
        filtered_context.append(log_entry)
    
    return filtered_context


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
    else:
        row["is_rule_based"] = False
    return row


def process_file(filepath):
    filename = os.path.basename(filepath)
    print(f"\n🔍 Processing {filename}")

    df, original_count = load_logs(filepath)
    if df is None or len(df) == 0:
        return

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
        df = detect_anomalies_lof(df, app_config.TOP_PERCENT)

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

            if not anomalies_df.empty:
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

                # Ensure classifications are properly saved
                anomalies_df["classification"] = classifications
                anomalies_df["reason"] = reasons
                anomalies_df["tag"] = tags_list
                anomalies_df["cleaned_log"] = cleaned_logs
                anomalies_df["is_llm_anomaly"] = True
                anomalies_df["anomaly_source"] = "LLM"

                if app_config.ENABLE_DEPENDENT_ANOMALY_FILTER:
                    anomalies_df = anomalies_df.apply(apply_dependent_anomaly_filter, axis=1)

                llm_classification_done = True
            else:
                llm_stats = {}
        else:
            llm_stats = {}

    # Remove logs that LLM classified as non-anomalous
    normal_indices = anomalies_df[anomalies_df["classification"].isin(["Routine", "Normal"])].index
    anomalies_df.loc[normal_indices, "is_anomaly"] = 0

    if not app_config.ENABLE_LLM:
        context_logs = []
        for idx in anomalies_df.index:
            context = get_context_logs(df, idx)
            context_logs.append(context)
        anomalies_df["context_logs"] = context_logs

    df["log"] = df["log"].apply(redact_security_leaks)

    final_anomalies_df = pd.concat([
        df[df["is_rule_based"] == True],
        anomalies_df[anomalies_df["is_anomaly"] == 1]  # Only include actual anomalies
    ], ignore_index=True)

    out_file = os.path.join(app_config.RESULTS_FOLDER, f"{os.path.splitext(filename)[0]}_anomalies.json")
    final_anomalies_df.to_json(out_file, orient="records", indent=2)
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

    summary = {
        "filename": filename,
        "original_log_count": original_count,
        "processed_log_count": len(df),
        "anomalies_detected": int(final_anomalies_df["is_anomaly"].sum()),
        "volume_stats": volume_stats,
        "log_flood_detected": flood_detected,
        "flood_templates": flood_templates,
        "anomaly_output": out_file,
        "llm_stats": llm_stats,
        "log_severity_summary": severity_summary,
        "tag_summary": tag_summary,
        "llm_classification_done": llm_classification_done,
        "rule_based_anomalies": int(rule_based_count),
        "skipped_known_non_anomalies": skipped_non_anomalies,
        "security_leak_summary": leak_summary,
        "template_diversity": template_diversity,
        "time_metrics": time_metrics,
        "component_metrics": component_metrics,
        "max_logs_limit": app_config.MAX_LOG_LINES
    }

    summary_file = os.path.join(app_config.RESULTS_FOLDER, f"{os.path.splitext(filename)[0]}_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"📄 Summary saved to {summary_file}")


def process_all_files():
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
