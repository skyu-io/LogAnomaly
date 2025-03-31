import pytest
from loganomaly.llm_classifier import apply_dependent_anomaly_filter

def test_apply_dependent_anomaly_filter():
    row = {
        "log": "at function call stack",
        "classification": "Unknown",
        "is_anomaly": 1
    }
    result = apply_dependent_anomaly_filter(row)
    assert result["classification"] == "Dependent Anomaly"
