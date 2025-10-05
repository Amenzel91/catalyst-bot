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
