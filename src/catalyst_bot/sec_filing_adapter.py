"""SEC Filing to NewsItem adapter for pipeline integration.

This adapter converts SEC FilingSection objects into NewsItem format for
seamless integration with the existing catalyst pipeline (sentiment scoring,
keyword matching, alert generation).

Key Design Decisions:
- The summary field contains the LLM-extracted summary (NOT raw filing text)
- Source format: "sec_8k", "sec_10k", "sec_10q" (lowercase with underscore)
- Title format: "{TICKER} {FILING_TYPE} {ITEM_CODE} - {CATALYST_TYPE}"
- Timestamps default to current UTC if filing_date not provided

Integration Flow:
1. SEC filing arrives via WebSocket or RSS
2. Filing parsed into FilingSection objects (sec_parser.py)
3. Each section sent to LLM for summarization
4. filing_to_newsitem() converts FilingSection + LLM summary → NewsItem
5. NewsItem enters standard pipeline: classify.py → sentiment scoring → alerts

References:
- NewsItem: src/catalyst_bot/models.py
- FilingSection: src/catalyst_bot/sec_parser.py
- Pipeline integration: src/catalyst_bot/runner.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

try:
    from .models import NewsItem
    from .sec_parser import FilingSection, extract_distress_keywords
except ImportError:
    # Allow running tests without full package installation
    from models import NewsItem  # type: ignore
    from sec_parser import FilingSection, extract_distress_keywords  # type: ignore

try:
    from .logging_utils import get_logger

    log = get_logger("sec_filing_adapter")
except ImportError:
    import logging

    log = logging.getLogger("sec_filing_adapter")


def filing_to_newsitem(
    filing_section: FilingSection,
    llm_summary: Optional[str] = None,
    ticker: Optional[str] = None,
    filing_date: Optional[datetime] = None,
) -> NewsItem:
    """Convert SEC FilingSection to NewsItem for pipeline processing.

    Parameters
    ----------
    filing_section : FilingSection
        Parsed SEC filing section from sec_parser.py
    llm_summary : str, optional
        LLM-extracted summary to use for keyword scoring. If None, uses
        abbreviated filing text (not recommended for production).
    ticker : str, optional
        Stock ticker symbol. If None, extracted from filing_section if available.
    filing_date : datetime, optional
        Filing timestamp. If None, uses current UTC time.

    Returns
    -------
    NewsItem
        Formatted news item ready for pipeline processing

    Examples
    --------
    >>> from sec_parser import parse_8k_items
    >>> sections = parse_8k_items(filing_text, filing_url)
    >>> llm_summary = "Apple announces $500M buyback program"
    >>> news_item = filing_to_newsitem(
    ...     sections[0],
    ...     llm_summary=llm_summary,
    ...     ticker="AAPL",
    ...     filing_date=datetime(2025, 1, 15, tzinfo=timezone.utc)
    ... )
    >>> news_item.ticker
    'AAPL'
    >>> news_item.source
    'sec_8k'
    >>> news_item.summary
    'Apple announces $500M buyback program'

    Notes
    -----
    - The summary parameter is CRITICAL for keyword scoring accuracy
    - Raw filing text is too noisy for sentiment analysis
    - LLM summary should be 1-3 sentences highlighting key catalysts
    - Source format must be "sec_{filing_type_lower}" for runner.py routing
    """
    # Extract ticker from parameters or filing section
    ticker_value = ticker or getattr(filing_section, "ticker", None)

    # Use provided filing_date or current UTC time
    ts_utc = filing_date or datetime.now(timezone.utc)

    # Format source as "sec_8k", "sec_10k", "sec_10q"
    filing_type_lower = filing_section.filing_type.lower().replace("-", "")
    source = f"sec_{filing_type_lower}"

    # Log SEC filing adapter invocation for debugging
    log.info(
        "sec_filing_adapter_called ticker=%s filing_type=%s item_code=%s "
        "has_deal_size=%s has_share_count=%s is_amendment=%s has_llm_summary=%s",
        ticker_value or "N/A",
        filing_section.filing_type,
        filing_section.item_code or "N/A",
        getattr(filing_section, "deal_size_usd", None) is not None,
        getattr(filing_section, "share_count", None) is not None,
        getattr(filing_section, "is_amendment", False),
        llm_summary is not None,
    )

    # Build human-readable title
    title = _build_title(
        ticker=ticker_value,
        filing_type=filing_section.filing_type,
        item_code=filing_section.item_code,
        catalyst_type=filing_section.catalyst_type,
        item_title=filing_section.item_title,
    )

    # Use LLM summary if provided, otherwise fall back to truncated text
    # NOTE: Production should always provide llm_summary for best results
    summary_text = llm_summary
    if not summary_text:
        # Fallback: use first 500 chars of filing text (not ideal)
        summary_text = filing_section.text[:500] if filing_section.text else ""

    # Store original filing section for debugging and audit trail
    raw_data = {
        "item_code": filing_section.item_code,
        "item_title": filing_section.item_title,
        "catalyst_type": filing_section.catalyst_type,
        "filing_type": filing_section.filing_type,
        "filing_url": filing_section.filing_url,
        "cik": filing_section.cik,
        "accession": filing_section.accession,
        "text_preview": filing_section.text[:200] if filing_section.text else "",
        # WAVE 3 ENHANCEMENTS: Pass extracted numeric data and amendment context
        "is_amendment": getattr(filing_section, "is_amendment", False),
        "amendment_context": getattr(filing_section, "amendment_context", None),
        "deal_size_usd": getattr(filing_section, "deal_size_usd", None),
        "share_count": getattr(filing_section, "share_count", None),
        "extracted_amounts": getattr(filing_section, "extracted_amounts", {}),
    }

    # Create NewsItem for pipeline processing
    news_item = NewsItem(
        ts_utc=ts_utc,
        title=title,
        ticker=ticker_value,
        canonical_url=filing_section.filing_url,
        source=source,
        summary=summary_text,
        raw=raw_data,
    )

    # WAVE 3: Enhance title with amendment marker if applicable
    if getattr(filing_section, "is_amendment", False):
        # Add [AMENDED] tag to title for visibility
        news_item.title = f"[AMENDED] {news_item.title}"

        # Prepend amendment context to summary for better context
        amendment_ctx = getattr(filing_section, "amendment_context", None)
        if amendment_ctx and news_item.summary:
            news_item.summary = f"AMENDMENT: {amendment_ctx}\n\n{news_item.summary}"

    # WAVE 3: Enhance summary with deal details if available
    deal_size = getattr(filing_section, "deal_size_usd", None)
    share_count = getattr(filing_section, "share_count", None)

    if deal_size or share_count:
        deal_info_parts = []
        if deal_size:
            # Format as $2.9M, $150M, etc.
            if deal_size >= 1_000_000_000:
                deal_info_parts.append(f"${deal_size / 1_000_000_000:.1f}B")
            elif deal_size >= 1_000_000:
                deal_info_parts.append(f"${deal_size / 1_000_000:.1f}M")
            else:
                deal_info_parts.append(f"${deal_size:,.0f}")

        if share_count:
            # Format as 1.5M shares, 150K shares, etc.
            if share_count >= 1_000_000:
                deal_info_parts.append(f"{share_count / 1_000_000:.1f}M shares")
            elif share_count >= 1_000:
                deal_info_parts.append(f"{share_count / 1_000:.0f}K shares")
            else:
                deal_info_parts.append(f"{share_count:,} shares")

        deal_info = " | ".join(deal_info_parts)

        # Prepend deal info to summary
        if news_item.summary:
            news_item.summary = f"DEAL DETAILS: {deal_info}\n\n{news_item.summary}"

    # WAVE 3: Extract and inject distress keywords for Warning section
    # This ensures distress keywords (delisting, bankruptcy, going concern) are
    # detected BEFORE classify.py runs, so they populate the Warning section
    distress_categories = extract_distress_keywords(filing_section.text)

    if distress_categories:
        # Inject distress keywords into summary so classify.py picks them up
        # Use actual keywords from config.py distress_negative category
        distress_marker_keywords = []

        # Map detected categories to actual text keywords that classify.py will match
        if "distress_negative" in distress_categories:
            # Add marker keywords to summary that will trigger distress_negative in classify.py
            # These match the keywords in config.py distress_negative category
            filing_text_lower = filing_section.text.lower()

            # Check which specific keywords are present and add them to summary
            if "delisting" in filing_text_lower or "delist" in filing_text_lower:
                distress_marker_keywords.append("delisting")
            if "bankruptcy" in filing_text_lower:
                distress_marker_keywords.append("bankruptcy")
            if "going concern" in filing_text_lower:
                distress_marker_keywords.append("going concern warning")
            if "restatement" in filing_text_lower:
                distress_marker_keywords.append("financial restatement")
            if "chapter 11" in filing_text_lower or "chapter 7" in filing_text_lower:
                distress_marker_keywords.append("bankruptcy")

        # Prepend distress warning to summary
        if distress_marker_keywords and news_item.summary:
            distress_warning = (
                f"⚠️ FINANCIAL DISTRESS INDICATORS: {', '.join(distress_marker_keywords)}\n\n"
            )
            news_item.summary = distress_warning + news_item.summary

    return news_item


def _build_title(
    ticker: Optional[str],
    filing_type: str,
    item_code: str,
    catalyst_type: str,
    item_title: str,
) -> str:
    """Build human-readable title for Discord alerts.

    Format Examples:
    - "AAPL 8-K Item 2.02 - Earnings Release"
    - "TSLA 10-Q - Quarterly Report"
    - "NVDA 8-K Item 1.01 - Entry into Material Agreement"

    Parameters
    ----------
    ticker : str, optional
        Stock ticker symbol
    filing_type : str
        Filing type (8-K, 10-Q, 10-K)
    item_code : str
        Item code (e.g., "1.01", "2.02", "N/A")
    catalyst_type : str
        Mapped catalyst type (e.g., "earnings", "acquisitions")
    item_title : str
        Item title from filing

    Returns
    -------
    str
        Formatted title string
    """
    # Start with ticker if available
    parts = []
    if ticker:
        parts.append(ticker)

    # Add filing type
    parts.append(filing_type)

    # Add item code for 8-K filings (exclude "N/A")
    if item_code and item_code != "N/A":
        parts.append(f"Item {item_code}")

    # Build catalyst descriptor
    # Use item_title for 8-Ks, generic description for 10-Q/10-K
    if filing_type == "8-K" and item_title:
        # Truncate long item titles
        descriptor = item_title[:60] + "..." if len(item_title) > 60 else item_title
    elif filing_type == "10-Q":
        descriptor = "Quarterly Report"
    elif filing_type == "10-K":
        descriptor = "Annual Report"
    else:
        # Fallback to catalyst type
        descriptor = catalyst_type.replace("_", " ").title()

    # Combine all parts
    title = " ".join(parts)
    if descriptor:
        title += f" - {descriptor}"

    return title
