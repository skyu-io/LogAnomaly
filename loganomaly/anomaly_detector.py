import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
from tqdm import tqdm


def compute_embeddings(df):
    print("🔤 Computing embeddings...")
    model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L6-v2")
    embeddings = model.encode(df["log"].tolist(), show_progress_bar=True)
    return embeddings


def detect_anomalies(df, top_percent):
    embeddings = compute_embeddings(df)
    print("📈 Calculating anomaly scores...")
    knn = NearestNeighbors(n_neighbors=5, metric="cosine")
    knn.fit(embeddings)
    distances, _ = knn.kneighbors(embeddings)
    scores = distances.mean(axis=1)
    df["anomaly_score"] = scores

    top_n = int(top_percent * len(df)) or 1
    df = df.sort_values(by="anomaly_score", ascending=False).reset_index(drop=True)
    df["is_anomaly"] = 0
    df.loc[:top_n, "is_anomaly"] = 1

    return df
