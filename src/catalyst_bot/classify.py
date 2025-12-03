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
import re
from pathlib import Path
from typing import Dict, List, Optional

from .ai_adapter import AIEnrichment, get_adapter

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None  # type: ignore

from .config import get_settings
from .logging_utils import get_logger
from .models import NewsItem, ScoredItem
from .source_credibility import get_source_category, get_source_tier, get_source_weight

# Ticker profiler for per-ticker keyword affinity (optional)
try:
    from .ticker_profiler import get_ticker_profiler
    TICKER_PROFILER_AVAILABLE = True
except ImportError:
    TICKER_PROFILER_AVAILABLE = False

    def get_ticker_profiler():
        return None

# Dynamic source scorer for performance-based source weighting (optional)
try:
    from .dynamic_source_scorer import get_dynamic_source_weight
    DYNAMIC_SOURCE_SCORER_AVAILABLE = True
except ImportError:
    DYNAMIC_SOURCE_SCORER_AVAILABLE = False

    def get_dynamic_source_weight(url: str) -> float:
        return 1.0

# Module-level logger
log = get_logger(__name__)

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


# Import offering sentiment correction to handle offering stage detection
try:
    from .offering_sentiment import (
        apply_offering_sentiment_correction,
        get_offering_stage_label,
        is_debt_offering,
    )

    OFFERING_SENTIMENT_AVAILABLE = True
except ImportError:
    OFFERING_SENTIMENT_AVAILABLE = False

    def apply_offering_sentiment_correction(*args, **kwargs):
        return kwargs.get("current_sentiment", 0.0), None, False

    def get_offering_stage_label(stage):
        return "OFFERING"

    def is_debt_offering(*args, **kwargs):
        return False


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

    # 5. Google Trends Sentiment (retail search volume indicator)
    # Get search volume trends for the ticker
    ticker = getattr(item, "ticker", None)
    if ticker and os.getenv("FEATURE_GOOGLE_TRENDS", "0") == "1":
        try:
            from .google_trends_sentiment import get_google_trends_sentiment

            trends_result = get_google_trends_sentiment(ticker)
            if trends_result:
                trends_score, trends_label, trends_metadata = trends_result
                sentiment_sources["google_trends"] = float(trends_score)

                log.debug(
                    "google_trends_sentiment_aggregated ticker=%s score=%.3f spike_ratio=%.2fx direction=%s",
                    ticker,
                    trends_score,
                    trends_metadata.get("spike_ratio", 0.0),
                    trends_metadata.get("trend_direction", "UNKNOWN")
                )
        except Exception as e:
            log.debug("google_trends_sentiment_failed ticker=%s err=%s", ticker, str(e))

    # 6. Short Interest Sentiment (squeeze potential amplifier)
    # Amplifies bullish sentiment when short interest is high
    if ticker and os.getenv("FEATURE_SHORT_INTEREST_BOOST", "1") == "1":
        try:
            from .short_interest_sentiment import calculate_si_sentiment

            # Calculate temporary base sentiment from sources collected so far
            temp_sentiment = 0.0
            if sentiment_sources:
                temp_sum = sum(sentiment_sources.values())
                temp_sentiment = temp_sum / len(sentiment_sources) if temp_sum else 0.0

            si_result = calculate_si_sentiment(ticker, sentiment=temp_sentiment)
            if si_result and si_result.get("sentiment_boost", 0.0) != 0.0:
                sentiment_sources["short_interest"] = float(si_result["sentiment_boost"])

                log.debug(
                    "short_interest_sentiment ticker=%s si_pct=%.1f%% multiplier=%.2fx boost=%.3f",
                    ticker,
                    si_result.get("short_interest_pct", 0.0),
                    si_result.get("squeeze_multiplier", 1.0),
                    si_result["sentiment_boost"]
                )
        except Exception as e:
            log.debug("short_interest_sentiment_failed ticker=%s err=%s", ticker, str(e))

    # 7. Pre-Market Action Sentiment (leading price indicator)
    # Only active during pre-market hours (4am-10am ET)
    if ticker and os.getenv("FEATURE_PREMARKET_SENTIMENT", "1") == "1":
        try:
            from .premarket_sentiment import get_premarket_sentiment

            pm_result = get_premarket_sentiment(ticker)
            if pm_result:
                pm_score, pm_metadata = pm_result
                sentiment_sources["premarket"] = float(pm_score)

                log.debug(
                    "premarket_sentiment ticker=%s change_pct=%.2f%% score=%.3f",
                    ticker,
                    pm_metadata.get("premarket_change_pct", 0.0),
                    pm_score
                )
        except Exception as e:
            log.debug("premarket_sentiment_failed ticker=%s err=%s", ticker, str(e))

    # 8. After-Market Action Sentiment (earnings and news signal)
    # Only active during after-market hours (4pm-8pm ET)
    if ticker and os.getenv("FEATURE_AFTERMARKET_SENTIMENT", "1") == "1":
        try:
            from .aftermarket_sentiment import get_aftermarket_sentiment

            am_result = get_aftermarket_sentiment(ticker)
            if am_result:
                am_score, am_metadata = am_result
                sentiment_sources["aftermarket"] = float(am_score)

                log.debug(
                    "aftermarket_sentiment ticker=%s change_pct=%.2f%% score=%.3f",
                    ticker,
                    am_metadata.get("aftermarket_change_pct", 0.0),
                    am_score
                )
        except Exception as e:
            log.debug("aftermarket_sentiment_failed ticker=%s err=%s", ticker, str(e))

    # 9. News Velocity Sentiment (article momentum indicator)
    # Detects article spikes that indicate breaking news or viral catalysts
    if ticker and os.getenv("FEATURE_NEWS_VELOCITY", "1") == "1":
        try:
            from .news_velocity import get_velocity_tracker

            velocity_tracker = get_velocity_tracker()
            velocity_result = velocity_tracker.get_velocity_sentiment(ticker)

            if velocity_result and velocity_result.get("sentiment", 0.0) != 0.0:
                sentiment_sources["news_velocity"] = float(velocity_result["sentiment"])

                log.debug(
                    "news_velocity_sentiment ticker=%s articles_1h=%d velocity_score=%.3f is_spike=%s",
                    ticker,
                    velocity_result.get("articles_1h", 0),
                    velocity_result["sentiment"],
                    velocity_result.get("is_spike", False)
                )
        except Exception as e:
            log.debug("news_velocity_sentiment_failed ticker=%s err=%s", ticker, str(e))

    # 10. Insider Trading Sentiment (SEC Form 4 analysis)
    # Analyzes insider buying/selling as a leading indicator
    if ticker and os.getenv("FEATURE_INSIDER_SENTIMENT", "1") == "1":
        try:
            from .insider_trading_sentiment import get_insider_sentiment

            insider_result = get_insider_sentiment(ticker, lookback_days=30)

            if insider_result:
                insider_score, insider_metadata = insider_result
                if insider_score != 0.0:
                    sentiment_sources["insider"] = float(insider_score)

                    log.debug(
                        "insider_sentiment ticker=%s score=%.3f signal=%s net_value=$%.0f key_insiders=%s",
                        ticker,
                        insider_score,
                        insider_metadata.get("signal_strength", "NEUTRAL"),
                        insider_metadata.get("net_value_usd", 0.0),
                        insider_metadata.get("key_insiders", [])
                    )
        except Exception as e:
            log.debug("insider_sentiment_failed ticker=%s err=%s", ticker, str(e))

    # 11. Volume-Price Divergence (technical signal - weak rally / strong selloff detection)
    if ticker and os.getenv("FEATURE_VOLUME_PRICE_DIVERGENCE", "1") == "1":
        try:
            from .volume_price_divergence import detect_divergence, calculate_price_change, calculate_volume_change_from_rvol
            from .rvol import calculate_rvol_intraday

            # Get RVol data (already calculated earlier in classify())
            rvol_data = calculate_rvol_intraday(ticker)
            if rvol_data:
                # Calculate price change
                price_change = calculate_price_change(ticker)

                # Calculate volume change from RVol
                volume_change = calculate_volume_change_from_rvol(rvol_data)

                if price_change is not None and volume_change is not None:
                    divergence_result = detect_divergence(
                        ticker,
                        price_change,
                        volume_change
                    )

                    if divergence_result and divergence_result.get("sentiment_adjustment") != 0.0:
                        # Add divergence sentiment adjustment
                        sentiment_sources["divergence"] = float(divergence_result["sentiment_adjustment"])

                        log.debug(
                            "divergence_detected ticker=%s type=%s strength=%s adjustment=%.3f price_change=%.2f%% volume_change=%.2f%%",
                            ticker,
                            divergence_result.get("divergence_type", "UNKNOWN"),
                            divergence_result.get("signal_strength", "UNKNOWN"),
                            divergence_result["sentiment_adjustment"],
                            price_change * 100,
                            volume_change * 100
                        )
        except Exception as e:
            log.debug("divergence_detection_failed ticker=%s error=%s", ticker, str(e))

    # 12. AI Adapter Sentiment (if available)
    # Note: This is handled separately in enrichment step

    # Define weights (configurable via environment)
    weights = {
        "earnings": float(os.getenv("SENTIMENT_WEIGHT_EARNINGS", "0.35")),
        "ml": float(os.getenv("SENTIMENT_WEIGHT_ML", "0.25")),
        "vader": float(os.getenv("SENTIMENT_WEIGHT_VADER", "0.25")),
        "llm": float(os.getenv("SENTIMENT_WEIGHT_LLM", "0.15")),
        # Additional sentiment sources
        "google_trends": float(os.getenv("SENTIMENT_WEIGHT_GOOGLE_TRENDS", "0.08")),
        "short_interest": float(os.getenv("SENTIMENT_WEIGHT_SHORT_INTEREST", "0.08")),
        "premarket": float(os.getenv("SENTIMENT_WEIGHT_PREMARKET", "0.15")),
        "aftermarket": float(os.getenv("SENTIMENT_WEIGHT_AFTERMARKET", "0.15")),
        "news_velocity": float(os.getenv("SENTIMENT_WEIGHT_NEWS_VELOCITY", "0.05")),
        "insider": float(os.getenv("SENTIMENT_WEIGHT_INSIDER", "0.12")),
        "divergence": float(os.getenv("SENTIMENT_WEIGHT_DIVERGENCE", "0.08")),
    }

    # Define confidence multipliers for each source
    confidence_map = {
        "earnings": 0.95,  # Highest - hard data
        "ml": 0.85,  # High - trained financial model
        "llm": 0.70,  # Medium - general LLM
        "vader": 0.60,  # Lower - rule-based
        # Additional sources
        "google_trends": 0.65,  # Indirect proxy for retail interest
        "short_interest": 0.80,  # Quantitative squeeze data
        "premarket": 0.80,  # Price action - leading indicator
        "aftermarket": 0.80,  # Price action - leading indicator (same as premarket)
        "news_velocity": 0.70,  # Attention indicator
        "insider": 0.85,  # SEC filings - high confidence, insider actions are highly predictive
        "divergence": 0.75,  # Technical signal - moderate confidence
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

    # --- VIX CONFIDENCE SCALING (Bonus) ---
    # Apply volatility penalty to confidence during high VIX periods
    # High VIX = uncertain market = lower confidence in sentiment signals
    volatility_penalty = 1.0
    try:
        # Check if market regime data is available (contains VIX)
        from .market_regime import get_current_regime

        regime_data = get_current_regime()
        if regime_data:
            vix = regime_data.get("vix", 0.0)
            if vix > 20:  # VIX above 20 = elevated volatility
                # Scale confidence down: VIX 20 = 1.0x, VIX 30 = 0.8x, VIX 40 = 0.6x, etc.
                # Formula: 1.0 - ((vix - 20) * 0.02) with floor of 0.5
                volatility_penalty = max(0.5, 1.0 - ((vix - 20) * 0.02))

                # Apply penalty to confidence
                pre_vix_confidence = confidence
                confidence = confidence * volatility_penalty

                log.info(
                    "vix_confidence_scaling ticker=%s vix=%.2f penalty=%.2f "
                    "pre_confidence=%.3f post_confidence=%.3f",
                    ticker or "N/A",
                    vix,
                    volatility_penalty,
                    pre_vix_confidence,
                    confidence,
                )
    except ImportError:
        # market_regime module not available yet
        pass
    except Exception as e:
        log.debug("vix_confidence_scaling_failed ticker=%s err=%s", ticker or "N/A", str(e))

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


def fast_classify(
    item: NewsItem, keyword_weights: Optional[Dict[str, float]] = None
) -> ScoredItem:
    """Fast classification: only fast operations (keywords, sentiment, regime, source).

    This function performs ONLY fast operations that can complete in <100ms:
    - Keyword matching
    - VADER sentiment (no API)
    - ML sentiment scoring (batched, relatively fast)
    - Regime adjustments (VIX/SPY, cached)
    - Source credibility scoring
    - Earnings scorer

    Does NOT include slow operations like:
    - RVOL fetching/adjustment
    - Float data fetching/adjustment
    - VWAP calculation/adjustment
    - Volume/price divergence
    - Insider trading sentiment

    Parameters
    ----------
    item : NewsItem
        News item to classify
    keyword_weights : Optional[Dict[str, float]]
        Dynamic keyword weights from analyzer

    Returns
    -------
    ScoredItem
        Scored item with enriched=False
    """
    settings = get_settings()
    keyword_categories = settings.keyword_categories

    # --- WAVE 0.1: Earnings Scorer Integration ---
    earnings_result = None
    import os

    if os.getenv("FEATURE_EARNINGS_SCORER", "1") == "1":
        try:
            ticker = getattr(item, "ticker", None) or ""
            source = getattr(item, "source", None) or ""
            raw = getattr(item, "raw", None) or {}

            if not source and isinstance(raw, dict):
                source = raw.get("source", "")

            earnings_result = score_earnings_event(
                title=item.title or "",
                description=getattr(item, "summary", None) or "",
                ticker=ticker,
                source=source,
                use_api=True,
            )
        except Exception:
            earnings_result = None

    # Sentiment - Use multi-source aggregation (FAST sources only)
    sentiment, sentiment_confidence, sentiment_breakdown = aggregate_sentiment_sources(
        item, earnings_result=earnings_result
    )

    # --- Multi-dimensional sentiment ---
    multi_dim_sentiment = None
    if hasattr(item, "raw") and item.raw and isinstance(item.raw, dict):
        multi_dim_data = item.raw.get("sentiment_analysis")
        if multi_dim_data:
            try:
                from .llm_schemas import SentimentAnalysis

                multi_dim_sentiment = SentimentAnalysis(**multi_dim_data)

                if multi_dim_sentiment.confidence < 0.5:
                    log.debug(
                        "multi_dim_sentiment_rejected_low_confidence ticker=%s confidence=%.2f",
                        getattr(item, "ticker", "N/A"),
                        multi_dim_sentiment.confidence,
                    )
                    multi_dim_sentiment = None
                else:
                    if multi_dim_sentiment.confidence > sentiment_confidence:
                        sentiment_confidence = multi_dim_sentiment.confidence

                    categorical_sentiment = multi_dim_sentiment.to_numeric_sentiment()
                    sentiment = 0.7 * sentiment + 0.3 * categorical_sentiment

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
                log.debug("multi_dim_sentiment_parse_failed err=%s", str(e))

    # Store breakdown in item for debugging/analysis
    if hasattr(item, "raw") and item.raw:
        item.raw["sentiment_breakdown"] = sentiment_breakdown
        item.raw["sentiment_confidence"] = sentiment_confidence

    # Keyword hits & weights
    title_lower = (item.title or "").lower()
    summary_lower = (getattr(item, "summary", None) or "").lower()
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
                break

    # --- NEGATIVE KEYWORD DETECTION ---
    negative_keywords = []
    negative_keyword_categories = {
        "offering_negative",
        "warrant_negative",
        "dilution_negative",
        "distress_negative",
    }

    for category in hits:
        if category in negative_keyword_categories:
            negative_keywords.append(category)

    # --- OFFERING SENTIMENT CORRECTION ---
    # Apply intelligent offering stage detection BEFORE marking as negative
    # This distinguishes between:
    # - Dilutive offerings (announcement/pricing/upsize) = negative
    # - Debt/notes offerings = neutral/positive (no dilution)
    # - Offering closings = slightly positive (completion, no more dilution)
    # - Oversubscribed offerings = possibly positive (demand signal)
    offering_stage = None
    offering_corrected = False
    is_offering_related = "offering_negative" in negative_keywords

    if is_offering_related and OFFERING_SENTIMENT_AVAILABLE:
        title = item.title or ""
        summary = getattr(item, "summary", None) or ""

        # Apply offering sentiment correction
        corrected_sentiment, offering_stage, offering_corrected = (
            apply_offering_sentiment_correction(
                title=title,
                text=summary,
                current_sentiment=sentiment,
                min_confidence=0.7,
            )
        )

        if offering_corrected:
            log.info(
                "offering_sentiment_corrected ticker=%s stage=%s "
                "prev_sentiment=%.3f new_sentiment=%.3f",
                getattr(item, "ticker", "N/A"),
                offering_stage,
                sentiment,
                corrected_sentiment,
            )
            # Override sentiment with corrected value
            sentiment = corrected_sentiment

            # If offering stage is "closing" or "debt", don't treat as negative alert
            # Closing = completion of offering (anti-dilutive, slightly bullish)
            # Debt = notes/bonds offering (no equity dilution, neutral/positive)
            if offering_stage in ("closing", "debt"):
                # Remove offering_negative from negative_keywords
                negative_keywords = [
                    kw for kw in negative_keywords if kw != "offering_negative"
                ]
                log.info(
                    "offering_non_dilutive_detected ticker=%s stage=%s removed_from_negative_alerts=True",
                    getattr(item, "ticker", "N/A"),
                    offering_stage,
                )

    alert_type = "N/A"
    if negative_keywords and getattr(settings, "feature_negative_alerts", False):
        alert_type = "NEGATIVE"
        total_keyword_score = total_keyword_score * -2.0

        log.info(
            "negative_alert_detected ticker=%s negative_keywords=%s score_penalty_applied=True",
            getattr(item, "ticker", "N/A"),
            negative_keywords,
        )

    # Source weight
    src_host = (item.source_host or "").lower()
    source_weight = settings.rss_sources.get(src_host, 1.0)

    # --- Source credibility scoring ---
    credibility_weight = 1.0
    credibility_tier = 3
    source_url = getattr(item, "canonical_url", None) or getattr(item, "link", None)

    if source_url:
        credibility_tier = get_source_tier(source_url)
        credibility_weight = get_source_weight(source_url)

        # --- DYNAMIC SOURCE SCORER INTEGRATION ---
        # Optionally replace static weight with dynamic performance-based weight
        if DYNAMIC_SOURCE_SCORER_AVAILABLE and os.getenv("FEATURE_DYNAMIC_SOURCE_SCORER", "0") == "1":
            try:
                dynamic_weight = get_dynamic_source_weight(source_url)

                # Blend static and dynamic: 50% each when both available
                # This provides stability while incorporating performance data
                if dynamic_weight != 1.0:
                    original_weight = credibility_weight
                    credibility_weight = (credibility_weight * 0.5) + (dynamic_weight * 0.5)

                    log.info(
                        "dynamic_source_weight_applied url=%s static=%.2f dynamic=%.2f blended=%.2f",
                        source_url[:80] if source_url else "N/A",
                        original_weight,
                        dynamic_weight,
                        credibility_weight,
                    )
            except Exception as e:
                log.debug("dynamic_source_scorer_failed url=%s err=%s", source_url[:50] if source_url else "N/A", str(e))

        if credibility_tier == 3 and credibility_weight < 1.0:
            log.debug(
                "source_credibility_downweight url=%s tier=%d weight=%.2f",
                source_url[:100] if source_url else "N/A",
                credibility_tier,
                credibility_weight,
            )

    combined_source_weight = float(source_weight) * float(credibility_weight)

    # --- SEMANTIC KEYWORD EXTRACTION (KeyBERT) ---
    semantic_keywords = []
    if _semantic_extractor and _semantic_extractor.is_available():
        try:
            import os

            if os.getenv("FEATURE_SEMANTIC_KEYWORDS", "1") == "1":
                top_n = int(os.getenv("SEMANTIC_KEYWORDS_TOP_N", "5"))
                ngram_max = int(os.getenv("SEMANTIC_KEYWORDS_NGRAM_MAX", "3"))

                semantic_keywords = _semantic_extractor.extract_from_feed_item(
                    title=item.title or "",
                    summary=getattr(item, "summary", None) or "",
                    top_n=top_n,
                    keyphrase_ngram_range=(1, ngram_max),
                )

                log.debug(
                    "semantic_keywords_extracted ticker=%s keywords=%s",
                    getattr(item, "ticker", "N/A"),
                    semantic_keywords,
                )
        except Exception as e:
            log.debug("semantic_keyword_extraction_failed err=%s", str(e))

    # Aggregate relevance
    relevance = float(total_keyword_score) * float(combined_source_weight)

    # --- TICKER PROFILER INTEGRATION ---
    # Apply ticker-specific keyword affinity multiplier (0.5x to 2.5x)
    # This adjusts scoring based on historical performance for specific tickers
    ticker_multiplier = 1.0
    ticker = getattr(item, "ticker", None)

    if ticker and TICKER_PROFILER_AVAILABLE and os.getenv("FEATURE_TICKER_PROFILER", "1") == "1":
        try:
            profiler = get_ticker_profiler()
            if profiler:
                # Get sector from item if available
                sector = None
                if hasattr(item, "raw") and item.raw:
                    sector = item.raw.get("sector")

                ticker_multiplier = profiler.get_ticker_multiplier(
                    ticker=ticker,
                    keywords=hits,
                    sector=sector
                )

                if ticker_multiplier != 1.0:
                    log.info(
                        "ticker_profiler_applied ticker=%s multiplier=%.2f keywords=%s",
                        ticker,
                        ticker_multiplier,
                        hits[:5],  # Log first 5 keywords
                    )
        except Exception as e:
            log.debug("ticker_profiler_failed ticker=%s err=%s", ticker, str(e))

    # Apply ticker multiplier to relevance
    relevance = relevance * ticker_multiplier

    # Total score: simple combination
    total_score = relevance + sentiment

    # Earnings boost/penalty
    if earnings_result and earnings_result.get("is_earnings_result"):
        earnings_sentiment = earnings_result.get("sentiment_score", 0.0)

        if earnings_sentiment > 0.5:
            total_score += 2.0
            confidence_boost = 0.15
        elif earnings_sentiment > 0:
            total_score += 1.0
            confidence_boost = 0.10
        elif earnings_sentiment < -0.5:
            total_score -= 1.5
            confidence_boost = 0.10
        elif earnings_sentiment < 0:
            total_score -= 0.5
            confidence_boost = 0.05
        else:
            confidence_boost = 0.0

        sentiment_confidence = min(1.0, sentiment_confidence + confidence_boost)

        if "earnings" not in hits:
            hits.append("earnings")
        if sentiment_label := earnings_result.get("sentiment_label"):
            label_keyword = sentiment_label.lower().replace(" ", "_")
            if label_keyword not in hits:
                hits.append(label_keyword)

    # --- FUNDAMENTAL DATA INTEGRATION ---
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

                if fundamental_metadata.get("float_reason"):
                    float_tag = f"fundamental_{fundamental_metadata['float_reason']}"
                    if float_tag not in hits:
                        hits.append(float_tag)

                if fundamental_metadata.get("si_reason"):
                    si_tag = f"fundamental_{fundamental_metadata['si_reason']}"
                    if si_tag not in hits:
                        hits.append(si_tag)

                log.info(
                    "fundamental_boost_applied ticker=%s boost=%.3f float_score=%.3f si_score=%.3f",
                    ticker,
                    fundamental_score,
                    fundamental_metadata.get("float_score", 0.0),
                    fundamental_metadata.get("si_score", 0.0),
                )
        except ImportError:
            pass
        except Exception as e:
            log.debug(
                "fundamental_scoring_failed ticker=%s err=%s",
                ticker,
                e.__class__.__name__,
            )

    # --- MARKET REGIME ADJUSTMENT ---
    # PHASE 1 FIX (2025-11-27): Feature flag check ADDED
    # Previously ran unconditionally
    regime_multiplier = 1.0
    regime_data = None

    if os.getenv("FEATURE_MARKET_REGIME", "0") == "1":
        try:
            from .market_regime import get_current_regime

            regime_data = get_current_regime()
            regime_multiplier = regime_data.get("multiplier", 1.0)

            pre_regime_score = total_score
            total_score = total_score * regime_multiplier

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
            pass
        except Exception as e:
            log.debug("regime_adjustment_failed ticker=%s err=%s", ticker or "N/A", str(e))

    # Build ScoredItem with enriched=False
    scored: ScoredItem | dict
    try:
        scored = ScoredItem(
            relevance=relevance,
            sentiment=sentiment,
            tags=hits,
            source_weight=total_score,
            keyword_hits=hits.copy(),
            enriched=False,
            enrichment_timestamp=None,
        )
    except TypeError:
        try:
            scored = ScoredItem(relevance, sentiment, hits, total_score)
        except Exception:
            scored = {
                "relevance": relevance,
                "sentiment": sentiment,
                "keywords": hits,
                "score": total_score,
            }

    # Attach metadata to scored item (helper functions)
    def _set_attr(obj, key, value):
        if isinstance(obj, dict):
            obj[key] = value
        else:
            try:
                setattr(obj, key, value)
            except Exception:
                pass

    # Negative alert metadata
    _set_attr(scored, "alert_type", alert_type)
    _set_attr(scored, "negative_keywords", negative_keywords)

    # Multi-dimensional sentiment metadata
    if multi_dim_sentiment:
        _set_attr(scored, "market_sentiment", multi_dim_sentiment.market_sentiment)
        _set_attr(scored, "sentiment_confidence", multi_dim_sentiment.confidence)
        _set_attr(scored, "urgency", multi_dim_sentiment.urgency)
        _set_attr(scored, "risk_level", multi_dim_sentiment.risk_level)
        _set_attr(scored, "institutional_interest", multi_dim_sentiment.institutional_interest)
        _set_attr(scored, "retail_hype_score", multi_dim_sentiment.retail_hype_score)
        _set_attr(scored, "sentiment_reasoning", multi_dim_sentiment.reasoning)

    # Source credibility metadata
    _set_attr(scored, "source_credibility_tier", credibility_tier)
    _set_attr(scored, "source_credibility_weight", credibility_weight)
    _set_attr(
        scored,
        "source_credibility_category",
        get_source_category(source_url) if source_url else "unknown",
    )

    # Earnings metadata
    if earnings_result:
        _set_attr(scored, "is_earnings_result", True)
        _set_attr(scored, "earnings_sentiment_score", earnings_result.get("sentiment_score"))
        _set_attr(scored, "earnings_sentiment_label", earnings_result.get("sentiment_label"))
        _set_attr(scored, "earnings_eps_actual", earnings_result.get("eps_actual"))
        _set_attr(scored, "earnings_eps_estimate", earnings_result.get("eps_estimate"))
        _set_attr(scored, "earnings_revenue_actual", earnings_result.get("revenue_actual"))
        _set_attr(scored, "earnings_revenue_estimate", earnings_result.get("revenue_estimate"))
        _set_attr(scored, "earnings_data_source", earnings_result.get("data_source"))

    # Fundamental metadata
    if fundamental_metadata:
        _set_attr(scored, "fundamental_score", fundamental_score)
        _set_attr(scored, "fundamental_float_shares", fundamental_metadata.get("float_shares"))
        _set_attr(scored, "fundamental_short_interest", fundamental_metadata.get("short_interest"))
        _set_attr(scored, "fundamental_float_score", fundamental_metadata.get("float_score"))
        _set_attr(scored, "fundamental_si_score", fundamental_metadata.get("si_score"))
        _set_attr(scored, "fundamental_float_reason", fundamental_metadata.get("float_reason"))
        _set_attr(scored, "fundamental_si_reason", fundamental_metadata.get("si_reason"))

    # Market regime metadata
    if regime_data:
        _set_attr(scored, "market_regime", regime_data.get("regime"))
        _set_attr(scored, "market_vix", regime_data.get("vix"))
        _set_attr(scored, "market_spy_trend", regime_data.get("spy_trend"))
        _set_attr(scored, "market_regime_multiplier", regime_multiplier)
        _set_attr(scored, "market_spy_20d_return", regime_data.get("spy_20d_return"))

    # Semantic keywords metadata
    if semantic_keywords:
        _set_attr(scored, "semantic_keywords", semantic_keywords)

    # AI enrichment (optional, fast)
    try:
        adapter = get_adapter()
        enr: AIEnrichment = adapter.enrich(item.title or "", None)

        def _get_tags(obj):
            if isinstance(obj, dict):
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

        if enr.ai_tags:
            cur = set(_get_tags(scored))
            cur.update(enr.ai_tags)
            _set_tags(scored, sorted(cur))

        if enr.ai_sentiment:
            extra = _get_extra(scored)
            extra["ai_sentiment"] = {
                "label": enr.ai_sentiment.label,
                "score": float(enr.ai_sentiment.score),
            }
    except Exception:
        pass

    return scored


def enrich_scored_item(
    scored: ScoredItem,
    item: NewsItem,
) -> ScoredItem:
    """Enrich a scored item with slow operations (RVOL, float, VWAP, divergence, insider).

    This function performs ONLY slow operations that may take >100ms:
    - RVOL fetching/adjustment (API calls)
    - Float data fetching/adjustment (API calls)
    - VWAP calculation/adjustment (API calls)
    - Volume/price divergence (requires RVOL data)
    - Insider trading sentiment (SEC API calls)

    Parameters
    ----------
    scored : ScoredItem
        Scored item from fast_classify()
    item : NewsItem
        Original news item (for ticker, etc.)

    Returns
    -------
    ScoredItem
        Enriched scored item with enriched=True
    """
    import os
    import time

    # Helper to set attributes
    def _set_attr(obj, key, value):
        if isinstance(obj, dict):
            obj[key] = value
        else:
            try:
                setattr(obj, key, value)
            except Exception:
                pass

    ticker = getattr(item, "ticker", None)
    if not ticker or not ticker.strip():
        # No ticker, can't enrich with these data sources
        _set_attr(scored, "enriched", True)
        _set_attr(scored, "enrichment_timestamp", time.time())
        return scored

    # Get current total_score from scored item
    total_score = _get_score(scored)

    # --- RVOL (RELATIVE VOLUME) BOOST ---
    # PHASE 1 FIX (2025-11-27): Feature flag check ADDED
    # Previously ran unconditionally, causing mid-pump alerts
    rvol_multiplier = 1.0
    rvol_data = None

    if ticker and os.getenv("FEATURE_RVOL", "0") == "1":
        try:
            from .rvol import calculate_rvol_intraday

            rvol_data = calculate_rvol_intraday(ticker)
            if rvol_data:
                rvol_multiplier = rvol_data.get("multiplier", 1.0)

                pre_rvol_score = total_score
                total_score = total_score * rvol_multiplier

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
            pass
        except Exception as e:
            log.debug(
                "rvol_calculation_failed ticker=%s err=%s", ticker or "N/A", str(e)
            )

    # --- FLOAT-BASED CONFIDENCE ADJUSTMENT ---
    float_multiplier = 1.0
    float_data = None

    try:
        from .float_data import get_float_data

        float_data = get_float_data(ticker)
        float_multiplier = float_data.get("multiplier", 1.0)

        pre_float_score = total_score
        total_score = total_score * float_multiplier

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
        log.warning("float_adjustment_failed ticker=%s err=%s", ticker or "N/A", str(e))

    # --- VOLUME-PRICE DIVERGENCE DETECTION ---
    divergence_data = None
    divergence_adjustment = 0.0

    if rvol_data:
        try:
            from .volume_price_divergence import (
                calculate_price_change,
                calculate_volume_change_from_rvol,
                detect_divergence,
            )

            price_change_pct = calculate_price_change(ticker)
            volume_change_pct = calculate_volume_change_from_rvol(rvol_data)

            if price_change_pct is not None and volume_change_pct is not None:
                divergence_data = detect_divergence(
                    ticker=ticker,
                    price_change_pct=price_change_pct,
                    volume_change_pct=volume_change_pct,
                )

                if divergence_data:
                    divergence_adjustment = divergence_data.get("sentiment_adjustment", 0.0)

                    pre_divergence_score = total_score
                    total_score = total_score + divergence_adjustment

                    log.info(
                        "divergence_adjustment ticker=%s type=%s strength=%s "
                        "price_change=%.2f%% volume_change=%.2f%% adjustment=%.3f "
                        "pre_score=%.3f post_score=%.3f",
                        ticker,
                        divergence_data.get("divergence_type", "NONE"),
                        divergence_data.get("signal_strength", "NONE"),
                        divergence_data.get("price_change", 0.0) * 100,
                        divergence_data.get("volume_change", 0.0) * 100,
                        divergence_adjustment,
                        pre_divergence_score,
                        total_score,
                    )
        except ImportError:
            pass
        except Exception as e:
            log.debug(
                "divergence_detection_failed ticker=%s err=%s",
                ticker or "N/A",
                str(e.__class__.__name__),
            )

    # --- VWAP (VOLUME WEIGHTED AVERAGE PRICE) ANALYSIS ---
    vwap_multiplier = 1.0
    vwap_data = None

    try:
        from .vwap_calculator import calculate_vwap, get_vwap_multiplier

        vwap_data = calculate_vwap(ticker)
        if vwap_data:
            vwap_multiplier = get_vwap_multiplier(vwap_data)

            pre_vwap_score = total_score
            total_score = total_score * vwap_multiplier

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
        pass
    except Exception as e:
        log.debug(
            "vwap_calculation_failed ticker=%s err=%s", ticker or "N/A", str(e)
        )

    # Update the scored item's total_score
    _set_attr(scored, "source_weight", total_score)

    # Attach enrichment metadata
    if rvol_data:
        _set_attr(scored, "rvol", rvol_data.get("rvol"))
        _set_attr(scored, "rvol_class", rvol_data.get("rvol_class"))
        _set_attr(scored, "rvol_multiplier", rvol_data.get("multiplier"))
        _set_attr(scored, "current_volume", rvol_data.get("current_volume"))
        _set_attr(scored, "avg_volume_20d", rvol_data.get("avg_volume_20d"))

    if float_data:
        _set_attr(scored, "float_shares", float_data.get("float_shares"))
        _set_attr(scored, "float_class", float_data.get("float_class"))
        _set_attr(scored, "float_multiplier", float_data.get("multiplier"))
        _set_attr(scored, "short_interest_pct", float_data.get("short_interest_pct"))

    if divergence_data:
        _set_attr(scored, "divergence_type", divergence_data.get("divergence_type"))
        _set_attr(scored, "divergence_signal_strength", divergence_data.get("signal_strength"))
        _set_attr(scored, "divergence_sentiment_adjustment", divergence_adjustment)
        _set_attr(scored, "price_change_pct", divergence_data.get("price_change"))
        _set_attr(scored, "volume_change_pct", divergence_data.get("volume_change"))
        _set_attr(scored, "divergence_interpretation", divergence_data.get("interpretation"))

    if vwap_data:
        _set_attr(scored, "vwap", vwap_data.get("vwap"))
        _set_attr(scored, "vwap_signal", vwap_data.get("vwap_signal"))
        _set_attr(scored, "vwap_multiplier", vwap_multiplier)
        _set_attr(scored, "vwap_distance_pct", vwap_data.get("distance_from_vwap_pct"))
        _set_attr(scored, "is_above_vwap", vwap_data.get("is_above_vwap"))
        _set_attr(scored, "vwap_current_price", vwap_data.get("current_price"))
        _set_attr(scored, "vwap_cumulative_volume", vwap_data.get("cumulative_volume"))

    # Mark as enriched
    _set_attr(scored, "enriched", True)
    _set_attr(scored, "enrichment_timestamp", time.time())

    return scored


def _get_score(scored) -> float:
    """Extract numeric score from scored object or dict."""
    for name in ("source_weight", "total_score", "score", "relevance"):
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


def is_substantive_news(title: str, text: str = "") -> bool:
    """Filter non-substantive news articles.

    Rejects articles that contain no actionable information:
    - "Why [TICKER] Stock Is Down Today" summaries
    - "Company not aware of any reason" press releases
    - Generic trading updates with no content
    - Earnings previews (not results)

    Parameters
    ----------
    title : str
        Article headline/title
    text : str, optional
        Article body/summary text

    Returns
    -------
    bool
        True if the article is substantive, False if it should be filtered
    """
    # Combine title and text for pattern matching
    combined = f"{title} {text}".lower()

    # --- Reject very short titles (< 20 chars) ---
    if len(title) < 20:
        return False

    # --- Pattern 1: Summary-style articles with no substance ---
    # "Why [TICKER] Shares Are Plunging Today"
    # "Why [TICKER] Stock Is Down Today"
    # "Why [TICKER] Stock Is Moving Today"
    # Post-mortem patterns: "[Action] after [Event]" = explaining what already happened
    # "Stock Plunges After Company Cuts Outlook"
    # "Shares Drop After Missing Estimates"
    # Note: Pattern matches ticker with optional parentheses/apostrophes (e.g., "Chegg (CHGG)" or "Denny's (DENN)")
    summary_patterns = [
        r"why\s+[\w'\s()]+\s+shares?\s+(are\s+)?(plunging|soaring|moving|rallying|dropping|falling|rising|climbing|surging|tumbling)",
        r"why\s+[\w'\s()]+\s+stock\s+is\s+(up|down|moving|higher|lower)",
        r"what\s+investors\s+need\s+to\s+know\s*$",  # Standalone "What Investors Need to Know"
        r"why\s+[\w'\s()]+\s+shares?\s+(are\s+)?(up|down)\s+today",
        r"^why\s+(is\s+)?[\w'\s()]+\s+(stock|shares?)\s+(rising|falling|moving)",
        # Post-mortem patterns (stock moved, then news explains why)
        r"(stock|shares?)\s+(plunge|plummet|drop|fall|surge|soar|jump|climb|rally|tumble)s?\s+after",
        r"(plunge|plummet|drop|fall|surge|soar|jump|climb|rally|tumble)s?\s+after\s+[\w'\s]+\s+(cut|lower|reduce|miss|disappoint)",
        r"[\w'\s()]+\s+(stock|shares?)\s+(tank|crater|nosedive)s?\s+after",
    ]

    for pattern in summary_patterns:
        if re.search(pattern, combined):
            return False

    # --- Pattern 2: "We don't know" press releases ---
    # "Company not aware of any reason for price movement"
    # "Management has no explanation for trading activity"
    no_explanation_patterns = [
        r"not\s+aware\s+of\s+any\s+(material\s+)?(change|reason|explanation|information)",
        r"(has\s+)?no\s+(knowledge|explanation|information)\s+(of|regarding|for)",
        r"cannot\s+account\s+for",
        r"no\s+undisclosed\s+(material\s+)?information",
        r"no\s+material\s+changes?\s+to\s+business",
        r"(has\s+)?no\s+pending\s+announcements?",
        r"nothing\s+to\s+report\s+regarding",
    ]

    for pattern in no_explanation_patterns:
        if re.search(pattern, combined):
            return False

    # --- Pattern 3: Generic trading updates ---
    # "Trading Update" (too short/generic)
    # "TOVX Trading Activity Notice"
    # "Notice on price fluctuation"
    generic_patterns = [
        r"^trading\s+update\s*$",
        r"trading\s+activity\s+notice",
        r"notice\s+on\s+price\s+fluctuation",
        r"wish(es)?\s+to\s+clarify\s+recent\s+trading",
    ]

    for pattern in generic_patterns:
        if re.search(pattern, combined):
            return False

    # --- Pattern 4: Earnings previews (not results) ---
    # "Earnings Preview: AAPL"
    # "What to expect from XYZ earnings"
    # Note: "Earnings Results" should NOT be filtered
    earnings_preview_patterns = [
        r"earnings\s+preview(?!.*results?)",  # Preview without results
        r"what\s+to\s+expect\s+from\s+\w+\s+earnings",
        r"(ahead\s+of|before)\s+earnings",
    ]

    for pattern in earnings_preview_patterns:
        if re.search(pattern, combined):
            return False

    # If none of the filters matched, the article is substantive
    return True


def classify(
    item: NewsItem, keyword_weights: Optional[Dict[str, float]] = None
) -> ScoredItem:
    """Classify a news item and return a scored representation.

    Combines sentiment, keyword-category hits (with analyzer-provided
    dynamic weights when available), and source weighting.

    WAVE 0.1: Includes earnings result detection and sentiment scoring.

    This function now calls fast_classify() followed by enrich_scored_item()
    to maintain backward compatibility while supporting the new fast/slow
    separation architecture.
    """
    # Fast classification (keywords, sentiment, regime, source)
    scored = fast_classify(item, keyword_weights=keyword_weights)

    # Slow enrichment (RVOL, float, VWAP, divergence, insider)
    scored = enrich_scored_item(scored, item)

    return scored


def classify_legacy(
    item: NewsItem, keyword_weights: Optional[Dict[str, float]] = None
) -> ScoredItem:
    """LEGACY: Original classify() implementation before fast/slow separation.

    This function is kept for reference and comparison during migration.
    DO NOT USE - use classify() instead which calls fast_classify() + enrich_scored_item().

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

    # --- NEGATIVE KEYWORD DETECTION ---
    # Identify negative catalyst keywords (offerings, dilution, warrants, distress)
    # and flag the alert as NEGATIVE with score penalty
    negative_keywords = []
    negative_keyword_categories = {
        "offering_negative",
        "warrant_negative",
        "dilution_negative",
        "distress_negative",
    }

    for category in hits:
        if category in negative_keyword_categories:
            negative_keywords.append(category)

    # --- OFFERING SENTIMENT CORRECTION ---
    # Apply intelligent offering stage detection BEFORE marking as negative
    # This distinguishes between:
    # - Dilutive offerings (announcement/pricing/upsize) = negative
    # - Debt/notes offerings = neutral/positive (no dilution)
    # - Offering closings = slightly positive (completion, no more dilution)
    # - Oversubscribed offerings = possibly positive (demand signal)
    offering_stage = None
    offering_corrected = False
    is_offering_related = "offering_negative" in negative_keywords

    if is_offering_related and OFFERING_SENTIMENT_AVAILABLE:
        title = item.title or ""
        summary = getattr(item, "summary", None) or ""

        # Apply offering sentiment correction
        corrected_sentiment, offering_stage, offering_corrected = (
            apply_offering_sentiment_correction(
                title=title,
                text=summary,
                current_sentiment=sentiment,
                min_confidence=0.7,
            )
        )

        if offering_corrected:
            log.info(
                "offering_sentiment_corrected ticker=%s stage=%s "
                "prev_sentiment=%.3f new_sentiment=%.3f",
                getattr(item, "ticker", "N/A"),
                offering_stage,
                sentiment,
                corrected_sentiment,
            )
            # Override sentiment with corrected value
            sentiment = corrected_sentiment

            # If offering stage is "closing" or "debt", don't treat as negative alert
            # Closing = completion of offering (anti-dilutive, slightly bullish)
            # Debt = notes/bonds offering (no equity dilution, neutral/positive)
            if offering_stage in ("closing", "debt"):
                # Remove offering_negative from negative_keywords
                negative_keywords = [
                    kw for kw in negative_keywords if kw != "offering_negative"
                ]
                log.info(
                    "offering_non_dilutive_detected ticker=%s stage=%s removed_from_negative_alerts=True",
                    getattr(item, "ticker", "N/A"),
                    offering_stage,
                )

    # Apply negative alert logic if feature is enabled
    alert_type = "N/A"
    if negative_keywords and getattr(settings, "feature_negative_alerts", False):
        alert_type = "NEGATIVE"
        # Apply score penalty: invert score or make it significantly negative
        # This ensures negative catalysts are deprioritized or flagged for exit
        total_keyword_score = total_keyword_score * -2.0  # Double negative penalty

        log.info(
            "negative_alert_detected ticker=%s negative_keywords=%s score_penalty_applied=True",
            getattr(item, "ticker", "N/A"),
            negative_keywords,
        )

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

                log.debug(
                    "semantic_keywords_extracted ticker=%s keywords=%s",
                    getattr(item, "ticker", "N/A"),
                    semantic_keywords,
                )
        except Exception as e:
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
            log.debug(
                "fundamental_scoring_failed ticker=%s err=%s",
                ticker,
                e.__class__.__name__,
            )

    # --- MARKET REGIME ADJUSTMENT ---
    # PHASE 1 FIX (2025-11-27): Feature flag check ADDED (SEC Digester)
    # Previously ran unconditionally
    # Apply regime multiplier to total_score based on current market conditions
    # This adjusts scores based on overall market environment (VIX, SPY trend)
    regime_multiplier = 1.0
    regime_data = None

    if os.getenv("FEATURE_MARKET_REGIME", "0") == "1":
        try:
            from .market_regime import get_current_regime

            regime_data = get_current_regime()
            regime_multiplier = regime_data.get("multiplier", 1.0)

            # Store pre-adjustment score for logging
            pre_regime_score = total_score

            # Apply regime adjustment to total_score
            total_score = total_score * regime_multiplier

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
            log.debug("regime_adjustment_failed ticker=%s err=%s", ticker or "N/A", str(e))

    # --- RVOL (RELATIVE VOLUME) BOOST ---
    # PHASE 1 FIX (2025-11-27): Feature flag check ADDED (SEC Digester)
    # Previously ran unconditionally, causing mid-pump alerts
    # Apply RVol multiplier to boost scores for tickers with unusual volume
    # RVol >2.0x indicates elevated interest, often preceding significant price moves
    rvol_multiplier = 1.0
    rvol_data = None

    if ticker and ticker.strip() and os.getenv("FEATURE_RVOL", "0") == "1":
        try:
            from .rvol import calculate_rvol_intraday

            rvol_data = calculate_rvol_intraday(ticker)
            if rvol_data:
                rvol_multiplier = rvol_data.get("multiplier", 1.0)

                # Apply to total_score
                pre_rvol_score = total_score
                total_score = total_score * rvol_multiplier

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
        log.warning("float_adjustment_failed ticker=%s err=%s", ticker or "N/A", str(e))

    # --- VOLUME-PRICE DIVERGENCE DETECTION ---
    # Detect divergence between price movement and volume to identify:
    # - Weak rallies (price up, volume down) = bearish
    # - Strong selloff reversals (price down, volume down) = bullish
    # - Confirmed moves (price and volume aligned) = confirmation
    divergence_data = None
    divergence_adjustment = 0.0

    if ticker and ticker.strip() and rvol_data:
        try:
            from .volume_price_divergence import (
                calculate_price_change,
                calculate_volume_change_from_rvol,
                detect_divergence,
            )

            # Calculate price change (today vs yesterday)
            price_change_pct = calculate_price_change(ticker)

            # Calculate volume change from RVol data
            volume_change_pct = calculate_volume_change_from_rvol(rvol_data)

            if price_change_pct is not None and volume_change_pct is not None:
                # Detect divergence pattern
                divergence_data = detect_divergence(
                    ticker=ticker,
                    price_change_pct=price_change_pct,
                    volume_change_pct=volume_change_pct,
                )

                if divergence_data:
                    divergence_adjustment = divergence_data.get("sentiment_adjustment", 0.0)

                    # Apply sentiment adjustment to total_score
                    pre_divergence_score = total_score
                    total_score = total_score + divergence_adjustment

                    log.info(
                        "divergence_adjustment ticker=%s type=%s strength=%s "
                        "price_change=%.2f%% volume_change=%.2f%% adjustment=%.3f "
                        "pre_score=%.3f post_score=%.3f",
                        ticker,
                        divergence_data.get("divergence_type", "NONE"),
                        divergence_data.get("signal_strength", "NONE"),
                        divergence_data.get("price_change", 0.0) * 100,
                        divergence_data.get("volume_change", 0.0) * 100,
                        divergence_adjustment,
                        pre_divergence_score,
                        total_score,
                    )
        except ImportError:
            # volume_price_divergence module not available (shouldn't happen)
            pass
        except Exception as e:
            log.debug(
                "divergence_detection_failed ticker=%s err=%s",
                ticker or "N/A",
                str(e.__class__.__name__),
            )

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

    # --- NEGATIVE ALERT METADATA: Attach negative alert data to scored item ---
    # Add alert_type and negative_keywords to the scored item
    try:
        # Helper to set attributes on both dict and object types
        def _set_neg_attr(obj, key, value):
            if isinstance(obj, dict):
                obj[key] = value
            else:
                try:
                    setattr(obj, key, value)
                except Exception:
                    pass

        _set_neg_attr(scored, "alert_type", alert_type)
        _set_neg_attr(scored, "negative_keywords", negative_keywords)
    except Exception:
        # Don't let metadata attachment break the pipeline
        pass

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

    # --- DIVERGENCE DATA: Attach volume-price divergence metadata to scored item ---
    # Add divergence detection data to the scored item for downstream processing
    if divergence_data:
        try:
            # Helper to set attributes on both dict and object types
            def _set_div_attr(obj, key, value):
                if isinstance(obj, dict):
                    obj[key] = value
                else:
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass

            _set_div_attr(scored, "divergence_type", divergence_data.get("divergence_type"))
            _set_div_attr(
                scored, "divergence_signal_strength", divergence_data.get("signal_strength")
            )
            _set_div_attr(
                scored, "divergence_sentiment_adjustment", divergence_adjustment
            )
            _set_div_attr(scored, "price_change_pct", divergence_data.get("price_change"))
            _set_div_attr(
                scored, "volume_change_pct", divergence_data.get("volume_change")
            )
            _set_div_attr(
                scored, "divergence_interpretation", divergence_data.get("interpretation")
            )
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
