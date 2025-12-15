"""
Shared embedding model cache to avoid reloading SentenceTransformer weights
multiple times per process. This speeds up both KNN and LOF detectors,
especially on Fargate where cold starts and disk reads are costly.
"""

import os
from typing import Dict

from sentence_transformers import SentenceTransformer

# Avoid tokenizer parallelism warnings and extra threads
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Simple in-process cache keyed by model name
_MODEL_CACHE: Dict[str, SentenceTransformer] = {}


def get_embedding_model(model_name: str) -> SentenceTransformer:
    """
    Return a cached SentenceTransformer instance for the given model name.
    """
    if model_name not in _MODEL_CACHE:
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]

