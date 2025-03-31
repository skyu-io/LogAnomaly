import streamlit as st
import os
import json
import pandas as pd

SUMMARY_FOLDER = "results"

def load_summary(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def load_anomalies(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def show_summary(summary):
    st.subheader(f"📄 Summary: {summary['filename']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Original Logs", summary["original_log_count"])
    col2.metric("Processed Logs", summary["processed_log_count"])
    col3.metric("Anomalies", summary["anomalies_detected"])

    col4, col5, col6 = st.columns(3)
    col4.metric("Rule-based Anomalies", summary["rule_based_anomalies"])
    col5.metric("Security Leaks", summary["security_leak_summary"]["leak_count"])
    col6.metric("Log Flood Detected", str(summary["log_flood_detected"]))

    st.write("### 🔥 Volume Stats")
    st.json(summary["volume_stats"])

    if summary["log_flood_detected"]:
        st.write("### 🚨 Flooding Templates")
        st.json(summary["flood_templates"])

    st.write("### 🏷️ Tag Summary")
    st.json(summary.get("tag_summary", {}))

    st.write("### 📊 Log Level Summary")
    st.json(summary.get("log_severity_summary", {}))

    if summary["security_leak_summary"]["leak_count"] > 0:
        st.write("### 🔐 Security Leak Examples")
        st.code("\n".join(summary["security_leak_summary"]["examples"]))

    st.download_button(
        label="⬇️ Download Full Summary",
        data=json.dumps(summary, indent=2),
        file_name=f"{summary['filename']}_summary.json",
        mime="application/json"
    )

def show_anomalies(anomalies):
    st.write("## 🚨 Anomaly Logs")

    df = pd.DataFrame(anomalies)
    st.write(f"Total Anomalies: {len(df)}")

    filter_text = st.text_input("🔍 Filter anomalies (search text):")
    if filter_text:
        df = df[df["log"].str.contains(filter_text, case=False, na=False)]

    st.dataframe(df[["timestamp", "classification", "reason", "tag", "log"]])

    st.download_button(
        label="⬇️ Download Anomalies JSON",
        data=json.dumps(anomalies, indent=2),
        file_name="anomalies.json",
        mime="application/json"
    )


def main():
    st.title("🧩 Log Audit Summary Dashboard")

    summary_files = [f for f in os.listdir(SUMMARY_FOLDER) if f.endswith("_summary.json")]
    selected_file = st.selectbox("Select Summary File", summary_files)

    if selected_file:
        summary = load_summary(os.path.join(SUMMARY_FOLDER, selected_file))
        show_summary(summary)

        # === Load Anomalies
        anomalies_file = summary["anomaly_output"]
        if os.path.exists(anomalies_file):
            anomalies = load_anomalies(anomalies_file)
            show_anomalies(anomalies)
        else:
            st.warning("No anomalies file found.")


if __name__ == "__main__":
    main()
