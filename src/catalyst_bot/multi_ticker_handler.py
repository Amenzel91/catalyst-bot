# -*- coding: utf-8 -*-
"""Multi-ticker article handling and primary ticker detection.

WAVE 3 Data Quality: Improve handling of articles that mention multiple tickers
by scoring ticker relevance and selecting only primary subjects for alerting.

PROBLEM:
- Articles mentioning multiple tickers are sent to all mentioned tickers
- Secondary mentions create false positives (e.g., "AAPL down, MSFT up" → both)
- No primary ticker detection
- Users receive alerts where their ticker is barely mentioned
- Duplicate alerts with different primary tickers for same article

SOLUTION:
- Score each ticker based on position in title, frequency, and context
- Alert only primary ticker(s) with relevance score >= threshold
- Include secondary tickers in alert metadata: "Also mentions: X, Y, Z"
- Filter out low-relevance tickers (score < 40) entirely
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .logging_utils import get_logger

log = get_logger(__name__)


def score_ticker_relevance(ticker: str, title: str, text: str) -> float:
    """Score how relevant an article is to a specific ticker (0-100).

    Scoring algorithm:
    - Title appearance (50 points max):
      * Earlier in title = higher score
      * Position-based: 50 - (position/length * 20)
      * Example: ticker at start = 50, ticker at end = 30
    - First paragraph (30 points max):
      * Ticker in first 300 chars = 30 points
    - Frequency (20 points max):
      * Mentions throughout article
      * min(mentions * 5, 20) points

    Args:
        ticker: Ticker symbol to score (e.g., "AAPL")
        title: Article title
        text: Article body/summary text

    Returns:
        Relevance score from 0-100
        - 100 = highly relevant (ticker is main subject)
        - 40-60 = moderately relevant (ticker is discussed)
        - <40 = barely mentioned (likely comparison/context)

    Examples:
        >>> score_ticker_relevance("AAPL", "AAPL Reports Q3 Earnings Beat", "Apple Inc...")
        95.0  # High score: title start + first para + multiple mentions

        >>> score_ticker_relevance("MSFT", "AAPL Down 5%, MSFT Up 2%", "Markets today...")
        35.0  # Low score: mentioned but not primary subject
    """
    if not ticker:
        return 0.0

    ticker_upper = ticker.upper().strip()
    title_upper = (title or "").upper()
    text_upper = (text or "").upper()

    score = 0.0

    # ═══════════════════════════════════════════════════════════════════════
    # TITLE APPEARANCE: 50 points max (earlier = more important)
    # ═══════════════════════════════════════════════════════════════════════
    if ticker_upper in title_upper:
        # Find position of first occurrence
        position = title_upper.index(ticker_upper)
        title_len = max(len(title_upper), 1)  # Avoid division by zero

        # Score decreases as ticker appears later in title
        # Position 0 (start) → 50 points
        # Position at 40% → 42 points
        # Position at end → 30 points
        position_penalty = (position / title_len) * 20
        title_score = 50 - position_penalty
        score += max(title_score, 30)  # Minimum 30 if in title at all

    # ═══════════════════════════════════════════════════════════════════════
    # FIRST PARAGRAPH: 30 points max
    # ═══════════════════════════════════════════════════════════════════════
    first_para = text_upper[:300] if text_upper else ""
    if ticker_upper in first_para:
        score += 30

    # ═══════════════════════════════════════════════════════════════════════
    # FREQUENCY: 20 points max (more mentions = more relevant)
    # ═══════════════════════════════════════════════════════════════════════
    full_text = f"{title_upper} {text_upper}"
    mentions = full_text.count(ticker_upper)
    # Each mention = 5 points, capped at 20
    score += min(mentions * 5, 20)

    # Clamp to valid range
    final_score = min(score, 100.0)

    log.debug(
        "ticker_relevance_scored ticker=%s score=%.1f in_title=%s in_first_para=%s mentions=%d",
        ticker,
        final_score,
        ticker_upper in title_upper,
        ticker_upper in first_para,
        mentions,
    )

    return final_score


def select_primary_tickers(
    ticker_scores: Dict[str, float],
    min_score: float = 40.0,
    max_tickers: int = 2,
    score_diff_threshold: float = 30.0,
) -> List[str]:
    """Select primary ticker(s) from a set of scored tickers.

    Selection strategy:
    1. Filter out tickers below min_score threshold
    2. Sort by score descending
    3. If top scorer is >score_diff_threshold higher than 2nd → single primary
    4. If scores within score_diff_threshold → multi-ticker story (keep top N)

    Args:
        ticker_scores: Dict mapping ticker → relevance score
        min_score: Minimum score to be considered (default: 40)
        max_tickers: Maximum number of primary tickers (default: 2)
        score_diff_threshold: Score gap to consider truly single-ticker (default: 30)

    Returns:
        List of primary ticker symbols (1-2 tickers)

    Examples:
        >>> scores = {"AAPL": 85, "MSFT": 25, "GOOGL": 15}
        >>> select_primary_tickers(scores, min_score=40)
        ["AAPL"]  # Only AAPL above threshold

        >>> scores = {"AAPL": 75, "GOOGL": 70}
        >>> select_primary_tickers(scores, score_diff_threshold=30)
        ["AAPL", "GOOGL"]  # Both high + close scores = true multi-ticker
    """
    if not ticker_scores:
        return []

    # Filter by minimum score
    qualified = {t: s for t, s in ticker_scores.items() if s >= min_score}

    if not qualified:
        log.debug(
            "no_qualified_tickers all_scores=%s min_score=%.1f",
            {t: f"{s:.1f}" for t, s in ticker_scores.items()},
            min_score,
        )
        return []

    # Sort by score descending
    sorted_tickers = sorted(qualified.items(), key=lambda x: x[1], reverse=True)

    # Extract top ticker
    top_ticker, top_score = sorted_tickers[0]

    # If only one qualified ticker, return it
    if len(sorted_tickers) == 1:
        log.info(
            "single_primary_ticker ticker=%s score=%.1f",
            top_ticker,
            top_score,
        )
        return [top_ticker]

    # Check score difference with second ticker
    second_ticker, second_score = sorted_tickers[1]
    score_diff = top_score - second_score

    # Single primary if score difference exceeds threshold
    if score_diff > score_diff_threshold:
        log.info(
            "single_primary_ticker_by_margin ticker=%s score=%.1f "
            "second=%s second_score=%.1f margin=%.1f",
            top_ticker,
            top_score,
            second_ticker,
            second_score,
            score_diff,
        )
        return [top_ticker]

    # Multi-ticker story: return top N tickers (up to max_tickers)
    primary_tickers = [t for t, _ in sorted_tickers[:max_tickers]]

    log.info(
        "multi_ticker_story primary_tickers=%s scores=%s",
        ",".join(primary_tickers),
        {t: f"{s:.1f}" for t, s in sorted_tickers[:max_tickers]},
    )

    return primary_tickers


def should_alert_for_ticker(
    ticker: str,
    article_data: Dict,
    min_score: float = 40.0,
) -> Tuple[bool, Optional[float]]:
    """Determine if a ticker should receive an alert for this article.

    Args:
        ticker: Ticker to evaluate
        article_data: Dict with keys 'title', 'text', 'summary'
        min_score: Minimum relevance score required (default: 40)

    Returns:
        Tuple of (should_alert, relevance_score)
        - should_alert: True if ticker is relevant enough
        - relevance_score: Numeric relevance score (0-100) or None if error
    """
    try:
        title = article_data.get("title", "")
        # Prefer summary over text for body content
        text = article_data.get("summary") or article_data.get("text", "")

        score = score_ticker_relevance(ticker, title, text)

        should_alert = score >= min_score

        if not should_alert:
            log.debug(
                "ticker_filtered_low_relevance ticker=%s score=%.1f min_score=%.1f",
                ticker,
                score,
                min_score,
            )

        return (should_alert, score)

    except Exception as e:
        log.warning(
            "ticker_relevance_check_failed ticker=%s err=%s",
            ticker,
            str(e),
        )
        # On error, allow through (don't block on technical failures)
        return (True, None)


def analyze_multi_ticker_article(
    tickers: List[str],
    article_data: Dict,
    min_score: float = 40.0,
    max_primary: int = 2,
    score_diff_threshold: float = 30.0,
) -> Tuple[List[str], List[str], Dict[str, float]]:
    """Analyze an article with multiple tickers and select primary subjects.

    This is the main entry point for multi-ticker article handling.
    Scores all tickers, selects primary ones, and separates secondary mentions.

    Args:
        tickers: List of all tickers mentioned in article
        article_data: Dict with 'title', 'text', 'summary' keys
        min_score: Minimum relevance score (default: 40)
        max_primary: Maximum primary tickers to alert (default: 2)
        score_diff_threshold: Score gap for single-ticker classification (default: 30)

    Returns:
        Tuple of (primary_tickers, secondary_tickers, all_scores)
        - primary_tickers: List of tickers that should receive alerts
        - secondary_tickers: List of mentioned tickers below threshold
        - all_scores: Dict mapping all tickers to their relevance scores

    Example:
        >>> article = {
        ...     "title": "AAPL Reports Record Q3, Analysts Upgrade; MSFT Mentioned",
        ...     "summary": "Apple Inc (AAPL) announced..."
        ... }
        >>> primary, secondary, scores = analyze_multi_ticker_article(
        ...     ["AAPL", "MSFT"], article
        ... )
        >>> primary
        ["AAPL"]
        >>> secondary
        ["MSFT"]
        >>> scores
        {"AAPL": 95.0, "MSFT": 35.0}
    """
    if not tickers:
        return ([], [], {})

    title = article_data.get("title", "")
    text = article_data.get("summary") or article_data.get("text", "")

    # Score all tickers
    ticker_scores = {}
    for ticker in tickers:
        score = score_ticker_relevance(ticker, title, text)
        ticker_scores[ticker] = score

    # Select primary tickers
    primary_tickers = select_primary_tickers(
        ticker_scores,
        min_score=min_score,
        max_tickers=max_primary,
        score_diff_threshold=score_diff_threshold,
    )

    # Separate secondary tickers (mentioned but not primary)
    secondary_tickers = [t for t in tickers if t not in primary_tickers]

    log.info(
        "multi_ticker_analysis_complete title=%s total_tickers=%d "
        "primary=%s secondary=%s scores=%s",
        title[:50] if title else "N/A",
        len(tickers),
        ",".join(primary_tickers) if primary_tickers else "none",
        ",".join(secondary_tickers) if secondary_tickers else "none",
        {t: f"{s:.1f}" for t, s in ticker_scores.items()},
    )

    return (primary_tickers, secondary_tickers, ticker_scores)
