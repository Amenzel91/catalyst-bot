"""
424B5 Offering Document Parser for Catalyst-Bot.

This module parses SEC 424B5 offering documents to detect dilution events,
extract offering details (size, share count, price), and calculate dilution
impact. The parser applies negative sentiment adjustments to catalyst scores
based on offering severity.

424B5 filings indicate stock offerings (dilution events) with an average
-18% market impact. This module helps traders identify and avoid dilution
events by:

1. Parsing offering size, share count, and price from SEC HTML documents
2. Calculating dilution percentage relative to current float
3. Classifying severity (MINOR/MODERATE/SEVERE/EXTREME)
4. Caching parsed results to avoid redundant network calls

Functions
---------
parse_424b5_filing(filing_url, ticker)
    Main parser that extracts offering details from a 424B5 document URL
extract_offering_size(text)
    Extract dollar amount from document text (e.g. "$12.5 million")
extract_share_count(text)
    Extract number of shares offered (e.g. "5,000,000 shares")
extract_offering_price(text)
    Extract price per share (e.g. "$2.50 per share")
calculate_dilution(shares_offered, current_price, ticker)
    Calculate dilution percentage and price impact
classify_offering_severity(dilution_pct)
    Classify severity as MINOR/MODERATE/SEVERE/EXTREME
fetch_filing_text(filing_url)
    Download and parse HTML content from SEC EDGAR
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup

    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

log = logging.getLogger(__name__)

# Offering severity thresholds and multipliers
SEVERITY_THRESHOLDS = {
    "MINOR": 5.0,  # < 5% dilution
    "MODERATE": 15.0,  # 5-15% dilution
    "SEVERE": 30.0,  # 15-30% dilution
    "EXTREME": 100.0,  # > 30% dilution
}

SEVERITY_MULTIPLIERS = {
    "MINOR": -0.05,
    "MODERATE": -0.15,
    "SEVERE": -0.30,
    "EXTREME": -0.50,
}

# Cache storage path
CACHE_FILE = "data/offerings_cache.json"
CACHE_TTL_DAYS = 90  # Offerings don't change


def _load_cache() -> Dict[str, Any]:
    """Load offering cache from disk."""
    try:
        cache_path = Path(CACHE_FILE)
        if not cache_path.exists():
            return {}

        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)

        # Clean expired entries
        now = datetime.now(timezone.utc)
        cleaned = {}
        for url, entry in cache.items():
            try:
                cached_dt = datetime.fromisoformat(entry.get("cached_at", ""))
                if (now - cached_dt).days < CACHE_TTL_DAYS:
                    cleaned[url] = entry
            except Exception:
                # Skip malformed entries
                continue

        return cleaned
    except Exception as e:
        log.warning("offering_cache_load_failed err=%s", str(e))
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    """Save offering cache to disk."""
    try:
        cache_path = Path(CACHE_FILE)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

        log.debug("offering_cache_saved entries=%d", len(cache))
    except Exception as e:
        log.warning("offering_cache_save_failed err=%s", str(e))


def _extract_numeric_value(text: str, pattern: str) -> Optional[float]:
    """
    Extract numeric value from text using regex pattern.

    Handles formats like:
    - $12.5 million
    - $12,500,000
    - 5,000,000 shares
    - 5 million shares
    - $2.50 per share

    Parameters
    ----------
    text : str
        Source text to search
    pattern : str
        Regex pattern to match

    Returns
    -------
    Optional[float]
        Extracted numeric value, or None if not found
    """
    if not text or not pattern:
        return None

    try:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None

        # Extract numeric part and multiplier (if present)
        value_str = match.group(1)

        # Remove commas and dollar signs
        value_str = value_str.replace(",", "").replace("$", "").strip()

        # Parse base value
        value = float(value_str)

        # Check for million/billion multipliers
        if "million" in match.group(0).lower():
            value *= 1_000_000
        elif "billion" in match.group(0).lower():
            value *= 1_000_000_000

        return value
    except Exception as e:
        log.debug("numeric_extraction_failed pattern=%s err=%s", pattern[:50], str(e))
        return None


def extract_offering_size(text: str) -> Optional[float]:
    """
    Extract offering dollar amount from document text.

    Searches for patterns like:
    - "$12.5 million"
    - "$12,500,000"
    - "aggregate gross proceeds of approximately $12.5 million"

    Parameters
    ----------
    text : str
        Document text to parse

    Returns
    -------
    Optional[float]
        Offering size in dollars, or None if not found
    """
    if not text:
        return None

    # Try multiple patterns in order of specificity
    patterns = [
        r"aggregate\s+gross\s+proceeds\s+of\s+approximately?\s+\$?([\d,\.]+)\s*(million|billion)?",
        r"gross\s+proceeds\s+of\s+approximately?\s+\$?([\d,\.]+)\s*(million|billion)?",
        r"offering\s+of\s+\$?([\d,\.]+)\s*(million|billion)?",
        r"\$?([\d,\.]+)\s*(million|billion)\s+offering",
    ]

    for pattern in patterns:
        value = _extract_numeric_value(text, pattern)
        if value is not None and value > 0:
            log.debug("offering_size_extracted value=%.2f pattern=%s", value, pattern[:50])
            return value

    return None


def extract_share_count(text: str) -> Optional[int]:
    """
    Extract number of shares offered from document text.

    Searches for patterns like:
    - "5,000,000 shares"
    - "5 million shares"
    - "offering of 5,000,000 shares"

    Parameters
    ----------
    text : str
        Document text to parse

    Returns
    -------
    Optional[int]
        Number of shares offered, or None if not found
    """
    if not text:
        return None

    patterns = [
        r"offering\s+of\s+([\d,\.]+)\s*(million|billion)?\s+shares",
        r"([\d,\.]+)\s*(million|billion)?\s+shares\s+of\s+common\s+stock",
        r"([\d,\.]+)\s*(million|billion)?\s+shares",
    ]

    for pattern in patterns:
        value = _extract_numeric_value(text, pattern)
        if value is not None and value > 0:
            log.debug("share_count_extracted value=%d pattern=%s", int(value), pattern[:50])
            return int(value)

    return None


def extract_offering_price(text: str) -> Optional[float]:
    """
    Extract offering price per share from document text.

    Searches for patterns like:
    - "$2.50 per share"
    - "at a price of $2.50"
    - "price of $2.50 per share"

    Parameters
    ----------
    text : str
        Document text to parse

    Returns
    -------
    Optional[float]
        Price per share in dollars, or None if not found
    """
    if not text:
        return None

    patterns = [
        r"\$?([\d,\.]+)\s+per\s+share",
        r"price\s+of\s+\$?([\d,\.]+)\s+per\s+share",
        r"at\s+a\s+price\s+of\s+\$?([\d,\.]+)",
        r"public\s+offering\s+price\s+of\s+\$?([\d,\.]+)",
    ]

    for pattern in patterns:
        value = _extract_numeric_value(text, pattern)
        if value is not None and value > 0:
            log.debug("offering_price_extracted value=%.2f pattern=%s", value, pattern[:50])
            return value

    return None


def calculate_dilution(
    shares_offered: int, current_price: float, ticker: str
) -> Dict[str, Any]:
    """
    Calculate dilution percentage and price impact for an offering.

    Uses fundamental_data module to get current float shares. Estimates
    price impact as ~60% of dilution percentage (empirical average).

    Parameters
    ----------
    shares_offered : int
        Number of shares being offered
    current_price : float
        Current market price per share
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Dict[str, Any]
        Dictionary containing:
        - dilution_pct: Percentage dilution of float
        - price_impact_estimate: Estimated price impact percentage
        - current_float: Current float shares (if available)
    """
    result = {
        "dilution_pct": 0.0,
        "price_impact_estimate": 0.0,
        "current_float": None,
    }

    if not shares_offered or shares_offered <= 0:
        return result

    try:
        # Try to get current float from fundamental_data module
        try:
            from .fundamental_data import get_float_data

            float_data = get_float_data(ticker)
            current_float = float_data.get("float_shares")
        except Exception:
            # Fallback: use yfinance if available
            current_float = None
            try:
                import yfinance as yf

                stock = yf.Ticker(ticker)
                info = stock.info
                current_float = info.get("floatShares")
            except Exception:
                pass

        if current_float and current_float > 0:
            result["current_float"] = current_float

            # Calculate dilution percentage
            dilution_pct = (shares_offered / current_float) * 100.0
            result["dilution_pct"] = dilution_pct

            # Estimate price impact (~60% of dilution shows in price)
            # This is an empirical average; actual impact varies
            price_impact = -1.0 * (dilution_pct * 0.6)
            result["price_impact_estimate"] = price_impact

            log.info(
                "dilution_calculated ticker=%s shares_offered=%d "
                "current_float=%d dilution_pct=%.2f%% price_impact=%.2f%%",
                ticker,
                shares_offered,
                current_float,
                dilution_pct,
                price_impact,
            )
        else:
            log.warning(
                "dilution_calc_no_float ticker=%s shares_offered=%d",
                ticker,
                shares_offered,
            )
    except Exception as e:
        log.warning(
            "dilution_calc_failed ticker=%s shares_offered=%d err=%s",
            ticker,
            shares_offered,
            str(e),
        )

    return result


def classify_offering_severity(dilution_pct: float) -> str:
    """
    Classify offering severity based on dilution percentage.

    Thresholds:
    - MINOR: < 5% dilution (multiplier: -0.05)
    - MODERATE: 5-15% dilution (multiplier: -0.15)
    - SEVERE: 15-30% dilution (multiplier: -0.30)
    - EXTREME: > 30% dilution (multiplier: -0.50)

    Parameters
    ----------
    dilution_pct : float
        Dilution percentage (0-100)

    Returns
    -------
    str
        Severity classification
    """
    if dilution_pct < SEVERITY_THRESHOLDS["MINOR"]:
        return "MINOR"
    elif dilution_pct < SEVERITY_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    elif dilution_pct < SEVERITY_THRESHOLDS["SEVERE"]:
        return "SEVERE"
    else:
        return "EXTREME"


def fetch_filing_text(filing_url: str) -> str:
    """
    Download and extract text from SEC EDGAR filing URL.

    Fetches HTML document, parses with BeautifulSoup, and extracts
    plain text. Includes User-Agent header as required by SEC.

    Parameters
    ----------
    filing_url : str
        Full URL to SEC filing (e.g. https://www.sec.gov/Archives/edgar/...)

    Returns
    -------
    str
        Plain text extracted from filing, or empty string on error
    """
    if not REQUESTS_AVAILABLE or not BEAUTIFULSOUP_AVAILABLE:
        log.warning(
            "filing_fetch_unavailable url=%s reason=missing_dependencies",
            filing_url[:80],
        )
        return ""

    try:
        # SEC requires User-Agent header
        headers = {
            "User-Agent": "Catalyst-Bot/1.0 (compliance@example.com)",
        }

        response = requests.get(filing_url, headers=headers, timeout=15)
        response.raise_for_status()

        # Parse HTML and extract text
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Collapse whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        log.debug("filing_text_fetched url=%s length=%d", filing_url[:80], len(text))
        return text
    except Exception as e:
        log.warning("filing_fetch_failed url=%s err=%s", filing_url[:80], str(e))
        return ""


def parse_424b5_filing(filing_url: str, ticker: str) -> Optional[Dict[str, Any]]:
    """
    Parse a 424B5 offering document and extract key details.

    This is the main entry point for the offering parser. It:
    1. Checks cache for previously parsed results
    2. Fetches and parses the filing document
    3. Extracts offering size, share count, and price
    4. Calculates dilution and classifies severity
    5. Caches results for future use

    Parameters
    ----------
    filing_url : str
        Full URL to the 424B5 filing on SEC EDGAR
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Optional[Dict[str, Any]]
        Dictionary containing:
        - ticker: Stock ticker
        - filing_url: URL to filing
        - filing_date: Date extracted from URL or current date
        - offering_size: Dollar amount of offering
        - shares_offered: Number of shares
        - price_per_share: Price per share
        - dilution_pct: Dilution percentage
        - severity: MINOR/MODERATE/SEVERE/EXTREME
        - price_impact_estimate: Estimated price impact
        - current_float: Current float shares (if available)
        - cached_at: Timestamp when cached

        Returns None if parsing fails or required fields missing
    """
    if not filing_url or not ticker:
        return None

    # Check cache first
    cache = _load_cache()
    if filing_url in cache:
        log.debug("offering_cache_hit url=%s ticker=%s", filing_url[:80], ticker)
        return cache[filing_url]

    log.info("offering_parse_start url=%s ticker=%s", filing_url[:80], ticker)

    # Fetch filing text
    text = fetch_filing_text(filing_url)
    if not text:
        log.warning("offering_parse_no_text url=%s ticker=%s", filing_url[:80], ticker)
        return None

    # Extract offering details
    offering_size = extract_offering_size(text)
    shares_offered = extract_share_count(text)
    price_per_share = extract_offering_price(text)

    # Require at least offering size OR shares offered
    if not offering_size and not shares_offered:
        log.warning(
            "offering_parse_incomplete url=%s ticker=%s",
            filing_url[:80],
            ticker,
        )
        return None

    # Try to derive missing values
    if offering_size and shares_offered and not price_per_share:
        # Calculate price from size and share count
        price_per_share = offering_size / shares_offered
    elif offering_size and price_per_share and not shares_offered:
        # Calculate shares from size and price
        shares_offered = int(offering_size / price_per_share)

    # Calculate dilution if we have share count
    dilution_data = {}
    dilution_pct = 0.0
    severity = "UNKNOWN"

    if shares_offered:
        # Need current price for dilution calculation
        try:
            from .market import get_last_price_snapshot

            snapshot = get_last_price_snapshot(ticker)
            current_price = snapshot.get("last_price") if snapshot else None
        except Exception:
            current_price = None

        if current_price:
            dilution_data = calculate_dilution(shares_offered, current_price, ticker)
            dilution_pct = dilution_data.get("dilution_pct", 0.0)
            severity = classify_offering_severity(dilution_pct)

    # Extract filing date from URL (if possible)
    filing_date = None
    try:
        # URL format: /Archives/edgar/data/{cik}/{accession}/{filename}
        # Accession format: YYYYMMDD-XX-XXXXXX
        parsed = urlparse(filing_url)
        path_parts = parsed.path.split("/")
        if len(path_parts) >= 3:
            accession = path_parts[-2]
            date_part = accession.split("-")[0]
            if len(date_part) == 18:  # YYYYMMDD format
                filing_date = datetime.strptime(date_part[:8], "%Y%m%d").date().isoformat()
    except Exception:
        pass

    if not filing_date:
        filing_date = datetime.now(timezone.utc).date().isoformat()

    # Build result
    result = {
        "ticker": ticker.upper(),
        "filing_url": filing_url,
        "filing_date": filing_date,
        "offering_size": offering_size,
        "shares_offered": shares_offered,
        "price_per_share": price_per_share,
        "dilution_pct": dilution_pct,
        "severity": severity,
        "price_impact_estimate": dilution_data.get("price_impact_estimate", 0.0),
        "current_float": dilution_data.get("current_float"),
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache result
    cache[filing_url] = result
    _save_cache(cache)

    log.info(
        "offering_parse_complete ticker=%s offering_size=%.2fM shares=%d "
        "dilution_pct=%.2f%% severity=%s",
        ticker,
        (offering_size / 1_000_000) if offering_size else 0,
        shares_offered if shares_offered else 0,
        dilution_pct,
        severity,
    )

    return result
