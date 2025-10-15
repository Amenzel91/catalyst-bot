"""Fundamental data collection system for float shares and short interest.

This module provides FinViz Elite-powered data collection for fundamental metrics
that are critical volatility predictors for catalyst trading:

- Float shares: Strongest volatility predictor (4.2x impact vs other factors)
- Short interest: Squeeze potential indicator (>15% indicates high squeeze risk)

The module implements intelligent caching to minimize API calls:
- Float data: 30-day cache (quarterly updates sufficient)
- Short interest: 14-day cache (bi-weekly updates)

Data is scraped from FinViz Elite quote pages and stored in SQLite for fast retrieval.

**Note on FinViz Elite "API":**
FinViz does not provide an official REST API. This module scrapes data from the
FinViz Elite web interface using authenticated HTTP requests. The user must have
a valid FinViz Elite subscription and provide their auth cookie via the
FINVIZ_ELITE_AUTH or FINVIZ_API_KEY environment variable.

Usage:
    >>> from catalyst_bot.fundamental_data import get_float_shares, get_short_interest
    >>>
    >>> # Get float shares for a ticker
    >>> float_shares = get_float_shares("AAPL")
    >>> if float_shares:
    >>>     print(f"Float: {float_shares:,.0f} shares")
    >>>
    >>> # Get short interest percentage
    >>> short_pct = get_short_interest("GME")
    >>> if short_pct and short_pct > 15.0:
    >>>     print(f"High short interest: {short_pct:.2f}%")
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

from .logging_utils import get_logger

log = get_logger("fundamental_data")

# Cache configuration
CACHE_DB_PATH = os.getenv(
    "FUNDAMENTALS_CACHE_DB", "data/cache/fundamentals.db"
)
FLOAT_CACHE_DAYS = 30  # Quarterly updates sufficient
SHORT_CACHE_DAYS = 14  # Bi-weekly updates

# FinViz configuration
FINVIZ_BASE = "https://finviz.com"
FINVIZ_QUOTE_PATH = "/quote.ashx"

# Rate limiting configuration
MIN_REQUEST_INTERVAL_SEC = 1.0  # Minimum 1 second between requests
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # Base delay for exponential backoff


# Module-level state for rate limiting
_last_request_time = 0.0


def _get_auth_token() -> str:
    """Retrieve FinViz Elite authentication token from environment.

    Checks multiple environment variables for backward compatibility:
    1. FINVIZ_API_KEY (preferred for this module)
    2. FINVIZ_ELITE_AUTH (standard)
    3. FINVIZ_AUTH_TOKEN (legacy)

    Returns:
        Authentication token string

    Raises:
        RuntimeError: If no valid token is found
    """
    token = (
        os.getenv("FINVIZ_API_KEY", "").strip()
        or os.getenv("FINVIZ_ELITE_AUTH", "").strip()
        or os.getenv("FINVIZ_AUTH_TOKEN", "").strip()
    )
    if not token:
        raise RuntimeError(
            "FinViz Elite authentication token not found. Set FINVIZ_API_KEY, "
            "FINVIZ_ELITE_AUTH, or FINVIZ_AUTH_TOKEN environment variable."
        )
    return token


def _rate_limit() -> None:
    """Enforce minimum interval between FinViz requests.

    Implements a simple rate limiter to respect FinViz's service and avoid
    triggering anti-scraping measures. Sleeps if necessary to maintain the
    minimum interval between requests.
    """
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL_SEC:
        sleep_time = MIN_REQUEST_INTERVAL_SEC - elapsed
        log.debug("rate_limit_sleep sleep_sec=%.2f", sleep_time)
        time.sleep(sleep_time)
    _last_request_time = time.time()


def _fetch_quote_page(ticker: str, retries: int = MAX_RETRIES) -> Optional[str]:
    """Fetch FinViz quote page HTML with retry logic.

    Args:
        ticker: Stock ticker symbol
        retries: Maximum number of retry attempts (default: 3)

    Returns:
        HTML content as string, or None on failure

    Notes:
        - Implements exponential backoff on failures
        - Respects rate limiting between requests
        - Logs telemetry for monitoring
    """
    try:
        token = _get_auth_token()
    except RuntimeError as e:
        log.error("auth_token_missing error=%s", str(e))
        return None

    url = f"{FINVIZ_BASE}{FINVIZ_QUOTE_PATH}"
    params = {"t": ticker.upper().strip()}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": f"elite={token}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for attempt in range(retries + 1):
        try:
            _rate_limit()

            t0 = time.perf_counter()
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if resp.status_code == 200:
                log.info(
                    "finviz_quote_fetch ticker=%s status=ok t_ms=%.1f",
                    ticker,
                    elapsed_ms,
                )
                return resp.text

            if resp.status_code in (401, 403):
                log.error(
                    "finviz_auth_failed ticker=%s status=%d",
                    ticker,
                    resp.status_code,
                )
                return None

            if resp.status_code == 429:
                log.warning(
                    "finviz_rate_limit ticker=%s attempt=%d",
                    ticker,
                    attempt + 1,
                )
                if attempt < retries:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    time.sleep(delay)
                    continue

            log.warning(
                "finviz_http_error ticker=%s status=%d attempt=%d",
                ticker,
                resp.status_code,
                attempt + 1,
            )

            if attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)

        except requests.Timeout:
            log.warning("finviz_timeout ticker=%s attempt=%d", ticker, attempt + 1)
            if attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)
        except Exception as e:
            log.error(
                "finviz_request_error ticker=%s error=%s attempt=%d",
                ticker,
                e.__class__.__name__,
                attempt + 1,
            )
            if attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)

    return None


def _parse_fundamental_value(html: str, label: str) -> Optional[float]:
    """Parse a fundamental metric from FinViz quote page HTML.

    Args:
        html: Full HTML content of quote page
        label: Label text to search for (e.g., "Shs Float", "Short Float")

    Returns:
        Parsed numeric value, or None if not found/parseable

    Notes:
        FinViz quote pages use a table structure where labels are in one cell
        and values are in the adjacent cell. This parser looks for the label
        and extracts the next cell's content.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Find all table cells
        cells = soup.find_all("td", class_="snapshot-td2-cp")

        for i, cell in enumerate(cells):
            cell_text = cell.get_text(strip=True)
            if cell_text == label:
                # Value is in the next cell
                if i + 1 < len(cells):
                    value_cell = cells[i + 1]
                    value_text = value_cell.get_text(strip=True)
                    return _parse_numeric_value(value_text)

        # Fallback: try alternate table structure
        # Some quote pages use different class names
        all_tds = soup.find_all("td")
        for i, td in enumerate(all_tds):
            if label in td.get_text(strip=True):
                if i + 1 < len(all_tds):
                    value_text = all_tds[i + 1].get_text(strip=True)
                    return _parse_numeric_value(value_text)

        log.debug("fundamental_label_not_found label=%s", label)
        return None

    except Exception as e:
        log.error(
            "fundamental_parse_error label=%s error=%s",
            label,
            e.__class__.__name__,
        )
        return None


def _parse_numeric_value(text: str) -> Optional[float]:
    """Parse a numeric value from FinViz format.

    FinViz uses suffixes for large numbers:
    - K = thousands
    - M = millions
    - B = billions
    - T = trillions

    Also handles percentages (removes % sign).

    Args:
        text: Value string (e.g., "50.23M", "15.6%", "1.23B")

    Returns:
        Numeric value, or None if not parseable
    """
    if not text or text in ("-", "—", "N/A", ""):
        return None

    try:
        # Remove commas and percent signs
        clean = text.replace(",", "").replace("%", "").strip()

        # Handle suffix multipliers
        multiplier = 1.0
        if clean.endswith("K"):
            multiplier = 1_000
            clean = clean[:-1]
        elif clean.endswith("M"):
            multiplier = 1_000_000
            clean = clean[:-1]
        elif clean.endswith("B"):
            multiplier = 1_000_000_000
            clean = clean[:-1]
        elif clean.endswith("T"):
            multiplier = 1_000_000_000_000
            clean = clean[:-1]

        value = float(clean) * multiplier
        return value

    except (ValueError, AttributeError):
        log.debug("numeric_parse_failed text=%s", text)
        return None


def _init_cache_db() -> None:
    """Initialize the fundamentals cache database and schema.

    Creates the SQLite database file and tables if they don't exist.
    Uses WAL mode for better concurrent access.
    """
    db_path = Path(CACHE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fundamental_cache (
                ticker TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (ticker, metric)
            );

            CREATE INDEX IF NOT EXISTS idx_fundamental_cache_ticker
                ON fundamental_cache(ticker);

            CREATE INDEX IF NOT EXISTS idx_fundamental_cache_metric
                ON fundamental_cache(metric);
        """)
        conn.commit()
    finally:
        conn.close()


def _get_cached_value(
    ticker: str, metric: str, max_age_days: int
) -> Optional[float]:
    """Retrieve a cached fundamental value if still fresh.

    Args:
        ticker: Stock ticker symbol
        metric: Metric name (e.g., "float_shares", "short_interest")
        max_age_days: Maximum cache age in days

    Returns:
        Cached value if fresh, None otherwise
    """
    try:
        _init_cache_db()
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            cursor = conn.execute(
                "SELECT value, cached_at FROM fundamental_cache WHERE ticker = ? AND metric = ?",
                (ticker.upper().strip(), metric),
            )
            row = cursor.fetchone()

            if not row:
                return None

            value, cached_at_str = row
            cached_at = datetime.fromisoformat(cached_at_str)
            age = datetime.now(timezone.utc) - cached_at

            if age.days < max_age_days:
                log.debug(
                    "cache_hit ticker=%s metric=%s age_days=%d",
                    ticker,
                    metric,
                    age.days,
                )
                return value
            else:
                log.debug(
                    "cache_expired ticker=%s metric=%s age_days=%d",
                    ticker,
                    metric,
                    age.days,
                )
                return None

        finally:
            conn.close()

    except Exception as e:
        log.error(
            "cache_read_error ticker=%s metric=%s error=%s",
            ticker,
            metric,
            e.__class__.__name__,
        )
        return None


def _cache_value(ticker: str, metric: str, value: Optional[float]) -> None:
    """Store a fundamental value in the cache.

    Args:
        ticker: Stock ticker symbol
        metric: Metric name (e.g., "float_shares", "short_interest")
        value: Value to cache (can be None)
    """
    try:
        _init_cache_db()
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO fundamental_cache (ticker, metric, value, cached_at)
                VALUES (?, ?, ?, ?)
                """,
                (ticker.upper().strip(), metric, value, now),
            )
            conn.commit()
            log.debug("cache_write ticker=%s metric=%s value=%s", ticker, metric, value)
        finally:
            conn.close()
    except Exception as e:
        log.error(
            "cache_write_error ticker=%s metric=%s error=%s",
            ticker,
            metric,
            e.__class__.__name__,
        )


def get_float_shares(ticker: str) -> Optional[float]:
    """Get float shares for a ticker from FinViz Elite.

    Float shares = Shares Outstanding - Insider Shares - Above 5% Owners - Rule 144 Shares

    This is the strongest volatility predictor (4.2x impact vs other factors).
    Low float stocks (<10M shares) tend to have explosive moves on catalysts.

    **Caching:** Results are cached for 30 days. Quarterly updates are sufficient
    for float data as it changes slowly.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Float shares count, or None if unavailable

    Examples:
        >>> float_shares = get_float_shares("AAPL")
        >>> if float_shares and float_shares < 10_000_000:
        >>>     print("Low float - high volatility potential!")
    """
    if not ticker or not ticker.strip():
        return None

    ticker = ticker.upper().strip()

    # Check cache first
    cached = _get_cached_value(ticker, "float_shares", FLOAT_CACHE_DAYS)
    if cached is not None:
        return cached

    # Fetch fresh data
    html = _fetch_quote_page(ticker)
    if not html:
        return None

    # Parse float shares
    # FinViz label: "Shs Float"
    value = _parse_fundamental_value(html, "Shs Float")

    # Cache the result (even if None to avoid repeated failed lookups)
    _cache_value(ticker, "float_shares", value)

    if value:
        log.info("float_shares_fetched ticker=%s value=%.0f", ticker, value)
    else:
        log.warning("float_shares_not_found ticker=%s", ticker)

    return value


def get_short_interest(ticker: str) -> Optional[float]:
    """Get short interest percentage for a ticker from FinViz Elite.

    Short interest = (Shares Short / Float Shares) * 100

    High short interest (>15%) indicates squeeze potential. When heavily shorted
    stocks rally on positive catalysts, short sellers are forced to cover,
    creating additional buying pressure.

    **Caching:** Results are cached for 14 days. Bi-weekly updates capture changes
    in short positions while minimizing API calls.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Short interest as percentage (e.g., 25.5 for 25.5%), or None if unavailable

    Examples:
        >>> short_pct = get_short_interest("GME")
        >>> if short_pct and short_pct > 15.0:
        >>>     print(f"High squeeze potential: {short_pct:.1f}% short")
    """
    if not ticker or not ticker.strip():
        return None

    ticker = ticker.upper().strip()

    # Check cache first
    cached = _get_cached_value(ticker, "short_interest", SHORT_CACHE_DAYS)
    if cached is not None:
        return cached

    # Fetch fresh data
    html = _fetch_quote_page(ticker)
    if not html:
        return None

    # Parse short interest
    # FinViz label: "Short Float" (already in percentage form)
    value = _parse_fundamental_value(html, "Short Float")

    # Cache the result (even if None to avoid repeated failed lookups)
    _cache_value(ticker, "short_interest", value)

    if value:
        log.info("short_interest_fetched ticker=%s value=%.2f%%", ticker, value)
    else:
        log.warning("short_interest_not_found ticker=%s", ticker)

    return value


def get_fundamentals(ticker: str) -> Tuple[Optional[float], Optional[float]]:
    """Get both float shares and short interest in a single call.

    More efficient than calling get_float_shares() and get_short_interest()
    separately, as it fetches the quote page only once.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Tuple of (float_shares, short_interest_pct)
        Either value may be None if unavailable

    Examples:
        >>> float_shares, short_pct = get_fundamentals("TSLA")
        >>> if float_shares and short_pct:
        >>>     print(f"Float: {float_shares:,.0f}, Short: {short_pct:.1f}%")
    """
    if not ticker or not ticker.strip():
        return None, None

    ticker = ticker.upper().strip()

    # Check cache for both metrics
    float_cached = _get_cached_value(ticker, "float_shares", FLOAT_CACHE_DAYS)
    short_cached = _get_cached_value(ticker, "short_interest", SHORT_CACHE_DAYS)

    # If both are cached, return immediately
    if float_cached is not None and short_cached is not None:
        return float_cached, short_cached

    # Need to fetch at least one value
    html = _fetch_quote_page(ticker)
    if not html:
        return float_cached, short_cached

    # Parse both values if not cached
    float_shares = float_cached
    if float_shares is None:
        float_shares = _parse_fundamental_value(html, "Shs Float")
        _cache_value(ticker, "float_shares", float_shares)

    short_interest = short_cached
    if short_interest is None:
        short_interest = _parse_fundamental_value(html, "Short Float")
        _cache_value(ticker, "short_interest", short_interest)

    return float_shares, short_interest


def clear_cache(ticker: Optional[str] = None, metric: Optional[str] = None) -> int:
    """Clear cached fundamental data.

    Useful for forcing fresh data fetches or managing cache size.

    Args:
        ticker: If provided, clear only this ticker's cache
        metric: If provided, clear only this metric (requires ticker)

    Returns:
        Number of cache entries cleared

    Examples:
        >>> # Clear all cache
        >>> count = clear_cache()
        >>>
        >>> # Clear cache for specific ticker
        >>> count = clear_cache("AAPL")
        >>>
        >>> # Clear specific metric for ticker
        >>> count = clear_cache("AAPL", "short_interest")
    """
    try:
        _init_cache_db()
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            if ticker and metric:
                cursor = conn.execute(
                    "DELETE FROM fundamental_cache WHERE ticker = ? AND metric = ?",
                    (ticker.upper().strip(), metric),
                )
            elif ticker:
                cursor = conn.execute(
                    "DELETE FROM fundamental_cache WHERE ticker = ?",
                    (ticker.upper().strip(),),
                )
            else:
                cursor = conn.execute("DELETE FROM fundamental_cache")

            count = cursor.rowcount
            conn.commit()

            log.info("cache_cleared ticker=%s metric=%s count=%d", ticker, metric, count)
            return count

        finally:
            conn.close()

    except Exception as e:
        log.error("cache_clear_error error=%s", e.__class__.__name__)
        return 0


# Public API
__all__ = [
    "get_float_shares",
    "get_short_interest",
    "get_fundamentals",
    "clear_cache",
]
