from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, Tuple, Optional


import requests
from prefect import get_run_logger  # keep if you’re running under Prefect

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# import your pure aggregation utils
# from siem_aggregate import aggregate_directory
# (If this handler lives in the same file, import locally instead.)

def aggregate_directory(
    summaries_dir: str | Path,
    pattern: str = "*_summary.json",
    top_k: int = 10,
) -> Dict:
    """
    Aggregates multiple summary JSON files into a single report structure.
    
    Args:
        summaries_dir: Directory containing summary files
        pattern: Glob pattern for summary files
        top_k: Top K threat indicators to include
        
    Returns:
        Dict with "aggregate" and "reports" keys
    """
    logger = get_run_logger()
    summaries_path = Path(summaries_dir).resolve()    # keep it absolute
    
    logger.info(f"Scanning for pattern '{pattern}' in: {summaries_path}")

    # Find all summary files
    summary_files = list(summaries_path.glob(pattern))
    logger.info(f"Found {len(summary_files)} summary files in {summaries_path}")
    
    if not summary_files:
        return {"aggregate": {
                    "total_reports": 0,
                    "total_security_incidents": 0,
                    "total_critical_anomalies": 0,
                    "max_risk": "LOW",
                    "top_threat_indicators": [],
                    "time_window": {}
                },
                "reports": []}

    # Load all summary data
    reports = []
    for summary_file in summary_files:
        try:
            with open(summary_file, 'r') as f:
                report_data = json.load(f)
                reports.append(report_data)
        except Exception as e:
            logger.warning(f"Failed to load {summary_file}: {e}")
    
    # Build aggregate statistics
    total_reports = len(reports)
    total_security_incidents = sum(r.get("siem_report", {}).get("security_incidents", 0) for r in reports)
    total_critical_anomalies = sum(r.get("siem_report", {}).get("critical_anomalies", 0) for r in reports)
    
    # Collect all threat indicators
    all_threat_indicators = []
    for r in reports:
        indicators = r.get("siem_report", {}).get("threat_indicators", [])
        all_threat_indicators.extend(indicators)
    
    # Count threat indicator frequencies
    from collections import Counter
    indicator_counts = Counter(all_threat_indicators)
    top_threat_indicators = [{"indicator": k, "count": v} for k, v in indicator_counts.most_common(top_k)]
    
    # Find max risk level
    risk_levels = [r.get("siem_report", {}).get("risk_level", "LOW") for r in reports]
    risk_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    max_risk = max(risk_levels, key=lambda r: risk_order.get(r, 0)) if risk_levels else "LOW"
    
    # Calculate time window
    all_start_times = []
    all_end_times = []
    for r in reports:
        period = r.get("siem_report", {}).get("analysis_period", {})
        start = period.get("start_time")
        end = period.get("end_time")
        if start:
            all_start_times.append(start)
        if end:
            all_end_times.append(end)
    
    time_window = {}
    if all_start_times:
        time_window["start"] = min(all_start_times)
    if all_end_times:
        time_window["end"] = max(all_end_times)
    
    # Build aggregate
    aggregate = {
        "total_reports": total_reports,
        "total_security_incidents": total_security_incidents,
        "total_critical_anomalies": total_critical_anomalies,
        "max_risk": max_risk,
        "top_threat_indicators": top_threat_indicators,
        "time_window": time_window,
    }
    
    return {
        "aggregate": aggregate,
        "reports": reports,
    }

def _compute_subject_and_preheader(payload: Dict) -> Dict[str, str]:
    """
    Returns {"subject": "...", "preheader": "..."} based on aggregate or single-report data.
    Matches the Handlebars logic you used in the template.
    """
    agg = payload.get("aggregate") or {}
    reports = payload.get("reports") or []

    # Fallback to single-report shape (if someone passes just one dict)
    first = reports[0] if reports else {}

    # SUBJECT
    if agg.get("total_reports"):
        risk = (agg.get("max_risk") or "LOW").upper()
        subject = f"[{risk}] SIEM Alert — {agg['total_reports']} reports"
    else:
        siem = first.get("siem_report") or {}
        risk = (siem.get("risk_level") or "LOW").upper()
        src = siem.get("source_file") or "unknown"
        subject = f"[{risk}] SIEM Alert — {src}"

    # PREHEADER
    if agg.get("time_window", {}).get("start") and agg.get("time_window", {}).get("end"):
        ph = f"Window: {agg['time_window']['start']} → {agg['time_window']['end']}"
    else:
        siem = first.get("siem_report") or {}
        ts = siem.get("analysis_timestamp")
        ph = f"Analysis: {ts}" if ts else "Automated SIEM notification"

    return {"subject": subject, "preheader": ph}


def build_template_data(
    *,
    summaries_dir: str | Path,
    pattern: str = "*_summary.json",
    top_k: int = 10,
    max_reports: Optional[int] = None,
) -> Dict:
    """
    Build the SendGrid template data from a directory of *_summary.json files.

    Args:
      summaries_dir: Directory containing summary files.
      pattern: Glob pattern (default '*_summary.json').
      top_k: Top N threat indicators in the aggregate.
      max_reports: If set, trim the reports array to this length (from newest by analysis_timestamp if possible).

    Returns:
      Dict matching your template: {"aggregate": {...}, "reports": [...]}
      Also includes computed "subject" and "preheader" at the top-level.
    """
    payload = aggregate_directory(summaries_dir, pattern=pattern, top_k=top_k)

    # Optionally trim reports (try to sort by analysis_timestamp desc when present)
    if max_reports is not None and isinstance(payload.get("reports"), list):
        def _ts(r: Dict) -> str:
            return (r.get("siem_report", {}).get("analysis_timestamp") or "")
        payload["reports"] = sorted(payload["reports"], key=_ts, reverse=True)[:max_reports]

    # Compute subject/preheader and attach for the template to consume (optional)
    meta = _compute_subject_and_preheader(payload)
    payload.update(meta)
    return payload


# def send_siem_alert_email(
#     *,
#     summaries_dir: str | Path,
#     pattern: str = "*_summary.json",
#     top_k: int = 10,
#     max_reports: Optional[int] = None,

# ) -> Tuple[int, str, Dict]:
#     """
#     High-level convenience handler:
#       1) aggregates *_summary.json files,
#       2) computes subject & preheader for your template,
#       3) sends the email via SKYU Notifications.

#     Returns (status_code, response_text, template_data_used).
#     If dry_run=True, returns (0, "DRY_RUN", template_data) and does not call the service.
#     """
#     logger = get_run_logger()
#     template_data = build_template_data(
#         summaries_dir=summaries_dir,
#         pattern=pattern,
#         top_k=top_k,
#         max_reports=max_reports,
#     )

#     # Optionally cap top_threat_indicators in the aggregate to keep emails short
#     agg = template_data.get("aggregate") or {}
#     if "top_threat_indicators" in agg and isinstance(agg["top_threat_indicators"], list):
#         agg["top_threat_indicators"] = agg["top_threat_indicators"][:top_k]
#         template_data["aggregate"] = agg

    
#     logger.info("[dry_run] would send SIEM email", extra={"template_data": template_data})
#     return template_data
