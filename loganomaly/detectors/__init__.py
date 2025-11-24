import numpy as np
from sklearn.neighbors import LocalOutlierFactor


def compute_lof_scores(features, n_neighbors=20):
    """
    Compute Local Outlier Factor scores.

    Args:
        features (np.ndarray): 2D array of vectorized log features.
        n_neighbors (int): Number of neighbors to use.

    Returns:
        np.ndarray: Negative LOF scores (-1 is normal, lower values more anomalous).
    """
    n_samples = features.shape[0]
    
    # Validate minimum samples
    if n_samples < 2:
        return np.zeros(n_samples), np.ones(n_samples, dtype=int)
    
    # Adjust n_neighbors to be at most n_samples - 1
    adjusted_neighbors = min(n_neighbors, n_samples - 1)
    
    lof = LocalOutlierFactor(n_neighbors=adjusted_neighbors, contamination='auto', n_jobs=-1)
    lof_scores = lof.fit_predict(features)
    negative_factor = lof.negative_outlier_factor_
    return negative_factor, lof_scores


def mark_lof_anomalies(df, vectorizer, threshold=-1.5):
    """
    Vectorize logs and mark LOF-based anomalies.

    Args:
        df (pd.DataFrame): DataFrame with 'log' column.
        vectorizer: Pre-trained sentence transformer or TF-IDF vectorizer.
        threshold (float): LOF score threshold.

    Returns:
        pd.DataFrame: Updated DataFrame with 'lof_score' and 'is_lof_anomaly'.
    """
    log_texts = df["log"].tolist()
    features = vectorizer.encode(log_texts) if hasattr(vectorizer, "encode") else vectorizer.transform(log_texts).toarray()

    negative_scores, _ = compute_lof_scores(features)
    df["lof_score"] = negative_scores
    df["is_lof_anomaly"] = df["lof_score"] <= threshold

    return df
