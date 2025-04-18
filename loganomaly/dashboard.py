import streamlit as st
import os
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

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

    # Template Diversity Metrics
    if "template_diversity" in summary:
        st.write("### 📊 Template Diversity")
        diversity = summary["template_diversity"]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Unique Templates", diversity["unique_templates"])
        col2.metric("Template Entropy", diversity["template_entropy"])
        col3.metric("Top Template Ratio", f"{diversity['top_template_ratio']:.1%}")
        
        st.write("*Higher entropy means more diverse logs. Top template ratio shows how dominant the most common template is.*")

    # Volume Stats
    st.write("### 🔥 Volume Stats")
    if summary["volume_stats"]:
        volume_df = pd.DataFrame(summary["volume_stats"])
        
        # Create a bar chart for volume stats
        if not volume_df.empty:
            fig = px.bar(volume_df, x="template", y="count", 
                         hover_data=["ratio"], 
                         title="Top Log Templates by Count",
                         labels={"template": "Log Template", "count": "Count", "ratio": "Ratio"})
            st.plotly_chart(fig)
        
        st.json(summary["volume_stats"])
    else:
        st.info("No volume stats available.")

    # Time-based Metrics
    if "time_metrics" in summary and summary["time_metrics"]["available"]:
        st.write("### ⏱️ Time-based Metrics")
        
        time_metrics = summary["time_metrics"]
        
        col1, col2 = st.columns(2)
        col1.metric("Logs per Second", f"{time_metrics['logs_per_second']:.2f}")
        col2.metric("Peak Rate (logs/min)", time_metrics['peak_rate_per_minute'])
        
        col3, col4 = st.columns(2)
        col3.metric("Time Span", f"{time_metrics['time_span_seconds'] / 3600:.2f} hours")
        col4.metric("Error Rate", f"{time_metrics['error_rate']:.2%}")
        
        st.write(f"*Log period: {time_metrics['start_time']} to {time_metrics['end_time']}*")

    # Component Analysis
    if "component_metrics" in summary and summary["component_metrics"]["available"]:
        st.write("### 🧩 Component Analysis")
        
        components = summary["component_metrics"]
        st.write(f"Unique Components: {components['unique_components']}")
        
        if components["top_components"]:
            comp_df = pd.DataFrame(components["top_components"])
            
            # Create a pie chart for component distribution
            fig = px.pie(comp_df, values="count", names="name", 
                         title="Top Components by Log Count")
            st.plotly_chart(fig)

    if summary["log_flood_detected"]:
        st.write("### 🚨 Flooding Templates")
        st.json(summary["flood_templates"])

    st.write("### 🏷️ Tag Summary")
    tag_summary = summary.get("tag_summary", {})
    st.json(tag_summary)
    
    # Create a bar chart for tags if available
    if tag_summary:
        tag_df = pd.DataFrame([(k, v) for k, v in tag_summary.items()], 
                              columns=["Tag", "Count"])
        tag_df = tag_df.sort_values("Count", ascending=False)
        
        fig = px.bar(tag_df, x="Tag", y="Count", 
                     title="Anomaly Tags Distribution")
        st.plotly_chart(fig)

    st.write("### 📊 Log Level Summary")
    severity = summary.get("log_severity_summary", {})
    st.json(severity)
    
    # Create a pie chart for severity levels
    if severity:
        severity_df = pd.DataFrame([(k.upper(), v) for k, v in severity.items()], 
                                  columns=["Level", "Count"])
        
        fig = px.pie(severity_df, values="Count", names="Level", 
                     title="Log Severity Distribution",
                     color_discrete_map={
                         'ERROR': 'red',
                         'WARN': 'orange',
                         'INFO': 'blue',
                         'DEBUG': 'green'
                     })
        st.plotly_chart(fig)

    if summary["security_leak_summary"]["leak_count"] > 0:
        st.write("### 🔐 Security Leak Examples")
        st.code("\n".join(summary["security_leak_summary"]["examples"]))

    # LLM Stats
    if "llm_stats" in summary and summary["llm_stats"]:
        st.write("### 🤖 LLM Usage Stats")
        llm_stats = summary["llm_stats"]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Calls", llm_stats.get("total_calls", 0))
        col2.metric("Avg Time (s)", f"{llm_stats.get('total_time', 0) / max(llm_stats.get('total_calls', 1), 1):.2f}")
        col3.metric("Errors", llm_stats.get("errors", 0))

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

    # Add classification filter
    if "classification" in df.columns:
        classifications = ["All"] + sorted(df["classification"].unique().tolist())
        selected_class = st.selectbox("Filter by classification:", classifications)
        
        if selected_class != "All":
            df = df[df["classification"] == selected_class]

    st.dataframe(df[["timestamp", "classification", "reason", "tag", "log"]])

    st.download_button(
        label="⬇️ Download Anomalies JSON",
        data=json.dumps(anomalies, indent=2),
        file_name="anomalies.json",
        mime="application/json"
    )


def main():
    st.set_page_config(
        page_title="Log Audit Dashboard",
        page_icon="🧩",
        layout="wide"
    )
    
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
