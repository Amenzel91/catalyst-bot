"""Input validation utilities for ticker symbols and other user inputs.

This module provides validation functions to prevent injection attacks and
ensure data integrity throughout the application.
"""

from __future__ import annotations

import re
from typing import Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("validation")


log = get_logger("validation")


# Valid ticker format: letters, numbers, dots, hyphens, forward slash (for forex/crypto)
# Examples: AAPL, BRK.B, BTC-USD, EUR/USD
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-/=^]+$", re.IGNORECASE)

# Maximum ticker length (some tickers can be longer than 5 chars)
MAX_TICKER_LENGTH = 20

# Common crypto tickers to block (unless on user watchlist)
# These are not stocks but cryptocurrencies
CRYPTO_TICKERS = {
    "BTC", "ETH", "SOL", "ADA", "DOT", "LINK", "UNI", "AVAX", "MATIC",
    "DOGE", "SHIB", "LTC", "XRP", "BCH", "ETC", "XLM", "ATOM", "ALGO",
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "DOT-USD",  # Yahoo Finance crypto format
    "BTCUSD", "ETHUSD", "SOLUSD",  # Alternative crypto formats
}


def validate_ticker(ticker: str, allow_empty: bool = False) -> Optional[str]:
    """Validate and sanitize a ticker symbol.

    Parameters
    ----------
    ticker : str
        The ticker symbol to validate
    allow_empty : bool
        Whether to allow empty strings (default: False)

    Returns
    -------
    str or None
        Sanitized ticker symbol in uppercase, or None if invalid

    Examples
    --------
    >>> validate_ticker("AAPL")
    'AAPL'
    >>> validate_ticker("brk.b")
    'BRK.B'
    >>> validate_ticker("BTC-USD")
    'BTC-USD'
    >>> validate_ticker("'; DROP TABLE--")
    None
    >>> validate_ticker("../../../etc/passwd")
    None
    """
    if ticker is None:
        log.warning("ticker_validation_failed reason=none_input")
        return None

    # Convert to string and strip whitespace
    ticker_str = str(ticker).strip()

    # Check empty
    if not ticker_str:
        if allow_empty:
            return ""
        log.warning("ticker_validation_failed reason=empty_input")
        return None

    # Check length
    if len(ticker_str) > MAX_TICKER_LENGTH:
        log.warning(
            "ticker_validation_failed reason=too_long length=%d ticker=%s",
            len(ticker_str),
            ticker_str[:20],
        )
        return None

    # Check format - must match pattern
    if not TICKER_PATTERN.match(ticker_str):
        log.warning(
            "ticker_validation_failed reason=invalid_format ticker=%s", ticker_str[:20]
        )
        return None

    # Normalize to uppercase
    ticker_normalized = ticker_str.upper()

    # Block OTC/foreign tickers (user doesn't want these alerting)
    # - Foreign ADRs ending in "F" are typically 5+ chars (e.g., AIMTF, NSRGY)
    # - Don't block short tickers like CLF (3 chars, NYSE-listed)
    if ticker_normalized.endswith("F") and len(ticker_normalized) >= 5:
        log.info("ticker_validation_failed reason=foreign_adr ticker=%s", ticker_normalized)
        return None

    # Block OTC market suffixes
    if ticker_normalized.endswith(("OTC", "PK", "QB", "QX")):
        log.info("ticker_validation_failed reason=otc_market ticker=%s", ticker_normalized)
        return None

    # Additional security checks - block obvious injection attempts
    dangerous_patterns = [
        "..",  # Path traversal
        "/",  # Path traversal (except in forex tickers like EUR/USD)
        "\\",  # Path traversal
        ";",  # SQL/command injection
        "--",  # SQL comment
        "/*",  # SQL comment
        "*/",  # SQL comment
        "DROP",  # SQL keyword
        "DELETE",  # SQL keyword
        "INSERT",  # SQL keyword
        "UPDATE",  # SQL keyword
        "SELECT",  # SQL keyword
        "<",  # XSS
        ">",  # XSS
        "&",  # Command injection
        "|",  # Command injection
        "$",  # Command injection
        "`",  # Command injection
    ]

    # Allow forward slash only for forex pairs (e.g., EUR/USD)
    if "/" in ticker_normalized:
        parts = ticker_normalized.split("/")
        if len(parts) != 2 or not all(p and p.isalpha() and len(p) == 3 for p in parts):
            log.warning(
                "ticker_validation_failed reason=invalid_forex_format ticker=%s",
                ticker_normalized,
            )
            return None

    # Check for dangerous patterns (excluding '/' which we handle separately)
    for pattern in dangerous_patterns:
        if pattern == "/":
            continue  # Already validated forex format above
        if pattern in ticker_normalized:
            log.warning(
                "ticker_validation_failed reason=dangerous_pattern pattern=%s ticker=%s",
                pattern,
                ticker_normalized[:20],
            )
            return None

    log.debug("ticker_validated ticker=%s", ticker_normalized)
    return ticker_normalized


def is_crypto_ticker(ticker: str, watchlist: Optional[set] = None) -> bool:
    """Check if a ticker is a cryptocurrency (unless on watchlist).

    Parameters
    ----------
    ticker : str
        The ticker symbol to check (should be normalized/uppercase)
    watchlist : Optional[set]
        Set of watchlist tickers. If provided and ticker is in watchlist,
        crypto tickers are allowed through.

    Returns
    -------
    bool
        True if ticker is crypto AND not on watchlist (should be filtered),
        False if ticker is allowed (either not crypto, or crypto but on watchlist)

    Examples
    --------
    >>> is_crypto_ticker("BTC")
    True
    >>> is_crypto_ticker("SOL-USD")
    True
    >>> is_crypto_ticker("AAPL")
    False
    >>> is_crypto_ticker("BTC", watchlist={"BTC", "AAPL"})
    False  # Allowed because on watchlist
    """
    if not ticker:
        return False

    ticker_upper = ticker.upper()

    # Check if it's a known crypto ticker
    if ticker_upper in CRYPTO_TICKERS:
        # If watchlist provided and ticker is on it, allow it
        if watchlist and ticker_upper in watchlist:
            log.debug("crypto_ticker_allowed ticker=%s reason=on_watchlist", ticker_upper)
            return False  # Not filtered (allowed)
        # Crypto ticker not on watchlist - should be filtered
        return True

    return False


def validate_timeframe(timeframe: str) -> Optional[str]:
    """Validate timeframe parameter for charts.

    Parameters
    ----------
    timeframe : str
        Timeframe to validate (e.g., '1D', '5D', '1M', '3M', '1Y')

    Returns
    -------
    str or None
        Validated timeframe in uppercase, or None if invalid
    """
    if not timeframe:
        return None

    tf = str(timeframe).strip().upper()

    # Valid timeframes
    valid_timeframes = {"1D", "5D", "1M", "3M", "6M", "1Y", "2Y", "5Y", "MAX", "YTD"}

    if tf in valid_timeframes:
        return tf

    log.warning("timeframe_validation_failed timeframe=%s", timeframe)
    return None


def sanitize_filename(filename: str, max_length: int = 255) -> Optional[str]:
    """Sanitize a filename to prevent path traversal and other attacks.

    Parameters
    ----------
    filename : str
        The filename to sanitize
    max_length : int
        Maximum allowed filename length (default: 255)

    Returns
    -------
    str or None
        Sanitized filename, or None if invalid
    """
    if not filename:
        return None

    name = str(filename).strip()

    # Remove path separators and dangerous characters
    name = re.sub(r'[/\\:*?"<>|]', "", name)

    # Remove leading/trailing dots and spaces
    name = name.strip(". ")

    # Check length
    if len(name) > max_length or len(name) == 0:
        log.warning(
            "filename_validation_failed length=%d name=%s",
            len(name),
            name[:50] if name else "",
        )
        return None

    return name
