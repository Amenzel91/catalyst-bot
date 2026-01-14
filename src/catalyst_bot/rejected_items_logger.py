"""
Rejected Items Logger - MOA Phase 1: Data Capture

Logs items that were rejected by filters so they can be analyzed later
by the Missed Opportunities Analyzer to discover new keywords and optimize filters.

Only logs items within price range ($0.10-$10) to avoid massive files.

CRITICAL FIX: Added deduplication based on (ticker, rejection_ts) tuple to prevent
duplicate logging of the same rejection event. Uses a bounded LRU cache for memory efficiency.

MOA Phase 2 (Jan 2026): Added integration with MOA real-time outcome tracking database.
Rejected items are now also recorded to the SQLite database for incremental price tracking.

Author: Claude Code (MOA Phase 1)
Date: 2025-10-10
Updated: 2025-10-16 (Added deduplication)
Updated: 2026-01-06 (Added MOA outcome tracking integration)
"""

import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Price range filter: only log items within this range
PRICE_FLOOR = 0.10
PRICE_CEILING = 10.00

# Deduplication cache: stores (ticker, rejection_ts_minute) tuples
# Uses OrderedDict as an LRU cache with max 10,000 entries
_DEDUPE_CACHE: OrderedDict[tuple, bool] = OrderedDict()
_DEDUPE_CACHE_MAX_SIZE = 10_000  # Keep last 10k rejections (~ 1-2 days at high volume)


def should_log_rejected_item(price: Optional[float]) -> bool:
    """
    Determine if a rejected item should be logged based on price range.

    Only items priced between $0.10 and $10.00 are logged to the rejected items file.
    Items outside this range are not useful for the MOA system.

    Args:
        price: Current price of the ticker (None if unknown)

    Returns:
        bool: True if item should be logged, False otherwise
    """
    if price is None:
        return False

    return PRICE_FLOOR <= price <= PRICE_CEILING


def _dedupe_check_and_add(ticker: str, rejection_reason: str) -> bool:
    """
    Check if this (ticker, rejection_reason) tuple was already logged recently.

    Uses a bounded LRU cache to track recent rejections and prevent duplicates.
    The cache is keyed by (ticker, rejection_reason, timestamp_minute) to deduplicate
    within 1-minute windows.

    Args:
        ticker: Stock ticker symbol
        rejection_reason: Reason code (LOW_SCORE, HIGH_PRICE, etc.)

    Returns:
        bool: True if this is a new rejection (should log), False if duplicate
    """
    global _DEDUPE_CACHE

    # Create deduplication key: (ticker, reason, minute)
    # This groups rejections within 1-minute windows to prevent rapid-fire duplicates
    now = datetime.now(timezone.utc)
    minute_ts = now.replace(second=0, microsecond=0).isoformat()
    dedupe_key = (ticker.upper(), rejection_reason, minute_ts)

    # Check if we've seen this key recently
    if dedupe_key in _DEDUPE_CACHE:
        # Move to end (LRU)
        _DEDUPE_CACHE.move_to_end(dedupe_key)
        return False  # Duplicate, skip logging

    # New rejection - add to cache
    _DEDUPE_CACHE[dedupe_key] = True

    # Trim cache if it exceeds max size (LRU eviction)
    if len(_DEDUPE_CACHE) > _DEDUPE_CACHE_MAX_SIZE:
        # Remove oldest entry (FIFO from front)
        _DEDUPE_CACHE.popitem(last=False)

    return True  # New rejection, should log


def log_rejected_item(
    item: Dict[str, Any],
    rejection_reason: str,
    price: Optional[float] = None,
    score: Optional[float] = None,
    sentiment: Optional[float] = None,
    keywords: Optional[list] = None,
    scored: Optional[Any] = None,
) -> None:
    """
    Log a rejected item to data/rejected_items.jsonl with deduplication.

    Uses a bounded LRU cache to prevent duplicate logging of the same rejection
    event within 1-minute windows. This prevents log file bloat when the same
    ticker is rejected multiple times in quick succession.

    Args:
        item: Original news item dict
        rejection_reason: Reason for rejection (LOW_SCORE, HIGH_PRICE, etc.)
        price: Current price (required for MOA)
        score: Classification score
        sentiment: Sentiment score
        keywords: List of keywords found
        scored: Full scored object/dict from classifier (optional, for sentiment breakdown)
    """
    # Only log items within price range
    if not should_log_rejected_item(price):
        return

    # Extract core fields
    ticker = item.get("ticker", "").strip()
    if not ticker:
        return  # Skip items without tickers

    # CRITICAL FIX: Check for duplicates before logging
    # This prevents the same rejection from being logged multiple times
    if not _dedupe_check_and_add(ticker, rejection_reason):
        return  # Duplicate rejection, skip logging

    # Extract sentiment breakdown from item's raw dict
    # The breakdown is stored in item.raw by classify.py (line 341-342)
    sentiment_breakdown = None
    sentiment_confidence = None
    sentiment_sources_used = None

    try:
        # Check if item has 'raw' field with sentiment data
        raw_data = item.get("raw")
        if raw_data and isinstance(raw_data, dict):
            sentiment_breakdown = raw_data.get("sentiment_breakdown")
            sentiment_confidence = raw_data.get("sentiment_confidence")

            # If we got a breakdown, calculate which sources were used
            if sentiment_breakdown and isinstance(sentiment_breakdown, dict):
                sentiment_sources_used = [
                    source
                    for source in ["vader", "ml", "llm", "earnings"]
                    if sentiment_breakdown.get(source) is not None
                ]
    except Exception:
        # Silently ignore extraction errors
        pass

    # Build cls section with enhanced sentiment data
    cls_data = {
        "score": score or 0.0,
        "sentiment": sentiment or 0.0,
        "keywords": keywords or [],
    }

    # Add sentiment breakdown if available
    if sentiment_breakdown:
        cls_data["sentiment_breakdown"] = sentiment_breakdown
    if sentiment_confidence is not None:
        cls_data["sentiment_confidence"] = sentiment_confidence
    if sentiment_sources_used:
        cls_data["sentiment_sources_used"] = sentiment_sources_used

    # Build rejected item record
    rejected_item = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "title": item.get("title", ""),
        "source": item.get("source", ""),
        "price": price,
        "cls": cls_data,
        "rejected": True,
        "rejection_reason": rejection_reason,
    }

    # Add market regime data if available from scored object
    if scored:
        try:
            # Extract regime fields from scored object
            if hasattr(scored, "market_regime"):
                rejected_item["market_regime"] = getattr(scored, "market_regime", None)
                rejected_item["market_vix"] = getattr(scored, "market_vix", None)
                rejected_item["market_spy_trend"] = getattr(scored, "market_spy_trend", None)
                rejected_item["market_regime_multiplier"] = getattr(
                    scored, "market_regime_multiplier", None
                )
            elif isinstance(scored, dict):
                rejected_item["market_regime"] = scored.get("market_regime")
                rejected_item["market_vix"] = scored.get("market_vix")
                rejected_item["market_spy_trend"] = scored.get("market_spy_trend")
                rejected_item["market_regime_multiplier"] = scored.get("market_regime_multiplier")
        except Exception:
            # Silently ignore regime extraction errors
            pass

    # Write to JSONL file
    log_path = Path("data/rejected_items.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rejected_item, ensure_ascii=False) + "\n")
    except Exception:
        # Silently fail - don't crash the bot if logging fails
        pass

    # MOA Phase 2: Record rejection to SQLite database for real-time outcome tracking
    # This enables the MOA system to track price movements of rejected items
    try:
        from .moa.rejection_recorder import record_rejection_simple

        # Extract keywords as list from the cls_data
        kw_list: List[str] = cls_data.get("keywords", [])

        record_rejection_simple(
            ticker=ticker,
            reason=rejection_reason,
            score=score or 0.0,
            price=price or 0.0,
            keywords=kw_list,
            source=item.get("source", "unknown"),
            headline=item.get("title", ""),
        )
    except ImportError:
        # MOA module not available - silently skip
        pass
    except Exception:
        # Don't crash on MOA recording errors
        pass


def get_rejection_stats() -> Dict[str, int]:
    """
    Get statistics about rejected items logged today.

    Returns:
        Dict with counts by rejection reason
    """
    log_path = Path("data/rejected_items.jsonl")

    if not log_path.exists():
        return {}

    today = datetime.now(timezone.utc).date().isoformat()
    stats: Dict[str, int] = {}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    ts = item.get("ts", "")

                    # Only count today's items
                    if ts.startswith(today):
                        reason = item.get("rejection_reason", "UNKNOWN")
                        stats[reason] = stats.get(reason, 0) + 1
                except Exception:
                    continue
    except Exception:
        return {}

    return stats


def clear_old_rejected_items(days_to_keep: int = 30) -> int:
    """
    Remove rejected items older than specified days.

    Args:
        days_to_keep: Number of days to retain (default 30)

    Returns:
        Number of items removed
    """
    log_path = Path("data/rejected_items.jsonl")

    if not log_path.exists():
        return 0

    cutoff = datetime.now(timezone.utc).timestamp() - (days_to_keep * 86400)
    kept_items = []
    removed_count = 0

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    ts_str = item.get("ts", "")

                    # Parse timestamp
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                    if ts.timestamp() >= cutoff:
                        kept_items.append(line)
                    else:
                        removed_count += 1
                except Exception:
                    # Keep items we can't parse
                    kept_items.append(line)

        # Rewrite file with kept items
        if removed_count > 0:
            with open(log_path, "w", encoding="utf-8") as f:
                f.writelines(kept_items)
    except Exception:
        return 0

    return removed_count
