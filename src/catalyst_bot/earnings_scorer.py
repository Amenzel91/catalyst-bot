"""Smart Earnings Scorer for Catalyst-Bot.

This module detects actual earnings RESULTS (not calendar announcements) and
assigns sentiment scores based on beat/miss performance. It distinguishes
between earnings calendar events (scheduled announcements) and actual earnings
results (reported with EPS/revenue data).

WAVE 0.1 Implementation:
- Detects if an event is an actual earnings result vs calendar announcement
- Parses EPS actual/estimate and revenue actual/estimate from title/description
- Calculates sentiment based on beat/miss magnitude
- Integrates with Finnhub API when available for accurate data
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("earnings_scorer")


log = get_logger("earnings_scorer")


def detect_earnings_result(title: str, description: str = "") -> bool:
    """Detect if this is an actual earnings RESULT (not a calendar announcement).

    Parameters
    ----------
    title : str
        The news headline/title
    description : str
        The news description/summary (optional)

    Returns
    -------
    bool
        True if this is an earnings result with actual data, False if it's
        just a calendar announcement
    """
    if not title:
        return False

    text = f"{title} {description}".lower()

    # Calendar keywords that indicate this is just an announcement, not a result
    calendar_keywords = [
        "scheduled",
        "expected to report",
        "upcoming earnings",
        "earnings calendar",
        "to report",
        "will report",
        "earnings date",
        "conference call scheduled",
    ]

    # Check if this looks like a calendar announcement
    for keyword in calendar_keywords:
        if keyword in text:
            return False

    # Result keywords that indicate actual reported data
    result_keywords = [
        "reports",
        "reported",
        "announces",
        "announced",
        "earnings",
        "eps",
        "beat",
        "miss",
        "exceeds",
        "falls short",
        "topped",
        "surpassed",
        "disappointed",
    ]

    # Look for actual numbers indicating results
    # Patterns like "EPS $1.23" or "revenue $100M" or "Q4 2024"
    number_patterns = [
        r"\$\d+\.\d+",  # $1.23
        r"\$\d+[kKmMbB]",  # $100M, $1.5B
        r"eps\s+\$?\d+",  # EPS $1.23 or eps 1.23
        r"revenue\s+\$?\d+",  # revenue $100M
        r"q[1-4]\s+\d{4}",  # Q4 2024
        r"earnings\s+of\s+\$",  # earnings of $
    ]

    has_result_keyword = any(kw in text for kw in result_keywords)
    has_numbers = any(
        re.search(pattern, text, re.IGNORECASE) for pattern in number_patterns
    )

    # It's a result if it has result keywords AND numbers (suggesting actual data)
    return has_result_keyword and has_numbers


def parse_earnings_data(
    title: str, description: str = ""
) -> Dict[str, Optional[float]]:
    """Parse earnings data from title and description.

    Extracts EPS actual, EPS estimate, revenue actual, and revenue estimate.

    Parameters
    ----------
    title : str
        The news headline/title
    description : str
        The news description/summary (optional)

    Returns
    -------
    dict
        Dictionary with keys:
        - eps_actual: Actual EPS reported (or None)
        - eps_estimate: EPS estimate/consensus (or None)
        - revenue_actual: Actual revenue reported (or None)
        - revenue_estimate: Revenue estimate/consensus (or None)
        - beat_miss_status: "beat", "miss", "inline", or None
    """
    text = f"{title} {description}"

    result: Dict[str, Optional[float]] = {
        "eps_actual": None,
        "eps_estimate": None,
        "revenue_actual": None,
        "revenue_estimate": None,
        "beat_miss_status": None,
    }

    # Parse EPS actual
    # Patterns: "EPS $1.23", "earnings of $1.23", "reported EPS of 1.23"
    eps_actual_patterns = [
        r"eps\s+(?:of\s+)?\$?(\d+\.\d+)",
        r"earnings\s+of\s+\$?(\d+\.\d+)",
        r"reported\s+(?:eps\s+)?(?:of\s+)?\$?(\d+\.\d+)",
    ]

    for pattern in eps_actual_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                result["eps_actual"] = float(match.group(1))
                break
            except ValueError:
                continue

    # Parse EPS estimate
    # Patterns: "vs estimate $1.20", "expected $1.20", "consensus $1.20"
    eps_estimate_patterns = [
        r"(?:vs|versus)\s+(?:estimate|expected|consensus)\s+\$?(\d+\.\d+)",
        r"estimate\s+\$?(\d+\.\d+)",
        r"expected\s+\$?(\d+\.\d+)",
        r"consensus\s+\$?(\d+\.\d+)",
    ]

    for pattern in eps_estimate_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                result["eps_estimate"] = float(match.group(1))
                break
            except ValueError:
                continue

    # Parse revenue actual
    # Patterns: "revenue $100M", "sales of $1.5B"
    revenue_actual_patterns = [
        r"revenue\s+(?:of\s+)?\$?(\d+(?:\.\d+)?)\s*([kKmMbB])?",
        r"sales\s+(?:of\s+)?\$?(\d+(?:\.\d+)?)\s*([kKmMbB])?",
    ]

    for pattern in revenue_actual_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                unit = match.group(2).upper() if match.group(2) else None

                # Convert to millions
                if unit == "B":
                    value *= 1000
                elif unit == "K":
                    value /= 1000
                # Default is already in millions if M or no unit after number

                result["revenue_actual"] = value
                break
            except (ValueError, AttributeError):
                continue

    # Parse revenue estimate
    # Look specifically for revenue estimate patterns (not EPS estimate)
    revenue_estimate_patterns = [
        r"revenue\s+\$?\d+(?:\.\d+)?\s*[kKmMbB]?\s+(?:vs|versus)\s+(?:estimate|expected|consensus)\s+\$?(\d+(?:\.\d+)?)\s*([kKmMbB])?",  # noqa: E501
        r"revenue\s+estimate\s+\$?(\d+(?:\.\d+)?)\s*([kKmMbB])?",
        # Match pattern like "revenue $25.7B vs estimate $25.6B"
        r"revenue\s+\$?\d+(?:\.\d+)?\s*[kKmMbB]?\s+vs\s+estimate\s+\$?(\d+(?:\.\d+)?)\s*([kKmMbB])?",  # noqa: E501
    ]

    for pattern in revenue_estimate_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                unit = match.group(2).upper() if match.group(2) else None

                if unit == "B":
                    value *= 1000
                elif unit == "K":
                    value /= 1000

                result["revenue_estimate"] = value
                break
            except (ValueError, AttributeError):
                continue

    # Determine beat/miss status from keywords
    text_lower = text.lower()
    if any(word in text_lower for word in ["beat", "topped", "exceeded", "surpassed"]):
        result["beat_miss_status"] = "beat"
    elif any(
        word in text_lower for word in ["miss", "missed", "fell short", "disappointed"]
    ):
        result["beat_miss_status"] = "miss"
    elif (
        "inline" in text_lower
        or "in line" in text_lower
        or "met expectations" in text_lower
    ):
        result["beat_miss_status"] = "inline"

    return result


def calculate_earnings_sentiment(
    eps_actual: Optional[float],
    eps_estimate: Optional[float],
    revenue_actual: Optional[float] = None,
    revenue_estimate: Optional[float] = None,
) -> Tuple[float, str]:
    """Calculate sentiment score based on earnings beat/miss.

    Parameters
    ----------
    eps_actual : float or None
        Actual EPS reported
    eps_estimate : float or None
        EPS estimate/consensus
    revenue_actual : float or None
        Actual revenue reported (in millions)
    revenue_estimate : float or None
        Revenue estimate/consensus (in millions)

    Returns
    -------
    tuple of (float, str)
        - Sentiment score in range -1.0 to +1.0
        - Label: "Strong Beat", "Beat", "Inline", "Miss", "Strong Miss", or "Unknown"
    """
    # Get configuration from environment
    try:
        beat_threshold_high = float(os.getenv("EARNINGS_BEAT_THRESHOLD_HIGH", "0.10"))
        beat_threshold_low = float(os.getenv("EARNINGS_BEAT_THRESHOLD_LOW", "0.05"))
        sentiment_beat_high = float(os.getenv("EARNINGS_SENTIMENT_BEAT_HIGH", "0.85"))
        sentiment_beat_low = float(os.getenv("EARNINGS_SENTIMENT_BEAT_LOW", "0.50"))
        sentiment_miss = float(os.getenv("EARNINGS_SENTIMENT_MISS", "-0.60"))
    except (ValueError, TypeError):
        # Use defaults if env vars are invalid
        beat_threshold_high = 0.10
        beat_threshold_low = 0.05
        sentiment_beat_high = 0.85
        sentiment_beat_low = 0.50
        sentiment_miss = -0.60

    eps_score = 0.0
    revenue_score = 0.0
    eps_weight = 0.7  # EPS is more important than revenue
    revenue_weight = 0.3

    # Calculate EPS score
    if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
        eps_surprise = (eps_actual - eps_estimate) / abs(eps_estimate)

        if eps_surprise >= beat_threshold_high:
            # Beat by >10%: Strong positive
            eps_score = sentiment_beat_high
        elif eps_surprise >= beat_threshold_low:
            # Beat by 5-10%: Moderate positive
            eps_score = sentiment_beat_low
        elif eps_surprise >= -beat_threshold_low:
            # Inline (-5% to +5%): Neutral to slightly positive
            eps_score = 0.15
        else:
            # Miss: Negative
            eps_score = sentiment_miss

    # Calculate revenue score
    if (
        revenue_actual is not None
        and revenue_estimate is not None
        and revenue_estimate != 0
    ):
        rev_surprise = (revenue_actual - revenue_estimate) / abs(revenue_estimate)

        if rev_surprise >= beat_threshold_high:
            revenue_score = (
                sentiment_beat_high * 0.8
            )  # Slightly less weight than EPS beat
        elif rev_surprise >= beat_threshold_low:
            revenue_score = sentiment_beat_low * 0.8
        elif rev_surprise >= -beat_threshold_low:
            revenue_score = 0.10
        else:
            revenue_score = sentiment_miss * 0.8

    # Combine scores
    if eps_actual is not None and eps_estimate is not None:
        if revenue_actual is not None and revenue_estimate is not None:
            # Have both EPS and revenue
            final_score = eps_score * eps_weight + revenue_score * revenue_weight
        else:
            # Only have EPS
            final_score = eps_score
    elif revenue_actual is not None and revenue_estimate is not None:
        # Only have revenue
        final_score = revenue_score
    else:
        # No data to calculate score
        return 0.0, "Unknown"

    # Determine label
    if final_score >= sentiment_beat_high:
        label = "Strong Beat"
    elif final_score >= sentiment_beat_low:
        label = "Beat"
    elif final_score >= 0:
        label = "Inline"
    elif final_score >= sentiment_miss:
        label = "Miss"
    else:
        label = "Strong Miss"

    return final_score, label


def fetch_earnings_from_finnhub(ticker: str) -> Optional[Dict[str, Optional[float]]]:
    """Fetch actual earnings data from Finnhub API.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    dict or None
        Dictionary with eps_actual, eps_estimate, revenue_actual, revenue_estimate
        or None if API unavailable or no data
    """
    # Try to import finnhub client safely
    try:
        from .finnhub_client import get_finnhub_client

        FINNHUB_CLIENT_AVAILABLE = True
    except ImportError:
        log.debug("finnhub_client_not_available")
        return None
    except Exception:
        log.debug("finnhub_client_import_error")
        return None

    if not FINNHUB_CLIENT_AVAILABLE:
        return None

    client = get_finnhub_client()
    if not client:
        return None

    try:
        # Get earnings calendar for this ticker (includes historical)
        from datetime import datetime, timedelta, timezone

        # Look back 7 days for recent earnings
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d"
        )

        earnings = client.get_earnings_calendar(
            from_date=from_date, to_date=to_date, ticker=ticker
        )

        if not earnings:
            return None

        # Get the most recent earnings entry
        latest = earnings[0] if earnings else None
        if not latest:
            return None

        return {
            "eps_actual": latest.get("epsActual"),
            "eps_estimate": latest.get("epsEstimate"),
            "revenue_actual": latest.get("revenueActual"),
            "revenue_estimate": latest.get("revenueEstimate"),
        }

    except Exception as e:
        log.debug("finnhub_earnings_fetch_error ticker=%s err=%s", ticker, str(e))
        return None


def score_earnings_event(
    title: str,
    description: str = "",
    ticker: str = "",
    source: str = "",
    use_api: bool = True,
) -> Optional[Dict[str, Any]]:
    """Main entry point to score an earnings event.

    Parameters
    ----------
    title : str
        News headline/title
    description : str
        News description/summary (optional)
    ticker : str
        Stock ticker symbol (optional)
    source : str
        News source (optional)
    use_api : bool
        Whether to try fetching from Finnhub API (default: True)

    Returns
    -------
    dict or None
        Dictionary with:
        - is_earnings_result: bool
        - sentiment_score: float (-1.0 to +1.0)
        - sentiment_label: str
        - eps_actual: float or None
        - eps_estimate: float or None
        - revenue_actual: float or None
        - revenue_estimate: float or None
        - data_source: "api" or "parsed" or "none"

        Returns None if not an earnings result
    """
    # First check if this is an earnings result (not just calendar)
    if not detect_earnings_result(title, description):
        return None

    log.info("earnings_result_detected ticker=%s source=%s", ticker, source)

    # Try to get data from Finnhub API first (most accurate)
    earnings_data = None
    data_source = "none"

    if use_api and ticker and os.getenv("FEATURE_EARNINGS_SCORER", "1") == "1":
        earnings_data = fetch_earnings_from_finnhub(ticker)
        if earnings_data and earnings_data.get("eps_actual") is not None:
            data_source = "api"
            log.debug("earnings_data_from_api ticker=%s", ticker)

    # Fallback to parsing if API didn't work
    if not earnings_data or earnings_data.get("eps_actual") is None:
        earnings_data = parse_earnings_data(title, description)
        if earnings_data.get("eps_actual") is not None:
            data_source = "parsed"
            log.debug("earnings_data_from_parsing ticker=%s", ticker)

    # Calculate sentiment
    sentiment_score, sentiment_label = calculate_earnings_sentiment(
        eps_actual=earnings_data.get("eps_actual"),
        eps_estimate=earnings_data.get("eps_estimate"),
        revenue_actual=earnings_data.get("revenue_actual"),
        revenue_estimate=earnings_data.get("revenue_estimate"),
    )

    return {
        "is_earnings_result": True,
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
        "eps_actual": earnings_data.get("eps_actual"),
        "eps_estimate": earnings_data.get("eps_estimate"),
        "revenue_actual": earnings_data.get("revenue_actual"),
        "revenue_estimate": earnings_data.get("revenue_estimate"),
        "data_source": data_source,
    }


if __name__ == "__main__":
    # Test cases
    print("Testing Earnings Scorer...")
    print("=" * 70)

    # Test 1: Calendar announcement (should be False)
    result1 = detect_earnings_result(
        "AAPL Earnings scheduled for October 31, 2024",
        "Apple Inc. is expected to report earnings on October 31",
    )
    print("\nTest 1 - Calendar Detection:")
    print("  Title: 'AAPL Earnings scheduled for October 31, 2024'")
    print(f"  Is Result: {result1} (expected: False)")
    print(f"  Status: {'PASS' if not result1 else 'FAIL'}")

    # Test 2: Actual result (should be True)
    result2 = detect_earnings_result(
        "AAPL reports Q4 earnings of $1.64, beats estimates",
        "Apple reported EPS of $1.64 vs estimate of $1.60",
    )
    print("\nTest 2 - Result Detection:")
    print("  Title: 'AAPL reports Q4 earnings of $1.64, beats estimates'")
    print(f"  Is Result: {result2} (expected: True)")
    print(f"  Status: {'PASS' if result2 else 'FAIL'}")

    # Test 3: Parse earnings data with both EPS and estimate
    title3 = "TSLA reports Q4 EPS of $1.19 vs estimate $1.13, revenue $25.7B vs estimate $25.6B"
    parsed = parse_earnings_data(title3)
    print("\nTest 3 - Parsing Earnings Data:")
    print(f"  Title: '{title3}'")
    print(f"  EPS Actual: {parsed.get('eps_actual')}")
    print(f"  EPS Estimate: {parsed.get('eps_estimate')}")
    print(f"  Revenue Actual: {parsed.get('revenue_actual')}M")
    print(f"  Revenue Estimate: {parsed.get('revenue_estimate')}M")
    print(f"  Beat/Miss: {parsed.get('beat_miss_status')}")

    # Test 4: Calculate sentiment for strong beat (>10%)
    score, label = calculate_earnings_sentiment(
        eps_actual=1.64,
        eps_estimate=1.45,  # ~13% beat
    )
    print("\nTest 4 - Strong Beat Sentiment:")
    print("  EPS: $1.64 vs estimate $1.45 (~13% beat)")
    print(f"  Score: {score:.2f}")
    print(f"  Label: {label}")
    print("  Expected: Strong Beat (score ~0.85)")

    # Test 5: Calculate sentiment for moderate beat (5-10%)
    score, label = calculate_earnings_sentiment(
        eps_actual=1.64,
        eps_estimate=1.60,  # ~2.5% beat
    )
    print("\nTest 5 - Moderate Beat Sentiment:")
    print("  EPS: $1.64 vs estimate $1.60 (~2.5% beat)")
    print(f"  Score: {score:.2f}")
    print(f"  Label: {label}")
    print("  Expected: Inline (score ~0.15)")

    # Test 6: Calculate sentiment for miss
    score, label = calculate_earnings_sentiment(
        eps_actual=1.45,
        eps_estimate=1.60,  # ~9% miss
    )
    print("\nTest 6 - Miss Sentiment:")
    print("  EPS: $1.45 vs estimate $1.60 (~9% miss)")
    print(f"  Score: {score:.2f}")
    print(f"  Label: {label}")
    print("  Expected: Miss (score ~-0.60)")

    # Test 7: Full integration test
    print("\nTest 7 - Full Integration:")
    result = score_earnings_event(
        title="NVDA reports Q3 EPS of $0.68 vs estimate $0.61 - revenue $18.1B vs estimate $17.8B",
        description="NVIDIA reported strong Q3 results",
        ticker="NVDA",
        source="Test",
        use_api=False,  # Don't hit API in test
    )
    if result:
        print("  Ticker: NVDA")
        print(f"  Is Earnings Result: {result['is_earnings_result']}")
        print(f"  Sentiment Score: {result['sentiment_score']:.2f}")
        print(f"  Sentiment Label: {result['sentiment_label']}")
        print(f"  Data Source: {result['data_source']}")
        print(f"  EPS: ${result['eps_actual']} vs ${result['eps_estimate']}")
        print("  Status: PASS")
    else:
        print("  Status: FAIL - No result returned")

    print("\n" + "=" * 70)
    print("All tests completed!")
