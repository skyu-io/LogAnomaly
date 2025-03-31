import os
import json
import pandas as pd
import asyncio
from tqdm import tqdm
from collections import Counter

from loganomaly import config as app_config
from loganomaly.utils import (
    tag_label, summarize_log_levels, is_non_anomalous,
    find_security_leaks, summarize_tags, rule_based_classification,
    redact_security_leaks, load_custom_patterns
)
from loganomaly.pattern_miner import mine_templates
from loganomaly.anomaly_detector import detect_anomalies
from loganomaly.llm_classifier import classify_anomalies, apply_dependent_anomaly_filter

# === Load dynamic patterns from config ===
custom_rule_patterns, custom_security_patterns = load_custom_patterns()

def load_logs(filepath):
    filename = os.path.basename(filepath)
    log_lines = []
    with open(filepath, "r") as f:
        try:
            data = json.load(f)
            for record in data:
                message = record.get("@message", {}).get("log", "").strip()
                if message:
                    log_lines.append({
                        "timestamp": record.get("@timestamp", ""),
                        "log": message,
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
    return context


def apply_rule_based_classification(row):
    result = rule_based_classification(row["log"], custom_rule_patterns)
    if result:
        label, reason, tags = result
        row["classification"] = label
        row["reason"] = reason
        row["tag"] = tags
        row["is_rule_based"] = True
        row["is_anomaly"] = 1
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
    volume_stats, flood_detected, flood_templates = detect_volume_anomalies(df)
    df = detect_anomalies(df, app_config.TOP_PERCENT)

    df = df.apply(apply_rule_based_classification, axis=1)
    rule_based_count = df["is_rule_based"].sum()

    max_score = df["anomaly_score"].max()
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

                anomalies_df["classification"] = classifications
                anomalies_df["reason"] = reasons
                anomalies_df["tag"] = tags_list
                anomalies_df["cleaned_log"] = cleaned_logs
                anomalies_df["is_llm_anomaly"] = True

                if app_config.ENABLE_DEPENDENT_ANOMALY_FILTER:
                    anomalies_df = anomalies_df.apply(apply_dependent_anomaly_filter, axis=1)

                llm_classification_done = True
            else:
                llm_stats = {}
        else:
            llm_stats = {}

    routine_indices = anomalies_df[anomalies_df["classification"] == "Routine"].index
    anomalies_df.loc[routine_indices, "is_anomaly"] = 0

    if not app_config.ENABLE_LLM:
        context_logs = []
        for idx in anomalies_df.index:
            context = get_context_logs(df, idx)
            context_logs.append(context)
        anomalies_df["context_logs"] = context_logs

    df["log"] = df["log"].apply(redact_security_leaks)

    final_anomalies_df = pd.concat([
        df[df["is_rule_based"] == True],
        anomalies_df
    ], ignore_index=True)

    out_file = os.path.join(app_config.RESULTS_FOLDER, f"{os.path.splitext(filename)[0]}_anomalies.json")
    final_anomalies_df.to_json(out_file, orient="records", indent=2)
    print(f"✅ Saved anomalies to {out_file} ({len(final_anomalies_df)} anomalies)")

    severity_summary = summarize_log_levels(df)
    tag_summary = summarize_tags(final_anomalies_df)

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

    files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.endswith(".json")]
    if not files:
        print(f"⚠️ No JSON log files found in {input_folder}")
        return

    for file in tqdm(files, desc="Processing Log Files"):
        process_file(file)
