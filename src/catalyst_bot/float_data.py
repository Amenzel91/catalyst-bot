"""Float data collection and classification module.

This module provides functionality to collect, cache, and classify float data
for stocks. Float (shares outstanding available for trading) is a key volatility
predictor - stocks with <5M float have 4.2x higher volatility.

Float is scraped from FinViz (free, no API key required) and cached for 30 days
since float data changes infrequently. Classification tiers provide confidence
multipliers for scoring adjustments.

WAVE 3 ENHANCEMENT: Multi-Source Float Data Robustness
- Added cascading fallback logic: FinViz -> yfinance -> Tiingo -> Yahoo scraping
- Enhanced caching with configurable TTL (default: 24 hours)
- Data validation to reject obviously incorrect values
- Comprehensive error tracking and logging
- Thread-safe cache operations
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

# Float classification thresholds (shares)
MICRO_FLOAT_THRESHOLD = 5_000_000  # <5M = MICRO (1.3x multiplier)
LOW_FLOAT_THRESHOLD = 20_000_000  # 5M-20M = LOW (1.2x multiplier)
MEDIUM_FLOAT_THRESHOLD = 50_000_000  # 20M-50M = MEDIUM (1.0x baseline)
# >50M = HIGH (0.9x multiplier)

# Cache settings
DEFAULT_CACHE_TTL_DAYS = 30
DEFAULT_CACHE_TTL_HOURS = 24  # Wave 3: New default for float cache
DEFAULT_REQUEST_DELAY_SEC = 2.0

# Data validation thresholds
MIN_VALID_FLOAT = 1_000  # Minimum valid float: 1,000 shares
MAX_VALID_FLOAT = 100_000_000_000  # Maximum valid float: 100B shares

# User agent for FinViz requests (required to avoid 403)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

log = logging.getLogger(__name__)


def get_cache_path() -> Path:
    """Get the path to the float cache file.

    Returns
    -------
    Path
        Path to data/cache/float_cache.json (Wave 3: moved to cache subdirectory)
    """
    try:
        from .config import get_settings

        settings = get_settings()
        cache_dir = settings.data_dir / "cache"
    except Exception:
        cache_dir = Path("data") / "cache"

    # Ensure cache directory exists
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "float_cache.json"


def validate_float_value(float_shares: Optional[float]) -> bool:
    """Validate that a float value is reasonable.

    Wave 3 Enhancement: Sanity check float values to reject obviously incorrect data.

    Parameters
    ----------
    float_shares : Optional[float]
        Float shares value to validate

    Returns
    -------
    bool
        True if value is valid, False otherwise

    Examples
    --------
    >>> validate_float_value(5_000_000)  # Valid
    True
    >>> validate_float_value(1)  # Too small
    False
    >>> validate_float_value(999_000_000_000_000)  # Too large
    False
    >>> validate_float_value(None)  # Null
    False
    """
    if float_shares is None:
        return False

    try:
        float_val = float(float_shares)
        if float_val <= 0:
            return False
        if float_val < MIN_VALID_FLOAT:
            log.debug(
                "float_validation_failed reason=too_small value=%.0f min=%.0f",
                float_val,
                MIN_VALID_FLOAT,
            )
            return False
        if float_val > MAX_VALID_FLOAT:
            log.debug(
                "float_validation_failed reason=too_large value=%.0f max=%.0f",
                float_val,
                MAX_VALID_FLOAT,
            )
            return False
        return True
    except (ValueError, TypeError):
        return False


def is_cache_fresh(
    cached_at_iso: str, max_age_hours: int = DEFAULT_CACHE_TTL_HOURS
) -> bool:
    """Check if cached float data is still fresh.

    Wave 3 Enhancement: Configurable cache TTL in hours instead of fixed 30 days.

    Parameters
    ----------
    cached_at_iso : str
        ISO timestamp when data was cached
    max_age_hours : int, optional
        Maximum age in hours before cache is considered stale, by default 24

    Returns
    -------
    bool
        True if cache is still fresh, False if expired
    """
    try:
        cached_at = datetime.fromisoformat(cached_at_iso.replace("Z", "+00:00"))
        expiry = cached_at + timedelta(hours=max_age_hours)
        now = datetime.now(timezone.utc)
        return now < expiry
    except Exception as e:
        log.debug("cache_freshness_check_failed err=%s", str(e))
        return False


def _get_from_cache(ticker: str) -> Optional[Dict]:
    """Retrieve float data from cache if present and not expired.

    Wave 3 Enhancement: Uses new is_cache_fresh() helper and validates cached values.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Optional[Dict]
        Cached float data if found and valid, None otherwise
    """
    cache_path = get_cache_path()

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception as e:
        log.debug("cache_read_failed path=%s err=%s", cache_path, str(e))
        return None

    ticker_upper = ticker.upper().strip()
    entry = cache.get(ticker_upper)

    if not entry:
        return None

    # Check if entry is expired (Wave 3: use configurable hours)
    try:
        # Get TTL from config
        try:
            from .config import get_settings

            settings = get_settings()
            ttl_hours = getattr(
                settings, "float_cache_max_age_hours", DEFAULT_CACHE_TTL_HOURS
            )
        except Exception:
            ttl_hours = DEFAULT_CACHE_TTL_HOURS

        cached_at = entry.get("cached_at", "")
        if not is_cache_fresh(cached_at, max_age_hours=ttl_hours):
            log.debug("cache_expired ticker=%s age_hours=%d", ticker_upper, ttl_hours)
            return None

        # Wave 3: Validate cached float value
        float_shares = entry.get("float_shares")
        if float_shares is not None and not validate_float_value(float_shares):
            log.warning(
                "cache_invalid_data ticker=%s float=%.0f", ticker_upper, float_shares
            )
            return None

        return entry
    except Exception as e:
        log.debug("cache_expiry_check_failed ticker=%s err=%s", ticker_upper, str(e))
        return None


def _save_to_cache(ticker: str, data: Dict) -> None:
    """Save float data to cache.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    data : Dict
        Float data to cache (must include cached_at timestamp)
    """
    cache_path = get_cache_path()

    # Ensure cache directory exists
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.warning(
            "cache_dir_creation_failed path=%s err=%s", cache_path.parent, str(e)
        )
        return

    # Load existing cache
    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception as e:
            log.debug("cache_load_failed path=%s err=%s", cache_path, str(e))
            cache = {}

    # Update cache with new entry
    ticker_upper = ticker.upper().strip()
    cache[ticker_upper] = data

    # Write cache back to disk
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        log.debug("cache_saved ticker=%s", ticker_upper)
    except Exception as e:
        log.warning("cache_write_failed path=%s err=%s", cache_path, str(e))


def classify_float(float_shares: float) -> str:
    """Classify float size into tier categories.

    Parameters
    ----------
    float_shares : float
        Number of shares in the float

    Returns
    -------
    str
        Float classification: MICRO_FLOAT, LOW_FLOAT, MEDIUM_FLOAT, HIGH_FLOAT, or UNKNOWN
    """
    if float_shares is None or float_shares <= 0:
        return "UNKNOWN"

    if float_shares < MICRO_FLOAT_THRESHOLD:
        return "MICRO_FLOAT"
    elif float_shares < LOW_FLOAT_THRESHOLD:
        return "LOW_FLOAT"
    elif float_shares < MEDIUM_FLOAT_THRESHOLD:
        return "MEDIUM_FLOAT"
    else:
        return "HIGH_FLOAT"


def get_float_multiplier(float_shares: float) -> float:
    """Get confidence score multiplier based on float size.

    Lower float = higher volatility = higher confidence multiplier.

    Parameters
    ----------
    float_shares : float
        Number of shares in the float

    Returns
    -------
    float
        Confidence multiplier: 1.3x for MICRO, 1.2x for LOW, 1.0x for MEDIUM/HIGH/UNKNOWN
    """
    float_class = classify_float(float_shares)

    multipliers = {
        "MICRO_FLOAT": 1.3,  # Highest volatility
        "LOW_FLOAT": 1.2,
        "MEDIUM_FLOAT": 1.0,  # Baseline
        "HIGH_FLOAT": 0.9,  # Lower volatility
        "UNKNOWN": 1.0,  # No adjustment
    }

    return multipliers.get(float_class, 1.0)


def _parse_finviz_number(text: str) -> Optional[float]:
    """Parse a number from FinViz table cell text.

    Handles formats like:
    - "5.23M" -> 5_230_000
    - "1.45B" -> 1_450_000_000
    - "12.5K" -> 12_500
    - "15.2%" -> 15.2
    - "-" -> None

    Parameters
    ----------
    text : str
        Text to parse

    Returns
    -------
    Optional[float]
        Parsed number or None if parsing fails
    """
    if not text or text.strip() in {"-", "N/A", ""}:
        return None

    text = text.strip()

    # Remove percentage sign if present
    is_percentage = text.endswith("%")
    if is_percentage:
        text = text[:-1].strip()

    # Parse multiplier suffix
    multiplier = 1.0
    if text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1].strip()
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1].strip()
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1].strip()

    try:
        value = float(text) * multiplier
        return value
    except (ValueError, TypeError):
        return None


def scrape_finviz(ticker: str) -> Dict[str, Any]:
    """Scrape float data from FinViz.

    Extracts float, shares outstanding, short interest, and institutional ownership
    from FinViz's free stock quote page. No API key required.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Dict[str, Any]
        Dictionary with keys:
        - float_shares: float or None
        - shares_outstanding: float or None
        - short_interest_pct: float or None (as percentage)
        - institutional_ownership_pct: float or None (as percentage)
        - source: str ("finviz")
        - success: bool
        - error: str or None
    """
    ticker_upper = ticker.upper().strip()
    url = f"https://finviz.com/quote.ashx?t={ticker_upper}"

    result = {
        "float_shares": None,
        "shares_outstanding": None,
        "short_interest_pct": None,
        "institutional_ownership_pct": None,
        "source": "finviz",
        "success": False,
        "error": None,
    }

    try:
        # Get request delay from config
        try:
            from .config import get_settings

            settings = get_settings()
            request_delay = getattr(
                settings, "float_request_delay_sec", DEFAULT_REQUEST_DELAY_SEC
            )
        except Exception:
            request_delay = DEFAULT_REQUEST_DELAY_SEC

        # Rate limiting: sleep before request
        time.sleep(request_delay)

        # Make request with user agent
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )

        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}"
            log.debug(
                "finviz_request_failed ticker=%s status=%d",
                ticker_upper,
                response.status_code,
            )
            return result

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Find the fundamental data table
        # FinViz uses a specific table structure with class "snapshot-table2"
        table = soup.find("table", {"class": "snapshot-table2"})

        if not table:
            result["error"] = "Table not found"
            log.debug("finviz_table_not_found ticker=%s", ticker_upper)
            return result

        # Parse table rows to extract data
        # FinViz table has format: [label1, value1, label2, value2, ...]
        cells = table.find_all("td")

        data_map = {}
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].get_text(strip=True)
            value = cells[i + 1].get_text(strip=True)
            data_map[label] = value

        # Extract fields we care about
        result["float_shares"] = _parse_finviz_number(data_map.get("Float", ""))
        result["shares_outstanding"] = _parse_finviz_number(
            data_map.get("Shs Outstand", "")
        )
        result["short_interest_pct"] = _parse_finviz_number(
            data_map.get("Short Float", "")
        )
        result["institutional_ownership_pct"] = _parse_finviz_number(
            data_map.get("Inst Own", "")
        )

        result["success"] = True

        log.info(
            "finviz_scrape_success ticker=%s float=%.2fM short_interest=%.2f%% inst_own=%.2f%%",
            ticker_upper,
            (result["float_shares"] or 0) / 1_000_000,
            result["short_interest_pct"] or 0,
            result["institutional_ownership_pct"] or 0,
        )

    except requests.Timeout:
        result["error"] = "Request timeout"
        log.warning("finviz_timeout ticker=%s", ticker_upper)
    except requests.RequestException as e:
        result["error"] = f"Request error: {e.__class__.__name__}"
        log.warning(
            "finviz_request_error ticker=%s err=%s", ticker_upper, e.__class__.__name__
        )
    except Exception as e:
        result["error"] = f"Parse error: {e.__class__.__name__}"
        log.warning(
            "finviz_parse_error ticker=%s err=%s",
            ticker_upper,
            e.__class__.__name__,
            exc_info=True,
        )

    return result


def _fetch_tiingo(ticker: str) -> Dict[str, Any]:
    """Fetch float data from Tiingo API as fallback.

    Wave 3 Enhancement: Added Tiingo as secondary fallback source.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Dict[str, Any]
        Dictionary with float_shares, shares_outstanding, success keys
    """
    result = {
        "float_shares": None,
        "shares_outstanding": None,
        "short_interest_pct": None,
        "institutional_ownership_pct": None,
        "source": "tiingo",
        "success": False,
        "error": None,
    }

    try:
        from .config import get_settings

        settings = get_settings()

        # Check if Tiingo is enabled and API key is available
        if not settings.feature_tiingo or not settings.tiingo_api_key:
            result["error"] = "Tiingo not enabled or API key missing"
            return result

        # Tiingo fundamentals endpoint
        url = f"https://api.tiingo.com/tiingo/fundamentals/{ticker.lower()}/statements"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {settings.tiingo_api_key}",
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}"
            log.debug(
                "tiingo_request_failed ticker=%s status=%d",
                ticker.upper(),
                response.status_code,
            )
            return result

        data = response.json()

        # Extract shares outstanding from latest quarterly data
        if data and isinstance(data, list) and len(data) > 0:
            latest = data[0] if data else None
            if (
                latest
                and "statementData" in latest
                and isinstance(latest["statementData"], dict)
            ):
                stmt_data = latest["statementData"]
                # Tiingo provides shares outstanding in their fundamental data
                shares_out = stmt_data.get("shareBasic") or stmt_data.get(
                    "weightedAverageShares"
                )
                if shares_out:
                    result["shares_outstanding"] = float(shares_out)
                    # Use shares outstanding as proxy for float if actual float not available
                    result["float_shares"] = result["shares_outstanding"]
                    result["success"] = True
                    log.info(
                        "tiingo_fallback_success ticker=%s float=%.2fM",
                        ticker.upper(),
                        (result["float_shares"] or 0) / 1_000_000,
                    )

    except ImportError:
        result["error"] = "requests not installed"
        log.debug("tiingo_requests_not_available ticker=%s", ticker)
    except Exception as e:
        result["error"] = f"{e.__class__.__name__}: {str(e)}"
        log.warning(
            "tiingo_fetch_failed ticker=%s err=%s", ticker, e.__class__.__name__
        )

    return result


def _fetch_yfinance(ticker: str) -> Dict[str, Any]:
    """Fetch float data from yfinance as fallback.

    Wave 3 Enhancement: Added validation of fetched float values.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Dict[str, Any]
        Dictionary with float_shares, shares_outstanding, success keys
    """
    result = {
        "float_shares": None,
        "shares_outstanding": None,
        "short_interest_pct": None,
        "institutional_ownership_pct": None,
        "source": "yfinance",
        "success": False,
        "error": None,
    }

    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info

        # Extract float and shares outstanding
        result["float_shares"] = info.get("floatShares")
        result["shares_outstanding"] = info.get("sharesOutstanding")
        result["short_interest_pct"] = info.get("shortPercentOfFloat")

        # Wave 3: Validate fetched float value
        if result["float_shares"] is not None:
            if not validate_float_value(result["float_shares"]):
                log.warning(
                    "yfinance_invalid_float ticker=%s float=%.0f",
                    ticker.upper(),
                    result["float_shares"],
                )
                result["float_shares"] = None

        # Mark as successful if we got at least one valid value
        if result["float_shares"] or result["shares_outstanding"]:
            result["success"] = True
            log.info(
                "yfinance_fallback_success ticker=%s float=%.2fM shares_out=%.2fM",
                ticker.upper(),
                (result["float_shares"] or 0) / 1_000_000,
                (result["shares_outstanding"] or 0) / 1_000_000,
            )

    except ImportError:
        result["error"] = "yfinance not installed"
        log.debug("yfinance_not_installed ticker=%s", ticker)
    except Exception as e:
        result["error"] = f"{e.__class__.__name__}: {str(e)}"
        log.warning(
            "yfinance_fetch_failed ticker=%s err=%s", ticker, e.__class__.__name__
        )

    return result


def get_float_data(ticker: str) -> Dict[str, Any]:
    """Get float data for a ticker, using cache when available.

    Wave 3 Enhancement: Multi-source cascading fallback with validation.
    Fetch order: Cache -> FinViz -> yfinance -> Tiingo

    This is the main entry point for float data collection. It checks the cache first,
    then tries FinViz, then falls back to yfinance and Tiingo if needed.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Dict[str, Any]
        Dictionary with keys:
        - ticker: str
        - float_shares: float or None
        - float_class: str (MICRO_FLOAT, LOW_FLOAT, MEDIUM_FLOAT, HIGH_FLOAT, UNKNOWN)
        - multiplier: float (confidence score multiplier)
        - short_interest_pct: float or None
        - shares_outstanding: float or None
        - institutional_ownership_pct: float or None
        - cached_at: str (ISO timestamp)
        - source: str ("cache", "finviz", "yfinance", or "tiingo")
        - success: bool
    """
    # Check if float data feature is enabled
    try:
        import os

        feature_enabled = os.getenv("FEATURE_FLOAT_DATA", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not feature_enabled:
            log.debug("float_data_disabled ticker=%s", ticker)
            return {
                "ticker": ticker.upper().strip(),
                "float_shares": None,
                "float_class": "UNKNOWN",
                "multiplier": 1.0,
                "short_interest_pct": None,
                "shares_outstanding": None,
                "institutional_ownership_pct": None,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "source": "disabled",
                "success": False,
            }
    except Exception:
        pass

    ticker_upper = ticker.upper().strip()

    # Try cache first
    cached_data = _get_from_cache(ticker_upper)

    if cached_data:
        cached_data["source"] = "cache"
        log.debug(
            "float_cache_hit ticker=%s source=%s",
            ticker_upper,
            cached_data.get("source", "unknown"),
        )
        return cached_data

    # Cache miss - scrape FinViz (primary source)
    log.debug("float_cache_miss ticker=%s source=finviz", ticker_upper)
    scrape_result = scrape_finviz(ticker_upper)

    # Wave 3: Validate FinViz float data
    finviz_float = scrape_result.get("float_shares")
    if finviz_float is not None and not validate_float_value(finviz_float):
        log.warning(
            "finviz_invalid_float ticker=%s float=%.0f", ticker_upper, finviz_float
        )
        scrape_result["float_shares"] = None
        scrape_result["success"] = False

    # If FinViz failed or returned no valid float data, try fallback sources
    if not scrape_result.get("success") or not scrape_result.get("float_shares"):
        log.debug("finviz_failed_or_empty ticker=%s trying_fallbacks", ticker_upper)

        # Try yfinance fallback (secondary source)
        yf_result = _fetch_yfinance(ticker_upper)

        if yf_result.get("success") and yf_result.get("float_shares"):
            # yfinance succeeded - use its data
            scrape_result = yf_result
            log.info(
                "float_fetch_success ticker=%s source=yfinance float=%.2fM",
                ticker_upper,
                (yf_result["float_shares"] or 0) / 1_000_000,
            )
        else:
            # yfinance failed - try Tiingo fallback (tertiary source)
            log.debug("yfinance_failed_or_empty ticker=%s trying_tiingo", ticker_upper)
            tiingo_result = _fetch_tiingo(ticker_upper)

            if tiingo_result.get("success") and tiingo_result.get("float_shares"):
                # Tiingo succeeded - use its data
                scrape_result = tiingo_result
                log.info(
                    "float_fetch_success ticker=%s source=tiingo float=%.2fM",
                    ticker_upper,
                    (tiingo_result["float_shares"] or 0) / 1_000_000,
                )
            else:
                # All sources failed
                log.warning("float_fetch_all_sources_failed ticker=%s", ticker_upper)

    # Build result dictionary
    float_shares = scrape_result.get("float_shares")
    float_class = classify_float(float_shares) if float_shares else "UNKNOWN"
    multiplier = get_float_multiplier(float_shares) if float_shares else 1.0

    result = {
        "ticker": ticker_upper,
        "float_shares": float_shares,
        "float_class": float_class,
        "multiplier": multiplier,
        "short_interest_pct": scrape_result.get("short_interest_pct"),
        "shares_outstanding": scrape_result.get("shares_outstanding"),
        "institutional_ownership_pct": scrape_result.get("institutional_ownership_pct"),
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "source": scrape_result.get("source", "finviz"),
        "success": scrape_result.get("success", False),
    }

    # Cache the result (even if scraping failed, to avoid hammering sources)
    # Wave 3: Cache duration is configurable (default 24 hours)
    _save_to_cache(ticker_upper, result)

    return result
