import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors


def compute_embeddings(df, model_name="sentence-transformers/paraphrase-MiniLM-L6-v2"):
    """
    Compute sentence embeddings for log lines.

    Args:
        df (pd.DataFrame): DataFrame with 'log' column.
        model_name (str): Sentence transformer model name.

    Returns:
        np.ndarray: Embedding vectors.
    """
    print("🔤 Computing embeddings...")
    model = SentenceTransformer(model_name)
    embeddings = model.encode(df["log"].tolist(), show_progress_bar=True)
    return embeddings


def detect_knn_anomalies(df, top_percent=0.05, n_neighbors=5):
    """
    Detect anomalies using KNN distance-based scoring.

    Args:
        df (pd.DataFrame): DataFrame with 'log' column.
        top_percent (float): Percentage of top anomalies.
        n_neighbors (int): Number of neighbors.

    Returns:
        pd.DataFrame: Updated DataFrame with 'anomaly_score' and 'is_anomaly'.
    """
    n_samples = len(df)
    
    # Validate minimum samples
    if n_samples < 2:
        print(f"⚠️ Insufficient samples ({n_samples}) for KNN detection. Skipping...")
        df["anomaly_score"] = 0.0
        df["is_anomaly"] = 0
        return df, None
    
    # Adjust n_neighbors to be at most n_samples - 1
    adjusted_neighbors = min(n_neighbors, n_samples - 1)
    if adjusted_neighbors < n_neighbors:
        print(f"⚠️ Adjusted n_neighbors from {n_neighbors} to {adjusted_neighbors} (n_samples={n_samples})")
    
    embeddings = compute_embeddings(df)
    print("📈 Calculating anomaly scores...")

    knn = NearestNeighbors(n_neighbors=adjusted_neighbors, metric="cosine", n_jobs=-1)
    knn.fit(embeddings)
    distances, _ = knn.kneighbors(embeddings)
    scores = distances.mean(axis=1)
    df["anomaly_score"] = scores

    top_n = int(top_percent * len(df)) or 1
    df = df.sort_values(by="anomaly_score", ascending=False).reset_index(drop=True)
    df["is_anomaly"] = 0
    df.loc[:top_n, "is_anomaly"] = 1

    return df, embeddings
