"""
Model Switcher for Catalyst-Bot

This module provides a flexible model loading system that supports switching
between different sentiment analysis models based on configuration.

Supported Models:
- VADER (CPU-only, lightweight, instant)
- FinBERT (GPU, ~440MB, high accuracy for financial text)
- DistilBERT (GPU, ~250MB, 2x faster than BERT)
- RoBERTa Twitter Sentiment (GPU, ~500MB, fast and accurate)
- BERT Multilingual Sentiment (GPU, ~600MB, very accurate)

Features:
- Configuration-based model selection
- Automatic fallback to VADER if GPU models fail
- Model caching and reuse
- Performance metrics tracking

Usage:
    from catalyst_bot.ml.model_switcher import load_sentiment_model

    # Load model based on SENTIMENT_MODEL_NAME env var
    model = load_sentiment_model()

    # Or specify explicitly
    model = load_sentiment_model('distilbert')

    # Use model
    result = score_sentiment(model, "Great earnings beat!")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

# Model registry: maps friendly names to HuggingFace model IDs and metadata
MODEL_REGISTRY = {
    "vader": {
        "type": "vader",
        "description": "VADER lexicon-based sentiment (CPU-only, instant)",
        "size_mb": 0,
        "gpu_required": False,
        "accuracy": "medium",
        "speed": "instant",
        "huggingface_id": None,
    },
    "finbert": {
        "type": "transformers",
        "description": "FinBERT - Financial domain BERT (high accuracy)",
        "size_mb": 440,
        "gpu_required": False,  # Works on CPU but slow
        "gpu_recommended": True,
        "accuracy": "high",
        "speed": "slow",
        "huggingface_id": "ProsusAI/finbert",
    },
    "distilbert": {
        "type": "transformers",
        "description": "DistilBERT SST-2 - Distilled BERT (2x faster)",
        "size_mb": 250,
        "gpu_required": False,
        "gpu_recommended": True,
        "accuracy": "medium-high",
        "speed": "medium",
        "huggingface_id": "distilbert-base-uncased-finetuned-sst-2-english",
    },
    "roberta": {
        "type": "transformers",
        "description": "RoBERTa Twitter Sentiment (fast and accurate)",
        "size_mb": 500,
        "gpu_required": False,
        "gpu_recommended": True,
        "accuracy": "high",
        "speed": "medium-fast",
        "huggingface_id": "cardiffnlp/twitter-roberta-base-sentiment",
    },
    "bert-multilingual": {
        "type": "transformers",
        "description": "BERT Multilingual Sentiment (very accurate)",
        "size_mb": 600,
        "gpu_required": False,
        "gpu_recommended": True,
        "accuracy": "very-high",
        "speed": "slow",
        "huggingface_id": "nlptown/bert-base-multilingual-uncased-sentiment",
    },
}

# Cache for loaded models
_MODEL_CACHE: Dict[str, Any] = {}


def get_model_info(model_name: str) -> Dict[str, Any]:
    """Get metadata for a model.

    Args:
        model_name: Model identifier

    Returns:
        Model metadata dict

    Raises:
        ValueError: If model name is unknown
    """
    model_name_lower = model_name.lower()
    if model_name_lower not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model: {model_name}. Available: {list(MODEL_REGISTRY.keys())}"
        )

    return MODEL_REGISTRY[model_name_lower].copy()


def list_available_models() -> List[str]:
    """Get list of available model names.

    Returns:
        List of model identifiers
    """
    return list(MODEL_REGISTRY.keys())


def load_sentiment_model(
    model_name: Optional[str] = None,
    device: Optional[str] = None,
    cache: bool = True,
) -> Any:
    """Load a sentiment analysis model.

    Args:
        model_name: Model identifier (defaults to SENTIMENT_MODEL_NAME env var)
        device: Device to load on ('cuda', 'cpu', None=auto)
        cache: Use cached model if available

    Returns:
        Loaded sentiment model

    Raises:
        ValueError: If model name is invalid
        RuntimeError: If model loading fails
    """
    # Get model name from env if not specified
    if model_name is None:
        model_name = os.getenv("SENTIMENT_MODEL_NAME", "vader")

    model_name_lower = model_name.lower()

    # Check cache
    cache_key = f"{model_name_lower}:{device or 'auto'}"
    if cache and cache_key in _MODEL_CACHE:
        _logger.debug("Returning cached model: %s", cache_key)
        return _MODEL_CACHE[cache_key]

    # Get model info
    try:
        model_info = get_model_info(model_name_lower)
    except ValueError as e:
        _logger.error(str(e))
        _logger.warning("Falling back to VADER")
        model_name_lower = "vader"
        model_info = get_model_info("vader")

    _logger.info(
        "Loading sentiment model: %s (%s)",
        model_name_lower,
        model_info["description"],
    )

    # Load model based on type
    try:
        if model_info["type"] == "vader":
            model = _load_vader()
        elif model_info["type"] == "transformers":
            model = _load_transformers_model(
                model_info["huggingface_id"], device=device
            )
        else:
            raise ValueError(f"Unknown model type: {model_info['type']}")

        # Cache model
        if cache:
            _MODEL_CACHE[cache_key] = model
            _logger.info("Model cached: %s", cache_key)

        return model

    except Exception as e:
        _logger.error("Failed to load model %s: %s", model_name_lower, e)
        _logger.warning("Falling back to VADER")

        # Fallback to VADER
        if model_name_lower != "vader":
            model = _load_vader()
            if cache:
                _MODEL_CACHE[cache_key] = model
            return model
        else:
            raise RuntimeError(f"Failed to load VADER model: {e}")


def _load_vader() -> Any:
    """Load VADER sentiment analyzer.

    Returns:
        VADER SentimentIntensityAnalyzer
    """
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    return SentimentIntensityAnalyzer()


def _load_transformers_model(huggingface_id: str, device: Optional[str] = None) -> Any:
    """Load a HuggingFace transformers model.

    Args:
        huggingface_id: HuggingFace model ID
        device: Target device ('cuda', 'cpu', None=auto)

    Returns:
        Transformers sentiment-analysis pipeline
    """
    try:
        from transformers import pipeline
    except ImportError as e:
        raise RuntimeError(
            "transformers library not installed. Install with: pip install transformers torch"
        ) from e

    # Auto-detect device
    if device is None:
        device = _auto_detect_device()

    device_id = 0 if device == "cuda" else -1

    _logger.info("Loading %s on device: %s", huggingface_id, device)

    try:
        model = pipeline(
            "sentiment-analysis",
            model=huggingface_id,
            device=device_id,
        )
        return model
    except Exception as e:
        _logger.error("Failed to load transformers model: %s", e)
        raise


def _auto_detect_device() -> str:
    """Auto-detect best available device.

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


def score_sentiment(
    model: Any, text: str, model_name: Optional[str] = None
) -> Dict[str, Any]:
    """Score sentiment using a loaded model.

    Args:
        model: Loaded sentiment model
        text: Text to analyze
        model_name: Model name (for type detection, auto-detected if None)

    Returns:
        Sentiment score dict with 'compound', 'pos', 'neg', 'neu' scores
    """
    if model_name is None:
        # Try to detect model type
        model_type = type(model).__name__
        if "SentimentIntensityAnalyzer" in model_type:
            model_name = "vader"
        else:
            model_name = "transformers"

    if model_name.lower() == "vader":
        # VADER returns compound score directly
        return model.polarity_scores(text)
    else:
        # Transformers pipeline
        result = model(text)
        if isinstance(result, list) and len(result) > 0:
            return _normalize_transformers_result(result[0])
        return result


def _normalize_transformers_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize transformers output to VADER-like format.

    Args:
        result: Raw transformers result {'label': 'POSITIVE', 'score': 0.99}

    Returns:
        Normalized dict with 'compound', 'pos', 'neg', 'neu'
    """
    label = result.get("label", "").upper()
    score = result.get("score", 0.5)

    # Map to compound score (-1 to 1)
    if (
        "POSITIVE" in label
        or "BULLISH" in label
        or label.startswith("5")
        or label.startswith("4")
    ):
        # 5 stars = very positive, 4 stars = positive
        compound = score if label.startswith("5") else score * 0.7
    elif (
        "NEGATIVE" in label
        or "BEARISH" in label
        or label.startswith("1")
        or label.startswith("2")
    ):
        # 1 star = very negative, 2 stars = negative
        compound = -score if label.startswith("1") else -score * 0.7
    elif label.startswith("3"):
        # 3 stars = neutral
        compound = 0.0
    else:
        # NEUTRAL or unknown
        compound = 0.0

    # Approximate component scores
    pos = score if compound > 0 else 0.0
    neg = score if compound < 0 else 0.0
    neu = 1.0 - abs(compound)

    return {
        "compound": compound,
        "pos": pos,
        "neg": neg,
        "neu": neu,
        "label": label,
        "raw_score": score,
    }


def benchmark_model(
    model_name: str, test_texts: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Benchmark a sentiment model.

    Args:
        model_name: Model to benchmark
        test_texts: Test texts (uses defaults if None)

    Returns:
        Benchmark results dict
    """
    import time

    if test_texts is None:
        test_texts = [
            "Company beats earnings estimates and raises guidance",
            "Regulatory investigation leads to stock plunge",
            "Merger announced with strategic partner",
            "Clinical trial fails to meet primary endpoint",
            "Record quarterly revenue drives stock higher",
        ]

    _logger.info("Benchmarking model: %s", model_name)

    # Load model
    load_start = time.perf_counter()
    try:
        model = load_sentiment_model(model_name, cache=False)
    except Exception as e:
        return {
            "model_name": model_name,
            "success": False,
            "error": str(e),
        }
    load_time = (time.perf_counter() - load_start) * 1000

    # Score texts
    inference_times = []
    results = []

    for text in test_texts:
        start = time.perf_counter()
        try:
            result = score_sentiment(model, text, model_name)
            results.append(result)
        except Exception as e:
            _logger.error("Failed to score text: %s", e)
            results.append(None)
        elapsed = (time.perf_counter() - start) * 1000
        inference_times.append(elapsed)

    avg_inference_time = sum(inference_times) / len(inference_times)

    return {
        "model_name": model_name,
        "success": True,
        "load_time_ms": round(load_time, 2),
        "avg_inference_time_ms": round(avg_inference_time, 2),
        "items_per_second": round(
            1000 / avg_inference_time if avg_inference_time > 0 else 0, 2
        ),
        "sample_results": results[:3],  # First 3 results
    }


def compare_models(models: Optional[List[str]] = None) -> Dict[str, Any]:
    """Compare multiple sentiment models.

    Args:
        models: List of model names to compare (defaults to all)

    Returns:
        Comparison results dict
    """
    if models is None:
        models = ["vader", "distilbert", "finbert", "roberta"]

    _logger.info("Comparing models: %s", models)

    results = {}
    for model_name in models:
        try:
            results[model_name] = benchmark_model(model_name)
        except Exception as e:
            _logger.error("Failed to benchmark %s: %s", model_name, e)
            results[model_name] = {
                "model_name": model_name,
                "success": False,
                "error": str(e),
            }

    return {
        "comparison": results,
        "fastest": max(
            (m for m in results.values() if m.get("success")),
            key=lambda x: x.get("items_per_second", 0),
            default=None,
        ),
        "slowest": min(
            (m for m in results.values() if m.get("success")),
            key=lambda x: x.get("items_per_second", float("inf")),
            default=None,
        ),
    }


def get_recommended_model(gpu_available: bool = True, prioritize: str = "speed") -> str:
    """Get recommended model based on system capabilities.

    Args:
        gpu_available: Whether GPU is available
        prioritize: 'speed', 'accuracy', or 'balanced'

    Returns:
        Recommended model name
    """
    if not gpu_available:
        return "vader"

    if prioritize == "speed":
        return "distilbert"
    elif prioritize == "accuracy":
        return "finbert"
    else:  # balanced
        return "roberta"


def clear_model_cache() -> int:
    """Clear cached models.

    Returns:
        Number of models cleared
    """
    global _MODEL_CACHE
    count = len(_MODEL_CACHE)
    _MODEL_CACHE.clear()
    _logger.info("Cleared %d cached models", count)
    return count
