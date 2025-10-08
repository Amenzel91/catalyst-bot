"""
GPU Memory Management for Catalyst-Bot

This module provides utilities for managing GPU memory, including:
- Model caching to avoid repeated loading
- Explicit memory cleanup after operations
- Memory monitoring and leak detection
- VRAM usage tracking

Features:
- Singleton model cache for sentiment and LLM models
- Automatic garbage collection and CUDA cache clearing
- Memory usage logging and alerts
- Configurable cleanup strategies

Usage:
    from catalyst_bot.ml.gpu_memory import get_model, cleanup_gpu_memory

    # Get cached model (loaded once, reused)
    model = get_model('sentiment', 'finbert')

    # After batch processing
    cleanup_gpu_memory()
"""

from __future__ import annotations

import gc
import logging
import os
import time
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

# Global model cache
_MODEL_CACHE: Dict[str, Any] = {}
_LAST_CLEANUP_TIME: float = 0.0
_CLEANUP_INTERVAL_SEC: float = 60.0  # Minimum time between cleanups


def get_model(
    model_type: str,
    model_name: str,
    force_reload: bool = False,
    device: Optional[str] = None,
) -> Any:
    """Get or load a model from cache.

    Models are cached by (type, name) key to avoid repeated loading.
    Subsequent calls return the cached instance.

    Args:
        model_type: Model type ('sentiment', 'llm', 'transformers')
        model_name: Model identifier (e.g., 'finbert', 'vader', 'mistral')
        force_reload: Force reload even if cached
        device: Device to load model on ('cuda', 'cpu', None=auto)

    Returns:
        Loaded model instance
    """
    cache_key = f"{model_type}:{model_name}"

    if not force_reload and cache_key in _MODEL_CACHE:
        _logger.debug("Returning cached model: %s", cache_key)
        return _MODEL_CACHE[cache_key]

    _logger.info("Loading model: %s", cache_key)
    model = _load_model(model_type, model_name, device)

    _MODEL_CACHE[cache_key] = model
    _logger.info("Model cached: %s (cache size: %d)", cache_key, len(_MODEL_CACHE))

    return model


def _load_model(model_type: str, model_name: str, device: Optional[str] = None) -> Any:
    """Load a model based on type and name.

    Args:
        model_type: Model type ('sentiment', 'llm', etc.)
        model_name: Model identifier
        device: Target device

    Returns:
        Loaded model

    Raises:
        ValueError: If model type is unknown
    """
    if model_type == "sentiment":
        return _load_sentiment_model(model_name, device)
    elif model_type in ["llm", "transformers"]:
        return _load_transformers_model(model_name, device)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def _load_sentiment_model(model_name: str, device: Optional[str] = None) -> Any:
    """Load a sentiment analysis model.

    Args:
        model_name: Model name ('vader', 'finbert', 'distilbert', etc.)
        device: Target device

    Returns:
        Sentiment model
    """
    if model_name.lower() == "vader":
        # VADER is CPU-only
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        return SentimentIntensityAnalyzer()

    # Try loading transformers model
    try:
        from transformers import pipeline

        # Auto-detect device
        if device is None:
            device = _auto_detect_device()

        device_id = 0 if device == "cuda" else -1

        # Map common names to HuggingFace model IDs
        model_map = {
            "finbert": "ProsusAI/finbert",
            "distilbert": "distilbert-base-uncased-finetuned-sst-2-english",
            "roberta": "cardiffnlp/twitter-roberta-base-sentiment",
            "bert-sentiment": "nlptown/bert-base-multilingual-uncased-sentiment",
        }

        hf_model_id = model_map.get(model_name.lower(), model_name)

        _logger.info("Loading transformers model: %s (device: %s)", hf_model_id, device)

        model = pipeline(
            "sentiment-analysis",
            model=hf_model_id,
            device=device_id,
        )

        return model

    except ImportError as e:
        _logger.error(
            "transformers library not available, falling back to VADER: %s", e
        )
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        return SentimentIntensityAnalyzer()


def _load_transformers_model(model_name: str, device: Optional[str] = None) -> Any:
    """Load a generic transformers model.

    Args:
        model_name: HuggingFace model ID
        device: Target device

    Returns:
        Loaded model
    """
    from transformers import AutoModel, AutoTokenizer

    if device is None:
        device = _auto_detect_device()

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    if device == "cuda":
        try:
            import torch

            if torch.cuda.is_available():
                model = model.cuda()
        except Exception as e:
            _logger.warning("Failed to move model to CUDA: %s", e)

    return {"model": model, "tokenizer": tokenizer}


def _auto_detect_device() -> str:
    """Auto-detect available device (CUDA or CPU).

    Returns:
        'cuda' if GPU available, 'cpu' otherwise
    """
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass

    return "cpu"


def cleanup_gpu_memory(force: bool = False) -> Dict[str, float]:
    """Clean up GPU memory by clearing CUDA cache and running garbage collection.

    Args:
        force: Force cleanup even if recently cleaned

    Returns:
        Dict with memory stats before and after cleanup
    """
    global _LAST_CLEANUP_TIME

    # Rate limit cleanups to avoid overhead
    current_time = time.time()
    if not force and (current_time - _LAST_CLEANUP_TIME) < _CLEANUP_INTERVAL_SEC:
        _logger.debug("Skipping cleanup (too recent)")
        return {}

    mem_before = get_gpu_memory_stats()

    # Run garbage collection
    gc.collect()

    # Clear CUDA cache if available
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            _logger.debug("CUDA cache cleared")
    except ImportError:
        pass

    mem_after = get_gpu_memory_stats()

    freed_mb = mem_before.get("used_mb", 0) - mem_after.get("used_mb", 0)

    if freed_mb > 0:
        _logger.info("GPU memory cleanup: freed %.2f MB", freed_mb)
    else:
        _logger.debug("GPU memory cleanup: no memory freed")

    _LAST_CLEANUP_TIME = current_time

    return {
        "before_mb": mem_before.get("used_mb", 0),
        "after_mb": mem_after.get("used_mb", 0),
        "freed_mb": freed_mb,
    }


def get_gpu_memory_stats() -> Dict[str, float]:
    """Get current GPU memory usage statistics.

    Returns:
        Dict with 'used_mb', 'total_mb', 'free_mb', 'utilization_pct'
    """
    # Try PyTorch first
    try:
        import torch

        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated(0) / (1024**2)
            reserved = torch.cuda.memory_reserved(0) / (1024**2)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**2)
            free = total - used

            return {
                "used_mb": used,
                "reserved_mb": reserved,
                "total_mb": total,
                "free_mb": free,
                "utilization_pct": (used / total * 100) if total > 0 else 0.0,
            }
    except (ImportError, RuntimeError):
        pass

    # Fallback to nvidia-smi
    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                parts = lines[0].split(",")
                used = float(parts[0].strip())
                total = float(parts[1].strip())
                free = float(parts[2].strip())
                utilization = float(parts[3].strip())

                return {
                    "used_mb": used,
                    "total_mb": total,
                    "free_mb": free,
                    "utilization_pct": utilization,
                }
    except Exception as e:
        _logger.debug("nvidia-smi not available: %s", e)

    # No GPU detected
    return {
        "used_mb": 0.0,
        "total_mb": 0.0,
        "free_mb": 0.0,
        "utilization_pct": 0.0,
    }


def log_gpu_memory(prefix: str = "") -> None:
    """Log current GPU memory usage.

    Args:
        prefix: Optional prefix for log message
    """
    stats = get_gpu_memory_stats()

    if stats.get("total_mb", 0) > 0:
        msg = (
            f"{prefix}GPU memory: {stats['used_mb']:.0f}/{stats['total_mb']:.0f} MB "
            f"({stats['utilization_pct']:.1f}% used)"
        )
        _logger.info(msg)
    else:
        _logger.debug("%sNo GPU detected", prefix)


def check_gpu_memory_warning() -> Optional[str]:
    """Check if GPU memory usage is critically high.

    Returns:
        Warning message if memory usage > threshold, None otherwise
    """
    threshold = float(os.getenv("GPU_MAX_UTILIZATION_WARN", "90"))

    stats = get_gpu_memory_stats()
    utilization = stats.get("utilization_pct", 0)

    if utilization > threshold:
        return (
            f"GPU memory usage critically high: {utilization:.1f}% "
            f"(threshold: {threshold}%)"
        )

    return None


def clear_model_cache(model_type: Optional[str] = None) -> int:
    """Clear cached models from memory.

    Args:
        model_type: Clear only models of this type, or all if None

    Returns:
        Number of models cleared
    """
    global _MODEL_CACHE

    if model_type is None:
        count = len(_MODEL_CACHE)
        _MODEL_CACHE.clear()
        _logger.info("Cleared all cached models (%d)", count)
        cleanup_gpu_memory(force=True)
        return count

    # Clear specific type
    keys_to_remove = [k for k in _MODEL_CACHE if k.startswith(f"{model_type}:")]
    for key in keys_to_remove:
        del _MODEL_CACHE[key]

    _logger.info(
        "Cleared %d cached models of type: %s", len(keys_to_remove), model_type
    )
    cleanup_gpu_memory(force=True)

    return len(keys_to_remove)


def get_cache_stats() -> Dict[str, Any]:
    """Get model cache statistics.

    Returns:
        Dict with cache stats
    """
    return {
        "total_models": len(_MODEL_CACHE),
        "cached_models": list(_MODEL_CACHE.keys()),
        "memory_stats": get_gpu_memory_stats(),
    }


# Context manager for automatic cleanup
class GPUMemoryContext:
    """Context manager for automatic GPU memory cleanup.

    Usage:
        with GPUMemoryContext():
            # GPU operations
            model = get_model('sentiment', 'finbert')
            results = model(texts)
        # Automatic cleanup on exit
    """

    def __init__(self, log_prefix: str = ""):
        self.log_prefix = log_prefix

    def __enter__(self):
        log_gpu_memory(f"{self.log_prefix}[BEFORE] ")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        cleanup_stats = cleanup_gpu_memory(force=True)
        log_gpu_memory(f"{self.log_prefix}[AFTER] ")

        if cleanup_stats.get("freed_mb", 0) > 0:
            _logger.info(
                "%sFreed %.2f MB GPU memory",
                self.log_prefix,
                cleanup_stats["freed_mb"],
            )

        return False  # Don't suppress exceptions


# Auto-cleanup decorator
def with_gpu_cleanup(func):
    """Decorator for automatic GPU cleanup after function execution.

    Usage:
        @with_gpu_cleanup
        def process_batch(items):
            # GPU operations
            return results
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            cleanup_gpu_memory()

    return wrapper


# Enable/disable cleanup based on environment
def is_gpu_cleanup_enabled() -> bool:
    """Check if GPU memory cleanup is enabled.

    Returns:
        True if GPU_MEMORY_CLEANUP env var is set to 1
    """
    return os.getenv("GPU_MEMORY_CLEANUP", "1") == "1"


def maybe_cleanup_gpu_memory() -> None:
    """Clean up GPU memory if enabled in config."""
    if is_gpu_cleanup_enabled():
        cleanup_gpu_memory()
