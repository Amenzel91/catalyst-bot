"""
Accepted Items Logger - MOA Negative Keyword Tracking

Logs items that were ACCEPTED by the bot (sent as alerts) so they can be
analyzed later to identify false positives - catalysts that didn't produce
profitable outcomes.

This enables MOA to distinguish:
- Keywords in missed opportunities (should be weighted HIGHER)
- Keywords in false positives (should be weighted LOWER or removed)
- Keywords in true positives / accepted items (current weights are good)

This prevents MOA from adding keywords that appear frequently in both
accepted AND rejected items (which would increase false positives).

Only logs items within price range ($0.10-$10) to match rejected_items_logger.

Author: Claude Code (Agent 4: False Positive Analysis)
Date: 2025-10-12
Updated: 2025-10-14 (Added price filtering and negative keyword tracking)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Price range filter: only log items within this range (matches rejected_items_logger)
PRICE_FLOOR = 0.10
PRICE_CEILING = 10.00


def should_log_accepted_item(price: Optional[float]) -> bool:
    """
    Determine if an accepted item should be logged based on price range.

    Only items priced between $0.10 and $10.00 are logged to the accepted items file.
    Items outside this range are not useful for the MOA system (matches rejected items logic).

    Args:
        price: Current price of the ticker (None if unknown)

    Returns:
        bool: True if item should be logged, False otherwise
    """
    if price is None:
        return False

    return PRICE_FLOOR <= price <= PRICE_CEILING


def log_accepted_item(
    item: Dict[str, Any],
    price: Optional[float] = None,
    score: Optional[float] = None,
    sentiment: Optional[float] = None,
    keywords: Optional[list] = None,
    scored: Optional[Any] = None,
) -> None:
    """
    Log an accepted item to data/accepted_items.jsonl.

    This allows MOA to track which keywords appear in GOOD alerts (true positives)
    vs BAD alerts (false positives), preventing false positive keywords from being added.

    Args:
        item: Original news item dict
        price: Current price at alert time (required for MOA)
        score: Classification score
        sentiment: Sentiment score
        keywords: List of keywords found
        scored: Full scored object/dict from classifier (optional, for sentiment breakdown)
    """
    # Only log items within price range
    if not should_log_accepted_item(price):
        return

    # Extract core fields
    ticker = item.get("ticker", "").strip()
    if not ticker:
        return  # Skip items without tickers

    # Extract sentiment breakdown if available
    sentiment_breakdown = None
    sentiment_confidence = None
    sentiment_sources_used = None

    try:
        raw_data = item.get("raw")
        if raw_data and isinstance(raw_data, dict):
            sentiment_breakdown = raw_data.get("sentiment_breakdown")
            sentiment_confidence = raw_data.get("sentiment_confidence")

            if sentiment_breakdown and isinstance(sentiment_breakdown, dict):
                sentiment_sources_used = [
                    source
                    for source in ["vader", "ml", "llm", "earnings"]
                    if sentiment_breakdown.get(source) is not None
                ]
    except Exception:
        pass

    # Build cls section with classification data
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

    # Build accepted item record
    accepted_item = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "title": item.get("title", ""),
        "source": item.get("source", ""),
        "summary": item.get("summary", ""),
        "link": item.get("link", ""),
        "price": price,
        "cls": cls_data,
        "accepted": True,
    }

    # Add market regime data if available from scored object
    if scored:
        try:
            # Extract regime fields from scored object
            if hasattr(scored, "market_regime"):
                accepted_item["market_regime"] = getattr(scored, "market_regime", None)
                accepted_item["market_vix"] = getattr(scored, "market_vix", None)
                accepted_item["market_spy_trend"] = getattr(
                    scored, "market_spy_trend", None
                )
                accepted_item["market_regime_multiplier"] = getattr(
                    scored, "market_regime_multiplier", None
                )
            elif isinstance(scored, dict):
                accepted_item["market_regime"] = scored.get("market_regime")
                accepted_item["market_vix"] = scored.get("market_vix")
                accepted_item["market_spy_trend"] = scored.get("market_spy_trend")
                accepted_item["market_regime_multiplier"] = scored.get(
                    "market_regime_multiplier"
                )
        except Exception:
            # Silently ignore regime extraction errors
            pass

    # Write to JSONL file
    log_path = Path("data/accepted_items.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(accepted_item, ensure_ascii=False) + "\n")
    except Exception:
        # Silently fail - don't crash the bot if logging fails
        pass


def get_accepted_stats() -> Dict[str, int]:
    """
    Get statistics about accepted items logged today.

    Returns:
        Dict with counts by source and total count
    """
    log_path = Path("data/accepted_items.jsonl")

    if not log_path.exists():
        return {}

    today = datetime.now(timezone.utc).date().isoformat()
    stats: Dict[str, int] = {"total": 0}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    ts = item.get("ts", "")

                    # Only count today's items
                    if ts.startswith(today):
                        stats["total"] += 1
                        source = item.get("source", "unknown")
                        source_key = f"source_{source}"
                        stats[source_key] = stats.get(source_key, 0) + 1
                except Exception:
                    continue
    except Exception:
        return {}

    return stats


def clear_old_accepted_items(days_to_keep: int = 30) -> int:
    """
    Remove accepted items older than specified days.

    Args:
        days_to_keep: Number of days to retain (default 30)

    Returns:
        Number of items removed
    """
    log_path = Path("data/accepted_items.jsonl")

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


# ============================================================================
# INTEGRATION INSTRUCTIONS
# ============================================================================
"""
INTEGRATION POINT:
==================
This should be called from runner.py after an alert is successfully sent to Discord.

Location: runner.py, around line 1220-1240, after send_alert_safe() succeeds

Integration code:
-----------------
```python
from .accepted_items_logger import log_accepted_item

# After send_alert_safe() returns True
if ok:  # Alert was sent successfully
    # Log this as an accepted item for MOA tracking
    try:
        log_accepted_item(
            item=it,  # Original item dict
            price=last_px,  # Current price
            score=scored.score if hasattr(scored, "score") else None,
            sentiment=scored.sentiment if hasattr(scored, "sentiment") else None,
            keywords=scored.keywords if hasattr(scored, "keywords") else [],
            scored=scored,  # Full scored object for market regime data
        )
    except Exception as e:
        # Don't fail the alert if logging fails
        log.debug(f"accepted_item_logging_failed ticker={ticker} err={e}")
```

WHY THIS MATTERS FOR MOA (Negative Keyword Tracking):
=====================================================
Without accepted_items tracking, MOA could suggest adding keywords that:
1. Appear in missed opportunities (good moves we didn't catch) ✓
2. BUT ALSO appear in false positives (bad alerts we sent) ✗

Example Problem:
---------------
- Keyword "partnership" appears in 10 rejected items that went +50%
- MOA suggests adding "partnership" with high weight
- BUT "partnership" also appears in 20 accepted items that went -10% (false positives)
- Without this logger, MOA can't see that "partnership" has a 2:1 false positive ratio

With accepted_items tracking, MOA can calculate:
------------------------------------------------
- Keyword win rate: % of accepted items with keyword that were true positives
- False positive rate: % of accepted items with keyword that were false positives
- Net value: Only suggest keywords with high win rate AND low false positive rate

This prevents MOA from adding keywords that increase noise instead of signal.

DATAFLOW:
=========
1. Item passes all filters in classify.py (score > threshold, sentiment > threshold)
2. runner.py sends alert to Discord via send_alert_safe()
3. Alert succeeds (ok=True)
4. log_accepted_item() writes to data/accepted_items.jsonl
5. MOA analyzer compares accepted_items vs rejected_items to find optimal keywords

PRICE FILTERING:
===============
Only items priced between $0.10 and $10.00 are logged, matching rejected_items_logger.
This prevents massive log files and focuses on the price range where MOA is most useful.

FUTURE ENHANCEMENT:
==================
Once breakout_feedback.py tracks actual outcomes (true positive vs false positive),
we can enhance log_accepted_item() to include outcome data:
- outcome: "true_positive" | "false_positive" | "pending"
- max_gain_pct: Highest % gain achieved
- final_pnl_pct: Final % gain/loss at tracking end

This would enable even more precise keyword optimization by comparing:
- Keywords in true positives (definitely keep/increase weight)
- Keywords in false positives (definitely lower weight or remove)
- Keywords in missed opportunities (consider adding if not in false positives)
"""
