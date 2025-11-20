"""
MOA (Missed Opportunities Analyzer) - Phase 2

Analyzes rejected items to identify missed opportunities and recommend
keyword weight adjustments.

Requirements:
1. Read rejected_items.jsonl and parse entries
2. Track price outcomes for rejected tickers (1h, 4h, 1d, 7d after rejection)
3. Identify missed opportunities (rejected items where price went up >10%)
4. Keyword analysis: extract keywords, calculate frequency and success rate
5. Generate recommendations: new keywords and weight adjustments

Author: Claude Code (MOA Phase 2)
Date: 2025-10-11
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .config import get_settings
from .logging_utils import get_logger
from .market_hours import is_market_holiday, is_weekend

log = get_logger("moa")

# Configuration
PRICE_LOOKBACK_HOURS = [1, 4, 24, 168]  # 1h, 4h, 1d, 7d
SUCCESS_THRESHOLD_PCT = 10.0  # >10% price increase = missed opportunity
MIN_OCCURRENCES = 15  # Minimum occurrences for statistical significance (increased from 5 for robustness)
ANALYSIS_WINDOW_DAYS = 30  # Analyze last 30 days of rejected items

# Volume/Liquidity Constraints (configurable)
MIN_DAILY_VOLUME = 100_000  # Minimum daily volume (shares)
MAX_SPREAD_PCT = 0.05  # Maximum spread (5% for penny stocks)


def is_tradeable_opportunity(
    ticker: str,
    timestamp: datetime,
    price: float,
    volume_data: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    Check if opportunity had sufficient volume/liquidity to be tradeable.

    Args:
        ticker: Stock ticker
        timestamp: Time of opportunity
        price: Stock price at time
        volume_data: Optional dict with 'daily_volume', 'spread_pct', etc.

    Returns:
        (is_tradeable: bool, reason: str)

    Criteria:
        - Daily volume >= MIN_DAILY_VOLUME shares (default: 100,000)
        - Spread <= MAX_SPREAD_PCT for penny stocks (default: 5%)
        - Price data available

    Examples:
        >>> is_tradeable_opportunity("AAPL", datetime.now(), 150.0, {"daily_volume": 50_000_000})
        (True, "tradeable")

        >>> is_tradeable_opportunity("LOWVOL", datetime.now(), 2.5, {"daily_volume": 50_000})
        (False, "insufficient_volume_50000")

        >>> is_tradeable_opportunity("WIDESPREAD", datetime.now(), 1.5, {"spread_pct": 0.08})
        (False, "spread_too_wide_8.00%")
    """
    # If no volume data provided, assume tradeable (backward compatible)
    if volume_data is None:
        return True, "no_volume_data_available"

    # Check volume
    daily_volume = volume_data.get("daily_volume", 0)
    if daily_volume < MIN_DAILY_VOLUME:
        return False, f"insufficient_volume_{daily_volume}"

    # Check spread (if available)
    spread_pct = volume_data.get("spread_pct")
    if spread_pct is not None and spread_pct > MAX_SPREAD_PCT:
        return False, f"spread_too_wide_{spread_pct:.2%}"

    return True, "tradeable"


def _repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def _ensure_moa_dirs() -> Tuple[Path, Path]:
    """Ensure MOA directories exist and return paths."""
    root = _repo_root()
    moa_dir = root / "data" / "moa"
    moa_dir.mkdir(parents=True, exist_ok=True)
    return root, moa_dir


def load_rejected_items(
    since_days: int = ANALYSIS_WINDOW_DAYS,
) -> List[Dict[str, Any]]:
    """
    Load rejected items from data/rejected_items.jsonl.

    Args:
        since_days: Only load items from the last N days

    Returns:
        List of rejected item dictionaries
    """
    root, _ = _ensure_moa_dirs()
    rejected_path = root / "data" / "rejected_items.jsonl"

    if not rejected_path.exists():
        log.warning(f"rejected_items_not_found path={rejected_path}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    items = []

    try:
        with open(rejected_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(line)

                    # Parse timestamp
                    ts_str = item.get("ts", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        log.debug(f"invalid_timestamp line={line_num} ts={ts_str}")
                        continue

                    # Skip old items
                    if ts < cutoff:
                        continue

                    items.append(item)

                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        log.info(f"loaded_rejected_items count={len(items)} since_days={since_days}")
        return items

    except Exception as e:
        log.error(f"load_rejected_items_failed err={e}")
        return []


def load_accepted_items(since_days: int = ANALYSIS_WINDOW_DAYS) -> List[Dict[str, Any]]:
    """
    Load accepted items from data/accepted_items.jsonl.

    Args:
        since_days: Only load items from the last N days

    Returns:
        List of accepted item dictionaries
    """
    root, _ = _ensure_moa_dirs()
    accepted_path = root / "data" / "accepted_items.jsonl"

    if not accepted_path.exists():
        log.warning(f"accepted_items_not_found path={accepted_path}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    items = []

    try:
        with open(accepted_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(line)

                    # Parse timestamp
                    ts_str = item.get("ts", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        log.debug(f"invalid_timestamp line={line_num} ts={ts_str}")
                        continue

                    # Skip old items
                    if ts < cutoff:
                        continue

                    items.append(item)

                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        log.info(f"loaded_accepted_items count={len(items)} since_days={since_days}")
        return items

    except Exception as e:
        log.error(f"load_accepted_items_failed err={e}")
        return []


def load_outcome_volume_data() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Load volume data from outcomes.jsonl for tradeability checks.

    Returns:
        Dict mapping (ticker, rejection_ts) -> volume_data
        where volume_data contains: daily_volume, avg_volume_20d, relative_volume
    """
    _, moa_dir = _ensure_moa_dirs()
    outcomes_path = moa_dir / "outcomes.jsonl"

    if not outcomes_path.exists():
        log.debug(f"outcomes_not_found path={outcomes_path}")
        return {}

    volume_lookup = {}

    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    outcome = json.loads(line)

                    ticker = outcome.get("ticker", "")
                    rejection_ts = outcome.get("rejection_ts", "")

                    if not ticker or not rejection_ts:
                        continue

                    # Extract volume data from any available timeframe
                    # Prefer 1d timeframe, fall back to others
                    outcomes_dict = outcome.get("outcomes", {})

                    volume_data = None
                    for timeframe in ["1d", "4h", "1h", "30m", "15m", "7d"]:
                        tf_data = outcomes_dict.get(timeframe)
                        if tf_data and tf_data.get("volume"):
                            volume_data = {
                                "daily_volume": tf_data.get("volume", 0),
                                "avg_volume_20d": tf_data.get("avg_volume_20d"),
                                "relative_volume": tf_data.get("relative_volume"),
                            }
                            break

                    if volume_data:
                        key = (ticker, rejection_ts)
                        volume_lookup[key] = volume_data

                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json_outcome line={line_num} err={e}")
                    continue

        log.info(f"loaded_outcome_volume_data count={len(volume_lookup)}")
        return volume_lookup

    except Exception as e:
        log.error(f"load_outcome_volume_data_failed err={e}")
        return {}


def fetch_historical_price(
    ticker: str, target_time: datetime, cache: Optional[Dict] = None
) -> Optional[float]:
    """
    Fetch historical price at specific datetime using Tiingo.

    Args:
        ticker: Ticker symbol
        target_time: Exact time to fetch price (UTC)
        cache: Optional cache dict to store/retrieve prices

    Returns:
        Price at target_time, or None if unavailable
    """
    # Check cache first
    cache_key = f"{ticker}:{target_time.isoformat()}"
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    # Get Tiingo API key from settings
    try:
        settings = get_settings()
        api_key = settings.tiingo_api_key
        if not api_key:
            log.debug(f"tiingo_api_key_missing ticker={ticker}")
            return None
    except Exception as e:
        log.debug(f"settings_load_failed err={e}")
        return None

    # Skip forward over weekends/holidays to next market day
    adjusted_time = target_time
    max_skip_days = 7  # Prevent infinite loops
    days_skipped = 0

    while (
        is_weekend(adjusted_time) or is_market_holiday(adjusted_time)
    ) and days_skipped < max_skip_days:
        adjusted_time = adjusted_time + timedelta(days=1)
        days_skipped += 1

    if days_skipped >= max_skip_days:
        log.debug(
            f"max_skip_days_reached ticker={ticker} target={target_time.isoformat()}"
        )
        return None

    # Format dates for Tiingo API (need buffer for intraday data)
    start_date = (adjusted_time - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (adjusted_time + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        # Use Tiingo IEX intraday endpoint for hourly data
        url = f"https://api.tiingo.com/iex/{ticker.upper()}/prices"
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "resampleFreq": "1hour",  # Hourly bars for better accuracy
            "token": api_key,
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            log.debug(f"tiingo_api_error ticker={ticker} status={response.status_code}")
            return None

        data = response.json()

        if not data or not isinstance(data, list):
            log.debug(
                f"tiingo_no_data ticker={ticker} target={adjusted_time.isoformat()}"
            )
            return None

        # Find the closest price bar to target time
        target_ts = adjusted_time
        closest_price = None
        min_time_diff = None

        for bar in data:
            try:
                bar_time_str = bar.get("date")
                if not bar_time_str:
                    continue

                # Parse timestamp (Tiingo returns UTC ISO format)
                bar_time = datetime.fromisoformat(bar_time_str.replace("Z", "+00:00"))

                # Calculate time difference
                time_diff = abs((bar_time - target_ts).total_seconds())

                # Use close price (most reliable)
                bar_price = bar.get("close")
                if bar_price is None:
                    continue

                # Track closest bar
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_price = float(bar_price)

            except Exception as e:
                log.debug(f"bar_parse_error ticker={ticker} err={e}")
                continue

        # Cache the result if available
        if closest_price is not None and cache is not None:
            cache[cache_key] = closest_price

        return closest_price

    except requests.RequestException as e:
        log.debug(f"tiingo_request_failed ticker={ticker} err={e}")
        return None
    except Exception as e:
        log.debug(f"fetch_historical_price_failed ticker={ticker} err={e}")
        return None


def check_price_outcome(
    ticker: str,
    rejection_time: datetime,
    hours_after: int,
    price_cache: Optional[Dict] = None,
    volume_data: Optional[Dict] = None,
    check_tradeable: bool = False,
) -> Optional[float]:
    """
    Check ACTUAL price change N hours after rejection using historical data.

    Args:
        ticker: Ticker symbol
        rejection_time: When item was rejected (UTC)
        hours_after: Hours after rejection to check
        price_cache: Optional cache dict for historical prices
        volume_data: Optional dict with volume/liquidity data for tradeability check
        check_tradeable: If True, return None for non-tradeable opportunities

    Returns:
        Actual price change percentage, or None if data unavailable or non-tradeable
    """
    # Calculate target time
    target_time = rejection_time + timedelta(hours=hours_after)
    now = datetime.now(timezone.utc)

    # Don't check future times
    if target_time > now:
        return None

    # Fetch historical prices at rejection time and target time
    try:
        entry_price = fetch_historical_price(ticker, rejection_time, price_cache)
        exit_price = fetch_historical_price(ticker, target_time, price_cache)

        if entry_price is None or exit_price is None:
            log.debug(
                f"price_data_missing ticker={ticker} hours={hours_after} "
                f"entry={entry_price} exit={exit_price}"
            )
            return None

        # Avoid division by zero
        if abs(entry_price) < 1e-9:
            return None

        # Check if tradeable (optional)
        if check_tradeable and volume_data is not None:
            is_tradeable, reason = is_tradeable_opportunity(
                ticker, rejection_time, entry_price, volume_data
            )

            if not is_tradeable:
                log.debug(
                    f"non_tradeable_opportunity ticker={ticker} hours={hours_after} "
                    f"reason={reason}"
                )
                return None

        # Calculate actual price change percentage
        change_pct = ((exit_price - entry_price) / entry_price) * 100.0

        log.debug(
            f"price_outcome ticker={ticker} hours={hours_after} "
            f"entry=${entry_price:.2f} exit=${exit_price:.2f} change={change_pct:.2f}%"
        )

        return change_pct

    except Exception as e:
        log.debug(f"price_check_failed ticker={ticker} hours={hours_after} err={e}")
        return None


def identify_missed_opportunities(
    items: List[Dict[str, Any]],
    threshold_pct: float = SUCCESS_THRESHOLD_PCT,
    check_tradeable: bool = False,
) -> List[Dict[str, Any]]:
    """
    Identify rejected items that became successful (missed opportunities).

    Args:
        items: List of rejected items
        threshold_pct: Success threshold percentage
        check_tradeable: If True, filter out non-tradeable opportunities (low volume/illiquid)

    Returns:
        List of missed opportunity items with price outcomes
    """
    missed_opps = []
    filtered_count = 0

    # Create shared price cache to avoid redundant API calls
    # Cache stores: "TICKER:ISO_TIMESTAMP" -> price
    price_cache: Dict[str, float] = {}

    # Load volume data from outcomes if checking tradeability
    volume_lookup = {}
    if check_tradeable:
        volume_lookup = load_outcome_volume_data()
        log.info(f"volume_data_loaded count={len(volume_lookup)}")

    for item in items:
        ticker = item.get("ticker", "")
        ts_str = item.get("ts", "")

        if not ticker or not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Get volume data for this opportunity (if available)
        volume_data = volume_lookup.get((ticker, ts_str)) if check_tradeable else None

        # Check price outcomes at different time horizons
        price_outcomes = {}
        is_missed_opp = False

        for hours in PRICE_LOOKBACK_HOURS:
            change_pct = check_price_outcome(
                ticker, ts, hours, price_cache, volume_data, check_tradeable
            )

            if change_pct is not None:
                price_outcomes[f"{hours}h"] = change_pct

                # Check if this qualifies as a missed opportunity
                if change_pct >= threshold_pct:
                    is_missed_opp = True
            elif check_tradeable and volume_data is not None:
                # Track filtered opportunities (had outcome data but was non-tradeable)
                filtered_count += 1

        # Add to missed opportunities if criteria met
        if is_missed_opp:
            missed_item = item.copy()
            missed_item["price_outcomes"] = price_outcomes
            missed_opps.append(missed_item)

    log_msg = (
        f"identified_missed_opportunities "
        f"total={len(items)} missed={len(missed_opps)} "
        f"rate={len(missed_opps)/len(items)*100:.1f}% "
        f"cache_hits={len(price_cache)}"
    )

    if check_tradeable:
        log_msg += f" filtered_non_tradeable={filtered_count}"

    log.info(log_msg)

    return missed_opps


def extract_keywords_from_missed_opps(
    missed_opps: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Extract and analyze keywords from missed opportunities.

    Args:
        missed_opps: List of missed opportunity items

    Returns:
        Dict mapping keyword -> stats (occurrences, success_rate, avg_return)
    """
    keyword_stats = defaultdict(
        lambda: {"occurrences": 0, "successes": 0, "total_return": 0.0}
    )

    for item in missed_opps:
        keywords = item.get("cls", {}).get("keywords", [])
        price_outcomes = item.get("price_outcomes", {})

        # Get best return from all timeframes
        best_return = 0.0
        for timeframe, change_pct in price_outcomes.items():
            if change_pct > best_return:
                best_return = change_pct

        # Track stats for each keyword
        for kw in keywords:
            kw_lower = str(kw).lower()
            keyword_stats[kw_lower]["occurrences"] += 1

            if best_return >= SUCCESS_THRESHOLD_PCT:
                keyword_stats[kw_lower]["successes"] += 1

            keyword_stats[kw_lower]["total_return"] += best_return

    # Calculate success rates and average returns
    results = {}
    for kw, stats in keyword_stats.items():
        occurrences = stats["occurrences"]

        if occurrences >= MIN_OCCURRENCES:
            results[kw] = {
                "occurrences": occurrences,
                "successes": stats["successes"],
                "success_rate": stats["successes"] / occurrences,
                "avg_return": stats["total_return"] / occurrences,
            }

    log.info(
        f"extracted_keywords "
        f"total_unique={len(keyword_stats)} "
        f"significant={len(results)} "
        f"min_occurrences={MIN_OCCURRENCES}"
    )

    return results


def discover_keywords_from_missed_opportunities(
    missed_opps: List[Dict[str, Any]],
    min_occurrences: int = 5,
    min_lift: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Discover new keyword candidates from missed opportunities using text mining.

    Compares keywords in missed opportunities vs false positives to find
    discriminative phrases that predict price movement.

    Args:
        missed_opps: List of missed opportunity items (went up >10% after rejection)
        min_occurrences: Minimum times keyword must appear
        min_lift: Minimum lift ratio (positive_rate / negative_rate)

    Returns:
        List of discovered keyword dicts:
        [
            {
                'keyword': 'regulatory approval',
                'lift': 5.2,
                'positive_count': 12,
                'negative_count': 2,
                'type': 'discovered',
                'recommended_weight': 0.5
            },
            ...
        ]
    """
    try:
        from .keyword_miner import mine_discriminative_keywords
    except ImportError:
        log.warning("keyword_miner module not available, skipping keyword discovery")
        return []

    # Extract titles from missed opportunities (positives)
    positive_titles = [
        item.get("title", "") for item in missed_opps if item.get("title")
    ]

    # Load accepted items (items we alerted on)
    # Filter for false positives (items that went down or stayed flat)
    # For now, use ALL accepted items as negatives (conservative approach)
    # TODO: Once outcome tracking is available, filter for actual false positives
    accepted_items = load_accepted_items(since_days=ANALYSIS_WINDOW_DAYS)

    negative_titles = [
        item.get("title", "") for item in accepted_items if item.get("title")
    ]

    if not positive_titles or not negative_titles:
        log.info(
            "insufficient_data_for_keyword_discovery "
            f"positive={len(positive_titles)} negative={len(negative_titles)}"
        )
        return []

    # Mine discriminative keywords
    try:
        scored_phrases = mine_discriminative_keywords(
            positive_titles=positive_titles,
            negative_titles=negative_titles,
            min_occurrences=min_occurrences,
            min_lift=min_lift,
            max_ngram_size=4,
        )

        # Convert to recommendation format
        discovered = []
        for phrase, lift, pos_count, neg_count in scored_phrases:
            # Calculate recommended weight based on lift and frequency
            # Higher lift = stronger signal = higher weight
            # But cap at 0.8 for newly discovered keywords (conservative)
            base_weight = 0.3
            lift_bonus = min(0.5, (lift - min_lift) * 0.1)  # 0.0-0.5 based on lift
            freq_bonus = min(0.2, pos_count / 20.0)  # 0.0-0.2 based on frequency

            recommended_weight = round(base_weight + lift_bonus + freq_bonus, 2)
            recommended_weight = min(0.8, recommended_weight)  # Cap at 0.8

            discovered.append(
                {
                    "keyword": phrase,
                    "lift": round(lift, 2),
                    "positive_count": pos_count,
                    "negative_count": neg_count,
                    "type": "discovered",
                    "recommended_weight": recommended_weight,
                }
            )

        log.info(
            f"discovered_keywords count={len(discovered)} "
            f"from_positive={len(positive_titles)} from_negative={len(negative_titles)}"
        )

        return discovered

    except Exception as e:
        log.error(f"keyword_discovery_failed err={e}", exc_info=True)
        return []


def load_current_keyword_weights() -> Dict[str, float]:
    """
    Load current keyword weights from data/analyzer/keyword_stats.json.

    Returns:
        Dict mapping keyword -> weight
    """
    root, _ = _ensure_moa_dirs()
    weights_path = root / "data" / "analyzer" / "keyword_stats.json"

    if not weights_path.exists():
        log.warning(f"keyword_stats_not_found path={weights_path}")
        return {}

    try:
        with open(weights_path, "r", encoding="utf-8") as f:
            weights = json.load(f)

        log.info(f"loaded_keyword_weights count={len(weights)}")
        return weights

    except Exception as e:
        log.error(f"load_keyword_weights_failed err={e}")
        return {}


def calculate_weight_recommendations(
    keyword_stats: Dict[str, Dict[str, Any]], current_weights: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    Generate keyword weight recommendations.

    Args:
        keyword_stats: Keyword statistics from missed opportunities
        current_weights: Current keyword weights

    Returns:
        List of recommendation dictionaries
    """
    recommendations = []

    for keyword, stats in keyword_stats.items():
        occurrences = stats["occurrences"]
        success_rate = stats["success_rate"]
        avg_return = stats["avg_return"]

        # Determine recommendation type
        current_weight = current_weights.get(keyword)

        if current_weight is None:
            # New keyword recommendation
            rec_type = "new"
            # Conservative initial weight based on success rate
            recommended_weight = round(1.0 + (success_rate - 0.5) * 2.0, 2)
            recommended_weight = max(0.5, min(recommended_weight, 2.0))
        else:
            # Weight increase recommendation
            rec_type = "weight_increase"

            # Calculate adjustment based on success rate
            if success_rate >= 0.7:
                # Strong performer - increase weight
                adjustment = 0.3
            elif success_rate >= 0.6:
                # Good performer - modest increase
                adjustment = 0.2
            else:
                # Moderate performer - small increase
                adjustment = 0.1

            recommended_weight = round(current_weight + adjustment, 2)
            recommended_weight = max(0.5, min(recommended_weight, 3.0))

            # Skip if weight wouldn't change significantly
            if abs(recommended_weight - current_weight) < 0.1:
                continue

        # Calculate confidence based on sample size and success rate
        if occurrences >= 20 and success_rate >= 0.7:
            confidence = 0.9
        elif occurrences >= 10 and success_rate >= 0.6:
            confidence = 0.75
        elif occurrences >= MIN_OCCURRENCES:
            confidence = 0.6
        else:
            confidence = 0.5

        recommendations.append(
            {
                "keyword": keyword,
                "type": rec_type,
                "current_weight": current_weight,
                "recommended_weight": recommended_weight,
                "confidence": confidence,
                "evidence": {
                    "occurrences": occurrences,
                    "success_rate": round(success_rate, 3),
                    "avg_return": round(avg_return / 100, 3),  # Convert to decimal
                },
            }
        )

    # Sort by confidence (highest first)
    recommendations.sort(key=lambda x: x["confidence"], reverse=True)

    log.info(f"generated_recommendations count={len(recommendations)}")
    return recommendations


def save_recommendations(
    recommendations: List[Dict[str, Any]],
    analysis_period: Tuple[datetime, datetime],
    total_rejected: int,
    missed_opportunities: int,
) -> Path:
    """
    Save recommendations to data/moa/recommendations.json.

    Args:
        recommendations: List of recommendation dicts
        analysis_period: (start, end) datetime tuple
        total_rejected: Total rejected items analyzed
        missed_opportunities: Number of missed opportunities identified

    Returns:
        Path to saved recommendations file
    """
    _, moa_dir = _ensure_moa_dirs()
    recommendations_path = moa_dir / "recommendations.json"

    period_str = (
        f"{analysis_period[0].date().isoformat()} to "
        f"{analysis_period[1].date().isoformat()}"
    )

    # Count discovered keywords
    discovered_count = len(
        [r for r in recommendations if "discovered" in r.get("type", "")]
    )

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis_period": period_str,
        "total_rejected": total_rejected,
        "missed_opportunities": missed_opportunities,
        "discovered_keywords_count": discovered_count,
        "recommendations": recommendations,
    }

    try:
        with open(recommendations_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        log.info(f"saved_recommendations path={recommendations_path}")
        return recommendations_path

    except Exception as e:
        log.error(f"save_recommendations_failed err={e}")
        raise


def load_analysis_state() -> Dict[str, Any]:
    """
    Load analysis state from data/moa/analysis_state.json.

    Returns:
        State dictionary or empty dict if not found
    """
    _, moa_dir = _ensure_moa_dirs()
    state_path = moa_dir / "analysis_state.json"

    if not state_path.exists():
        return {}

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state
    except Exception as e:
        log.error(f"load_analysis_state_failed err={e}")
        return {}


def save_analysis_state(state: Dict[str, Any]) -> None:
    """
    Save analysis state to data/moa/analysis_state.json.

    Args:
        state: State dictionary to save
    """
    _, moa_dir = _ensure_moa_dirs()
    state_path = moa_dir / "analysis_state.json"

    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        log.info(f"saved_analysis_state path={state_path}")
    except Exception as e:
        log.error(f"save_analysis_state_failed err={e}")


def run_moa_analysis(
    since_days: int = ANALYSIS_WINDOW_DAYS, check_tradeable: bool = False
) -> Dict[str, Any]:
    """
    Run complete MOA analysis pipeline.

    Args:
        since_days: Number of days to analyze
        check_tradeable: If True, filter out non-tradeable opportunities (low volume/illiquid)

    Returns:
        Analysis results dictionary
    """
    start_time = time.time()
    log.info(
        f"moa_analysis_start since_days={since_days} check_tradeable={check_tradeable}"
    )

    try:
        # 1. Load rejected items
        rejected_items = load_rejected_items(since_days=since_days)

        if not rejected_items:
            log.warning("no_rejected_items_found")
            return {
                "status": "no_data",
                "message": "No rejected items found to analyze",
            }

        # Calculate analysis period
        timestamps = []
        for item in rejected_items:
            try:
                ts = datetime.fromisoformat(item["ts"].replace("Z", "+00:00"))
                timestamps.append(ts)
            except Exception:
                continue

        if not timestamps:
            return {
                "status": "no_data",
                "message": "No valid timestamps in rejected items",
            }

        analysis_period = (min(timestamps), max(timestamps))

        # 2. Identify missed opportunities (with optional volume filtering)
        missed_opps = identify_missed_opportunities(
            rejected_items, check_tradeable=check_tradeable
        )

        if not missed_opps:
            log.warning("no_missed_opportunities")
            return {
                "status": "no_opportunities",
                "message": "No missed opportunities identified",
                "total_rejected": len(rejected_items),
            }

        # 3. Extract keywords and calculate statistics
        keyword_stats = extract_keywords_from_missed_opps(missed_opps)

        # 3b. DISCOVER NEW KEYWORDS using text mining
        discovered_keywords = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=5,
            min_lift=2.0,
        )

        if not keyword_stats and not discovered_keywords:
            log.warning("no_significant_keywords")
            return {
                "status": "no_keywords",
                "message": "No keywords with sufficient occurrences",
                "total_rejected": len(rejected_items),
                "missed_opportunities": len(missed_opps),
            }

        # 4. Load current keyword weights
        current_weights = load_current_keyword_weights()

        # 5. Generate recommendations (from existing keywords)
        recommendations = calculate_weight_recommendations(
            keyword_stats, current_weights
        )

        # 5b. Add discovered keyword recommendations
        for disc in discovered_keywords:
            # Check if keyword already exists in recommendations
            existing = next(
                (r for r in recommendations if r["keyword"] == disc["keyword"]), None
            )

            if existing:
                # Merge with existing recommendation (prefer discovered if higher weight)
                if disc["recommended_weight"] > existing.get("recommended_weight", 0):
                    existing["recommended_weight"] = disc["recommended_weight"]
                    existing["type"] = "discovered_and_existing"
                    existing["evidence"]["lift"] = disc["lift"]
                    existing["evidence"]["discovered_positive_count"] = disc[
                        "positive_count"
                    ]
                    existing["evidence"]["discovered_negative_count"] = disc[
                        "negative_count"
                    ]
            else:
                # Add as new recommendation
                recommendations.append(
                    {
                        "keyword": disc["keyword"],
                        "type": "new_discovered",
                        "current_weight": None,
                        "recommended_weight": disc["recommended_weight"],
                        "confidence": 0.7,  # Medium confidence for discovered keywords
                        "evidence": {
                            "lift": disc["lift"],
                            "positive_count": disc["positive_count"],
                            "negative_count": disc["negative_count"],
                        },
                    }
                )

        # 6. Save recommendations
        save_recommendations(
            recommendations,
            analysis_period,
            len(rejected_items),
            len(missed_opps),
        )

        # 7. Update analysis state
        state = {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "last_analysis_period": {
                "start": analysis_period[0].isoformat(),
                "end": analysis_period[1].isoformat(),
            },
            "total_rejected": len(rejected_items),
            "missed_opportunities": len(missed_opps),
            "recommendations_count": len(recommendations),
        }
        save_analysis_state(state)

        elapsed = time.time() - start_time
        log.info(
            f"moa_analysis_complete "
            f"elapsed={elapsed:.2f}s "
            f"rejected={len(rejected_items)} "
            f"missed={len(missed_opps)} "
            f"recommendations={len(recommendations)}"
        )

        return {
            "status": "success",
            "total_rejected": len(rejected_items),
            "missed_opportunities": len(missed_opps),
            "recommendations_count": len(recommendations),
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as e:
        log.error(f"moa_analysis_failed err={e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def get_moa_summary() -> Dict[str, Any]:
    """
    Get summary of last MOA analysis.

    Returns:
        Summary dictionary with key metrics
    """
    state = load_analysis_state()

    if not state:
        return {"status": "never_run", "message": "MOA analysis has not been run yet"}

    _, moa_dir = _ensure_moa_dirs()
    recommendations_path = moa_dir / "recommendations.json"

    recommendations = []
    if recommendations_path.exists():
        try:
            with open(recommendations_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                recommendations = data.get("recommendations", [])
        except Exception:
            pass

    return {
        "status": "ok",
        "last_run": state.get("last_run"),
        "analysis_period": state.get("last_analysis_period"),
        "total_rejected": state.get("total_rejected"),
        "missed_opportunities": state.get("missed_opportunities"),
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
    }


# Expose public API
__all__ = [
    "run_moa_analysis",
    "get_moa_summary",
    "load_rejected_items",
    "load_accepted_items",
    "load_outcome_volume_data",
    "is_tradeable_opportunity",
    "identify_missed_opportunities",
    "extract_keywords_from_missed_opps",
    "discover_keywords_from_missed_opportunities",
    "calculate_weight_recommendations",
    "save_recommendations",
    "load_analysis_state",
    "save_analysis_state",
    "MIN_DAILY_VOLUME",
    "MAX_SPREAD_PCT",
]
