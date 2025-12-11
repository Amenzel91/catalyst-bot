# -*- coding: utf-8 -*-
"""Lightweight ticker extraction from PR/news titles.

Default scope: US-listed symbols you can trade on Webull/Robinhood
(Nasdaq, NYSE, NYSE American, AMEX, NYSE Arca, Cboe) + $TICKER.

Env/args toggles:
- ALLOW_OTC_TICKERS=1           -> include OTC/OTCMKTS/OTCQX/OTCQB exchange prefixes
- DOLLAR_TICKERS_REQUIRE_EXCHANGE=1 -> disable loose $TICKER matches (exchange-qualified only)
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Pattern, Tuple

# -----------------------
# Base exchange patterns
# -----------------------

# Keep this list tight for the core platforms.
_EXCH_PREFIX_CORE = r"(?:NASDAQ|Nasdaq|NYSE(?:\s+American)?|AMEX|NYSE\s*Arca|CBOE|Cboe)"

# Optional OTC family (opt-in).
_OTC_PREFIX = r"(?:OTC(?:MKTS)?|OTCQX|OTCQB|OTC\s*Markets?)"

# Core ticker shape:
#  - starts with a letter
#  - letters/digits/.- up to 5 more (total 1-6) => covers BRK.A, BF.B, GOOG, GOOGL
_TICKER_CORE = r"([A-Z][A-Z0-9.\-]{0,5})"

# Dollar-prefixed pattern: "... $ABCD ..."
_DOLLAR_PATTERN = rf"(?:(?<!\w)\${_TICKER_CORE}\b)"


def _build_regex(allow_otc: bool, require_exch_for_dollar: bool) -> Pattern[str]:
    """Build combined regex pattern for ticker extraction.

    Pattern priority (most specific to least specific):
    1. Exchange-qualified: "Nasdaq: AAPL", "NYSE: BA"
    2. Company + Ticker: "Apple (AAPL)", "Tesla Inc. (TSLA)"
    3. Headline start: "TSLA: Deliveries Beat"
    4. Dollar ticker: "$AAPL", "$NVDA"

    The exchange pattern uses inline case-insensitive flag (?i:...) for exchange names,
    but company and headline patterns remain case-sensitive to avoid false positives.
    """
    exch_prefix = rf"(?:{_EXCH_PREFIX_CORE}{'|' + _OTC_PREFIX if allow_otc else ''})"
    # Use inline case-insensitive flag (?i:...) only for the exchange pattern
    exch_pattern = rf"(?i:\b{exch_prefix}\s*[:\-]\s*)\$?{_TICKER_CORE}\b"

    # Build combined pattern with priority ordering
    # Company+ticker and headline patterns are case-sensitive for ticker validation
    if require_exch_for_dollar:
        # Only exchange-qualified patterns (no loose dollar tickers)
        combined = rf"{exch_pattern}|{_COMPANY_TICKER_PATTERN}|{_HEADLINE_START_TICKER}|{_TICKER_SYMBOL_PATTERN}"
    else:
        # Include all patterns
        combined = (
            rf"{exch_pattern}|{_COMPANY_TICKER_PATTERN}|"
            rf"{_HEADLINE_START_TICKER}|{_TICKER_SYMBOL_PATTERN}|{_DOLLAR_PATTERN}"
        )

    # No global IGNORECASE flag - use inline flags where needed
    return re.compile(combined)


# Small cache so we don't recompile every call
_RE_CACHE: Dict[Tuple[bool, bool], Pattern[str]] = {}

# -----------------------
# Enhanced patterns for improved coverage
# -----------------------

# Company name followed by ticker in parentheses
# Matches: "Apple (AAPL)", "Tesla Inc. (TSLA)", "Amazon.com Inc. (AMZN)"
# Pattern breakdown:
#   - [A-Z][A-Za-z0-9&\.\-]* : Company name starting with uppercase
#   - (?:\s+(?:Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|L\.P\.))? : Optional suffix
#   - \s*\( : Opening parenthesis (with optional whitespace)
#   - ([A-Z]{2,5}(?:\.[A-Z])?) : Ticker (2-5 uppercase, optional dot)
#   - \) : Closing parenthesis
_COMPANY_TICKER_PATTERN = (
    r"[A-Z][A-Za-z0-9&\.\-]*"
    r"(?:\s+(?:Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|L\.P\.))?"
    r"\s*\(([A-Z]{2,5}(?:\.[A-Z])?)\)"
)

# Headline start ticker pattern
# Matches: "TSLA: Deliveries Beat", "AAPL: Reports Strong Q3"
# Pattern: ^([A-Z]{2,5}):\s+
#   - ^ : Start of string
#   - ([A-Z]{2,5}) : Ticker (2-5 uppercase letters)
#   - :\s+ : Colon followed by whitespace
_HEADLINE_START_TICKER = r"^([A-Z]{2,5}):\s+"

# Ticker symbol pattern
# Matches: "Ticker symbol: AAPL", "ticker symbol TSLA"
# Pattern: (?:ticker\s+symbol\s*:?\s*)([A-Z]{2,5}(?:\.[A-Z])?)
#   - (?:ticker\s+symbol\s*:?\s*) : Non-capturing group for "ticker symbol" with optional colon
#   - ([A-Z]{2,5}(?:\.[A-Z])?) : Ticker (2-5 uppercase letters, optional class like .A)
_TICKER_SYMBOL_PATTERN = r"(?i:ticker\s+symbol\s*):?\s*([A-Z]{2,5}(?:\.[A-Z])?)"

# Exclusion list for false positives in headline start patterns
# These are common words that appear at the start of headlines with colons
# but are NOT stock tickers (e.g., "PRICE: Stock rises", "UPDATE: Company announces")
_HEADLINE_EXCLUSIONS = {
    "PRICE",
    "UPDATE",
    "ALERT",
    "NEWS",
    "WATCH",
    "FLASH",
    "BRIEF",
    "BREAKING",
    "LIVE",
}

# Exclusion list for common acronyms that appear in parentheses but are NOT tickers
# These are organizations, conferences, regulatory bodies, etc. that get falsely matched
# by the company+ticker pattern like "European Society for Medical Oncology (ESMO)"
_PARENTHETICAL_EXCLUSIONS = {
    # Medical/Scientific Conferences
    "ESMO",  # European Society for Medical Oncology
    "ASCO",  # American Society of Clinical Oncology
    "ASH",   # American Society of Hematology
    "AACR",  # American Association for Cancer Research
    "AHA",   # American Heart Association
    # Regulatory/Government
    "FDA",   # Food and Drug Administration
    "EMA",   # European Medicines Agency
    "SEC",   # Securities and Exchange Commission (already a filing source, but not a ticker)
    "FTC",   # Federal Trade Commission
    "DOJ",   # Department of Justice
    "EPA",   # Environmental Protection Agency
    "WHO",   # World Health Organization
    "CDC",   # Centers for Disease Control
    # Stock Exchanges (to avoid matching exchange names as tickers)
    "NYSE",  # New York Stock Exchange
    "NASDAQ",
    "AMEX",  # American Stock Exchange
    # Business/Industry Organizations
    "CEO",   # Chief Executive Officer
    "CFO",   # Chief Financial Officer
    "CTO",   # Chief Technology Officer
    "COO",   # Chief Operating Officer
    "IPO",   # Initial Public Offering
    "M&A",   # Mergers and Acquisitions
    "R&D",   # Research and Development
    # Common Abbreviations
    "USA",
    "EU",
    "UK",
}


def _get_regex(
    allow_otc: Optional[bool],
    require_exch_for_dollar: Optional[bool],
) -> Pattern[str]:
    # Resolve flags from env if not provided as args
    if allow_otc is None:
        allow_otc = str(os.getenv("ALLOW_OTC_TICKERS", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if require_exch_for_dollar is None:
        require_exch_for_dollar = str(
            os.getenv("DOLLAR_TICKERS_REQUIRE_EXCHANGE", "0")
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    key = (bool(allow_otc), bool(require_exch_for_dollar))
    re_pat = _RE_CACHE.get(key)
    if re_pat is None:
        re_pat = _build_regex(allow_otc, require_exch_for_dollar)
        _RE_CACHE[key] = re_pat
    return re_pat


def _norm(t: str) -> str:
    return (t or "").strip().upper()


def ticker_from_title(
    title: Optional[str],
    *,
    allow_otc: Optional[bool] = None,
    require_exch_for_dollar: Optional[bool] = None,
) -> Optional[str]:
    """Return the first matched ticker from a title, or None.

    Args override env toggles when provided.

    Validates headline start patterns against exclusion list to avoid
    false positives like "PRICE: Stock rises" or "UPDATE: Company announces".
    Also validates against parenthetical exclusions to avoid matching
    organization acronyms like "(ESMO)" or "(FDA)" as tickers.
    """
    if not title:
        return None
    pat = _get_regex(allow_otc, require_exch_for_dollar)
    m = pat.search(title)
    if not m:
        return None
    # Take first non-empty group so this works for both shapes (with/without $-branch)
    raw = next((g for g in m.groups() if g), None)
    if not raw:
        return None

    # Normalize ticker
    t = _norm(raw)

    # Check against parenthetical exclusions (ESMO, FDA, etc.)
    if t in _PARENTHETICAL_EXCLUSIONS:
        return None

    # Check if this is a headline start pattern match
    # The headline pattern is ^([A-Z]{2,5}):\s+ so it matches at start with a colon
    # We can check if the match is at the beginning and the matched text contains ':'
    if m.start() == 0 and ":" in m.group(0):
        # This is a headline start pattern, check against exclusions
        if t in _HEADLINE_EXCLUSIONS:
            return None

    return t


def extract_tickers_from_title(
    title: Optional[str],
    *,
    allow_otc: Optional[bool] = None,
    require_exch_for_dollar: Optional[bool] = None,
) -> List[str]:
    """Return all unique tickers in reading order from a title.

    Args override env toggles when provided.

    Validates headline start patterns against exclusion list to avoid
    false positives like "PRICE: Stock rises" or "UPDATE: Company announces".
    Also validates against parenthetical exclusions to avoid matching
    organization acronyms like "(ESMO)" or "(FDA)" as tickers.
    """
    if not title:
        return []
    pat = _get_regex(allow_otc, require_exch_for_dollar)
    seen = set()
    out: List[str] = []
    for m in pat.finditer(title):
        raw = next((g for g in m.groups() if g), None)
        if not raw:
            continue
        t = _norm(raw)

        # Check against parenthetical exclusions (ESMO, FDA, etc.)
        if t in _PARENTHETICAL_EXCLUSIONS:
            continue

        # Check if this is a headline start pattern match
        # The headline pattern is ^([A-Z]{2,5}):\s+ so it matches at start with a colon
        if m.start() == 0 and ":" in m.group(0):
            # This is a headline start pattern, check against exclusions
            if t in _HEADLINE_EXCLUSIONS:
                continue

        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def ticker_from_summary(
    summary: Optional[str],
    *,
    max_chars: int = 500,
) -> Optional[str]:
    """Extract ticker from article summary/body text.

    This is a fallback function for when ticker_from_title() returns None.
    It looks for exchange-qualified ticker patterns like "(Nasdaq: FRGT)"
    or "(NYSE: BA)" in the first N characters of the summary.

    This function is optimized for speed by only scanning the beginning
    of the summary text, where exchange qualifications typically appear.

    Args:
        summary: Article summary or body text
        max_chars: Maximum characters to scan (default: 500)

    Returns:
        First ticker found, or None

    Examples:
        >>> ticker_from_summary("Freight Technologies (Nasdaq: FRGT) announced...")
        'FRGT'
        >>> ticker_from_summary("Boeing (NYSE: BA) reported...")
        'BA'
        >>> ticker_from_summary("No ticker here")
        None
    """
    if not summary:
        return None

    # Only scan first N characters for performance
    text = summary[:max_chars]

    # Pattern: (Nasdaq: TICKER), (NYSE: TICKER), (AMEX: TICKER), etc.
    # This matches the format commonly used in press releases and news articles
    # Pattern breakdown:
    #   \( : Opening parenthesis (escaped)
    #   (?:Nasdaq|NYSE|AMEX|NYSE American|NYSE Arca|CBOE|Cboe) : Exchange name
    #   :\s* : Colon followed by optional whitespace
    #   ([A-Z]{2,5}(?:\.[A-Z])?) : Ticker (2-5 uppercase, optional dot like BRK.A)
    #   \) : Closing parenthesis (escaped)
    pattern = re.compile(
        r'\((?:Nasdaq|NYSE|AMEX|NYSE American|NYSE Arca|CBOE|Cboe):\s*([A-Z]{2,5}(?:\.[A-Z])?)\)',
        re.IGNORECASE  # Case insensitive for exchange names
    )

    match = pattern.search(text)
    if not match:
        return None

    ticker = match.group(1).upper()

    # Validate against parenthetical exclusions
    if ticker in _PARENTHETICAL_EXCLUSIONS:
        return None

    return ticker


if __name__ == "__main__":
    # quick self-checks
    tests = [
        ("Alpha (Nasdaq: ABCD) + $EFGH; OTCMKTS: XYZ should be ignored", {}),
        ("Up-listing news OTCMKTS: XYZ, plus (Nasdaq: ABCD)", {"allow_otc": True}),
        (
            "Just $ABCD with no exchange should be dropped; but (NYSE: XYZ) should pass",
            {"require_exch_for_dollar": True},
        ),
    ]
    for s, opts in tests:
        print(s, "->", extract_tickers_from_title(s, **opts))
