"""
False Positive Tracker - Outcome Tracking for Accepted Items

Fetches price outcomes for accepted items to identify false positives.
Reuses logic from historical_bootstrapper for consistent outcome tracking.

Classification:
- SUCCESS: 1h return > 2% OR 4h return > 3% OR 1d return > 5%
- FAILURE: All timeframes negative or minimal positive (<1%)

Author: Claude Code (Agent 4: False Positive Analysis)
Date: 2025-10-12
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

from .logging_utils import get_logger

log = get_logger("false_positive_tracker")

# Success thresholds for outcome classification
SUCCESS_THRESHOLDS = {
    "1h": 2.0,  # 1h return > 2% = SUCCESS
    "4h": 3.0,  # 4h return > 3% = SUCCESS
    "1d": 5.0,  # 1d return > 5% = SUCCESS
}

# Timeframes to track
TIMEFRAMES = {
    "1h": 1,
    "4h": 4,
    "1d": 24,
}


def _repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def _ensure_fp_dirs() -> Tuple[Path, Path]:
    """Ensure false_positives directories exist and return paths."""
    root = _repo_root()
    fp_dir = root / "data" / "false_positives"
    fp_dir.mkdir(parents=True, exist_ok=True)
    return root, fp_dir


def read_accepted_items() -> List[Dict[str, Any]]:
    """
    Read accepted items from data/accepted_items.jsonl.

    Returns:
        List of accepted item dictionaries
    """
    root, _ = _ensure_fp_dirs()
    accepted_path = root / "data" / "accepted_items.jsonl"

    if not accepted_path.exists():
        log.warning(f"accepted_items_not_found path={accepted_path}")
        return []

    items = []
    try:
        with open(accepted_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(line)
                    items.append(item)
                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        log.info(f"loaded_accepted_items count={len(items)}")
        return items

    except Exception as e:
        log.error(f"load_accepted_items_failed err={e}")
        return []


def fetch_price_outcome(
    ticker: str, acceptance_date: datetime, timeframe: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch price outcome for a specific timeframe.

    Args:
        ticker: Stock ticker
        acceptance_date: Date when alert was sent
        timeframe: Timeframe to check (1h, 4h, 1d)

    Returns:
        Outcome dict with price, return_pct, or None if unavailable
    """
    if timeframe not in TIMEFRAMES:
        return None

    hours = TIMEFRAMES[timeframe]
    target_date = acceptance_date + timedelta(hours=hours)

    # Don't fetch future data
    if target_date > datetime.now(timezone.utc):
        return None

    try:
        # Map timeframe to yfinance interval
        interval_map = {
            "1h": "1h",
            "4h": "1h",  # Use 1h and resample
            "1d": "1d",
        }

        interval = interval_map.get(timeframe, "1h")

        # Fetch historical data
        ticker_obj = yf.Ticker(ticker)
        start = acceptance_date.strftime("%Y-%m-%d")
        end = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

        hist = ticker_obj.history(start=start, end=end, interval=interval)

        if hist is None or hist.empty:
            return None

        # Get prices at acceptance and target time
        acceptance_price = None
        target_price = None

        # Get acceptance price (first bar)
        if len(hist) > 0:
            acceptance_price = float(hist["Close"].iloc[0])

        # Get target price based on timeframe
        if timeframe == "1d":
            # Use daily close
            target_price = float(hist["Close"].iloc[-1])
        else:
            # For intraday, find closest bar to target time
            hist_index = hist.index
            time_diffs = [
                (idx, abs((idx - target_date).total_seconds())) for idx in hist_index
            ]
            if time_diffs:
                closest_idx, _ = min(time_diffs, key=lambda x: x[1])
                target_price = float(hist.loc[closest_idx, "Close"])

        if acceptance_price is None or target_price is None:
            return None

        # Guard against division by zero
        if acceptance_price == 0:
            return None

        return_pct = ((target_price - acceptance_price) / acceptance_price) * 100.0

        return {
            "acceptance_price": acceptance_price,
            "target_price": target_price,
            "return_pct": round(return_pct, 2),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log.debug(f"fetch_outcome_failed ticker={ticker} timeframe={timeframe} err={e}")
        return None


def classify_outcome(outcomes: Dict[str, Dict[str, Any]]) -> Tuple[str, float]:
    """
    Classify outcome as SUCCESS or FAILURE based on thresholds.

    SUCCESS: 1h return > 2% OR 4h return > 3% OR 1d return > 5%
    FAILURE: All timeframes negative or minimal positive (<1%)

    Args:
        outcomes: Dict mapping timeframe -> outcome data

    Returns:
        Tuple of (classification, max_return_pct)
    """
    max_return = float("-inf")
    is_success = False

    for timeframe, outcome in outcomes.items():
        return_pct = outcome.get("return_pct", 0.0)
        max_return = max(max_return, return_pct)

        # Check if this timeframe meets success criteria
        threshold = SUCCESS_THRESHOLDS.get(timeframe)
        if threshold and return_pct >= threshold:
            is_success = True

    # Return classification with overall max return
    if is_success:
        return ("SUCCESS", max_return)

    # No timeframe met success criteria
    # Check if all returns are negative or minimal
    if max_return < 1.0:
        return ("FAILURE", max_return)

    # Between 1% and success thresholds - borderline, classify as FAILURE
    return ("FAILURE", max_return)


def track_accepted_outcomes(
    lookback_days: int = 7,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Track outcomes for accepted items from the last N days.

    Args:
        lookback_days: How many days back to analyze (default 7)
        max_items: Maximum items to process (None = all)

    Returns:
        Statistics dictionary
    """
    start_time = time.time()
    log.info(f"track_accepted_outcomes_start lookback_days={lookback_days}")

    # Read accepted items
    all_items = read_accepted_items()

    if not all_items:
        return {
            "status": "no_data",
            "message": "No accepted items found",
        }

    # Filter by lookback period
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    recent_items = []

    for item in all_items:
        ts_str = item.get("ts", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts >= cutoff_date:
                    recent_items.append(item)
            except Exception:
                continue

    log.info(
        f"filtered_items total={len(all_items)} recent={len(recent_items)} "
        f"lookback_days={lookback_days}"
    )

    if not recent_items:
        return {
            "status": "no_recent_items",
            "message": f"No items found in last {lookback_days} days",
        }

    # Limit if max_items specified
    if max_items:
        recent_items = recent_items[:max_items]

    # Load existing outcomes to avoid re-fetching
    _, fp_dir = _ensure_fp_dirs()
    outcomes_path = fp_dir / "outcomes.jsonl"
    existing_outcomes = set()

    if outcomes_path.exists():
        try:
            with open(outcomes_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        outcome = json.loads(line.strip())
                        key = (outcome.get("ticker"), outcome.get("acceptance_ts"))
                        existing_outcomes.add(key)
                    except Exception:
                        continue
        except Exception:
            pass

    # Process items
    stats = {
        "processed": 0,
        "successes": 0,
        "failures": 0,
        "pending": 0,
        "errors": 0,
        "skipped_existing": 0,
    }

    for item in recent_items:
        ticker = item.get("ticker", "").strip()
        ts_str = item.get("ts", "")

        if not ticker or not ts_str:
            stats["errors"] += 1
            continue

        # Skip if already processed
        if (ticker, ts_str) in existing_outcomes:
            stats["skipped_existing"] += 1
            continue

        try:
            acceptance_date = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

            # Check if enough time has passed for all timeframes
            min_elapsed = (
                datetime.now(timezone.utc) - acceptance_date
            ).total_seconds() / 3600
            max_timeframe_hours = max(TIMEFRAMES.values())

            if min_elapsed < max_timeframe_hours:
                stats["pending"] += 1
                continue

            # Fetch outcomes for all timeframes
            outcomes = {}
            for timeframe in TIMEFRAMES:
                outcome = fetch_price_outcome(ticker, acceptance_date, timeframe)
                if outcome:
                    outcomes[timeframe] = outcome
                # Small delay between API calls
                time.sleep(0.5)

            if not outcomes:
                stats["errors"] += 1
                continue

            # Classify outcome
            classification, max_return = classify_outcome(outcomes)

            # Build outcome record
            outcome_record = {
                "ticker": ticker,
                "acceptance_ts": ts_str,
                "acceptance_price": item.get("price"),
                "source": item.get("source"),
                "title": item.get("title"),
                "keywords": item.get("cls", {}).get("keywords", []),
                "score": item.get("cls", {}).get("score", 0.0),
                "sentiment": item.get("cls", {}).get("sentiment", 0.0),
                "outcomes": outcomes,
                "classification": classification,
                "max_return_pct": round(max_return, 2),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

            # Write to outcomes file
            with open(outcomes_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(outcome_record, ensure_ascii=False) + "\n")

            stats["processed"] += 1
            if classification == "SUCCESS":
                stats["successes"] += 1
            else:
                stats["failures"] += 1

            log.info(
                f"outcome_tracked ticker={ticker} classification={classification} "
                f"max_return={max_return:.2f}%"
            )

        except Exception as e:
            log.error(f"track_outcome_failed ticker={ticker} err={e}")
            stats["errors"] += 1

    elapsed = time.time() - start_time

    log.info(
        f"track_accepted_outcomes_complete "
        f"processed={stats['processed']} "
        f"successes={stats['successes']} "
        f"failures={stats['failures']} "
        f"pending={stats['pending']} "
        f"errors={stats['errors']} "
        f"elapsed={elapsed:.1f}s"
    )

    return {
        "status": "success",
        "stats": stats,
        "elapsed_seconds": round(elapsed, 2),
    }


# CLI entry point
def main():
    """Run false positive outcome tracking from command line."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Track outcomes for accepted items (false positive analysis)"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Days to look back (default: 7)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Maximum items to process (default: all)",
    )

    args = parser.parse_args()

    print("Tracking outcomes for accepted items...")
    print(f"  Lookback: {args.lookback_days} days")
    print(f"  Max items: {args.max_items or 'all'}")
    print()

    result = track_accepted_outcomes(
        lookback_days=args.lookback_days,
        max_items=args.max_items,
    )

    if result["status"] == "success":
        stats = result["stats"]
        print("\nResults:")
        print(f"  Processed: {stats['processed']}")
        print(f"  Successes: {stats['successes']}")
        print(f"  Failures: {stats['failures']}")
        print(f"  Pending: {stats['pending']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Already tracked: {stats['skipped_existing']}")
        print(f"\nElapsed: {result['elapsed_seconds']:.1f}s")

        if stats["processed"] > 0:
            false_positive_rate = stats["failures"] / stats["processed"] * 100
            print(f"\nFalse Positive Rate: {false_positive_rate:.1f}%")

        print("\nOutcomes saved to: data/false_positives/outcomes.jsonl")
        return 0
    else:
        print(f"\nError: {result.get('message', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
