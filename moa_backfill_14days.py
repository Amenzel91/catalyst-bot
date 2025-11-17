"""
MOA 14-Day Backfill Script
===========================

Backfills price outcomes for rejected items from the last 14 days only.
This provides fresh data for the MOA rolling window analysis.

Usage:
    python moa_backfill_14days.py
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from catalyst_bot.moa_price_tracker import record_outcome
from catalyst_bot.logging_utils import get_logger

log = get_logger("moa_backfill")

def backfill_last_14_days():
    """Backfill outcomes for last 14 days of rejected items."""

    # Load rejected items
    rejected_path = Path("data/rejected_items.jsonl")
    if not rejected_path.exists():
        log.error("rejected_items_not_found")
        return

    # Calculate 14-day cutoff
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)

    log.info(f"backfill_start cutoff={cutoff.isoformat()}")

    # Read and filter rejected items
    recent_items = []
    with open(rejected_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                ts_str = item.get("ts", "")

                # Parse timestamp
                if "." in ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                else:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                # Only include last 14 days
                if ts >= cutoff:
                    recent_items.append(item)

            except Exception as e:
                log.warning(f"parse_failed err={e}")
                continue

    log.info(f"filtered_items total={len(recent_items)} since={cutoff.isoformat()}")

    if not recent_items:
        log.warning("no_recent_rejections")
        return

    # Backfill outcomes for each timeframe
    timeframes = ["1h", "4h", "1d", "7d"]

    for timeframe in timeframes:
        log.info(f"backfilling_timeframe timeframe={timeframe}")
        success_count = 0
        error_count = 0

        for item in recent_items:
            ticker = item.get("ticker", "").strip()
            ts_str = item.get("ts", "")
            price = item.get("price")
            reason = item.get("rejection_reason", "UNKNOWN")

            if not ticker or not ts_str or price is None:
                continue

            try:
                result = record_outcome(
                    ticker=ticker,
                    timeframe=timeframe,
                    rejection_ts=ts_str,
                    rejection_price=price,
                    rejection_reason=reason,
                )

                if result:
                    success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                log.warning(f"record_failed ticker={ticker} timeframe={timeframe} err={e}")
                error_count += 1
                continue

        log.info(f"timeframe_complete timeframe={timeframe} success={success_count} errors={error_count}")

    log.info("backfill_complete")

if __name__ == "__main__":
    backfill_last_14_days()
