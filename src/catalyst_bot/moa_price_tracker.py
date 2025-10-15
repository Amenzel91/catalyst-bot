"""
MOA Price Tracking Module - Track Price Outcomes for Rejected Items
====================================================================

Monitors price movements of rejected items over multiple timeframes to
identify missed opportunities and optimize rejection filters.

Timeframes tracked:
- 15m: Flash catalyst detection (requires 1-minute bars, last 7 days only)
- 30m: Momentum confirmation (requires 1-minute bars, last 7 days only)
- 1h: Early momentum after rejection
- 4h: Intraday continuation
- 1d: Daily follow-through
- 7d: Weekly trend validation

Author: Claude Code (MOA Phase 2)
Date: 2025-10-11
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger
from .market import get_last_price_change
from .market_hours import get_market_status

log = get_logger("moa_price_tracker")

# Import yfinance for intraday price fetching
try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None  # type: ignore

# Timeframes to track (in hours)
TRACKING_TIMEFRAMES = {
    "15m": 0.25,  # 15 minutes - flash catalyst detection
    "30m": 0.5,  # 30 minutes - momentum confirmation
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "7d": 168,
}

# Threshold for "missed opportunity" detection
MISSED_OPPORTUNITY_THRESHOLD = 10.0  # % return

# Rate limiting: minimum seconds between price checks per ticker
RATE_LIMIT_SECONDS = 60


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime object."""
    try:
        # Handle both with and without microseconds
        if "." in ts_str:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_intraday_price(ticker: str, target_time: datetime) -> Optional[float]:
    """
    Fetch price at specific time using 1-minute bars.

    yfinance provides 1-minute data for the last 7 days.
    For times older than 7 days, return None.

    This function is used for short timeframes (15m, 30m) that require
    precise historical price data at specific points in time.

    Args:
        ticker: Stock symbol (e.g., "AAPL")
        target_time: Specific datetime to fetch price for (timezone-aware)

    Returns:
        Price at that time, or None if unavailable

    Examples:
        >>> # Fetch price 15 minutes after rejection
        >>> rejection_time = datetime(2025, 10, 11, 10, 0, 0, tzinfo=timezone.utc)
        >>> target = rejection_time + timedelta(minutes=15)
        >>> price = fetch_intraday_price("AAPL", target)
    """
    if yf is None:
        log.debug("yfinance_not_available ticker=%s", ticker)
        return None

    # Check if target time is within yfinance's 1-minute data window (last 7 days)
    now = datetime.now(timezone.utc)
    age_days = (now - target_time).total_seconds() / 86400.0

    if age_days > 7.0:
        log.debug(
            f"intraday_price_too_old ticker={ticker} age_days={age_days:.1f} "
            "target_time=%s",
            target_time.isoformat(),
        )
        return None

    try:
        # Fetch 1-minute bars for a window around the target time
        # Use a 2-day window to ensure we capture the target time
        start_time = target_time - timedelta(hours=12)
        end_time = target_time + timedelta(hours=12)

        log.debug(
            f"fetching_intraday_price ticker={ticker} target={target_time.isoformat()}"
        )

        # Download 1-minute bars
        hist = yf.download(
            ticker,
            start=start_time.strftime("%Y-%m-%d"),
            end=end_time.strftime("%Y-%m-%d"),
            interval="1m",
            progress=False,
            auto_adjust=False,
        )

        if hist is None or hist.empty:
            log.debug(f"no_intraday_data ticker={ticker}")
            return None

        # Convert index to UTC if needed
        if hist.index.tz is None:
            hist.index = hist.index.tz_localize("America/New_York").tz_convert("UTC")
        else:
            hist.index = hist.index.tz_convert("UTC")

        # Find the closest bar to target_time (within +/- 5 minutes tolerance)
        time_diffs = (hist.index - target_time).total_seconds().abs()
        min_diff_idx = time_diffs.idxmin()
        min_diff_seconds = time_diffs.min()

        # Only accept bars within 5 minutes of target
        if min_diff_seconds > 300:  # 5 minutes
            log.debug(
                f"no_close_match ticker={ticker} min_diff_min={min_diff_seconds/60:.1f}"
            )
            return None

        # Get the closing price of the closest bar
        price = float(hist.loc[min_diff_idx, "Close"])

        log.debug(
            f"intraday_price_found ticker={ticker} price={price:.2f} "
            f"diff_min={min_diff_seconds/60:.1f}"
        )

        return price

    except Exception as e:
        log.warning(
            f"fetch_intraday_price_failed ticker={ticker} target={target_time.isoformat()} "
            f"err={e.__class__.__name__}"
        )
        return None


def _read_rejected_items() -> List[Dict[str, Any]]:
    """Read all rejected items from data/rejected_items.jsonl."""
    rejected_path = Path("data/rejected_items.jsonl")

    if not rejected_path.exists():
        return []

    items = []
    try:
        with open(rejected_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    items.append(item)
                except Exception as e:
                    log.warning(f"parse_rejected_item_failed err={e}")
                    continue
    except Exception as e:
        log.error(f"read_rejected_items_failed err={e}")
        return []

    return items


def _read_outcomes() -> Dict[str, Dict[str, Any]]:
    """
    Read existing outcomes from data/moa/outcomes.jsonl.

    Returns dict keyed by (ticker, rejection_ts) for fast lookup.
    """
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        return {}

    outcomes = {}
    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    outcome = json.loads(line)
                    ticker = outcome.get("ticker", "")
                    rejection_ts = outcome.get("rejection_ts", "")
                    if ticker and rejection_ts:
                        key = f"{ticker}:{rejection_ts}"
                        outcomes[key] = outcome
                except Exception as e:
                    log.warning(f"parse_outcome_failed err={e}")
                    continue
    except Exception as e:
        log.error(f"read_outcomes_failed err={e}")
        return {}

    return outcomes


def _write_outcome(outcome: Dict[str, Any]) -> None:
    """Append outcome to data/moa/outcomes.jsonl."""
    outcomes_path = Path("data/moa/outcomes.jsonl")
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(outcomes_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(outcome, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"write_outcome_failed ticker={outcome.get('ticker')} err={e}")


def _update_outcome(outcome: Dict[str, Any]) -> None:
    """
    Update existing outcome in data/moa/outcomes.jsonl.

    Reads all outcomes, replaces the matching one, and rewrites the file.
    """
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        _write_outcome(outcome)
        return

    ticker = outcome.get("ticker", "")
    rejection_ts = outcome.get("rejection_ts", "")
    key = f"{ticker}:{rejection_ts}"

    updated_lines = []
    found = False

    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing = json.loads(line)
                    existing_key = (
                        f"{existing.get('ticker')}:{existing.get('rejection_ts')}"
                    )
                    if existing_key == key:
                        updated_lines.append(json.dumps(outcome, ensure_ascii=False))
                        found = True
                    else:
                        updated_lines.append(line)
                except Exception:
                    updated_lines.append(line)

        # If not found, append
        if not found:
            updated_lines.append(json.dumps(outcome, ensure_ascii=False))

        # Rewrite file
        with open(outcomes_path, "w", encoding="utf-8") as f:
            for line in updated_lines:
                f.write(line + "\n")

    except Exception as e:
        log.error(f"update_outcome_failed ticker={ticker} err={e}")


def is_missed_opportunity(outcomes: Dict[str, Optional[Dict[str, Any]]]) -> bool:
    """
    Determine if any timeframe had >10% return, indicating a missed opportunity.

    Args:
        outcomes: Dict of timeframe -> outcome data

    Returns:
        True if any timeframe shows >10% return
    """
    for timeframe, outcome_data in outcomes.items():
        if outcome_data and isinstance(outcome_data, dict):
            return_pct = outcome_data.get("return_pct")
            if return_pct is not None and return_pct > MISSED_OPPORTUNITY_THRESHOLD:
                return True
    return False


def get_max_return(outcomes: Dict[str, Optional[Dict[str, Any]]]) -> float:
    """
    Get maximum return percentage across all timeframes.

    Args:
        outcomes: Dict of timeframe -> outcome data

    Returns:
        Maximum return percentage, or 0.0 if no outcomes
    """
    max_ret = 0.0
    for timeframe, outcome_data in outcomes.items():
        if outcome_data and isinstance(outcome_data, dict):
            return_pct = outcome_data.get("return_pct")
            if return_pct is not None:
                max_ret = max(max_ret, return_pct)
    return max_ret


def get_pending_items(timeframe: str) -> List[Dict[str, Any]]:
    """
    Get rejected items that need outcome check at this timeframe.

    Args:
        timeframe: One of "15m", "30m", "1h", "4h", "1d", "7d"

    Returns:
        List of rejected items pending this timeframe check
    """
    if timeframe not in TRACKING_TIMEFRAMES:
        log.warning(f"invalid_timeframe timeframe={timeframe}")
        return []

    hours_elapsed = TRACKING_TIMEFRAMES[timeframe]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours_elapsed)

    # Read rejected items and existing outcomes
    rejected_items = _read_rejected_items()
    existing_outcomes = _read_outcomes()

    pending = []

    for item in rejected_items:
        ticker = item.get("ticker", "").strip()
        rejection_ts_str = item.get("ts", "")

        if not ticker or not rejection_ts_str:
            continue

        # Parse rejection timestamp
        rejection_ts = _parse_timestamp(rejection_ts_str)
        if not rejection_ts:
            continue

        # Check if enough time has elapsed for this timeframe
        if rejection_ts > cutoff:
            continue  # Too recent

        # Check if we already have outcome for this timeframe
        key = f"{ticker}:{rejection_ts_str}"
        existing = existing_outcomes.get(key)

        if existing:
            outcomes_data = existing.get("outcomes", {})
            if outcomes_data.get(timeframe) is not None:
                continue  # Already have this timeframe

        # Add to pending list
        pending.append(
            {
                "ticker": ticker,
                "rejection_ts": rejection_ts_str,
                "rejection_ts_dt": rejection_ts,
                "rejection_price": item.get("price"),
                "rejection_reason": item.get("rejection_reason", "UNKNOWN"),
                "title": item.get("title", ""),
                "source": item.get("source", ""),
            }
        )

    return pending


def record_outcome(
    ticker: str,
    timeframe: str,
    rejection_ts: str,
    rejection_price: float,
    rejection_reason: str = "UNKNOWN",
) -> bool:
    """
    Fetch current price and record outcome for specific timeframe.

    For short timeframes (15m, 30m), uses historical 1-minute bars to fetch
    the price at the exact target time. For longer timeframes (1h+), uses
    current market price.

    Args:
        ticker: Stock ticker symbol
        timeframe: One of "15m", "30m", "1h", "4h", "1d", "7d"
        rejection_ts: ISO timestamp of rejection
        rejection_price: Price at rejection time
        rejection_reason: Reason for rejection

    Returns:
        True if outcome was recorded successfully
    """
    if timeframe not in TRACKING_TIMEFRAMES:
        log.warning(f"invalid_timeframe timeframe={timeframe}")
        return False

    try:
        # Parse rejection timestamp
        rejection_dt = _parse_timestamp(rejection_ts)
        if not rejection_dt:
            log.warning(f"invalid_rejection_ts ticker={ticker} ts={rejection_ts}")
            return False

        # Determine whether to use intraday price fetch or current price
        is_intraday_timeframe = timeframe in ("15m", "30m")

        if is_intraday_timeframe:
            # For 15m/30m, fetch historical price at specific time
            hours_offset = TRACKING_TIMEFRAMES[timeframe]
            target_time = rejection_dt + timedelta(hours=hours_offset)

            current_price = fetch_intraday_price(ticker, target_time)

            if current_price is None:
                log.debug(
                    f"intraday_price_unavailable ticker={ticker} timeframe={timeframe} "
                    f"target={target_time.isoformat()}"
                )
                return False
        else:
            # For 1h+ timeframes, use current market price
            current_price, _ = get_last_price_change(ticker)

            if current_price is None:
                log.debug(f"price_fetch_failed ticker={ticker} timeframe={timeframe}")
                return False

        # Calculate return percentage
        return_pct = ((current_price - rejection_price) / rejection_price) * 100.0

        # Build outcome data for this timeframe
        outcome_data = {
            "price": current_price,
            "return_pct": round(return_pct, 2),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        # Read or create outcome record
        existing_outcomes = _read_outcomes()
        key = f"{ticker}:{rejection_ts}"

        if key in existing_outcomes:
            # Update existing record
            outcome_record = existing_outcomes[key]
            outcome_record["outcomes"][timeframe] = outcome_data

            # Recalculate missed opportunity and max return
            outcome_record["is_missed_opportunity"] = is_missed_opportunity(
                outcome_record["outcomes"]
            )
            outcome_record["max_return_pct"] = get_max_return(
                outcome_record["outcomes"]
            )

            _update_outcome(outcome_record)
        else:
            # Create new outcome record
            outcome_record = {
                "ticker": ticker,
                "rejection_ts": rejection_ts,
                "rejection_price": rejection_price,
                "rejection_reason": rejection_reason,
                "outcomes": {
                    "15m": None,
                    "30m": None,
                    "1h": None,
                    "4h": None,
                    "1d": None,
                    "7d": None,
                },
                "is_missed_opportunity": False,
                "max_return_pct": 0.0,
            }
            outcome_record["outcomes"][timeframe] = outcome_data
            outcome_record["is_missed_opportunity"] = is_missed_opportunity(
                outcome_record["outcomes"]
            )
            outcome_record["max_return_pct"] = get_max_return(
                outcome_record["outcomes"]
            )

            _write_outcome(outcome_record)

        log.info(
            f"outcome_recorded ticker={ticker} timeframe={timeframe} "
            f"return={return_pct:.2f}% missed_opp={outcome_record['is_missed_opportunity']}"
        )

        return True

    except Exception as e:
        log.error(
            f"record_outcome_failed ticker={ticker} timeframe={timeframe} err={e}"
        )
        return False


def track_pending_outcomes() -> Dict[str, int]:
    """
    Check and update outcomes for all pending items across all timeframes.

    This should be called periodically (e.g., every cycle) to update outcomes.
    Handles rate limiting and market hours detection.

    Returns:
        Dict mapping timeframe -> count of outcomes recorded
    """
    # Check market status - skip during closed market to reduce API calls
    try:
        market_status = get_market_status()
        if market_status == "closed":
            # Only check once per hour when market is closed
            # Use a simple time-based check to avoid excessive API calls
            current_minute = datetime.now(timezone.utc).minute
            if current_minute % 60 != 0:  # Only run on the hour
                return {}
    except Exception:
        pass  # If market hours check fails, proceed anyway

    update_counts = {}

    for timeframe in TRACKING_TIMEFRAMES.keys():
        pending = get_pending_items(timeframe)

        if not pending:
            update_counts[timeframe] = 0
            continue

        recorded = 0

        # Rate limit: track last check time per ticker
        last_check_times: Dict[str, float] = {}

        for item in pending:
            ticker = item["ticker"]

            # Rate limiting: don't check same ticker too frequently
            last_check = last_check_times.get(ticker, 0)
            now = time.time()
            if now - last_check < RATE_LIMIT_SECONDS:
                continue

            # Record outcome
            success = record_outcome(
                ticker=ticker,
                timeframe=timeframe,
                rejection_ts=item["rejection_ts"],
                rejection_price=item["rejection_price"],
                rejection_reason=item["rejection_reason"],
            )

            if success:
                recorded += 1
                last_check_times[ticker] = now

            # Small delay between API calls to respect rate limits
            time.sleep(0.1)

        update_counts[timeframe] = recorded

    total = sum(update_counts.values())
    if total > 0:
        log.info(f"moa_outcomes_tracked total={total} breakdown={update_counts}")

    return update_counts


def get_missed_opportunities(
    lookback_days: int = 7,
    min_return_pct: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Get all missed opportunities from the past N days.

    Args:
        lookback_days: Number of days to look back
        min_return_pct: Minimum return % to consider a missed opportunity

    Returns:
        List of missed opportunity records sorted by max return (descending)
    """
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    missed_opps = []

    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    outcome = json.loads(line)

                    # Check if within lookback window
                    rejection_ts = _parse_timestamp(outcome.get("rejection_ts", ""))
                    if not rejection_ts or rejection_ts < cutoff:
                        continue

                    # Check if missed opportunity
                    if not outcome.get("is_missed_opportunity", False):
                        continue

                    # Check if meets minimum return threshold
                    max_return = outcome.get("max_return_pct", 0.0)
                    if max_return < min_return_pct:
                        continue

                    missed_opps.append(outcome)

                except Exception as e:
                    log.warning(f"parse_missed_opp_failed err={e}")
                    continue
    except Exception as e:
        log.error(f"get_missed_opportunities_failed err={e}")
        return []

    # Sort by max return descending
    missed_opps.sort(key=lambda x: x.get("max_return_pct", 0.0), reverse=True)

    return missed_opps


def get_outcome_stats(lookback_days: int = 7) -> Dict[str, Any]:
    """
    Get statistics about tracked outcomes.

    Args:
        lookback_days: Number of days to analyze

    Returns:
        Dict with statistics about outcomes and missed opportunities
    """
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        return {
            "total_tracked": 0,
            "missed_opportunities": 0,
            "avg_return_15m": 0.0,
            "avg_return_30m": 0.0,
            "avg_return_1h": 0.0,
            "avg_return_4h": 0.0,
            "avg_return_1d": 0.0,
            "avg_return_7d": 0.0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    total_tracked = 0
    missed_opps = 0
    returns_by_timeframe: Dict[str, List[float]] = {
        "15m": [],
        "30m": [],
        "1h": [],
        "4h": [],
        "1d": [],
        "7d": [],
    }

    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    outcome = json.loads(line)

                    # Check if within lookback window
                    rejection_ts = _parse_timestamp(outcome.get("rejection_ts", ""))
                    if not rejection_ts or rejection_ts < cutoff:
                        continue

                    total_tracked += 1

                    if outcome.get("is_missed_opportunity", False):
                        missed_opps += 1

                    # Collect returns by timeframe
                    outcomes_data = outcome.get("outcomes", {})
                    for tf in TRACKING_TIMEFRAMES.keys():
                        tf_data = outcomes_data.get(tf)
                        if tf_data and isinstance(tf_data, dict):
                            ret = tf_data.get("return_pct")
                            if ret is not None:
                                returns_by_timeframe[tf].append(ret)

                except Exception:
                    continue
    except Exception as e:
        log.error(f"get_outcome_stats_failed err={e}")
        return {
            "total_tracked": 0,
            "missed_opportunities": 0,
            "avg_return_15m": 0.0,
            "avg_return_30m": 0.0,
            "avg_return_1h": 0.0,
            "avg_return_4h": 0.0,
            "avg_return_1d": 0.0,
            "avg_return_7d": 0.0,
        }

    # Calculate averages
    avg_returns = {}
    for tf, returns in returns_by_timeframe.items():
        if returns:
            avg_returns[f"avg_return_{tf}"] = round(sum(returns) / len(returns), 2)
        else:
            avg_returns[f"avg_return_{tf}"] = 0.0

    return {
        "total_tracked": total_tracked,
        "missed_opportunities": missed_opps,
        **avg_returns,
    }
