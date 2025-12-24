"""
Shared embedding model cache to avoid reloading SentenceTransformer weights
multiple times per process. This speeds up both KNN and LOF detectors,
especially on Fargate where cold starts and disk reads are costly.
"""

import atexit
import os
from typing import Dict, List, Optional, Tuple

from sentence_transformers import SentenceTransformer

from loganomaly import config as app_config

# Avoid tokenizer parallelism warnings and extra threads
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Simple in-process cache keyed by model name
_MODEL_CACHE: Dict[str, SentenceTransformer] = {}

# Reusable multi-process pools keyed by (model_name, target_devices)
_POOL_CACHE: Dict[Tuple[str, Tuple[str, ...]], object] = {}


def get_embedding_model(model_name: str) -> SentenceTransformer:
    """
    Return a cached SentenceTransformer instance for the given model name.
    """
    if model_name not in _MODEL_CACHE:
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


def _default_target_devices() -> List[str]:
    """
    Determine the target devices list for multi-process encoding.
    Uses config overrides when present, otherwise spreads across CPU cores.
    """
    configured = getattr(app_config, "EMBEDDING_POOL_DEVICES", None)
    if configured:
        return list(configured)

    cpu_workers = getattr(app_config, "EMBEDDING_CPU_WORKERS", None)
    if cpu_workers is None:
        logical_cpus = os.cpu_count() or 1
        # cap to avoid overwhelming small hosts; default to at most 4 workers
        cpu_workers = max(1, min(4, logical_cpus))

    return ["cpu"] * cpu_workers


def get_embedding_pool(
    model_name: str, target_devices: Optional[List[str]] = None
) -> Tuple[SentenceTransformer, object]:
    """
    Return (model, pool) for multi-process encoding on the requested devices.
    Pools are cached and reused to avoid process churn between encode calls.
    """
    devices = tuple(target_devices or _default_target_devices())
    model = get_embedding_model(model_name)
    key = (model_name, devices)

    if key not in _POOL_CACHE:
        _POOL_CACHE[key] = model.start_multi_process_pool(target_devices=list(devices))

    return model, _POOL_CACHE[key]


def stop_embedding_pools() -> None:
    """
    Stop all cached multi-process pools. Registered with atexit for cleanup.
    """
    for pool in _POOL_CACHE.values():
        SentenceTransformer.stop_multi_process_pool(pool)
    _POOL_CACHE.clear()


atexit.register(stop_embedding_pools)

