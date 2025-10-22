"""Insider Trading Sentiment (SEC Form 4 Analysis)

Analyzes SEC Form 4 filings (insider transactions) to generate sentiment signals.
Insider buying by executives (especially CEO/CFO) is one of the strongest bullish
indicators in equity markets.

Features:
- Fetches recent Form 4 filings from SEC EDGAR API (FREE, no key required)
- Parses transaction details using hybrid LLM (Gemini/Claude fallback)
- Calculates sentiment score based on transaction type, size, and insider role
- Filters out routine 10b5-1 automatic selling plans (not a signal)
- Caches results (24-hour TTL) to respect SEC rate limits

SEC Form 4 Reference:
- Statement of Changes in Beneficial Ownership
- Filed within 2 business days of transaction
- Reports insider purchases and sales
- Includes transaction price, shares, and insider relationship

Sentiment Scoring Logic:
- Large insider buying (>$500k by CEO/CFO): +0.6 to +0.8 sentiment
- Moderate buying ($100k-$500k): +0.3 to +0.5 sentiment
- Small buying (<$100k): +0.1 to +0.2 sentiment
- Routine selling (10b5-1 plans): 0.0 sentiment (neutral)
- Suspicious selling (large, not 10b5-1): -0.2 to -0.4 sentiment
- Weight by insider role: CEO/CFO = 1.0x, Directors = 0.7x, Officers = 0.5x

Architecture:
- Primary: SEC EDGAR API (free, requires User-Agent header)
- Parsing: LLM (Gemini/Claude) to extract transaction details from XML
- Fallback: Simple regex parsing if LLM unavailable
- Cache: 24-hour TTL (Form 4s don't change)
- Rate limit: 10 requests/second max (SEC requirement)

Usage:
    >>> from catalyst_bot.insider_trading_sentiment import get_insider_sentiment
    >>> sentiment, metadata = get_insider_sentiment("AAPL", lookback_days=30)
    >>> print(f"Sentiment: {sentiment:.2f}, Signal: {metadata['signal_strength']}")
    Sentiment: 0.65, Signal: STRONG_BUY

Author: Claude Code
Date: 2025-10-21
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

from .logging_utils import get_logger

log = get_logger("insider_sentiment")

# Cache settings
CACHE_DIR = Path("data/cache/insider_sentiment")
CACHE_TTL_HOURS = 24  # Form 4s don't change, cache for 24 hours
_memory_cache: Dict[str, Tuple[datetime, Tuple[float, Dict[str, Any]]]] = {}

# SEC rate limiting: 10 requests/second max
SEC_RATE_LIMIT = 0.1  # seconds between requests
_last_sec_request_time = 0.0

# Insider role weights (how much to trust each type of insider)
ROLE_WEIGHTS = {
    "ceo": 1.0,
    "chief executive officer": 1.0,
    "cfo": 1.0,
    "chief financial officer": 1.0,
    "president": 0.9,
    "director": 0.7,
    "officer": 0.5,
    "vice president": 0.5,
    "vp": 0.5,
    "10% owner": 0.6,
    "beneficial owner": 0.6,
}

# Initialize cache directory
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _apply_rate_limit() -> None:
    """Apply SEC rate limiting (max 10 requests/second)."""
    global _last_sec_request_time

    now = time.time()
    elapsed = now - _last_sec_request_time

    if elapsed < SEC_RATE_LIMIT:
        time.sleep(SEC_RATE_LIMIT - elapsed)

    _last_sec_request_time = time.time()


def _get_cik_from_ticker(ticker: str) -> Optional[str]:
    """
    Get CIK (Central Index Key) for a ticker.

    Uses existing ticker_map infrastructure.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Zero-padded 10-digit CIK string, or None if not found
    """
    try:
        from .ticker_map import load_cik_to_ticker

        cik_map = load_cik_to_ticker()
        ticker = ticker.upper().strip()

        # Reverse lookup (CIK -> ticker to ticker -> CIK)
        for cik, tkr in cik_map.items():
            if tkr.upper() == ticker:
                return cik  # Already zero-padded

        return None
    except Exception as e:
        log.debug("cik_lookup_failed ticker=%s err=%s", ticker, str(e))
        return None


def _fetch_form4_filings(ticker: str, cik: str, lookback_days: int) -> List[Dict[str, Any]]:
    """
    Fetch recent Form 4 filings from SEC EDGAR API.

    Args:
        ticker: Stock ticker symbol
        cik: Zero-padded 10-digit CIK
        lookback_days: Days to look back for filings

    Returns:
        List of Form 4 filing metadata dictionaries
    """
    from .config import get_settings

    settings = get_settings()
    user_email = getattr(settings, "sec_monitor_user_email", "")

    if not user_email:
        log.warning("sec_email_missing ticker=%s", ticker)
        # Use a default User-Agent if email not configured
        user_email = "catalyst-bot@example.com"

    # Build SEC API URL
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    # Required User-Agent header per SEC guidelines
    headers = {
        "User-Agent": f"Catalyst-Bot/1.0 ({user_email})",
        "Accept": "application/json",
    }

    try:
        # Apply rate limiting
        _apply_rate_limit()

        req = Request(url, headers=headers)
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        # Extract recent filings
        filings_data = data.get("filings", {}).get("recent", {})

        if not filings_data:
            log.debug("no_filings_data ticker=%s cik=%s", ticker, cik)
            return []

        # Parse filing arrays (parallel arrays indexed by position)
        form_types_list = filings_data.get("form", [])
        filing_dates = filings_data.get("filingDate", [])
        accession_numbers = filings_data.get("accessionNumber", [])
        primary_docs = filings_data.get("primaryDocument", [])

        # Calculate lookback cutoff
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Filter for Form 4 filings within lookback window
        form4_filings = []
        for i, form_type in enumerate(form_types_list):
            if form_type != "4":
                continue

            # Parse filing date
            try:
                filing_date_str = filing_dates[i]
                filing_dt = datetime.strptime(filing_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )

                # Skip filings older than lookback window
                if filing_dt < cutoff_time:
                    continue
            except (IndexError, ValueError) as e:
                log.debug("filing_date_parse_failed idx=%d err=%s", i, str(e))
                continue

            # Build filing URL
            try:
                accession = accession_numbers[i].replace("-", "")
                primary_doc = primary_docs[i]
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}"
                    f"/{accession}/{primary_doc}"
                )
            except (IndexError, KeyError):
                filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"

            filing = {
                "ticker": ticker,
                "form_type": form_type,
                "filed_at": filing_dt.isoformat(),
                "accession_number": accession_numbers[i] if i < len(accession_numbers) else "N/A",
                "filing_url": filing_url,
            }

            form4_filings.append(filing)

        log.info(
            "form4_filings_fetched ticker=%s cik=%s count=%d",
            ticker,
            cik,
            len(form4_filings)
        )

        return form4_filings

    except Exception as e:
        log.warning(
            "sec_api_error ticker=%s cik=%s err=%s",
            ticker,
            cik,
            e.__class__.__name__,
            exc_info=True,
        )
        return []


def _parse_form4_with_llm(filing_url: str, ticker: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parse Form 4 filing using LLM to extract transaction details.

    Uses existing llm_hybrid infrastructure (Gemini/Claude fallback).

    Args:
        filing_url: URL to Form 4 filing
        ticker: Stock ticker symbol

    Returns:
        List of transaction dictionaries, or None if parsing fails
    """
    try:
        from .llm_hybrid import query_llm

        # Fetch filing content
        from .sec_document_fetcher import fetch_sec_document_text

        doc_text = fetch_sec_document_text(filing_url)

        if not doc_text or len(doc_text) < 100:
            log.debug("form4_text_empty url=%s", filing_url)
            return None

        # Truncate to first 5000 chars (Form 4s are usually short)
        doc_excerpt = doc_text[:5000]

        # Build LLM prompt
        prompt = f"""Extract insider transactions from this SEC Form 4 filing for {ticker}.

For each transaction, provide:
1. Transaction type (Purchase or Sale)
2. Number of shares
3. Price per share (if available)
4. Transaction date
5. Insider name and title/relationship

Also identify if this is a 10b5-1 automatic trading plan (usually mentioned in footnotes).

Return JSON array format:
[
  {{
    "type": "Purchase" or "Sale",
    "shares": <number>,
    "price_per_share": <number or null>,
    "date": "YYYY-MM-DD",
    "insider_name": "...",
    "insider_title": "...",
    "is_10b5_1": true/false
  }}
]

Form 4 content:
{doc_excerpt}

Return ONLY the JSON array, no other text."""

        # Query LLM
        response = query_llm(prompt, timeout_secs=15.0)

        if not response:
            log.debug("llm_no_response url=%s", filing_url)
            return None

        # Parse JSON response
        # Try to extract JSON array from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            log.debug("llm_no_json url=%s response=%s", filing_url, response[:200])
            return None

        transactions = json.loads(json_match.group(0))

        if not isinstance(transactions, list):
            log.debug("llm_not_array url=%s", filing_url)
            return None

        log.info("form4_parsed_llm url=%s transactions=%d", filing_url, len(transactions))
        return transactions

    except Exception as e:
        log.debug("llm_parse_failed url=%s err=%s", filing_url, str(e))
        return None


def _parse_form4_regex_fallback(filing_url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fallback regex-based Form 4 parsing (simple heuristics).

    This is a minimal fallback if LLM is unavailable. It looks for common
    patterns in Form 4 text but is less accurate than LLM parsing.

    Args:
        filing_url: URL to Form 4 filing

    Returns:
        List of transaction dictionaries, or None if parsing fails
    """
    try:
        from .sec_document_fetcher import fetch_sec_document_text

        doc_text = fetch_sec_document_text(filing_url)

        if not doc_text:
            return None

        # Simple heuristics (very basic, LLM is much better)
        transactions = []

        # Look for purchase/sale keywords
        if re.search(r'\bpurchase\b|\bacquisition\b', doc_text, re.IGNORECASE):
            # Found purchase mention
            transactions.append({
                "type": "Purchase",
                "shares": 0,  # Unknown without LLM
                "price_per_share": None,
                "date": None,
                "insider_name": "Unknown",
                "insider_title": "Unknown",
                "is_10b5_1": False,
            })
        elif re.search(r'\bsale\b|\bdisposition\b', doc_text, re.IGNORECASE):
            # Found sale mention
            transactions.append({
                "type": "Sale",
                "shares": 0,
                "price_per_share": None,
                "date": None,
                "insider_name": "Unknown",
                "insider_title": "Unknown",
                "is_10b5_1": re.search(r'10b5-1', doc_text, re.IGNORECASE) is not None,
            })

        return transactions if transactions else None

    except Exception as e:
        log.debug("regex_parse_failed url=%s err=%s", filing_url, str(e))
        return None


def _calculate_transaction_value(shares: int, price: Optional[float]) -> float:
    """
    Calculate transaction value in USD.

    Args:
        shares: Number of shares
        price: Price per share (may be None)

    Returns:
        Transaction value in USD, or 0 if price unavailable
    """
    if price is None or price <= 0:
        return 0.0
    return float(shares) * price


def _get_role_weight(title: str) -> float:
    """
    Get weight for insider role/title.

    Args:
        title: Insider title/relationship (e.g., "CEO", "Director")

    Returns:
        Weight multiplier (0.5 to 1.0)
    """
    title_lower = title.lower()

    for role, weight in ROLE_WEIGHTS.items():
        if role in title_lower:
            return weight

    # Default weight for unknown roles
    return 0.5


def _score_transactions(transactions: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate insider sentiment score from transactions.

    Args:
        transactions: List of parsed transaction dictionaries

    Returns:
        Tuple of (sentiment_score, metadata)
    """
    if not transactions:
        return 0.0, {
            "transactions": [],
            "net_shares": 0,
            "net_value_usd": 0.0,
            "signal_strength": "NEUTRAL",
            "key_insiders": [],
            "filing_count": 0,
        }

    # Aggregate transactions
    net_shares = 0
    net_value_usd = 0.0
    key_insiders = set()
    buy_count = 0
    sell_count = 0

    for txn in transactions:
        txn_type = txn.get("type", "").lower()
        shares = int(txn.get("shares", 0))
        price = txn.get("price_per_share")
        title = txn.get("insider_title", "Unknown")
        is_10b5_1 = txn.get("is_10b5_1", False)

        # Skip 10b5-1 automatic plans (not a signal)
        if is_10b5_1:
            continue

        # Get role weight
        role_weight = _get_role_weight(title)

        # Track key insiders (CEO/CFO/President)
        if role_weight >= 0.9:
            key_insiders.add(title)

        # Calculate transaction value
        value = _calculate_transaction_value(shares, price)

        # Aggregate net position
        if "purchase" in txn_type or "acquisition" in txn_type:
            net_shares += shares
            net_value_usd += value * role_weight  # Weight by insider importance
            buy_count += 1
        elif "sale" in txn_type or "disposition" in txn_type:
            net_shares -= shares
            net_value_usd -= value * role_weight
            sell_count += 1

    # Calculate sentiment score
    sentiment_score = 0.0

    if net_value_usd > 0:
        # Insider buying (bullish)
        if net_value_usd >= 500000:  # $500k+ = large buying
            sentiment_score = min(0.8, 0.6 + (net_value_usd - 500000) / 5000000)
        elif net_value_usd >= 100000:  # $100k-$500k = moderate buying
            sentiment_score = 0.3 + (net_value_usd - 100000) / 2000000
        else:  # <$100k = small buying
            sentiment_score = min(0.2, net_value_usd / 500000)

        # Boost if CEO/CFO buying
        if any("ceo" in title.lower() or "cfo" in title.lower() for title in key_insiders):
            sentiment_score = min(1.0, sentiment_score * 1.2)

    elif net_value_usd < 0:
        # Insider selling (bearish, but muted)
        # Only assign negative sentiment if it's large selling (>$500k)
        if abs(net_value_usd) >= 500000:
            sentiment_score = max(-0.4, -0.2 - (abs(net_value_usd) - 500000) / 5000000)
        else:
            # Small selling is neutral (insiders sell for many reasons)
            sentiment_score = 0.0

    # Determine signal strength
    if sentiment_score >= 0.6:
        signal_strength = "STRONG_BUY"
    elif sentiment_score >= 0.3:
        signal_strength = "BUY"
    elif sentiment_score <= -0.2:
        signal_strength = "SELL"
    else:
        signal_strength = "NEUTRAL"

    metadata = {
        "transactions": transactions,
        "net_shares": net_shares,
        "net_value_usd": net_value_usd,
        "signal_strength": signal_strength,
        "key_insiders": list(key_insiders),
        "filing_count": len(transactions),
        "buy_count": buy_count,
        "sell_count": sell_count,
    }

    return sentiment_score, metadata


def get_insider_sentiment(ticker: str, lookback_days: int = 30) -> Optional[Tuple[float, Dict[str, Any]]]:
    """
    Fetch recent Form 4 filings and calculate insider sentiment.

    This is the main public interface for insider sentiment analysis.

    Args:
        ticker: Stock ticker symbol
        lookback_days: Days to look back for filings (default: 30)

    Returns:
        Tuple of (sentiment_score, metadata) or None if no data available

        sentiment_score: -1.0 to +1.0
        metadata: {
            "transactions": [...],  # List of transaction details
            "net_shares": int,  # Net shares bought (positive) or sold (negative)
            "net_value_usd": float,  # Net dollar value of transactions
            "signal_strength": str,  # "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL"
            "key_insiders": [str],  # Titles of key insiders who traded
            "filing_count": int,  # Number of Form 4 filings
            "buy_count": int,  # Number of purchase transactions
            "sell_count": int,  # Number of sale transactions
        }

    Examples:
        >>> sentiment, meta = get_insider_sentiment("AAPL")
        >>> if sentiment and sentiment > 0.5:
        ...     print(f"Strong insider buying: {meta['signal_strength']}")
    """
    from .config import get_settings

    settings = get_settings()

    # Check feature flag
    feature_enabled = getattr(settings, "feature_insider_sentiment", True)
    if not feature_enabled:
        log.debug("insider_sentiment_disabled ticker=%s", ticker)
        return None

    # Check memory cache first
    cache_key = f"{ticker}:{lookback_days}"
    if cache_key in _memory_cache:
        cached_at, cached_result = _memory_cache[cache_key]
        cache_age = datetime.now(timezone.utc) - cached_at

        if cache_age < timedelta(hours=CACHE_TTL_HOURS):
            log.debug("insider_cache_hit ticker=%s", ticker)
            return cached_result

        # Stale cache - remove
        del _memory_cache[cache_key]

    # Get CIK for ticker
    cik = _get_cik_from_ticker(ticker)
    if not cik:
        log.debug("cik_not_found ticker=%s", ticker)
        return None

    # Fetch Form 4 filings
    filings = _fetch_form4_filings(ticker, cik, lookback_days)

    if not filings:
        log.debug("no_form4_filings ticker=%s", ticker)
        # Cache null result to avoid repeated API calls
        _memory_cache[cache_key] = (datetime.now(timezone.utc), None)
        return None

    # Parse transactions from each filing
    all_transactions = []

    for filing in filings[:10]:  # Limit to 10 most recent filings to avoid excessive LLM calls
        filing_url = filing.get("filing_url", "")

        # Try LLM parsing first
        transactions = _parse_form4_with_llm(filing_url, ticker)

        # Fallback to regex parsing if LLM fails
        if not transactions:
            transactions = _parse_form4_regex_fallback(filing_url)

        if transactions:
            all_transactions.extend(transactions)

    # Calculate sentiment score
    sentiment_score, metadata = _score_transactions(all_transactions)

    result = (sentiment_score, metadata)

    # Cache result
    _memory_cache[cache_key] = (datetime.now(timezone.utc), result)

    log.info(
        "insider_sentiment ticker=%s score=%.3f signal=%s filings=%d transactions=%d",
        ticker,
        sentiment_score,
        metadata["signal_strength"],
        len(filings),
        len(all_transactions),
    )

    return result
