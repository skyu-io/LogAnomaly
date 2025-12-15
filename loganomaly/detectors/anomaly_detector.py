import numpy as np
from sklearn.neighbors import NearestNeighbors

from loganomaly import config as app_config
from loganomaly.embedding_cache import get_embedding_model

# Optional FAISS for approximate nearest neighbors (CPU or GPU)
try:  # pragma: no cover - optional dependency
    import faiss  # type: ignore

    HAVE_FAISS = True
    # Check for GPU support
    HAVE_FAISS_GPU = faiss.get_num_gpus() > 0
    if HAVE_FAISS_GPU:
        print(f"🚀 FAISS GPU available: {faiss.get_num_gpus()} GPU(s) detected")
except Exception:  # pragma: no cover - optional dependency
    HAVE_FAISS = False
    HAVE_FAISS_GPU = False


def compute_embeddings(df, model_name=None):
    """
    Compute sentence embeddings for log lines.

    Args:
        df (pd.DataFrame): DataFrame with 'log' column.
        model_name (str): Sentence transformer model name.

    Returns:
        np.ndarray: Embedding vectors.
    """
    print("🔤 Computing embeddings...")
    model_name = model_name or getattr(
        app_config, "EMBEDDING_MODEL", "sentence-transformers/paraphrase-MiniLM-L6-v2"
    )
    model = get_embedding_model(model_name)
    embeddings = model.encode(df["log"].tolist(), show_progress_bar=True)
    return embeddings


def _faiss_mean_cosine_distance(embeddings: np.ndarray, k: int) -> np.ndarray:
    """
    Approximate KNN mean cosine distance using FAISS (CPU-only, HNSW).
    
    Args:
        embeddings (np.ndarray): Embedding vectors (float32).
        k (int): Number of nearest neighbors.
    
    Returns:
        np.ndarray: Mean cosine distance for each vector.
    """
    vecs = embeddings.astype("float32", copy=True)
    faiss.normalize_L2(vecs)

    d = vecs.shape[1]

    print("💻 Using FAISS CPU (HNSW) for neighbor search...")

    # HNSW index
    m = getattr(app_config, "FAISS_HNSW_M", 32)
    ef_search = getattr(app_config, "FAISS_EF_SEARCH", 64)

    index = faiss.IndexHNSWFlat(d, m, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efSearch = ef_search
    index.add(vecs)

    distances, _ = index.search(vecs, k)

    # Convert cosine similarity to distance
    cosine_distances = 1.0 - distances
    return cosine_distances.mean(axis=1)


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

    use_faiss = getattr(app_config, "USE_FAISS", False) and HAVE_FAISS

    if use_faiss:
        scores = _faiss_mean_cosine_distance(embeddings, adjusted_neighbors)
    else:
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
