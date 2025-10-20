import pytest
import numpy as np
import pandas as pd
from loganomaly.detectors import compute_lof_scores, mark_lof_anomalies
from sklearn.feature_extraction.text import TfidfVectorizer

@pytest.fixture
def sample_features():
    """Create sample feature vectors for testing."""
    # Create a simple 2D array of features
    return np.array([
        [1.0, 0.2, 0.3, 0.0],
        [1.1, 0.1, 0.2, 0.1],
        [0.9, 0.3, 0.3, 0.0],
        [1.0, 0.2, 0.2, 0.1],
        [5.0, 4.0, 3.0, 2.0],  # Outlier
    ])

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
    
    return pd.DataFrame({"log": logs})

@pytest.fixture
def sample_vectorizer(sample_logs_df):
    """Create a sample TF-IDF vectorizer."""
    vectorizer = TfidfVectorizer(max_features=10)
    vectorizer.fit(sample_logs_df["log"].tolist())
    return vectorizer

def test_compute_lof_scores(sample_features):
    """Test computing LOF scores from feature vectors."""
    negative_scores, lof_scores = compute_lof_scores(sample_features, n_neighbors=3)
    
    # Check that we got the right shapes
    assert len(negative_scores) == sample_features.shape[0]
    assert len(lof_scores) == sample_features.shape[0]
    
    # Check that scores are negative (LOF convention)
    assert all(score <= 0 for score in negative_scores)
    
    # Check that the outlier has a lower (more negative) score
    outlier_idx = 4  # The outlier is at index 4
    normal_indices = [0, 1, 2, 3]
    
    # The outlier should have a more negative score than the normal points
    assert negative_scores[outlier_idx] < np.mean(negative_scores[normal_indices])

def test_mark_lof_anomalies(sample_logs_df, sample_vectorizer):
    """Test marking LOF anomalies in a DataFrame."""
    # Apply the LOF detector
    result_df = mark_lof_anomalies(sample_logs_df, sample_vectorizer, threshold=-1.5)
    
    # Check that the result has the expected columns
    assert "lof_score" in result_df.columns
    assert "is_lof_anomaly" in result_df.columns
    
    # Check that all rows have LOF scores
    assert not result_df["lof_score"].isna().any()
    
    # Check that is_lof_anomaly is a boolean column
    assert result_df["is_lof_anomaly"].dtype == bool
    
    # Check that some anomalies were detected (at least one)
    # This is a probabilistic test, but with our sample data it should work
    assert result_df["is_lof_anomaly"].sum() > 0
