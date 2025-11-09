"""XBRL financial data parser for 10-Q and 10-K filings.

This module extracts structured financial data from XBRL-formatted SEC filings.
XBRL (eXtensible Business Reporting Language) is the standard format for financial
reporting to the SEC.

Key metrics extracted:
- Total Revenue (Revenues, SalesRevenueNet)
- Net Income (NetIncomeLoss)
- Total Assets (Assets)
- Total Liabilities (Liabilities)
- Cash and Cash Equivalents (CashAndCashEquivalentsAtCarryingValue)

NOTE: This is a lightweight regex-based parser. For production use with complex
filings, consider integrating a full XBRL library like:
- python-xbrl: https://github.com/greedo/python-xbrl
- sec-edgar-xbrl: https://github.com/selgamal/xbrl-parser

References:
- SEC XBRL Resources: https://www.sec.gov/structureddata/osd-inline-xbrl.html
- US GAAP Taxonomy: https://xbrl.us/home/filers/secreportingtaxonomy/
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("xbrl_parser")


log = get_logger("xbrl_parser")


@dataclass
class XBRLFinancials:
    """Structured XBRL financial data."""

    total_revenue: Optional[float] = None  # in USD
    net_income: Optional[float] = None  # in USD
    total_assets: Optional[float] = None  # in USD
    total_liabilities: Optional[float] = None  # in USD
    cash_and_equivalents: Optional[float] = None  # in USD
    shares_outstanding: Optional[float] = None  # number of shares
    period: Optional[str] = None  # FY2024, Q1 2025, etc.
    filing_date: Optional[str] = None  # YYYY-MM-DD

    def is_empty(self) -> bool:
        """Check if no data was extracted."""
        return all(
            v is None
            for v in [
                self.total_revenue,
                self.net_income,
                self.total_assets,
                self.total_liabilities,
                self.cash_and_equivalents,
            ]
        )

    def summary(self) -> str:
        """Generate human-readable summary."""
        parts = []
        if self.total_revenue:
            parts.append(f"Revenue: ${self.total_revenue / 1e6:.1f}M")
        if self.net_income:
            parts.append(f"Net Income: ${self.net_income / 1e6:.1f}M")
        if self.total_assets:
            parts.append(f"Assets: ${self.total_assets / 1e6:.1f}M")
        if self.cash_and_equivalents:
            parts.append(f"Cash: ${self.cash_and_equivalents / 1e6:.1f}M")
        return " | ".join(parts) if parts else "No XBRL data extracted"


# ============================================================================
# XBRL Tag Patterns
# ============================================================================

# Common US GAAP tags for revenue (in order of preference)
REVENUE_TAGS = [
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]

# Net income tags
NET_INCOME_TAGS = [
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "ProfitLoss",
]

# Asset tags
ASSET_TAGS = [
    "Assets",
    "AssetsCurrent",
]

# Liability tags
LIABILITY_TAGS = [
    "Liabilities",
    "LiabilitiesAndStockholdersEquity",
]

# Cash tags
CASH_TAGS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    "CashCashEquivalentsAndShortTermInvestments",
]

# Shares outstanding tags
SHARES_TAGS = [
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
]


# ============================================================================
# Cache Management
# ============================================================================

CACHE_DIR = Path("data/xbrl_cache")
CACHE_TTL_DAYS = 90  # XBRL data changes infrequently


def _get_cache_path(cik: str, accession: str) -> Path:
    """Get cache file path for a filing."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize CIK and accession for filename
    safe_cik = re.sub(r"[^a-zA-Z0-9]", "", cik)
    safe_accession = re.sub(r"[^a-zA-Z0-9]", "", accession)
    return CACHE_DIR / f"{safe_cik}_{safe_accession}.json"


def _load_from_cache(cik: str, accession: str) -> Optional[XBRLFinancials]:
    """Load XBRL data from cache if fresh."""
    cache_path = _get_cache_path(cik, accession)

    if not cache_path.exists():
        return None

    # Check age
    file_age_days = (time.time() - cache_path.stat().st_mtime) / 86400
    if file_age_days > CACHE_TTL_DAYS:
        log.debug(f"Cache expired for CIK={cik}, age={file_age_days:.1f} days")
        return None

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        financials = XBRLFinancials(**data)
        log.info(f"Loaded XBRL data from cache for CIK={cik}")
        return financials

    except Exception as e:
        log.warning(f"Failed to load cache: {e}")
        return None


def _save_to_cache(cik: str, accession: str, financials: XBRLFinancials) -> None:
    """Save XBRL data to cache."""
    cache_path = _get_cache_path(cik, accession)

    try:
        data = {
            "total_revenue": financials.total_revenue,
            "net_income": financials.net_income,
            "total_assets": financials.total_assets,
            "total_liabilities": financials.total_liabilities,
            "cash_and_equivalents": financials.cash_and_equivalents,
            "shares_outstanding": financials.shares_outstanding,
            "period": financials.period,
            "filing_date": financials.filing_date,
        }

        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)

        log.debug(f"Saved XBRL data to cache for CIK={cik}")

    except Exception as e:
        log.warning(f"Failed to save cache: {e}")


# ============================================================================
# XBRL Extraction Functions
# ============================================================================


def parse_xbrl_from_filing(filing_text: str, cik: Optional[str] = None, accession: Optional[str] = None) -> XBRLFinancials:
    """Parse XBRL data from filing text.

    This is a lightweight regex-based parser that extracts key financial metrics
    from XBRL-tagged SEC filings. It handles both inline XBRL (iXBRL) and
    traditional XBRL formats.

    Parameters
    ----------
    filing_text : str
        Full text of the SEC filing
    cik : str, optional
        Company CIK number (for caching)
    accession : str, optional
        Filing accession number (for caching)

    Returns
    -------
    XBRLFinancials
        Structured financial data

    Examples
    --------
    >>> text = '<us-gaap:Revenues contextRef="Q1_2025">150000000</us-gaap:Revenues>'
    >>> financials = parse_xbrl_from_filing(text)
    >>> financials.total_revenue
    150000000.0
    """
    # Check cache first
    if cik and accession:
        cached = _load_from_cache(cik, accession)
        if cached:
            return cached

    financials = XBRLFinancials()

    # Extract revenue
    financials.total_revenue = _extract_xbrl_value(filing_text, REVENUE_TAGS)

    # Extract net income
    financials.net_income = _extract_xbrl_value(filing_text, NET_INCOME_TAGS)

    # Extract assets
    financials.total_assets = _extract_xbrl_value(filing_text, ASSET_TAGS)

    # Extract liabilities
    financials.total_liabilities = _extract_xbrl_value(filing_text, LIABILITY_TAGS)

    # Extract cash
    financials.cash_and_equivalents = _extract_xbrl_value(filing_text, CASH_TAGS)

    # Extract shares outstanding
    financials.shares_outstanding = _extract_xbrl_value(filing_text, SHARES_TAGS)

    # Extract period
    financials.period = _extract_period(filing_text)

    # Extract filing date
    financials.filing_date = _extract_filing_date(filing_text)

    # Save to cache
    if cik and accession and not financials.is_empty():
        _save_to_cache(cik, accession, financials)

    if financials.is_empty():
        log.warning("No XBRL data extracted from filing")
    else:
        log.info(f"Extracted XBRL data: {financials.summary()}")

    return financials


def _extract_xbrl_value(text: str, tag_names: list[str]) -> Optional[float]:
    """Extract numeric value from XBRL tags.

    Tries multiple tag names in order of preference.
    """
    for tag_name in tag_names:
        # Try inline XBRL format: <ix:nonfraction name="us-gaap:Revenues">150000000</ix:nonfraction>
        # Handle multi-line with optional whitespace
        pattern_inline = re.compile(
            rf'<ix:(?:nonfraction|nonfraction2)\s+.*?name=["\']us-gaap:{tag_name}["\'].*?>\s*([0-9.]+)\s*</ix:(?:nonfraction|nonfraction2)>',
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern_inline.search(text)
        if match:
            try:
                value = float(match.group(1).strip())
                log.debug(f"Extracted {tag_name}={value} (inline XBRL)")
                return value
            except ValueError:
                continue

        # Try traditional XBRL format: <us-gaap:Revenues>150000000</us-gaap:Revenues>
        # Handle multi-line with optional whitespace
        pattern_traditional = re.compile(
            rf"<us-gaap:{tag_name}[^>]*>\s*([0-9.]+)\s*</us-gaap:{tag_name}>",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern_traditional.search(text)
        if match:
            try:
                value = float(match.group(1).strip())
                log.debug(f"Extracted {tag_name}={value} (traditional XBRL)")
                return value
            except ValueError:
                continue

    return None


def _extract_period(text: str) -> Optional[str]:
    """Extract reporting period from filing."""
    # Look for "For the three months ended March 31, 2025"
    pattern_quarterly = re.compile(
        r"for the (?:three|six|nine) months ended ([A-Za-z]+ \d{1,2}, \d{4})",
        re.IGNORECASE,
    )
    match = pattern_quarterly.search(text[:5000])  # Search in first 5000 chars
    if match:
        return f"Quarterly: {match.group(1)}"

    # Look for "For the fiscal year ended December 31, 2024"
    pattern_annual = re.compile(
        r"for the (?:fiscal )?year ended ([A-Za-z]+ \d{1,2}, \d{4})",
        re.IGNORECASE,
    )
    match = pattern_annual.search(text[:5000])
    if match:
        return f"Annual: {match.group(1)}"

    return None


def _extract_filing_date(text: str) -> Optional[str]:
    """Extract filing date from document."""
    # Look for FILING DATE tag
    pattern = re.compile(
        r"<FILING-DATE>(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    )
    match = pattern.search(text[:10000])  # Search in first 10k chars
    if match:
        return match.group(1)

    return None


# ============================================================================
# Public API
# ============================================================================


def fetch_xbrl_data(filing_url: str, cik: Optional[str] = None, accession: Optional[str] = None) -> XBRLFinancials:
    """Fetch and parse XBRL data from a filing URL.

    NOTE: This is a stub that would need to be implemented to actually fetch
    the filing from EDGAR. For now, it returns empty financials.

    In a production implementation, this would:
    1. Download the filing from the URL
    2. Parse the XBRL data
    3. Cache the results

    Parameters
    ----------
    filing_url : str
        EDGAR URL for the filing
    cik : str, optional
        Company CIK (for caching)
    accession : str, optional
        Filing accession (for caching)

    Returns
    -------
    XBRLFinancials
        Extracted financial data
    """
    # Check cache
    if cik and accession:
        cached = _load_from_cache(cik, accession)
        if cached:
            return cached

    # TODO: Implement actual EDGAR fetching
    # For now, return empty financials with a note
    log.info(f"fetch_xbrl_data stub called for URL: {filing_url}")
    log.info("XBRL URL fetching not yet implemented - integrate with sec_monitor.py")

    return XBRLFinancials()


def clear_cache(older_than_days: int = CACHE_TTL_DAYS) -> int:
    """Clear old XBRL cache files.

    Parameters
    ----------
    older_than_days : int
        Remove files older than this many days

    Returns
    -------
    int
        Number of files removed
    """
    if not CACHE_DIR.exists():
        return 0

    removed = 0
    cutoff_time = time.time() - (older_than_days * 86400)

    for cache_file in CACHE_DIR.glob("*.json"):
        if cache_file.stat().st_mtime < cutoff_time:
            cache_file.unlink()
            removed += 1

    if removed > 0:
        log.info(f"Cleared {removed} old XBRL cache files")

    return removed
