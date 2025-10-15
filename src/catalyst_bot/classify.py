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
from .source_credibility import get_source_category, get_source_tier, get_source_weight

# Semantic keyword extraction (optional)
try:
    from .semantic_keywords import get_semantic_extractor

    _semantic_extractor = get_semantic_extractor()
except ImportError:
    _semantic_extractor = None

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


def clear_ml_batch_scorer() -> None:
    """Clear ML batch scorer to prevent memory leaks.

    CRITICAL BUG FIX: This function should be called at the end of each cycle
    in runner.py to prevent unbounded memory growth in the batch scorer.
    The batch scorer may accumulate items without proper cleanup, causing
    memory leaks in long-running processes.

    This function is safe to call even if ML sentiment is disabled or the
    batch scorer is not initialized.
    """
    global _ml_batch_scorer
    if _ml_batch_scorer is not None:
        try:
            # Check if the batch scorer has a clear() method
            if hasattr(_ml_batch_scorer, "clear"):
                _ml_batch_scorer.clear()
            # If not, try flush() to at least process pending items
            elif hasattr(_ml_batch_scorer, "flush"):
                _ml_batch_scorer.flush()
        except Exception:
            # Silently ignore errors - don't break the main loop
            pass


def log_credibility_distribution(items: List[NewsItem]) -> None:
    """Log the distribution of source credibility tiers across news items.

    This function analyzes a batch of news items and logs statistics about
    source quality distribution. Helps track the quality of incoming news
    sources and identify potential issues with low-credibility sources.

    Parameters
    ----------
    items : List[NewsItem]
        News items to analyze for credibility distribution

    Notes
    -----
    Logs at INFO level with the following metrics:
        - Total items processed
        - Count and percentage for each tier (1=HIGH, 2=MEDIUM, 3=LOW)
        - Average credibility weight across all items
    """
    import logging

    log = logging.getLogger(__name__)

    if not items:
        return

    tier_counts = {1: 0, 2: 0, 3: 0}
    total_weight = 0.0

    for item in items:
        url = getattr(item, "canonical_url", None) or getattr(item, "link", None)
        if url:
            tier = get_source_tier(url)
            weight = get_source_weight(url)
            tier_counts[tier] += 1
            total_weight += weight

    total = len(items)
    avg_weight = total_weight / total if total > 0 else 0.0

    log.info(
        "source_credibility_distribution total=%d tier1_high=%d(%.1f%%) "
        "tier2_medium=%d(%.1f%%) tier3_low=%d(%.1f%%) avg_weight=%.3f",
        total,
        tier_counts[1],
        (tier_counts[1] / total * 100) if total > 0 else 0,
        tier_counts[2],
        (tier_counts[2] / total * 100) if total > 0 else 0,
        tier_counts[3],
        (tier_counts[3] / total * 100) if total > 0 else 0,
        avg_weight,
    )


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

    # --- ENHANCEMENT #1: Extract multi-dimensional sentiment if available ---
    # Check if item has multi-dimensional sentiment analysis from LLM
    multi_dim_sentiment = None
    if hasattr(item, "raw") and item.raw and isinstance(item.raw, dict):
        multi_dim_data = item.raw.get("sentiment_analysis")
        if multi_dim_data:
            try:
                from .llm_schemas import SentimentAnalysis

                # Validate and parse multi-dimensional sentiment
                multi_dim_sentiment = SentimentAnalysis(**multi_dim_data)

                # Apply confidence threshold filtering (reject if confidence < 0.5)
                if multi_dim_sentiment.confidence < 0.5:
                    import logging

                    log = logging.getLogger(__name__)
                    log.debug(
                        "multi_dim_sentiment_rejected_low_confidence ticker=%s confidence=%.2f",
                        getattr(item, "ticker", "N/A"),
                        multi_dim_sentiment.confidence,
                    )
                    multi_dim_sentiment = None  # Reject low-confidence sentiment
                else:
                    # Use multi-dimensional sentiment to enhance numeric sentiment
                    # Override sentiment_confidence with LLM confidence if higher
                    if multi_dim_sentiment.confidence > sentiment_confidence:
                        sentiment_confidence = multi_dim_sentiment.confidence

                    # Optionally blend numeric sentiment with categorical sentiment
                    categorical_sentiment = multi_dim_sentiment.to_numeric_sentiment()
                    # Weighted blend: 70% original, 30% categorical
                    sentiment = 0.7 * sentiment + 0.3 * categorical_sentiment

                    import logging

                    log = logging.getLogger(__name__)
                    log.info(
                        "multi_dim_sentiment_applied ticker=%s "
                        "market_sentiment=%s urgency=%s risk=%s confidence=%.2f",
                        getattr(item, "ticker", "N/A"),
                        multi_dim_sentiment.market_sentiment,
                        multi_dim_sentiment.urgency,
                        multi_dim_sentiment.risk_level,
                        multi_dim_sentiment.confidence,
                    )
            except Exception as e:
                import logging

                log = logging.getLogger(__name__)
                log.debug("multi_dim_sentiment_parse_failed err=%s", str(e))

    # Store breakdown in item for debugging/analysis
    if hasattr(item, "raw") and item.raw:
        item.raw["sentiment_breakdown"] = sentiment_breakdown
        item.raw["sentiment_confidence"] = sentiment_confidence

    # Keyword hits & weights (prefer analyzer dynamic weights)
    # Search both title AND summary for keywords (enables SEC filing descriptions + news summaries)
    title_lower = (item.title or "").lower()
    summary_lower = (getattr(item, "summary", None) or "").lower()
    # Combine title and summary for keyword matching
    combined_text = f"{title_lower} {summary_lower}"

    hits: List[str] = []
    total_keyword_score = 0.0
    dynamic_weights = keyword_weights or load_dynamic_keyword_weights()

    for category, keywords in keyword_categories.items():
        for kw in keywords:
            if kw in combined_text:
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

    # --- ENHANCEMENT #2: Apply source credibility scoring ---
    # Get credibility weight based on source URL/domain
    # This applies a tier-based multiplier to prioritize high-quality sources
    credibility_weight = 1.0
    credibility_tier = 3  # Default to tier 3 (unknown)
    source_url = getattr(item, "canonical_url", None) or getattr(item, "link", None)

    if source_url:
        credibility_tier = get_source_tier(source_url)
        credibility_weight = get_source_weight(source_url)

        # Log when low-credibility sources are downweighted
        if credibility_tier == 3 and credibility_weight < 1.0:
            import logging

            log = logging.getLogger(__name__)
            log.debug(
                "source_credibility_downweight url=%s tier=%d weight=%.2f",
                source_url[:100] if source_url else "N/A",
                credibility_tier,
                credibility_weight,
            )

    # Combine legacy source weight with credibility weight
    combined_source_weight = float(source_weight) * float(credibility_weight)

    # --- SEMANTIC KEYWORD EXTRACTION (KeyBERT) ---
    # Extract context-aware keyphrases to supplement traditional keyword matching
    semantic_keywords = []
    if _semantic_extractor and _semantic_extractor.is_available():
        try:
            import os

            # Check if feature is enabled (default: enabled)
            if os.getenv("FEATURE_SEMANTIC_KEYWORDS", "1") == "1":
                top_n = int(os.getenv("SEMANTIC_KEYWORDS_TOP_N", "5"))
                ngram_max = int(os.getenv("SEMANTIC_KEYWORDS_NGRAM_MAX", "3"))

                semantic_keywords = _semantic_extractor.extract_from_feed_item(
                    title=item.title or "",
                    summary=getattr(item, "summary", None) or "",
                    top_n=top_n,
                    keyphrase_ngram_range=(1, ngram_max),
                )

                import logging

                log = logging.getLogger(__name__)
                log.debug(
                    "semantic_keywords_extracted ticker=%s keywords=%s",
                    getattr(item, "ticker", "N/A"),
                    semantic_keywords,
                )
        except Exception as e:
            import logging

            log = logging.getLogger(__name__)
            log.debug("semantic_keyword_extraction_failed err=%s", str(e))

    # Aggregate relevance (keep simple/deterministic)
    relevance = float(total_keyword_score) * float(combined_source_weight)

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

    # --- FUNDAMENTAL DATA INTEGRATION: Float shares and short interest scoring ---
    # Apply fundamental data boost if ticker is available and feature is enabled
    fundamental_score = 0.0
    fundamental_metadata = None
    ticker = getattr(item, "ticker", None)

    if ticker and ticker.strip():
        try:
            from .fundamental_scoring import calculate_fundamental_score

            fundamental_score, fundamental_metadata = calculate_fundamental_score(
                ticker
            )
            if fundamental_score > 0:
                total_score += fundamental_score

                # Add fundamental tags to hits list for downstream visibility
                if fundamental_metadata.get("float_reason"):
                    float_tag = f"fundamental_{fundamental_metadata['float_reason']}"
                    if float_tag not in hits:
                        hits.append(float_tag)

                if fundamental_metadata.get("si_reason"):
                    si_tag = f"fundamental_{fundamental_metadata['si_reason']}"
                    if si_tag not in hits:
                        hits.append(si_tag)

                import logging

                log = logging.getLogger(__name__)
                log.info(
                    "fundamental_boost_applied ticker=%s boost=%.3f float_score=%.3f si_score=%.3f",
                    ticker,
                    fundamental_score,
                    fundamental_metadata.get("float_score", 0.0),
                    fundamental_metadata.get("si_score", 0.0),
                )
        except ImportError:
            # fundamental_scoring module not available (shouldn't happen)
            pass
        except Exception as e:
            # Don't let fundamental scoring errors break classification
            import logging

            log = logging.getLogger(__name__)
            log.debug(
                "fundamental_scoring_failed ticker=%s err=%s",
                ticker,
                e.__class__.__name__,
            )

    # --- MARKET REGIME ADJUSTMENT ---
    # Apply regime multiplier to total_score based on current market conditions
    # This adjusts scores based on overall market environment (VIX, SPY trend)
    regime_multiplier = 1.0
    regime_data = None

    try:
        from .market_regime import get_current_regime

        regime_data = get_current_regime()
        regime_multiplier = regime_data.get("multiplier", 1.0)

        # Store pre-adjustment score for logging
        pre_regime_score = total_score

        # Apply regime adjustment to total_score
        total_score = total_score * regime_multiplier

        import logging

        log = logging.getLogger(__name__)
        log.info(
            "regime_adjustment_applied ticker=%s regime=%s vix=%.2f spy_trend=%s "
            "multiplier=%.2f pre_score=%.3f post_score=%.3f",
            ticker or "N/A",
            regime_data.get("regime", "UNKNOWN"),
            regime_data.get("vix", 0.0),
            regime_data.get("spy_trend", "UNKNOWN"),
            regime_multiplier,
            pre_regime_score,
            total_score,
        )
    except ImportError:
        # market_regime module not available yet
        pass
    except Exception as e:
        import logging

        log = logging.getLogger(__name__)
        log.debug("regime_adjustment_failed ticker=%s err=%s", ticker or "N/A", str(e))

    # --- RVOL (RELATIVE VOLUME) BOOST ---
    # Apply RVol multiplier to boost scores for tickers with unusual volume
    # RVol >2.0x indicates elevated interest, often preceding significant price moves
    rvol_multiplier = 1.0
    rvol_data = None

    if ticker and ticker.strip():
        try:
            from .rvol import calculate_rvol_intraday

            rvol_data = calculate_rvol_intraday(ticker)
            if rvol_data:
                rvol_multiplier = rvol_data.get("multiplier", 1.0)

                # Apply to total_score
                pre_rvol_score = total_score
                total_score = total_score * rvol_multiplier

                import logging

                log = logging.getLogger(__name__)
                log.info(
                    "rvol_adjustment ticker=%s rvol=%.2fx rvol_class=%s multiplier=%.2f "
                    "current_vol=%d avg_vol=%.0f pre_score=%.3f post_score=%.3f",
                    ticker,
                    rvol_data.get("rvol", 1.0),
                    rvol_data.get("rvol_class", "NORMAL"),
                    rvol_multiplier,
                    rvol_data.get("current_volume", 0),
                    rvol_data.get("avg_volume_20d", 0.0),
                    pre_rvol_score,
                    total_score,
                )
        except ImportError:
            # rvol module not available (shouldn't happen)
            pass
        except Exception as e:
            import logging

            log = logging.getLogger(__name__)
            log.debug(
                "rvol_calculation_failed ticker=%s err=%s", ticker or "N/A", str(e)
            )

    # --- FLOAT-BASED CONFIDENCE ADJUSTMENT ---
    # Apply float multiplier to adjust scores based on volatility expectations
    # Low float stocks (<5M shares) have 4.2x higher volatility
    float_multiplier = 1.0
    float_data = None

    try:
        from .float_data import get_float_data

        if ticker:
            float_data = get_float_data(ticker)
            float_multiplier = float_data.get("multiplier", 1.0)

            # Apply to total_score
            pre_float_score = total_score
            total_score = total_score * float_multiplier

            import logging

            log = logging.getLogger(__name__)
            log.info(
                "float_adjustment_applied ticker=%s float_class=%s float_shares=%.2fM "
                "multiplier=%.2f pre_score=%.3f post_score=%.3f",
                ticker,
                float_data.get("float_class", "UNKNOWN"),
                (float_data.get("float_shares") or 0) / 1_000_000,
                float_multiplier,
                pre_float_score,
                total_score,
            )
    except Exception as e:
        import logging

        log = logging.getLogger(__name__)
        log.warning("float_adjustment_failed ticker=%s err=%s", ticker or "N/A", str(e))

    # --- VWAP (VOLUME WEIGHTED AVERAGE PRICE) ANALYSIS ---
    # Calculate VWAP and determine if price is above/below (exit signal)
    # VWAP breaks (price below VWAP) are strong sell signals - 91% accuracy
    vwap_multiplier = 1.0
    vwap_data = None

    if ticker and ticker.strip():
        try:
            from .vwap_calculator import calculate_vwap, get_vwap_multiplier

            vwap_data = calculate_vwap(ticker)
            if vwap_data:
                vwap_multiplier = get_vwap_multiplier(vwap_data)

                # Apply to total_score
                pre_vwap_score = total_score
                total_score = total_score * vwap_multiplier

                import logging

                log = logging.getLogger(__name__)
                log.info(
                    "vwap_adjustment ticker=%s vwap=%.4f current_price=%.4f distance=%.2f%% "
                    "signal=%s multiplier=%.2f pre_score=%.3f post_score=%.3f",
                    ticker,
                    vwap_data.get("vwap", 0.0),
                    vwap_data.get("current_price", 0.0),
                    vwap_data.get("distance_from_vwap_pct", 0.0),
                    vwap_data.get("vwap_signal", "UNKNOWN"),
                    vwap_multiplier,
                    pre_vwap_score,
                    total_score,
                )
        except ImportError:
            # vwap_calculator module not available (shouldn't happen)
            pass
        except Exception as e:
            import logging

            log = logging.getLogger(__name__)
            log.debug(
                "vwap_calculation_failed ticker=%s err=%s", ticker or "N/A", str(e)
            )

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

    # --- ENHANCEMENT #1: Attach multi-dimensional sentiment metadata ---
    # Add multi-dimensional sentiment fields to scored item for downstream use
    if multi_dim_sentiment:
        try:
            # Helper to set attributes on both dict and object types
            def _set_md_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_md_attr(
                scored, "market_sentiment", multi_dim_sentiment.market_sentiment
            )
            _set_md_attr(scored, "sentiment_confidence", multi_dim_sentiment.confidence)
            _set_md_attr(scored, "urgency", multi_dim_sentiment.urgency)
            _set_md_attr(scored, "risk_level", multi_dim_sentiment.risk_level)
            _set_md_attr(
                scored,
                "institutional_interest",
                multi_dim_sentiment.institutional_interest,
            )
            _set_md_attr(
                scored, "retail_hype_score", multi_dim_sentiment.retail_hype_score
            )
            _set_md_attr(scored, "sentiment_reasoning", multi_dim_sentiment.reasoning)
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- ENHANCEMENT #2: Attach source credibility metadata ---
    # Add credibility tier and weight to scored item for downstream tracking
    try:
        # Helper to set attributes on both dict and object types
        def _set_cred_attr(obj, key, value):
            if isinstance(obj, dict):
                obj[key] = value
            else:
                try:
                    setattr(obj, key, value)
                except Exception:
                    pass

        _set_cred_attr(scored, "source_credibility_tier", credibility_tier)
        _set_cred_attr(scored, "source_credibility_weight", credibility_weight)
        _set_cred_attr(
            scored,
            "source_credibility_category",
            get_source_category(source_url) if source_url else "unknown",
        )
    except Exception:
        # Don't let metadata attachment break the pipeline
        pass

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

    # --- FUNDAMENTAL DATA: Attach fundamental metadata to scored item ---
    # Add fundamental data to the scored item for downstream processing
    if fundamental_metadata:
        try:
            # Helper to set attributes on both dict and object types
            def _set_fund_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_fund_attr(scored, "fundamental_score", fundamental_score)
            _set_fund_attr(
                scored,
                "fundamental_float_shares",
                fundamental_metadata.get("float_shares"),
            )
            _set_fund_attr(
                scored,
                "fundamental_short_interest",
                fundamental_metadata.get("short_interest"),
            )
            _set_fund_attr(
                scored,
                "fundamental_float_score",
                fundamental_metadata.get("float_score"),
            )
            _set_fund_attr(
                scored, "fundamental_si_score", fundamental_metadata.get("si_score")
            )
            _set_fund_attr(
                scored,
                "fundamental_float_reason",
                fundamental_metadata.get("float_reason"),
            )
            _set_fund_attr(
                scored, "fundamental_si_reason", fundamental_metadata.get("si_reason")
            )
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- MARKET REGIME: Attach regime metadata to scored item ---
    # Add market regime data to the scored item for downstream processing
    if regime_data:
        try:
            # Helper to set attributes on both dict and object types
            def _set_regime_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_regime_attr(scored, "market_regime", regime_data.get("regime"))
            _set_regime_attr(scored, "market_vix", regime_data.get("vix"))
            _set_regime_attr(scored, "market_spy_trend", regime_data.get("spy_trend"))
            _set_regime_attr(scored, "market_regime_multiplier", regime_multiplier)
            _set_regime_attr(
                scored, "market_spy_20d_return", regime_data.get("spy_20d_return")
            )
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- FLOAT DATA: Attach float metadata to scored item ---
    # Add float data to the scored item for downstream processing
    if float_data:
        try:
            # Helper to set attributes on both dict and object types
            def _set_float_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_float_attr(scored, "float_shares", float_data.get("float_shares"))
            _set_float_attr(scored, "float_class", float_data.get("float_class"))
            _set_float_attr(scored, "float_multiplier", float_data.get("multiplier"))
            _set_float_attr(
                scored, "short_interest_pct", float_data.get("short_interest_pct")
            )
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- RVOL DATA: Attach RVol metadata to scored item ---
    # Add relative volume data to the scored item for downstream processing
    if rvol_data:
        try:
            # Helper to set attributes on both dict and object types
            def _set_rvol_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_rvol_attr(scored, "rvol", rvol_data.get("rvol"))
            _set_rvol_attr(scored, "rvol_class", rvol_data.get("rvol_class"))
            _set_rvol_attr(scored, "rvol_multiplier", rvol_data.get("multiplier"))
            _set_rvol_attr(scored, "current_volume", rvol_data.get("current_volume"))
            _set_rvol_attr(scored, "avg_volume_20d", rvol_data.get("avg_volume_20d"))
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- VWAP DATA: Attach VWAP metadata to scored item ---
    # Add VWAP data to the scored item for downstream processing
    if vwap_data:
        try:
            # Helper to set attributes on both dict and object types
            def _set_vwap_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_vwap_attr(scored, "vwap", vwap_data.get("vwap"))
            _set_vwap_attr(scored, "vwap_signal", vwap_data.get("vwap_signal"))
            _set_vwap_attr(scored, "vwap_multiplier", vwap_multiplier)
            _set_vwap_attr(
                scored, "vwap_distance_pct", vwap_data.get("distance_from_vwap_pct")
            )
            _set_vwap_attr(scored, "is_above_vwap", vwap_data.get("is_above_vwap"))
            _set_vwap_attr(scored, "vwap_current_price", vwap_data.get("current_price"))
            _set_vwap_attr(
                scored, "vwap_cumulative_volume", vwap_data.get("cumulative_volume")
            )
        except Exception:
            # Don't let metadata attachment break the pipeline
            pass

    # --- SEMANTIC KEYWORDS: Attach semantic keywords to scored item ---
    # Add KeyBERT extracted keywords to the scored item for downstream processing
    if semantic_keywords:
        try:
            # Helper to set attributes on both dict and object types
            def _set_semantic_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_semantic_attr(scored, "semantic_keywords", semantic_keywords)
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
