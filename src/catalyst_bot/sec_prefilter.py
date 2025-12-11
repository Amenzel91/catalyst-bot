"""
SEC Pre-Filter Strategy
========================

Pre-filter SEC filings BEFORE expensive LLM calls to maximize cost efficiency.

This module implements ticker-based filtering that checks:
- Price ceiling/floor constraints
- Minimum liquidity (average volume)
- OTC stock exclusions
- Unit/warrant/rights exclusions

By applying these filters BEFORE LLM digestion, we can skip ~50% of filings
and reduce LLM costs by ~50% while maintaining alert quality.

Usage:
    from sec_prefilter import should_process_filing

    if should_process_filing(ticker, filing_data):
        result = await processor.process_8k(...)  # Expensive LLM call
    else:
        # Skip LLM call, log rejection reason
"""

from __future__ import annotations

import os
from typing import Dict, Any, Optional, Tuple

from .config import get_settings
from .logging_utils import get_logger
from .ticker_map import cik_from_text, load_cik_to_ticker
from .ticker_validation import TickerValidator
from .title_ticker import ticker_from_title

log = get_logger("sec_prefilter")

# Module-level cache for CIK map and ticker validator
_CIK_MAP: Dict[str, str] = {}
_TICKER_VALIDATOR: Optional[TickerValidator] = None


def init_prefilter():
    """
    Initialize pre-filter resources (CIK map, ticker validator).

    Should be called once at startup.
    """
    global _CIK_MAP, _TICKER_VALIDATOR

    if not _CIK_MAP:
        _CIK_MAP = load_cik_to_ticker()
        log.info("cik_map_loaded count=%d", len(_CIK_MAP))

    if _TICKER_VALIDATOR is None:
        _TICKER_VALIDATOR = TickerValidator()
        log.info("ticker_validator_initialized")


def extract_ticker_from_filing(filing: Dict[str, Any]) -> Optional[str]:
    """
    Extract ticker symbol from SEC filing.

    Tries multiple strategies:
    1. CIK lookup from filing URL/ID
    2. Ticker extraction from title
    3. Ticker extraction from summary

    Args:
        filing: Filing dict with keys like item_id, title, document_text

    Returns:
        Ticker symbol or None if not found
    """
    # Ensure CIK map is loaded
    if not _CIK_MAP:
        init_prefilter()

    # Strategy 1: Extract CIK from filing URL/ID
    item_id = filing.get("item_id", "") or filing.get("link", "")
    if item_id:
        cik = cik_from_text(item_id)
        if cik:
            ticker = _CIK_MAP.get(cik) or _CIK_MAP.get(str(cik).zfill(10))
            if ticker:
                log.debug("ticker_from_cik cik=%s ticker=%s", cik, ticker)
                return ticker.upper()

    # Strategy 2: Extract ticker from title
    title = filing.get("title", "")
    if title:
        ticker = ticker_from_title(title)
        if ticker:
            log.debug("ticker_from_title ticker=%s", ticker)
            return ticker.upper()

    # Strategy 3: Extract ticker from document text (first 500 chars)
    doc_text = filing.get("document_text", "")
    if doc_text:
        ticker = ticker_from_title(doc_text[:500])
        if ticker:
            log.debug("ticker_from_summary ticker=%s", ticker)
            return ticker.upper()

    log.debug("ticker_not_found filing=%s", item_id[:50] if item_id else "unknown")
    return None


def check_price_filters(ticker: str) -> Tuple[bool, Optional[str]]:
    """
    Check if ticker passes price ceiling/floor filters.

    Args:
        ticker: Stock ticker symbol

    Returns:
        (passes, reject_reason)
        - passes: True if within price range or filters not configured
        - reject_reason: String describing why rejected, or None if passed
    """
    settings = get_settings()

    # Get price ceiling/floor from settings
    price_ceiling_env = (os.getenv("PRICE_CEILING") or "").strip()
    price_ceiling = None
    try:
        if price_ceiling_env:
            price_ceiling = float(price_ceiling_env)
    except ValueError:
        log.warning("invalid_price_ceiling value=%s", price_ceiling_env)

    price_floor = getattr(settings, "price_floor", None)

    # If no price filters configured, pass
    if price_ceiling is None and price_floor is None:
        return True, None

    # Fetch current price
    try:
        from .market import get_last_price_snapshot

        last_px, _ = get_last_price_snapshot(ticker)

        if last_px is None:
            # Price fetch failed - reject to be safe (can't enforce filter)
            return False, f"price_fetch_failed ticker={ticker}"

        # Check for NaN/Inf
        import math
        if not isinstance(last_px, (int, float)) or math.isnan(last_px) or math.isinf(last_px):
            return False, f"invalid_price ticker={ticker} price={last_px}"

        # Check ceiling
        if price_ceiling is not None and float(last_px) > float(price_ceiling):
            return False, f"above_price_ceiling ticker={ticker} price={last_px:.2f} ceiling={price_ceiling}"

        # Check floor
        if price_floor is not None and float(last_px) < float(price_floor):
            return False, f"below_price_floor ticker={ticker} price={last_px:.2f} floor={price_floor}"

        # Passed all checks
        return True, None

    except Exception as e:
        log.warning("price_filter_check_failed ticker=%s err=%s", ticker, str(e))
        # Fail-safe: Don't reject if price check errors
        return True, None


def check_volume_filter(ticker: str) -> Tuple[bool, Optional[str]]:
    """
    Check if ticker passes minimum average volume filter.

    Args:
        ticker: Stock ticker symbol

    Returns:
        (passes, reject_reason)
    """
    settings = get_settings()
    min_avg_vol = getattr(settings, "min_avg_volume", None)

    # If filter not configured, pass
    if min_avg_vol is None:
        return True, None

    try:
        import yfinance as yf

        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        avg_volume = info.get("averageVolume") or info.get("averageVolume10days") or 0

        if avg_volume < min_avg_vol:
            return False, f"low_volume ticker={ticker} avg_volume={avg_volume} threshold={min_avg_vol}"

        return True, None

    except Exception as e:
        log.debug("volume_check_failed ticker=%s err=%s", ticker, e.__class__.__name__)
        # Fail-safe: Don't reject on volume fetch errors
        return True, None


def check_ticker_validity(ticker: str) -> Tuple[bool, Optional[str]]:
    """
    Check if ticker is valid and tradeable.

    Checks:
    - OTC stocks (rejected)
    - Unit/warrant/rights (rejected)
    - Ticker exists and is tradeable

    Args:
        ticker: Stock ticker symbol

    Returns:
        (passes, reject_reason)
    """
    global _TICKER_VALIDATOR

    if _TICKER_VALIDATOR is None:
        init_prefilter()

    # Check if ticker is OTC (reject)
    try:
        if _TICKER_VALIDATOR and _TICKER_VALIDATOR.is_otc(ticker):
            return False, f"otc_stock ticker={ticker}"
    except Exception as e:
        log.debug("otc_check_failed ticker=%s err=%s", ticker, str(e))

    # Check if ticker is unit/warrant/rights (reject)
    try:
        if _TICKER_VALIDATOR and _TICKER_VALIDATOR.is_unit_or_warrant(ticker):
            return False, f"unit_warrant ticker={ticker}"
    except Exception as e:
        log.debug("unit_warrant_check_failed ticker=%s err=%s", ticker, str(e))

    # Passed all checks
    return True, None


def should_process_filing(
    filing: Dict[str, Any],
    ticker: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Determine if SEC filing should be processed by LLM.

    Applies pre-filters in order:
    1. Ticker extraction (if not provided)
    2. Ticker validity (OTC, unit/warrant checks)
    3. Price ceiling/floor
    4. Minimum volume

    Args:
        filing: Filing dict with keys like item_id, title, document_text
        ticker: Optional pre-extracted ticker (if already known)

    Returns:
        (should_process, ticker, reject_reason)
        - should_process: True if filing should be sent to LLM
        - ticker: Extracted/validated ticker symbol
        - reject_reason: String describing why rejected, or None if passed
    """
    # Extract ticker if not provided
    if not ticker:
        ticker = extract_ticker_from_filing(filing)

    # If no ticker found, reject (can't apply filters)
    if not ticker:
        return False, None, "no_ticker_found"

    # Check ticker validity (OTC, unit/warrant)
    passes, reason = check_ticker_validity(ticker)
    if not passes:
        return False, ticker, reason

    # Check price filters
    passes, reason = check_price_filters(ticker)
    if not passes:
        return False, ticker, reason

    # Check volume filter
    passes, reason = check_volume_filter(ticker)
    if not passes:
        return False, ticker, reason

    # Passed all filters
    log.debug("filing_passed_prefilter ticker=%s", ticker)
    return True, ticker, None


def get_prefilter_stats() -> Dict[str, int]:
    """
    Get statistics about pre-filter performance.

    Returns:
        Dict with counts of rejections by reason
    """
    # This would be enhanced with actual tracking in a production system
    return {
        "total_checked": 0,
        "passed": 0,
        "rejected_no_ticker": 0,
        "rejected_otc": 0,
        "rejected_unit_warrant": 0,
        "rejected_price": 0,
        "rejected_volume": 0,
    }
