import pandas as pd
import logging
from sklearn.neighbors import LocalOutlierFactor

from loganomaly import config as app_config
from loganomaly.embedding_cache import get_embedding_model

# === Logger setup ===
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def compute_embeddings(df, model_name=None):
    if isinstance(df, tuple):
        logger.warning("Received tuple instead of DataFrame. Unpacking...")
        df = df[0] if isinstance(df[0], pd.DataFrame) else df[1]

    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected DataFrame, got {type(df)}")

    if "log" not in df.columns:
        raise KeyError("DataFrame missing required 'log' column")

    logger.info(f"🔤 Computing embeddings for {len(df)} log lines...")
    model_name = model_name or getattr(
        app_config, "EMBEDDING_MODEL", "sentence-transformers/paraphrase-MiniLM-L6-v2"
    )
    model = get_embedding_model(model_name)
    embeddings = model.encode(df["log"].tolist(), show_progress_bar=True)
    return embeddings


def detect_anomalies_lof(df, top_percent, n_neighbors=20, embeddings=None):
    logger.info("📈 Running LOF anomaly detection...")

    if isinstance(df, tuple):
        logger.warning("Received tuple instead of DataFrame. Unpacking...")
        df = df[0] if isinstance(df[0], pd.DataFrame) else df[1]

    n_samples = len(df)
    
    # Validate minimum samples
    if n_samples < 2:
        logger.warning(f"⚠️ Insufficient samples ({n_samples}) for LOF detection. Skipping...")
        df["lof_label"] = 1
        df["lof_score"] = 0.0
        df["is_anomaly"] = 0
        df["anomaly_source"] = "LOF"
        return df
    
    # Adjust n_neighbors to be at most n_samples - 1
    adjusted_neighbors = min(n_neighbors, n_samples - 1)
    if adjusted_neighbors < n_neighbors:
        logger.warning(f"⚠️ Adjusted n_neighbors from {n_neighbors} to {adjusted_neighbors} (n_samples={n_samples})")
    
    embeddings = embeddings if embeddings is not None else compute_embeddings(df)

    lof = LocalOutlierFactor(n_neighbors=adjusted_neighbors, contamination=top_percent / 100)
    labels = lof.fit_predict(embeddings)
    scores = lof.negative_outlier_factor_

    df["lof_label"] = labels  # -1 = anomaly, 1 = normal
    df["lof_score"] = -scores  # Higher = more anomalous
    df["is_anomaly"] = (labels == -1).astype(int)
    df["anomaly_source"] = "LOF"

    logger.info(f"✅ LOF detection complete. Anomalies found: {(df['is_anomaly'] == 1).sum()}")
    return df
