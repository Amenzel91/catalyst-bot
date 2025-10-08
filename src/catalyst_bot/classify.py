"""Classification and scoring of news items.

The classifier assigns a numerical score to each news item based on a
combination of sentiment analysis and keyword matches. Dynamic
adjustments derived from the analyzer are applied to keyword
categories to improve precision over time. The result is a
:class:`~catalyst_bot.models.ScoredItem` which encapsulates the
underlying news item along with its sentiment, keyword hits, and total
score.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .ai_adapter import AIEnrichment, get_adapter

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None  # type: ignore

from .config import get_settings
from .models import NewsItem, ScoredItem

# Import earnings scorer for earnings result detection and sentiment
try:
    from .earnings_scorer import score_earnings_event
except Exception:

    def score_earnings_event(*args, **kwargs):
        return None


# Initialize a single VADER sentiment analyzer instance if available
if SentimentIntensityAnalyzer is not None:
    _vader = SentimentIntensityAnalyzer()
else:
    _vader = None  # type: ignore

# ML sentiment models (WAVE 2.2)
try:
    from .ml.batch_sentiment import BatchSentimentScorer
    from .ml.model_switcher import load_sentiment_model

    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
except Exception as e:
    import logging

    log = logging.getLogger(__name__)
    log.warning("ml_sentiment_import_failed err=%s", str(e))
    ML_AVAILABLE = False

# Initialize ML model singleton
_ml_model = None
_ml_batch_scorer = None


def _init_ml_model():
    """Initialize ML sentiment model (singleton)."""
    global _ml_model, _ml_batch_scorer
    if _ml_model is not None:
        return _ml_model

    if not ML_AVAILABLE:
        return None

    try:
        import logging
        import os

        log = logging.getLogger(__name__)
        model_name = os.getenv("SENTIMENT_MODEL_NAME", "finbert")
        if not os.getenv("FEATURE_ML_SENTIMENT", "1") == "1":
            return None

        _ml_model = load_sentiment_model(model_name)
        if _ml_model:
            batch_size = int(os.getenv("SENTIMENT_BATCH_SIZE", "10"))
            _ml_batch_scorer = BatchSentimentScorer(
                _ml_model, max_batch_size=batch_size
            )
            log.info("ml_sentiment_model_loaded model=%s", model_name)
        return _ml_model
    except Exception as e:
        import logging

        log = logging.getLogger(__name__)
        log.warning("ml_model_init_failed err=%s", str(e))
        return None


def load_dynamic_keyword_weights(path: Optional[Path] = None) -> Dict[str, float]:
    """Load dynamic keyword weights from a JSON file.

    Parameters
    ----------
    path : Optional[Path]
        Path to the JSON file containing keyword statistics. If
        ``None``, defaults to ``data/analyzer/keyword_stats.json`` in
        the project directory.

    Returns
    -------
    Dict[str, float]
        Mapping of keyword category → weight. Falls back to empty dict
        if the file does not exist or is invalid.
    """
    settings = get_settings()
    if path is None:
        path = settings.data_dir / "analyzer" / "keyword_stats.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        weights = data.get("weights", {})
        # Ensure keys are lowercase strings and values are floats
        return {str(k).lower(): float(v) for k, v in weights.items()}
    except Exception:
        return {}


def aggregate_sentiment_sources(
    item,
    earnings_result: Optional[Dict] = None,
) -> tuple:
    """
    Aggregate sentiment from all available sources with confidence weighting.

    Args:
        item: NewsItem to analyze
        earnings_result: Optional earnings data from earnings_scorer

    Returns:
        Tuple of (final_sentiment, confidence, source_breakdown)
        - final_sentiment: -1.0 to +1.0
        - confidence: 0.0 to 1.0
        - source_breakdown: Dict[source_name, sentiment_score]
    """
    import logging
    import os

    log = logging.getLogger(__name__)

    sentiment_sources = {}

    # 1. VADER Sentiment (fast baseline)
    if _vader is not None:
        try:
            vader_scores = _vader.polarity_scores(item.title)
            vader_compound = float(vader_scores.get("compound", 0.0))
            sentiment_sources["vader"] = vader_compound
        except Exception as e:
            log.debug("vader_sentiment_failed err=%s", str(e))

    # 2. Earnings Sentiment (highest priority for earnings events)
    if earnings_result and earnings_result.get("is_earnings_result"):
        earnings_sentiment = float(earnings_result.get("sentiment_score", 0.0))
        sentiment_sources["earnings"] = earnings_sentiment

    # 3. ML Sentiment (FinBERT/DistilBERT via GPU)
    if os.getenv("FEATURE_ML_SENTIMENT", "1") == "1":
        ml_model = _init_ml_model()
        if ml_model is not None and _ml_batch_scorer is not None:
            try:
                # Score single item (batch scorer handles internally)
                result = _ml_batch_scorer.add(item.title)
                # If batch not full, flush to get result
                if result is None:
                    result = _ml_batch_scorer.flush()
                if result and len(result) > 0:
                    ml_sentiment = float(result[0].get("compound", 0.0))
                    sentiment_sources["ml"] = ml_sentiment
            except Exception as e:
                log.debug("ml_sentiment_failed err=%s", str(e))

    # 4. LLM Sentiment (Mistral via Ollama - if already computed)
    if hasattr(item, "raw") and item.raw:
        llm_sent = item.raw.get("llm_sentiment")
        if llm_sent is not None:
            try:
                sentiment_sources["llm"] = float(llm_sent)
            except (ValueError, TypeError):
                pass

    # 5. AI Adapter Sentiment (if available)
    # Note: This is handled separately in enrichment step

    # Define weights (configurable via environment)
    weights = {
        "earnings": float(os.getenv("SENTIMENT_WEIGHT_EARNINGS", "0.35")),
        "ml": float(os.getenv("SENTIMENT_WEIGHT_ML", "0.25")),
        "vader": float(os.getenv("SENTIMENT_WEIGHT_VADER", "0.25")),
        "llm": float(os.getenv("SENTIMENT_WEIGHT_LLM", "0.15")),
    }

    # Define confidence multipliers for each source
    confidence_map = {
        "earnings": 0.95,  # Highest - hard data
        "ml": 0.85,  # High - trained financial model
        "llm": 0.70,  # Medium - general LLM
        "vader": 0.60,  # Lower - rule-based
    }

    # Calculate weighted average with confidence
    weighted_sum = 0.0
    total_weight = 0.0

    for source, score in sentiment_sources.items():
        base_weight = weights.get(source, 0.0)
        confidence_mult = confidence_map.get(source, 0.5)

        # Effective weight = base_weight * confidence
        effective_weight = base_weight * confidence_mult
        weighted_sum += score * effective_weight
        total_weight += effective_weight

    # Calculate final sentiment
    if total_weight > 0:
        final_sentiment = weighted_sum / total_weight
    else:
        # Fallback if no sources available
        final_sentiment = 0.0

    # Calculate overall confidence (how many sources contributed)
    expected_total_weight = sum(weights.values())
    confidence = (
        min(1.0, total_weight / expected_total_weight)
        if expected_total_weight > 0
        else 0.0
    )

    # Log sentiment breakdown for debugging
    if sentiment_sources:
        log.debug(
            "sentiment_aggregated sources=%s final=%.3f confidence=%.3f",
            {k: f"{v:.3f}" for k, v in sentiment_sources.items()},
            final_sentiment,
            confidence,
        )

    return final_sentiment, confidence, sentiment_sources


def classify_batch_with_llm(
    items: List[NewsItem],
    keyword_weights: Optional[Dict[str, float]] = None,
    min_prescale_score: float = 0.20,
    batch_size: int = 5,
    batch_delay: float = 2.0,
) -> List[ScoredItem]:
    """
    Classify items in batches with intelligent pre-filtering.

    This reduces GPU load by only sending high-potential items (prescale >= threshold)
    to the expensive LLM, and processing them in small batches with delays to prevent
    GPU overload.

    Args:
        items: List of NewsItems to classify
        keyword_weights: Dynamic keyword weights
        min_prescale_score: Minimum score to qualify for LLM (default: 0.20)
        batch_size: Items per batch (default: 5)
        batch_delay: Seconds between batches (default: 2.0)

    Returns:
        List of ScoredItem objects with LLM sentiment added where applicable
    """
    import time

    from .config import get_settings
    from .logging_utils import get_logger

    log = get_logger(__name__)
    settings = get_settings()

    # Get config from settings (which loads from environment)
    batch_size = getattr(settings, "mistral_batch_size", batch_size)
    batch_delay = getattr(settings, "mistral_batch_delay", batch_delay)
    min_prescale_score = getattr(settings, "mistral_min_prescale", min_prescale_score)

    # Check if LLM classifier is enabled
    llm_enabled = getattr(settings, "feature_llm_classifier", False)

    # Pre-classify all items (fast: VADER + keywords only)
    prescored = []
    for item in items:
        # Quick classification without LLM
        scored = classify(item, keyword_weights=keyword_weights)
        prescored.append((item, scored))

    # Filter for LLM candidates (score >= threshold)
    llm_candidates = [
        (item, scored)
        for item, scored in prescored
        if _score_of(scored) >= min_prescale_score
    ]

    total_items = len(items)
    llm_count = len(llm_candidates)
    skipped = total_items - llm_count

    log.info(
        "llm_batch_filter total=%d llm_eligible=%d skipped=%d threshold=%.2f reduction=%.1f%%",
        total_items,
        llm_count,
        skipped,
        min_prescale_score,
        (skipped / total_items * 100) if total_items > 0 else 0,
    )

    # If we have LLM candidates and LLM is enabled, warm up GPU and process them
    if llm_candidates and llm_enabled:
        try:
            from .llm_client import prime_ollama_gpu, query_llm

            # Warm up GPU before batch processing
            warmup_success = prime_ollama_gpu()
            if warmup_success:
                log.info("llm_gpu_warmed candidates=%d", len(llm_candidates))

            # Process LLM candidates in batches
            total_batches = (len(llm_candidates) + batch_size - 1) // batch_size

            for i in range(0, len(llm_candidates), batch_size):
                batch = llm_candidates[i : i + batch_size]
                batch_num = (i // batch_size) + 1

                log.info(
                    "llm_batch_processing batch=%d/%d items=%d",
                    batch_num,
                    total_batches,
                    len(batch),
                )

                for item, scored in batch:
                    # Build LLM prompt for sentiment analysis
                    prompt = (
                        f"Analyze this financial news headline for trading sentiment:\n\n"
                        f"{item.title}\n\n"
                        f"Respond with ONLY a single number from -1.0 (very bearish) "
                        f"to +1.0 (very bullish). No explanation, just the number."
                    )

                    # Query LLM with timeout and retries
                    llm_result = query_llm(prompt, timeout=15.0, max_retries=3)

                    if llm_result:
                        # Parse sentiment from LLM response
                        try:
                            # Extract first number from response
                            import re

                            numbers = re.findall(r"-?\d+\.?\d*", llm_result)
                            if numbers:
                                llm_sentiment = float(numbers[0])
                                # Clamp to valid range
                                llm_sentiment = max(-1.0, min(1.0, llm_sentiment))

                                # Store in item's raw data
                                if not hasattr(item, "raw"):
                                    item.raw = {}
                                if item.raw is None:
                                    item.raw = {}
                                item.raw["llm_sentiment"] = llm_sentiment

                                log.debug(
                                    "llm_sentiment_added ticker=%s sentiment=%.3f",
                                    getattr(item, "ticker", "N/A"),
                                    llm_sentiment,
                                )
                        except (ValueError, AttributeError, IndexError) as e:
                            log.warning(
                                "llm_parse_failed response=%s err=%s",
                                llm_result[:50],
                                str(e),
                            )

                # Delay between batches (except last batch)
                if i + batch_size < len(llm_candidates):
                    log.debug("llm_batch_delay delay=%.1fs", batch_delay)
                    time.sleep(batch_delay)

        except ImportError:
            log.warning("llm_client_not_available skipping_llm_enrichment")
        except Exception as e:
            log.warning("llm_batch_processing_failed err=%s", str(e))

    # Return all scored items (both LLM-enriched and non-enriched)
    # Note: Items that got LLM sentiment will have it in their raw data,
    # which will be picked up by aggregate_sentiment_sources() in classify()
    results = [scored for item, scored in prescored]

    log.info("llm_batch_complete total=%d llm_enriched=%d", len(results), llm_count)

    return results


def _score_of(scored) -> float:
    """Extract numeric score from scored object or dict."""
    for name in ("total_score", "score", "source_weight", "relevance"):
        v = (
            scored.get(name)
            if isinstance(scored, dict)
            else getattr(scored, name, None)
        )
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def classify(
    item: NewsItem, keyword_weights: Optional[Dict[str, float]] = None
) -> ScoredItem:
    """Classify a news item and return a scored representation.

    Combines sentiment, keyword-category hits (with analyzer-provided
    dynamic weights when available), and source weighting.

    WAVE 0.1: Includes earnings result detection and sentiment scoring.
    """
    settings = get_settings()
    keyword_categories = settings.keyword_categories

    # --- WAVE 0.1: Earnings Scorer Integration ---
    # Check if this is an earnings result (not just calendar announcement)
    earnings_result = None
    import os

    if os.getenv("FEATURE_EARNINGS_SCORER", "1") == "1":
        try:
            # Extract ticker and source from item
            ticker = getattr(item, "ticker", None) or ""
            source = getattr(item, "source", None) or ""
            raw = getattr(item, "raw", None) or {}

            # Also check raw dict for source if not on item
            if not source and isinstance(raw, dict):
                source = raw.get("source", "")

            # Score the earnings event
            earnings_result = score_earnings_event(
                title=item.title or "",
                description=getattr(item, "summary", None) or "",
                ticker=ticker,
                source=source,
                use_api=True,
            )
        except Exception:
            # Don't let earnings scorer errors break classification
            earnings_result = None

    # Sentiment - Use multi-source aggregation
    sentiment, sentiment_confidence, sentiment_breakdown = aggregate_sentiment_sources(
        item, earnings_result=earnings_result
    )

    # Store breakdown in item for debugging/analysis
    if hasattr(item, "raw") and item.raw:
        item.raw["sentiment_breakdown"] = sentiment_breakdown
        item.raw["sentiment_confidence"] = sentiment_confidence

    # Keyword hits & weights (prefer analyzer dynamic weights)
    title_lower = (item.title or "").lower()
    hits: List[str] = []
    total_keyword_score = 0.0
    dynamic_weights = keyword_weights or load_dynamic_keyword_weights()

    for category, keywords in keyword_categories.items():
        for kw in keywords:
            if kw in title_lower:
                hits.append(category)
                weight = float(
                    dynamic_weights.get(category, settings.keyword_default_weight)
                )
                total_keyword_score += weight
                # Count at most one hit per category
                break

    # Source weight (wrapped to satisfy flake8 line length)
    src_host = (item.source_host or "").lower()
    source_weight = settings.rss_sources.get(src_host, 1.0)

    # Aggregate relevance (keep simple/deterministic)
    relevance = float(total_keyword_score) * float(source_weight)

    # Total score: simple combination that is deterministic and monotonic
    total_score = relevance + sentiment

    # Earnings boost/penalty (enhanced)
    if earnings_result and earnings_result.get("is_earnings_result"):
        earnings_sentiment = earnings_result.get("sentiment_score", 0.0)

        # Apply boost/penalty to total_score
        if earnings_sentiment > 0.5:  # Strong beat
            total_score += 2.0
            confidence_boost = 0.15
        elif earnings_sentiment > 0:  # Moderate beat
            total_score += 1.0
            confidence_boost = 0.10
        elif earnings_sentiment < -0.5:  # Strong miss
            total_score -= 1.5
            confidence_boost = 0.10  # Still confident, just bearish
        elif earnings_sentiment < 0:  # Moderate miss
            total_score -= 0.5
            confidence_boost = 0.05
        else:
            confidence_boost = 0.0

        # Boost confidence for earnings events (we trust the data)
        sentiment_confidence = min(1.0, sentiment_confidence + confidence_boost)

        # Add earnings keywords (existing code)
        if "earnings" not in hits:
            hits.append("earnings")
        if sentiment_label := earnings_result.get("sentiment_label"):
            label_keyword = sentiment_label.lower().replace(" ", "_")
            if label_keyword not in hits:
                hits.append(label_keyword)

    # Build ScoredItem first (keep existing behavior), then optionally enrich.
    # Use keyword arguments to ensure fields map correctly and populate
    # keyword_hits explicitly so tests can introspect matched categories.
    scored: ScoredItem | dict
    try:
        scored = ScoredItem(
            relevance=relevance,
            sentiment=sentiment,
            tags=hits,
            source_weight=total_score,
            keyword_hits=hits.copy(),
        )
    except TypeError:
        # Older builds may not accept keyword_hits; fall back to positional args
        try:
            scored = ScoredItem(relevance, sentiment, hits, total_score)
        except Exception:
            # Last resort so pipeline doesn't die; downstream runner handles dicts too
            scored = {
                "relevance": relevance,
                "sentiment": sentiment,
                "keywords": hits,
                "score": total_score,
            }

    # --- WAVE 0.1: Attach earnings metadata to scored item ---
    # Add earnings result data to the scored item for downstream processing
    if earnings_result:
        try:
            # Helper to set attributes on both dict and object types
            def _set_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_attr(scored, "is_earnings_result", True)
            _set_attr(
                scored,
                "earnings_sentiment_score",
                earnings_result.get("sentiment_score"),
            )
            _set_attr(
                scored,
                "earnings_sentiment_label",
                earnings_result.get("sentiment_label"),
            )
            _set_attr(scored, "earnings_eps_actual", earnings_result.get("eps_actual"))
            _set_attr(
                scored, "earnings_eps_estimate", earnings_result.get("eps_estimate")
            )
            _set_attr(
                scored, "earnings_revenue_actual", earnings_result.get("revenue_actual")
            )
            _set_attr(
                scored,
                "earnings_revenue_estimate",
                earnings_result.get("revenue_estimate"),
            )
            _set_attr(
                scored, "earnings_data_source", earnings_result.get("data_source")
            )

            # Add "earnings" tag if not already present
            try:
                if isinstance(scored, dict):
                    tags_list = scored.get("tags") or scored.get("keywords") or []
                    if "earnings" not in tags_list:
                        tags_list.append("earnings")
                        scored["tags"] = tags_list
                else:
                    tags_list = getattr(scored, "tags", []) or []
                    if "earnings" not in tags_list:
                        tags_list.append("earnings")
                        setattr(scored, "tags", tags_list)
            except Exception:
                pass
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- Optional AI enrichment (noop by default via AI_BACKEND=none) -------
    # Adds 'ai_sentiment' into .extra and merges 'ai_tags' into tags.
    try:
        adapter = get_adapter()
        enr: AIEnrichment = adapter.enrich(item.title or "", None)

        # Helper accessors for object-or-dict compatibility
        def _get_tags(obj):
            if isinstance(obj, dict):
                # prefer 'tags', fall back to 'keywords'
                return list(obj.get("tags") or obj.get("keywords") or [])
            return list(getattr(obj, "tags", []) or [])

        def _set_tags(obj, new_tags: List[str]):
            if isinstance(obj, dict):
                obj["tags"] = new_tags
            else:
                try:
                    setattr(obj, "tags", new_tags)
                except Exception:
                    pass

        def _get_extra(obj) -> dict:
            if isinstance(obj, dict):
                obj.setdefault("extra", {})
                return obj["extra"]
            extra = getattr(obj, "extra", None)
            if extra is None:
                try:
                    setattr(obj, "extra", {})
                    extra = getattr(obj, "extra", {})
                except Exception:
                    extra = {}
            return extra

        # Merge tags from AI (deduped)
        if enr.ai_tags:
            cur = set(_get_tags(scored))
            cur.update(enr.ai_tags)
            _set_tags(scored, sorted(cur))

        # Record AI sentiment in 'extra' without overriding numeric 'sentiment'
        if enr.ai_sentiment:
            extra = _get_extra(scored)
            extra["ai_sentiment"] = {
                "label": enr.ai_sentiment.label,
                "score": float(enr.ai_sentiment.score),
            }
    except Exception:
        # Never let enrichment break classification
        pass

    return scored
