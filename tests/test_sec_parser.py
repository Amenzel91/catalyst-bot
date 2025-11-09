"""Tests for SEC filing parser."""

import pytest

from catalyst_bot.sec_parser import (
    ITEM_CATALYST_MAP,
    FilingSection,
    extract_filing_metadata,
    get_high_priority_items,
    is_negative_catalyst,
    parse_8k_items,
    parse_10q_10k,
)


def test_parse_8k_simple():
    """Test parsing a simple 8-K with one item."""
    filing_text = """
    Item 1.01. Entry into a Material Definitive Agreement

    On January 15, 2025, Acme Corporation entered into a definitive merger
    agreement with Beta Industries for $500 million in cash and stock.
    """

    sections = parse_8k_items(filing_text, "https://sec.gov/test.htm")

    assert len(sections) == 1
    assert sections[0].item_code == "1.01"
    assert "Material Definitive Agreement" in sections[0].item_title
    assert sections[0].catalyst_type == "acquisitions"
    assert sections[0].filing_type == "8-K"
    assert "Acme Corporation" in sections[0].text


def test_parse_8k_multiple_items():
    """Test parsing 8-K with multiple items."""
    filing_text = """
    Item 2.02. Results of Operations and Financial Condition

    Acme Corp announced Q4 2024 results with revenue of $150M, up 25% YoY.

    Item 7.01. Regulation FD Disclosure

    The company is hosting an investor call on February 1st at 9am ET.
    """

    sections = parse_8k_items(filing_text)

    assert len(sections) == 2
    assert sections[0].item_code == "2.02"
    assert sections[0].catalyst_type == "earnings"
    assert sections[1].item_code == "7.01"
    assert sections[1].catalyst_type == "news"


def test_parse_8k_uppercase_format():
    """Test parsing 8-K with uppercase ITEM format."""
    filing_text = """
    ITEM 3.02: Unregistered Sales of Equity Securities

    The company issued 5 million shares in a registered direct offering at $2.50 per share.
    """

    sections = parse_8k_items(filing_text)

    assert len(sections) == 1
    assert sections[0].item_code == "3.02"
    assert sections[0].catalyst_type == "offering"


def test_parse_8k_empty():
    """Test parsing empty filing returns empty list."""
    sections = parse_8k_items("")
    assert sections == []


def test_parse_8k_skips_short_sections():
    """Test that very short sections are skipped."""
    filing_text = """
    Item 9.01. Financial Statements and Exhibits

    None.
    """

    sections = parse_8k_items(filing_text)

    # Should be empty because "None." is too short
    assert len(sections) == 0


def test_extract_filing_metadata():
    """Test extracting CIK and accession from EDGAR URL."""
    url = "https://www.sec.gov/Archives/edgar/data/1234567/000123456721000001/form8k.htm"

    metadata = extract_filing_metadata(url)

    assert metadata["cik"] == "1234567"
    assert metadata["accession"] == "000123456721000001"


def test_extract_filing_metadata_invalid_url():
    """Test extracting metadata from invalid URL."""
    url = "https://example.com/invalid"

    metadata = extract_filing_metadata(url)

    assert metadata["cik"] is None
    assert metadata["accession"] is None


def test_parse_10q():
    """Test parsing 10-Q filing."""
    filing_text = """
    UNITED STATES SECURITIES AND EXCHANGE COMMISSION
    FORM 10-Q
    QUARTERLY REPORT

    For the quarterly period ended September 30, 2024

    Acme Corporation reported net income of $25M for Q3 2024.
    """ * 10  # Make it long enough

    section = parse_10q_10k(filing_text, "10-Q", "https://sec.gov/10q.htm")

    assert section is not None
    assert section.filing_type == "10-Q"
    assert section.catalyst_type == "financial_results"
    assert "Acme Corporation" in section.text


def test_parse_10k():
    """Test parsing 10-K filing."""
    filing_text = "FORM 10-K ANNUAL REPORT - Full year results..." * 100

    section = parse_10q_10k(filing_text, "10-K", "https://sec.gov/10k.htm")

    assert section is not None
    assert section.filing_type == "10-K"
    assert section.catalyst_type == "financial_results"


def test_get_high_priority_items():
    """Test high-priority items list."""
    priority_items = get_high_priority_items()

    assert "1.01" in priority_items  # Material agreements
    assert "2.02" in priority_items  # Earnings
    assert "3.02" in priority_items  # Equity sales
    assert "5.02" in priority_items  # Leadership


def test_is_negative_catalyst_by_item():
    """Test negative catalyst detection by item code."""
    assert is_negative_catalyst("1.03", "Bankruptcy filing")
    assert is_negative_catalyst("3.02", "Equity sales")
    assert is_negative_catalyst("4.02", "Restatement")
    assert not is_negative_catalyst("1.01", "Merger agreement")


def test_is_negative_catalyst_by_keyword():
    """Test negative catalyst detection by text keywords."""
    text_bankruptcy = "The company filed for Chapter 11 bankruptcy protection."
    assert is_negative_catalyst("8.01", text_bankruptcy)

    text_delisting = "NASDAQ has threatened to delist the company's shares."
    assert is_negative_catalyst("8.01", text_delisting)

    text_offering = "Public offering of 10 million shares at $1.50 per share."
    assert is_negative_catalyst("8.01", text_offering)

    text_positive = "Company announces new product launch and partnership."
    assert not is_negative_catalyst("8.01", text_positive)


def test_item_catalyst_map_coverage():
    """Test that all important 8-K items are mapped."""
    # Verify key items are present
    assert ITEM_CATALYST_MAP["1.01"] == "acquisitions"
    assert ITEM_CATALYST_MAP["2.02"] == "earnings"
    assert ITEM_CATALYST_MAP["3.02"] == "offering"
    assert ITEM_CATALYST_MAP["5.02"] == "management_change"
    assert ITEM_CATALYST_MAP["1.03"] == "bankruptcy"

    # Verify we have good coverage
    assert len(ITEM_CATALYST_MAP) >= 15


def test_filing_section_dataclass():
    """Test FilingSection dataclass creation."""
    section = FilingSection(
        item_code="1.01",
        item_title="Entry into Material Agreement",
        text="Merger agreement text...",
        catalyst_type="acquisitions",
        filing_type="8-K",
        filing_url="https://sec.gov/test.htm",
        cik="1234567",
        accession="000123456721000001",
    )

    assert section.item_code == "1.01"
    assert section.catalyst_type == "acquisitions"
    assert section.cik == "1234567"


def test_parse_8k_with_mixed_formatting():
    """Test parsing 8-K with various formatting styles."""
    filing_text = """
    Item 1.01.   Entry into a Material Definitive Agreement

    Text for item 1.01...

    ITEM 5.02: Departure of Directors or Certain Officers

    Text for item 5.02...

    Item 8.01 - Other Events

    Text for item 8.01...
    """

    sections = parse_8k_items(filing_text)

    assert len(sections) == 3
    assert sections[0].item_code == "1.01"
    assert sections[1].item_code == "5.02"
    assert sections[2].item_code == "8.01"
