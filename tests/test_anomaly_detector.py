import pandas as pd
from loganomaly.anomaly_detector import detect_anomalies

def test_detect_anomalies():
    df = pd.DataFrame({
        "log": ["error log", "info log", "another error log"],
        "log_template": ["error", "info", "error"]
    })
    df = detect_anomalies(df, 0.5)
    assert "is_anomaly" in df.columns
    assert df["is_anomaly"].sum() > 0
