import pytest
from loganomaly.utils import rule_based_classification, clean_log_line, redact_security_leaks

def test_rule_based_classification():
    log = "Database connection error occurred"
    result = rule_based_classification(log)
    assert result is not None
    label, reason, tags = result
    assert label == "Operational Error"
    assert "Database" in tags

def test_clean_log_line():
    log = "2024-03-28T12:00:00Z User Token abcdef123456"
    cleaned = clean_log_line(log)
    assert "<SECRET>" in cleaned

def test_redact_security_leaks():
    log = "Authorization: Bearer abcdef123456"
    redacted = redact_security_leaks(log)
    assert "<REDACTED>" in redacted
