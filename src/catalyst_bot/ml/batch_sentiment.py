"""
Batch Sentiment Scoring for Catalyst-Bot

This module implements batch processing for sentiment analysis to improve
GPU utilization and reduce inference overhead. Instead of scoring items
one-by-one, it collects items into batches and processes them together.

Features:
- Automatic batching with configurable batch size
- Graceful fallback to individual scoring on errors
- Queue management with automatic flush
- Compatible with transformers-based models and VADER

Usage:
    scorer = BatchSentimentScorer(model, max_batch_size=10)

    # Add items to queue
    for text in texts:
        results = scorer.add(text)
        if results:
            # Batch was full and flushed
            process_results(results)

    # Flush remaining items
    final_results = scorer.flush()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)


class BatchSentimentScorer:
    """Batch sentiment analysis with automatic queue management.

    This class collects sentiment scoring requests into batches and processes
    them together to maximize GPU utilization. When the batch reaches the
    configured size, it automatically flushes and returns results.

    Attributes:
        model: Sentiment model (transformers pipeline or VADER analyzer)
        max_batch_size: Maximum items per batch before auto-flush
        queue: Internal queue of pending texts
        model_type: Type of model ('transformers' or 'vader')
    """

    def __init__(
        self,
        model: Any,
        max_batch_size: int = 10,
        model_type: Optional[str] = None,
    ):
        """Initialize batch scorer.

        Args:
            model: Sentiment model (transformers pipeline or VADER)
            max_batch_size: Maximum batch size (default: 10)
            model_type: Model type ('transformers' or 'vader'), auto-detected if None
        """
        self.model = model
        self.max_batch_size = max_batch_size
        self.queue: List[str] = []

        # Auto-detect model type
        if model_type is None:
            model_type = self._detect_model_type(model)
        self.model_type = model_type

        _logger.info(
            "BatchSentimentScorer initialized: type=%s, batch_size=%d",
            self.model_type,
            self.max_batch_size,
        )

    def _detect_model_type(self, model: Any) -> str:
        """Auto-detect model type."""
        model_class = type(model).__name__
        if "Pipeline" in model_class or "transformers" in str(type(model)):
            return "transformers"
        elif (
            "SentimentIntensityAnalyzer" in model_class
            or "vader" in model_class.lower()
        ):
            return "vader"
        else:
            _logger.warning(
                "Unknown model type: %s, defaulting to transformers", model_class
            )
            return "transformers"

    def add(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Add text to batch queue.

        If the queue reaches max_batch_size, automatically flushes and returns results.

        Args:
            text: Text to score

        Returns:
            List of results if batch was flushed, None otherwise
        """
        self.queue.append(text)

        if len(self.queue) >= self.max_batch_size:
            return self.flush()

        return None

    def flush(self) -> List[Dict[str, Any]]:
        """Process all queued items and return results.

        Returns:
            List of sentiment results, one per queued text.
            Each result is a dict with model-specific fields.
        """
        if not self.queue:
            return []

        batch_size = len(self.queue)
        _logger.debug("Flushing batch of %d items", batch_size)

        try:
            results = self._batch_inference(self.queue)
            self.queue = []
            return results
        except Exception as e:
            _logger.warning(
                "Batch inference failed, falling back to individual scoring: %s", e
            )
            # Fallback: score individually
            results = []
            for text in self.queue:
                try:
                    result = self._single_inference(text)
                    results.append(result)
                except Exception as ex:
                    _logger.error("Failed to score text individually: %s", ex)
                    # Return neutral sentiment on error
                    results.append(self._neutral_result())

            self.queue = []
            return results

    def _batch_inference(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Run batch inference on multiple texts.

        Args:
            texts: List of texts to score

        Returns:
            List of sentiment results
        """
        if self.model_type == "vader":
            # VADER doesn't support true batching, score individually
            return [self.model.polarity_scores(text) for text in texts]
        else:
            # Transformers pipeline supports batching
            raw_results = self.model(texts, batch_size=len(texts))

            # Normalize results to consistent format
            results = []
            for raw in raw_results:
                # Pipeline returns [{'label': 'POSITIVE', 'score': 0.99}, ...]
                if isinstance(raw, dict):
                    results.append(self._normalize_transformers_result(raw))
                else:
                    results.append(raw)

            return results

    def _single_inference(self, text: str) -> Dict[str, Any]:
        """Run inference on a single text.

        Args:
            text: Text to score

        Returns:
            Sentiment result dict
        """
        if self.model_type == "vader":
            return self.model.polarity_scores(text)
        else:
            result = self.model(text)
            if isinstance(result, list) and len(result) > 0:
                return self._normalize_transformers_result(result[0])
            return result

    def _normalize_transformers_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize transformers output to VADER-like format.

        Args:
            result: Raw transformers output {'label': 'POSITIVE', 'score': 0.99}

        Returns:
            Normalized dict with 'compound', 'pos', 'neg', 'neu' scores
        """
        label = result.get("label", "").upper()
        score = result.get("score", 0.5)

        # Map to compound score (-1 to 1)
        if "POSITIVE" in label or "BULLISH" in label:
            compound = score
        elif "NEGATIVE" in label or "BEARISH" in label:
            compound = -score
        else:
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

    def _neutral_result(self) -> Dict[str, Any]:
        """Return a neutral sentiment result for error cases.

        Returns:
            Neutral sentiment dict
        """
        return {
            "compound": 0.0,
            "pos": 0.0,
            "neg": 0.0,
            "neu": 1.0,
            "label": "NEUTRAL",
            "raw_score": 0.5,
        }

    def size(self) -> int:
        """Get current queue size.

        Returns:
            Number of items in queue
        """
        return len(self.queue)

    def is_empty(self) -> bool:
        """Check if queue is empty.

        Returns:
            True if queue is empty
        """
        return len(self.queue) == 0


class BatchSentimentManager:
    """High-level manager for batch sentiment scoring across multiple cycles.

    This class maintains a persistent batch scorer and provides convenience
    methods for integrating batch scoring into the main classification loop.

    Usage:
        manager = BatchSentimentManager.from_env()

        # In classification loop
        for item in items:
            score = manager.score_or_queue(item['title'])
            if score:
                item['sentiment'] = score

        # At end of cycle
        manager.flush_and_apply(items)
    """

    def __init__(
        self,
        model: Any,
        max_batch_size: int = 10,
        model_type: Optional[str] = None,
    ):
        """Initialize batch manager.

        Args:
            model: Sentiment model
            max_batch_size: Maximum batch size
            model_type: Model type (auto-detected if None)
        """
        self.scorer = BatchSentimentScorer(
            model, max_batch_size=max_batch_size, model_type=model_type
        )
        self.pending_items: List[Dict[str, Any]] = []

    @classmethod
    def from_env(cls, model: Any) -> BatchSentimentManager:
        """Create manager from environment configuration.

        Args:
            model: Sentiment model

        Returns:
            Configured BatchSentimentManager
        """
        import os

        batch_size = int(os.getenv("SENTIMENT_BATCH_SIZE", "10"))
        return cls(model, max_batch_size=batch_size)

    def score_or_queue(
        self, text: str, item: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Score text or add to queue.

        If batch is full, flushes and returns scores for queued items.
        Otherwise, queues the text and returns None.

        Args:
            text: Text to score
            item: Optional item dict to associate with this text

        Returns:
            Sentiment score dict if batch flushed, None otherwise
        """
        if item is not None:
            self.pending_items.append(item)

        results = self.scorer.add(text)

        if results:
            # Batch was flushed, attach results to pending items
            return self._attach_results(results)

        return None

    def flush_and_apply(
        self, items: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Flush remaining queue and apply scores to items.

        Args:
            items: Optional list of items to score (uses pending_items if None)

        Returns:
            List of items with sentiment scores attached
        """
        if items is None:
            items = self.pending_items

        results = self.scorer.flush()

        if results and items:
            for item, result in zip(items, results):
                item["sentiment_batch"] = result
                # Also set compound score for compatibility
                item["sentiment_score"] = result.get("compound", 0.0)

        self.pending_items = []
        return items

    def _attach_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Attach batch results to pending items.

        Args:
            results: Batch inference results

        Returns:
            List of scored items
        """
        scored_items = []
        for item, result in zip(self.pending_items, results):
            item["sentiment_batch"] = result
            item["sentiment_score"] = result.get("compound", 0.0)
            scored_items.append(item)

        self.pending_items = []
        return scored_items


def create_batch_scorer(
    model_name: str = "vader", max_batch_size: int = 10
) -> BatchSentimentScorer:
    """Factory function to create a batch scorer with specified model.

    Args:
        model_name: Model name ('vader', 'finbert', 'distilbert', etc.)
        max_batch_size: Maximum batch size

    Returns:
        Configured BatchSentimentScorer
    """
    if model_name.lower() == "vader":
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        model = SentimentIntensityAnalyzer()
        return BatchSentimentScorer(model, max_batch_size=max_batch_size)
    else:
        try:
            from transformers import pipeline

            model = pipeline("sentiment-analysis", model=model_name)
            return BatchSentimentScorer(
                model, max_batch_size=max_batch_size, model_type="transformers"
            )
        except ImportError:
            _logger.error("transformers not available, falling back to VADER")
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            model = SentimentIntensityAnalyzer()
            return BatchSentimentScorer(model, max_batch_size=max_batch_size)


# Convenience functions for backward compatibility
def batch_score_texts(
    texts: List[str], model: Any, batch_size: int = 10
) -> List[Dict[str, Any]]:
    """Score multiple texts using batch processing.

    Args:
        texts: List of texts to score
        model: Sentiment model
        batch_size: Batch size

    Returns:
        List of sentiment results
    """
    scorer = BatchSentimentScorer(model, max_batch_size=batch_size)

    results = []
    for text in texts:
        batch_results = scorer.add(text)
        if batch_results:
            results.extend(batch_results)

    # Flush remaining
    final_results = scorer.flush()
    results.extend(final_results)

    return results
