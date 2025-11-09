"""SEC Filing Parser with 8-K item-specific routing.

This module parses SEC filings (8-K, 10-Q, 10-K) and extracts structured data
including item codes, titles, and relevant sections. It routes 8-K items to
appropriate catalyst types for downstream processing.

8-K Item Mapping:
-----------------
- Item 1.01: Entry into Material Agreement → acquisitions, partnerships
- Item 2.02: Results of Operations (earnings) → earnings
- Item 3.02: Unregistered Sales of Equity → dilution, offering
- Item 5.02: Leadership Changes → management_change
- Item 7.01: Regulation FD Disclosure → general news
- Item 8.01: Other Events → general news

References:
- SEC 8-K Form Guide: https://www.sec.gov/files/form8-k.pdf
- EDGAR Filings: https://www.sec.gov/edgar/searchedgar/companysearch.html
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("sec_parser")


log = get_logger("sec_parser")


@dataclass
class FilingSection:
    """Structured representation of an SEC filing section."""

    item_code: str  # e.g., "1.01", "2.02"
    item_title: str  # e.g., "Entry into a Material Definitive Agreement"
    text: str  # Section text content
    catalyst_type: str  # Mapped catalyst: acquisitions, earnings, offering, etc.
    filing_type: str  # 8-K, 10-Q, 10-K
    filing_url: str  # EDGAR URL
    cik: Optional[str] = None  # Company CIK number
    accession: Optional[str] = None  # Filing accession number
    # WAVE 3 ENHANCEMENTS: Amendment detection and numeric extraction
    is_amendment: bool = False  # True if this is an 8-K/A, 10-Q/A, etc.
    amendment_context: Optional[str] = None  # What was amended and why
    deal_size_usd: Optional[float] = None  # Extracted deal size in USD
    share_count: Optional[int] = None  # Number of shares in offering
    extracted_amounts: dict = field(default_factory=dict)  # All extracted dollar amounts


# 8-K Item to Catalyst Type Mapping
# Based on historical analysis of high-impact filings
ITEM_CATALYST_MAP = {
    "1.01": "acquisitions",  # Entry into Material Agreement
    "1.02": "acquisitions",  # Termination of Material Agreement
    "1.03": "bankruptcy",  # Bankruptcy or Receivership
    "2.01": "financial_results",  # Completion of Acquisition
    "2.02": "earnings",  # Results of Operations (earnings release)
    "2.03": "offering",  # Creation of Direct Financial Obligation
    "2.04": "offering",  # Triggering Events That Accelerate Obligations
    "3.01": "bankruptcy",  # Notice of Delisting
    "3.02": "offering",  # Unregistered Sales of Equity Securities
    "3.03": "dilution",  # Material Modification to Rights of Shareholders
    "4.01": "management_change",  # Changes in Registrant's Certifying Accountant
    "4.02": "restatement",  # Non-Reliance on Previously Issued Financials
    "5.01": "management_change",  # Changes in Control of Registrant
    "5.02": "management_change",  # Departure/Appointment of Directors or Officers
    "5.03": "management_change",  # Amendments to Articles/Bylaws
    "5.04": "voting_change",  # Temporary Suspension of Trading
    "5.05": "offering",  # Listing on National Exchange
    "5.07": "warrant_exercise",  # Submission of Matters to a Vote
    "7.01": "news",  # Regulation FD Disclosure
    "8.01": "news",  # Other Events
    "9.01": "financial_statements",  # Financial Statements and Exhibits
}

# Item title patterns for extraction
ITEM_PATTERNS = [
    # Match "Item 1.01" with optional period and title
    re.compile(
        r"Item\s+(\d+\.\d+)[\.\s]+([^\n]+)",
        re.IGNORECASE,
    ),
    # Match "ITEM 1.01:" format
    re.compile(
        r"ITEM\s+(\d+\.\d+)\s*:?\s*([^\n]+)",
        re.IGNORECASE,
    ),
    # Match "Item 8.01 - Other Events" format (with dash)
    re.compile(
        r"Item\s+(\d+\.\d+)\s*-\s*([^\n]+)",
        re.IGNORECASE,
    ),
]


def parse_8k_items(filing_text: str, filing_url: str = "") -> list[FilingSection]:
    """Parse 8-K filing and extract item-specific sections.

    Parameters
    ----------
    filing_text : str
        Full text content of the 8-K filing
    filing_url : str, optional
        EDGAR URL for the filing

    Returns
    -------
    list[FilingSection]
        List of parsed filing sections with item codes and catalyst types

    Examples
    --------
    >>> text = "Item 1.01. Entry into Material Agreement\\nAcme Corp entered..."
    >>> sections = parse_8k_items(text)
    >>> sections[0].item_code
    '1.01'
    >>> sections[0].catalyst_type
    'acquisitions'
    """
    if not filing_text:
        log.warning("parse_8k_items called with empty filing_text")
        return []

    sections: list[FilingSection] = []
    lines = filing_text.split("\n")

    current_item = None
    current_title = None
    current_text = []

    for line in lines:
        # Try to match item patterns
        item_match = None
        for pattern in ITEM_PATTERNS:
            item_match = pattern.search(line)
            if item_match:
                break

        if item_match:
            # Save previous item if exists
            if current_item:
                _save_section(
                    sections,
                    current_item,
                    current_title,
                    current_text,
                    filing_url,
                    filing_type="8-K",
                    full_filing_text=filing_text,
                )

            # Start new item
            current_item = item_match.group(1)
            current_title = item_match.group(2).strip()
            current_text = []
            log.debug(f"Found item {current_item}: {current_title}")
        elif current_item:
            # Append to current item text
            current_text.append(line)

    # Save last item
    if current_item:
        _save_section(
            sections,
            current_item,
            current_title,
            current_text,
            filing_url,
            filing_type="8-K",
            full_filing_text=filing_text,
        )

    log.info(f"Parsed 8-K with {len(sections)} items: {[s.item_code for s in sections]}")
    return sections


def _save_section(
    sections: list[FilingSection],
    item_code: str,
    item_title: str,
    text_lines: list[str],
    filing_url: str,
    filing_type: str = "8-K",
    full_filing_text: str = "",
) -> None:
    """Save a filing section to the sections list with enhanced extraction.

    WAVE 3 ENHANCEMENTS: Now extracts deal amounts, share counts, and
    amendment context automatically.
    """
    text = "\n".join(text_lines).strip()

    # Skip empty sections
    if not text or len(text) < 50:
        log.debug(f"Skipping empty/short section for Item {item_code}")
        return

    # Map to catalyst type
    catalyst_type = ITEM_CATALYST_MAP.get(item_code, "news")

    # WAVE 3: Extract deal amounts and share counts
    amounts = extract_deal_amounts(text)

    # WAVE 3: Detect amendments (use full filing text for better detection)
    is_amendment, amendment_context = detect_amendment(
        full_filing_text if full_filing_text else text, filing_type
    )

    section = FilingSection(
        item_code=item_code,
        item_title=item_title,
        text=text,
        catalyst_type=catalyst_type,
        filing_type=filing_type,
        filing_url=filing_url,
        # WAVE 3 enhancements
        is_amendment=is_amendment,
        amendment_context=amendment_context,
        deal_size_usd=amounts.get("deal_size_usd"),
        share_count=amounts.get("share_count"),
        extracted_amounts=amounts,
    )

    sections.append(section)


def extract_filing_metadata(filing_url: str) -> dict[str, Optional[str]]:
    """Extract CIK and accession number from EDGAR URL.

    Parameters
    ----------
    filing_url : str
        EDGAR filing URL

    Returns
    -------
    dict
        Dictionary with 'cik' and 'accession' keys

    Examples
    --------
    >>> url = "https://www.sec.gov/Archives/edgar/data/1234567/000123456721000001/form8k.htm"
    >>> meta = extract_filing_metadata(url)
    >>> meta['cik']
    '1234567'
    """
    metadata = {"cik": None, "accession": None}

    # Pattern: /edgar/data/{CIK}/{ACCESSION}/...
    pattern = re.compile(r"/edgar/data/(\d+)/(\d+)/")
    match = pattern.search(filing_url)

    if match:
        metadata["cik"] = match.group(1)
        metadata["accession"] = match.group(2)
        log.debug(f"Extracted CIK={metadata['cik']}, accession={metadata['accession']}")

    return metadata


def parse_10q_10k(filing_text: str, filing_type: str, filing_url: str = "") -> FilingSection:
    """Parse 10-Q or 10-K filing into a single section.

    Unlike 8-Ks, 10-Q/10-K filings don't have item-specific routing.
    We treat them as a single entity for financial_results processing.

    Parameters
    ----------
    filing_text : str
        Full text content of the filing
    filing_type : str
        Either "10-Q" or "10-K"
    filing_url : str, optional
        EDGAR URL for the filing

    Returns
    -------
    FilingSection
        Single section representing the entire filing
    """
    if not filing_text:
        log.warning(f"parse_{filing_type.lower()} called with empty filing_text")
        return None

    # 10-Q/10-K are always financial results
    catalyst_type = "financial_results"

    # Extract first 5000 characters for summary (full text can be huge)
    summary_text = filing_text[:5000]

    section = FilingSection(
        item_code="N/A",
        item_title=f"{filing_type} Quarterly/Annual Report",
        text=summary_text,
        catalyst_type=catalyst_type,
        filing_type=filing_type,
        filing_url=filing_url,
    )

    log.info(f"Parsed {filing_type} filing")
    return section


def get_high_priority_items() -> list[str]:
    """Get list of high-priority 8-K items for urgent processing.

    Returns
    -------
    list[str]
        Item codes that should be processed immediately

    Notes
    -----
    Based on MOA analysis:
    - Item 1.01 (Material Agreements): High impact acquisitions
    - Item 2.02 (Earnings): Time-sensitive market movers
    - Item 3.02 (Equity Sales): Dilution red flags
    - Item 5.02 (Leadership): Management shake-ups
    """
    return ["1.01", "2.02", "3.02", "5.02"]


def is_negative_catalyst(item_code: str, text: str) -> bool:
    """Determine if an 8-K item represents a negative catalyst (exit signal).

    Parameters
    ----------
    item_code : str
        8-K item code (e.g., "3.02")
    text : str
        Section text content

    Returns
    -------
    bool
        True if this is a negative catalyst requiring exit alert

    Notes
    -----
    Negative catalysts include:
    - Item 1.03: Bankruptcy
    - Item 3.02: Unregistered equity sales (dilution)
    - Item 4.02: Financial restatements
    - Text containing: "going concern", "delisting", "warrant exercise"
    """
    # Known negative item codes
    negative_items = {"1.03", "3.01", "3.02", "4.02"}

    if item_code in negative_items:
        return True

    # Check text for negative keywords
    text_lower = text.lower()
    negative_keywords = [
        "going concern",
        "delisting",
        "delist",
        "bankruptcy",
        "warrant exercise",
        "dilution",
        "offering",
        "public offering",
        "registered direct",
    ]

    for keyword in negative_keywords:
        if keyword in text_lower:
            log.info(f"Detected negative catalyst keyword: {keyword}")
            return True

    return False


# ============================================================================
# WAVE 3 ENHANCEMENTS: Numeric Extraction & Amendment Detection
# ============================================================================


def extract_deal_amounts(text: str) -> dict:
    """Extract dollar amounts and share counts from SEC filing text.

    Targets ATM offerings, registered directs, and material agreements with
    specific deal sizes mentioned.

    Parameters
    ----------
    text : str
        Filing section text

    Returns
    -------
    dict
        Extracted amounts with keys:
        - deal_size_usd: float (primary deal size in USD)
        - share_count: int (number of shares)
        - all_amounts: list of tuples (amount, unit, context)

    Examples
    --------
    >>> text = "Agreement for $2.9 million ATM offering of 1,500,000 shares"
    >>> result = extract_deal_amounts(text)
    >>> result['deal_size_usd']
    2900000.0
    >>> result['share_count']
    1500000
    """
    result = {
        "deal_size_usd": None,
        "share_count": None,
        "all_amounts": [],
    }

    # Dollar amount patterns: $2.9M, $2.9 million, $150,000
    amount_patterns = [
        # Pattern: $2.9 million, $150M, $1.5B
        re.compile(
            r"\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B|MM)\b",
            re.IGNORECASE,
        ),
        # Pattern: $2,900,000 (with commas)
        re.compile(r"\$\s*([\d,]+)\b(?!\s*(?:million|billion|M|B))", re.IGNORECASE),
    ]

    # Share count patterns: 1,500,000 shares, 1.5M shares
    share_patterns = [
        re.compile(r"(\d+(?:\.\d+)?)\s*(million|M)\s+shares", re.IGNORECASE),
        re.compile(r"([\d,]+)\s+shares", re.IGNORECASE),
    ]

    # Extract dollar amounts
    for pattern in amount_patterns:
        for match in pattern.finditer(text):
            try:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)

                # Check if there's a unit multiplier
                if len(match.groups()) > 1 and match.group(2):
                    unit = match.group(2).lower()
                    if unit in ("million", "m", "mm"):
                        value *= 1_000_000
                    elif unit in ("billion", "b"):
                        value *= 1_000_000_000
                else:
                    # Raw dollar amount (e.g., $2,900,000)
                    # If value is less than 1000, it's probably millions mentioned without unit
                    if value < 1000:
                        value *= 1_000_000

                # Get surrounding context (±50 chars)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace("\n", " ")

                result["all_amounts"].append((value, match.group(0), context))

                # Set primary deal size to first/largest amount
                if result["deal_size_usd"] is None or value > result["deal_size_usd"]:
                    result["deal_size_usd"] = value

            except (ValueError, IndexError) as e:
                log.debug(f"Failed to parse amount '{match.group(0)}': {e}")
                continue

    # Extract share counts
    for pattern in share_patterns:
        for match in pattern.finditer(text):
            try:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)

                # Check for million multiplier
                if len(match.groups()) > 1 and match.group(2):
                    unit = match.group(2).lower()
                    if unit in ("million", "m"):
                        value *= 1_000_000

                share_count = int(value)

                # Set share count to first/largest found
                if result["share_count"] is None or share_count > result["share_count"]:
                    result["share_count"] = share_count

            except (ValueError, IndexError) as e:
                log.debug(f"Failed to parse share count '{match.group(0)}': {e}")
                continue

    if result["deal_size_usd"] or result["share_count"]:
        log.info(
            f"Extracted deal amounts: ${result['deal_size_usd']:,.0f} USD, "
            f"{result['share_count']:,} shares"
            if result["deal_size_usd"] and result["share_count"]
            else f"deal_size=${result['deal_size_usd']:,.0f}"
            if result["deal_size_usd"]
            else f"shares={result['share_count']:,}"
        )

    return result


def detect_amendment(filing_text: str, filing_type: str) -> tuple[bool, Optional[str]]:
    """Detect if filing is an amendment (8-K/A, 10-Q/A) and extract context.

    Parameters
    ----------
    filing_text : str
        Full text of the filing
    filing_type : str
        Filing type (8-K, 10-Q, 10-K)

    Returns
    -------
    tuple[bool, Optional[str]]
        (is_amendment, amendment_context)
        - is_amendment: True if this is an amended filing
        - amendment_context: 1-2 sentence explanation of what changed

    Examples
    --------
    >>> text = "FORM 8-K/A (AMENDMENT NO. 1) ... This amendment corrects the share count"
    >>> is_amend, context = detect_amendment(text, "8-K")
    >>> is_amend
    True
    >>> "corrects" in context
    True
    """
    is_amendment = False
    amendment_context = None

    # Check for amendment markers in filing type or header
    amendment_patterns = [
        re.compile(r"FORM\s+(\d+-[KQ]/A)", re.IGNORECASE),  # 8-K/A, 10-Q/A
        re.compile(r"AMENDMENT\s+NO\.\s*(\d+)", re.IGNORECASE),  # Amendment No. 1
        re.compile(r"/A\b", re.IGNORECASE),  # /A suffix
        re.compile(r"AMENDED", re.IGNORECASE),  # "Amended" keyword
    ]

    # Search first 1000 characters for amendment markers
    header_text = filing_text[:1000]

    for pattern in amendment_patterns:
        if pattern.search(header_text):
            is_amendment = True
            log.info(f"Detected amendment filing: {pattern.pattern}")
            break

    # Extract amendment context if this is an amendment
    if is_amendment:
        # Look for explanatory text patterns
        context_patterns = [
            # "This amendment corrects/revises/updates..."
            re.compile(
                r"(?:this|the)\s+amendment\s+(?:corrects?|revises?|updates?|clarifies?|amends?)\s+([^.]{20,150}\.)",
                re.IGNORECASE,
            ),
            # "The Company is filing this amendment to..."
            re.compile(
                r"(?:is|are)\s+filing\s+this\s+amendment\s+to\s+([^.]{20,150}\.)",
                re.IGNORECASE,
            ),
            # "Amended to reflect..."
            re.compile(
                r"amended\s+to\s+(?:reflect|correct|update|revise|clarify)\s+([^.]{20,150}\.)",
                re.IGNORECASE,
            ),
        ]

        # Search first 2000 characters for explanation
        search_text = filing_text[:2000]

        for pattern in context_patterns:
            match = pattern.search(search_text)
            if match:
                # Extract the explanation
                explanation = match.group(0).strip()
                # Clean up whitespace
                explanation = re.sub(r"\s+", " ", explanation)
                amendment_context = explanation[:200]  # Limit to 200 chars
                log.info(f"Extracted amendment context: {amendment_context}")
                break

        # Fallback: if no specific context found, provide generic message
        if not amendment_context:
            amendment_context = (
                f"This is an amended {filing_type} filing. "
                "Review the filing for corrections or additional disclosures."
            )

    return is_amendment, amendment_context


def extract_distress_keywords(text: str) -> list[str]:
    """Extract financial distress keywords that should populate Warning section.

    This function specifically looks for distress-related keywords that indicate
    financial trouble (delisting, bankruptcy, going concern, etc.) and returns
    them in a format compatible with the negative_keywords system.

    Parameters
    ----------
    text : str
        Filing section text

    Returns
    -------
    list[str]
        List of detected distress keyword categories (e.g., ["distress_negative"])

    Notes
    -----
    This addresses the AMST issue where distress keywords were detected but
    didn't populate the Warning section. The returned categories will be added
    to the negative_keywords list in classify.py.
    """
    detected_categories = []
    text_lower = text.lower()

    # Distress keyword groups (matches config.py distress_negative)
    distress_keywords = {
        "delisting": ["delisting", "delist", "nasdaq delisting", "nyse delisting"],
        "bankruptcy": ["bankruptcy", "chapter 11", "chapter 7", "insolvent"],
        "going_concern": ["going concern", "substantial doubt"],
        "financial_distress": [
            "financial restatement",
            "restatement",
            "sec investigation",
            "fraud investigation",
        ],
    }

    # Check for any distress keywords
    found_distress = False
    matched_keywords = []

    for category, keywords in distress_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                found_distress = True
                matched_keywords.append(keyword)
                log.info(f"Detected distress keyword: {keyword} (category: {category})")

    # Return distress_negative category if any keywords matched
    if found_distress:
        detected_categories.append("distress_negative")
        log.info(
            f"Filing contains distress indicators: {', '.join(matched_keywords[:3])} "
            f"-> flagged as distress_negative"
        )

    return detected_categories
