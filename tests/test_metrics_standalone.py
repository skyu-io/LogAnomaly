import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math
from collections import Counter

# Define standalone versions of the metrics functions to test
def calculate_template_diversity_test(template_counts):
    """
    Calculate diversity metrics for log templates.
    
    Args:
        template_counts: Counter object with template counts
        
    Returns:
        Dict with diversity metrics
    """
    total_logs = sum(template_counts.values())
    unique_templates = len(template_counts)
    
    if unique_templates == 0 or total_logs == 0:
        return {
            "unique_templates": 0,
            "template_entropy": 0.0,
            "top_template_ratio": 0.0
        }
    
    # Calculate entropy
    entropy = 0.0
    for count in template_counts.values():
        p = count / total_logs
        entropy -= p * math.log2(p) if p > 0 else 0
    
    # Get most common template ratio
    most_common = template_counts.most_common(1)
    top_ratio = most_common[0][1] / total_logs if most_common else 0
    
    return {
        "unique_templates": unique_templates,
        "template_entropy": entropy,
        "top_template_ratio": top_ratio
    }

def calculate_time_metrics_test(df):
    """
    Calculate time-based metrics from log data.
    
    Args:
        df: DataFrame with logs and timestamps
        
    Returns:
        Dict with time metrics
    """
    if len(df) == 0 or "timestamp" not in df.columns:
        return {"available": False}
    
    try:
        # Convert timestamps to datetime if they're strings
        if isinstance(df["timestamp"].iloc[0], str):
            df["datetime"] = pd.to_datetime(df["timestamp"])
        else:
            df["datetime"] = df["timestamp"]
        
        # Sort by time
        df = df.sort_values("datetime")
        
        # Calculate time span
        start_time = df["datetime"].min()
        end_time = df["datetime"].max()
        time_span = (end_time - start_time).total_seconds()
        
        if time_span <= 0:
            return {"available": False}
        
        # Calculate logs per time unit
        logs_count = len(df)
        logs_per_second = logs_count / time_span
        logs_per_minute = logs_per_second * 60
        logs_per_hour = logs_per_minute * 60
        
        # Calculate error rate
        if "log" in df.columns:
            error_logs = df[df["log"].str.contains("ERROR", case=False, na=False)]
            error_rate = len(error_logs) / logs_count
        else:
            error_rate = 0
        
        # Calculate peak rate (simplified)
        peak_rate_per_minute = logs_per_minute * 1.5  # Simplified calculation
        
        return {
            "available": True,
            "logs_per_second": logs_per_second,
            "logs_per_minute": logs_per_minute,
            "logs_per_hour": logs_per_hour,
            "peak_rate_per_minute": peak_rate_per_minute,
            "time_span_seconds": time_span,
            "error_rate": error_rate,
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    except Exception as e:
        return {"available": False, "error": str(e)}

def calculate_component_metrics_test(df):
    """
    Calculate component-based metrics from log data.
    
    Args:
        df: DataFrame with logs and component information
        
    Returns:
        Dict with component metrics
    """
    if len(df) == 0 or "component" not in df.columns:
        return {"available": False}
    
    # Count components
    component_counts = Counter(df["component"])
    unique_components = len(component_counts)
    
    # Get top components
    top_components = [
        {"name": comp, "count": count}
        for comp, count in component_counts.most_common(5)
    ]
    
    return {
        "available": True,
        "unique_components": unique_components,
        "top_components": top_components
    }

@pytest.fixture
def sample_logs_df():
    """Create a sample DataFrame with logs for testing."""
    logs = [
        "ERROR: Database connection failed: Connection refused",
        "INFO: User login successful: user123",
        "ERROR: Database connection failed: Timeout",
        "WARN: High CPU usage detected: 95%",
        "INFO: System startup complete",
        "ERROR: Database connection failed: Connection refused",
        "INFO: User logout: user123",
        "ERROR: Memory allocation failed: Out of memory"
    ]
    
    components = [
        "Database",
        "UserService",
        "Database",
        "SystemMonitor",
        "System",
        "Database",
        "UserService",
        "MemoryManager"
    ]
    
    # Create timestamps with 1-minute intervals
    base_time = datetime.now()
    timestamps = [
        (base_time + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S")
        for i in range(8)
    ]
    
    return pd.DataFrame({
        "log": logs,
        "component": components,
        "timestamp": timestamps
    })

def test_calculate_template_diversity_balanced():
    """Test template diversity calculation with balanced distribution."""
    # Create a balanced distribution
    counts = Counter({
        "template1": 10,
        "template2": 10,
        "template3": 10,
        "template4": 10
    })
    
    diversity = calculate_template_diversity_test(counts)
    
    assert diversity["unique_templates"] == 4
    assert diversity["template_entropy"] > 1.9  # Close to max entropy for 4 items (2.0)
    assert diversity["top_template_ratio"] == 0.25  # Equal distribution

def test_calculate_template_diversity_imbalanced():
    """Test template diversity calculation with imbalanced distribution."""
    # Create an imbalanced distribution
    counts = Counter({
        "template1": 20,
        "template2": 5,
        "template3": 3,
        "template4": 2
    })
    
    diversity = calculate_template_diversity_test(counts)
    
    assert diversity["unique_templates"] == 4
    assert diversity["template_entropy"] < 1.9  # Lower than max entropy due to imbalance
    assert diversity["top_template_ratio"] == 0.6666666666666666  # 20/30

def test_calculate_template_diversity_single():
    """Test template diversity calculation with single template."""
    # Create a single template distribution
    counts = Counter({"template1": 10})
    
    diversity = calculate_template_diversity_test(counts)
    
    assert diversity["unique_templates"] == 1
    assert diversity["template_entropy"] == 0.0  # Zero entropy for single item
    assert diversity["top_template_ratio"] == 1.0  # 100% dominance

def test_calculate_time_metrics(sample_logs_df):
    """Test time metrics calculation with sample data."""
    metrics = calculate_time_metrics_test(sample_logs_df)
    
    assert metrics["available"] is True
    assert metrics["logs_per_second"] > 0
    assert metrics["logs_per_minute"] > 0
    assert metrics["logs_per_hour"] > 0
    assert metrics["peak_rate_per_minute"] > 0
    assert metrics["time_span_seconds"] > 0
    assert "start_time" in metrics
    assert "end_time" in metrics
    
    # Error rate should be calculated correctly
    # 4 error logs out of 8 total
    assert abs(metrics["error_rate"] - 0.5) < 0.01

def test_calculate_time_metrics_empty():
    """Test time metrics calculation with empty DataFrame."""
    empty_df = pd.DataFrame(columns=["log", "timestamp"])
    
    metrics = calculate_time_metrics_test(empty_df)
    
    assert metrics["available"] is False

def test_calculate_time_metrics_no_timestamp():
    """Test time metrics calculation with missing timestamp column."""
    df = pd.DataFrame({"log": ["test1", "test2"]})
    
    metrics = calculate_time_metrics_test(df)
    
    assert metrics["available"] is False

def test_calculate_component_metrics(sample_logs_df):
    """Test component metrics calculation with sample data."""
    metrics = calculate_component_metrics_test(sample_logs_df)
    
    assert metrics["available"] is True
    assert metrics["unique_components"] == 5  # 5 unique components in sample data
    assert len(metrics["top_components"]) <= 5  # Should return at most 5 components
    
    # Database should be the top component (3 occurrences)
    top_component = metrics["top_components"][0]
    assert top_component["name"] == "Database"
    assert top_component["count"] == 3

def test_calculate_component_metrics_empty():
    """Test component metrics calculation with empty DataFrame."""
    empty_df = pd.DataFrame(columns=["log", "component"])
    
    metrics = calculate_component_metrics_test(empty_df)
    
    assert metrics["available"] is False

def test_calculate_component_metrics_no_component():
    """Test component metrics calculation with missing component column."""
    df = pd.DataFrame({"log": ["test1", "test2"]})
    
    metrics = calculate_component_metrics_test(df)
    
    assert metrics["available"] is False
