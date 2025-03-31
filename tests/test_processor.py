import os
import json
import shutil
import pytest
from loganomaly.processor import process_file
from loganomaly import config as app_config

SAMPLE_LOG_FILE = "tests/sample_logs/sample.json"
TEMP_RESULTS_FOLDER = "tests/test_results"

@pytest.fixture(scope="function")
def setup_and_cleanup():
    """Prepare test result folder and cleanup after test."""
    os.makedirs(TEMP_RESULTS_FOLDER, exist_ok=True)
    app_config.RESULTS_FOLDER = TEMP_RESULTS_FOLDER

    yield

    shutil.rmtree(TEMP_RESULTS_FOLDER)

@pytest.mark.functional
def test_process_sample_logs(setup_and_cleanup):
    process_file(SAMPLE_LOG_FILE)

    base_name = os.path.splitext(os.path.basename(SAMPLE_LOG_FILE))[0]
    anomalies_file = os.path.join(TEMP_RESULTS_FOLDER, f"{base_name}_anomalies.json")
    summary_file = os.path.join(TEMP_RESULTS_FOLDER, f"{base_name}_summary.json")

    # === Check files generated
    assert os.path.exists(anomalies_file), "❌ Anomalies file not generated"
    assert os.path.exists(summary_file), "❌ Summary file not generated"

    # === Validate Summary File
    with open(summary_file) as f:
        summary = json.load(f)

    assert summary.get("original_log_count") == 6, "❌ Incorrect original log count"
    assert "anomalies_detected" in summary, "❌ Anomalies count missing in summary"
    assert summary.get("log_flood_detected") in [True, False], "❌ Flood flag missing"

    # === Validate Anomalies File
    with open(anomalies_file) as f:
        anomalies = json.load(f)

    assert len(anomalies) > 0, "❌ No anomalies detected in sample log"

    for anomaly in anomalies:
        assert "log" in anomaly, "❌ Log field missing in anomaly"
        assert "classification" in anomaly, "❌ Classification missing in anomaly"
        assert "reason" in anomaly, "❌ Reason missing in anomaly"
        assert "tag" in anomaly, "❌ Tag missing in anomaly"
        assert "is_anomaly" in anomaly, "❌ is_anomaly flag missing"

