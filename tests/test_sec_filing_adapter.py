"""Tests for SEC filing to NewsItem adapter."""

from datetime import datetime, timezone

import pytest

from catalyst_bot.models import NewsItem
from catalyst_bot.sec_filing_adapter import _build_title, filing_to_newsitem
from catalyst_bot.sec_parser import FilingSection


def test_filing_to_newsitem_8k_with_item():
    """Test conversion of 8-K filing with item code to NewsItem."""
    # Create 8-K filing section
    filing = FilingSection(
        item_code="2.02",
        item_title="Results of Operations and Financial Condition",
        text="Apple Inc. announced Q1 2025 results with revenue of $120B, up 8% YoY.",
        catalyst_type="earnings",
        filing_type="8-K",
        filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000001/form8k.htm",
        cik="0000320193",
        accession="0000320193-25-000001",
    )

    llm_summary = "Apple reports strong Q1 earnings with $120B revenue, beating estimates"
    filing_date = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    # Convert to NewsItem
    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="AAPL",
        filing_date=filing_date,
    )

    # Verify NewsItem fields
    assert isinstance(news_item, NewsItem)
    assert news_item.ticker == "AAPL"
    assert news_item.ts_utc == filing_date
    assert news_item.canonical_url == filing.filing_url
    assert news_item.source == "sec_8k"
    assert news_item.summary == llm_summary

    # Verify title format: "AAPL 8-K Item 2.02 - Results of Operations..."
    assert "AAPL" in news_item.title
    assert "8-K" in news_item.title
    assert "Item 2.02" in news_item.title
    assert "Results of Operations" in news_item.title

    # Verify raw data preservation
    assert news_item.raw is not None
    assert news_item.raw["item_code"] == "2.02"
    assert news_item.raw["catalyst_type"] == "earnings"
    assert news_item.raw["cik"] == "0000320193"


def test_filing_to_newsitem_10q():
    """Test conversion of 10-Q filing to NewsItem."""
    filing = FilingSection(
        item_code="N/A",
        item_title="10-Q Quarterly/Annual Report",
        text="Quarterly report text for Q3 2024...",
        catalyst_type="financial_results",
        filing_type="10-Q",
        filing_url="https://www.sec.gov/Archives/edgar/data/1318605/000131860524000020/tsla-20240930.htm",
        cik="0001318605",
        accession="0001318605-24-000020",
    )

    llm_summary = "Tesla Q3 10-Q shows margin expansion and cash flow improvement"
    filing_date = datetime(2024, 11, 1, 16, 0, 0, tzinfo=timezone.utc)

    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="TSLA",
        filing_date=filing_date,
    )

    assert news_item.ticker == "TSLA"
    assert news_item.source == "sec_10q"
    assert news_item.summary == llm_summary

    # Title should be: "TSLA 10-Q - Quarterly Report"
    assert "TSLA" in news_item.title
    assert "10-Q" in news_item.title
    assert "Quarterly Report" in news_item.title
    # Should NOT include "Item N/A"
    assert "Item N/A" not in news_item.title


def test_filing_to_newsitem_10k():
    """Test conversion of 10-K filing to NewsItem."""
    filing = FilingSection(
        item_code="N/A",
        item_title="10-K Quarterly/Annual Report",
        text="Annual report text for fiscal 2024...",
        catalyst_type="financial_results",
        filing_type="10-K",
        filing_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581025000001/nvda-20241231.htm",
        cik="0001045810",
        accession="0001045810-25-000001",
    )

    llm_summary = "NVIDIA 10-K reveals record data center revenue growth of 217% YoY"
    filing_date = datetime(2025, 2, 20, 21, 0, 0, tzinfo=timezone.utc)

    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="NVDA",
        filing_date=filing_date,
    )

    assert news_item.ticker == "NVDA"
    assert news_item.source == "sec_10k"
    assert news_item.summary == llm_summary

    # Title should be: "NVDA 10-K - Annual Report"
    assert "NVDA" in news_item.title
    assert "10-K" in news_item.title
    assert "Annual Report" in news_item.title


def test_filing_to_newsitem_missing_llm_summary():
    """Test that adapter falls back to truncated text if LLM summary missing."""
    filing = FilingSection(
        item_code="1.01",
        item_title="Entry into Material Agreement",
        text="Long filing text that should be truncated if LLM summary is not provided. " * 50,
        catalyst_type="acquisitions",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
    )

    # Call without llm_summary
    news_item = filing_to_newsitem(
        filing,
        ticker="TEST",
        filing_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
    )

    # Should use truncated filing text (first 500 chars)
    assert news_item.summary is not None
    assert len(news_item.summary) <= 500
    assert "Long filing text" in news_item.summary


def test_filing_to_newsitem_missing_ticker():
    """Test that adapter handles missing ticker gracefully."""
    filing = FilingSection(
        item_code="5.02",
        item_title="Departure of Directors or Certain Officers",
        text="CEO resignation announcement...",
        catalyst_type="management_change",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
    )

    llm_summary = "CEO announces resignation effective immediately"

    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        filing_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
    )

    # Ticker should be None
    assert news_item.ticker is None
    # But conversion should still succeed
    assert news_item.summary == llm_summary
    assert news_item.source == "sec_8k"


def test_filing_to_newsitem_missing_filing_date():
    """Test that adapter defaults to current UTC time if filing_date missing."""
    filing = FilingSection(
        item_code="3.02",
        item_title="Unregistered Sales of Equity Securities",
        text="Registered direct offering...",
        catalyst_type="offering",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
    )

    llm_summary = "Company announces $50M registered direct offering"

    # Get time before conversion
    before = datetime.now(timezone.utc)

    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="DILUTE",
    )

    # Get time after conversion
    after = datetime.now(timezone.utc)

    # Timestamp should be between before and after
    assert before <= news_item.ts_utc <= after
    assert news_item.ts_utc.tzinfo == timezone.utc


def test_filing_to_newsitem_source_format():
    """Test that source field has correct format for runner.py routing."""
    test_cases = [
        ("8-K", "sec_8k"),
        ("10-Q", "sec_10q"),
        ("10-K", "sec_10k"),
    ]

    for filing_type, expected_source in test_cases:
        filing = FilingSection(
            item_code="test",
            item_title="Test Filing",
            text="Test text",
            catalyst_type="news",
            filing_type=filing_type,
            filing_url="https://www.sec.gov/test.htm",
        )

        news_item = filing_to_newsitem(
            filing,
            llm_summary="Test summary",
            ticker="TEST",
            filing_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        )

        assert news_item.source == expected_source


def test_filing_to_newsitem_raw_data_preservation():
    """Test that original filing data is preserved in raw field."""
    filing = FilingSection(
        item_code="1.01",
        item_title="Entry into Material Agreement",
        text="Full filing text here..." * 100,
        catalyst_type="acquisitions",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
        cik="1234567",
        accession="000123456725000001",
    )

    news_item = filing_to_newsitem(
        filing,
        llm_summary="Test summary",
        ticker="TEST",
        filing_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
    )

    # Verify all metadata is preserved
    assert news_item.raw is not None
    assert news_item.raw["item_code"] == "1.01"
    assert news_item.raw["item_title"] == "Entry into Material Agreement"
    assert news_item.raw["catalyst_type"] == "acquisitions"
    assert news_item.raw["filing_type"] == "8-K"
    assert news_item.raw["filing_url"] == filing.filing_url
    assert news_item.raw["cik"] == "1234567"
    assert news_item.raw["accession"] == "000123456725000001"
    # Text should be truncated in raw data
    assert "text_preview" in news_item.raw
    assert len(news_item.raw["text_preview"]) <= 200


def test_build_title_8k_with_item():
    """Test title building for 8-K with item code."""
    title = _build_title(
        ticker="AAPL",
        filing_type="8-K",
        item_code="2.02",
        catalyst_type="earnings",
        item_title="Results of Operations and Financial Condition",
    )

    assert "AAPL" in title
    assert "8-K" in title
    assert "Item 2.02" in title
    assert "Results of Operations" in title


def test_build_title_10q():
    """Test title building for 10-Q."""
    title = _build_title(
        ticker="TSLA",
        filing_type="10-Q",
        item_code="N/A",
        catalyst_type="financial_results",
        item_title="10-Q Quarterly/Annual Report",
    )

    assert "TSLA" in title
    assert "10-Q" in title
    assert "Quarterly Report" in title
    # Should NOT include "Item N/A"
    assert "Item N/A" not in title


def test_build_title_10k():
    """Test title building for 10-K."""
    title = _build_title(
        ticker="NVDA",
        filing_type="10-K",
        item_code="N/A",
        catalyst_type="financial_results",
        item_title="10-K Quarterly/Annual Report",
    )

    assert "NVDA" in title
    assert "10-K" in title
    assert "Annual Report" in title


def test_build_title_long_item_title():
    """Test that long item titles are truncated properly."""
    long_title = "Entry into Material Definitive Agreement with Multiple Parties Regarding Complex Transaction Structure"

    title = _build_title(
        ticker="TEST",
        filing_type="8-K",
        item_code="1.01",
        catalyst_type="acquisitions",
        item_title=long_title,
    )

    # Should be truncated with "..."
    assert "..." in title
    # But should still contain key parts
    assert "TEST" in title
    assert "8-K" in title
    assert "Item 1.01" in title


def test_build_title_missing_ticker():
    """Test title building without ticker."""
    title = _build_title(
        ticker=None,
        filing_type="8-K",
        item_code="7.01",
        catalyst_type="news",
        item_title="Regulation FD Disclosure",
    )

    # Should still work, just without ticker
    assert "8-K" in title
    assert "Item 7.01" in title
    assert "Regulation FD" in title


def test_filing_to_newsitem_integration_workflow():
    """Test complete workflow: filing section → LLM summary → NewsItem."""
    # Simulate real SEC filing workflow
    filing = FilingSection(
        item_code="2.02",
        item_title="Results of Operations and Financial Condition",
        text="""
        On January 15, 2025, Apple Inc. ("Apple") announced financial results
        for its fiscal 2025 first quarter ended December 28, 2024.

        The Company reported quarterly revenue of $119.6 billion, up 2 percent
        year over year, and quarterly earnings per diluted share of $2.18, up
        10 percent year over year. International sales accounted for 66 percent
        of the quarter's revenue.
        """,
        catalyst_type="earnings",
        filing_type="8-K",
        filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000001/form8k.htm",
        cik="0000320193",
        accession="0000320193-25-000001",
    )

    # Simulate LLM extraction
    llm_summary = (
        "Apple reports Q1 FY2025 revenue of $119.6B (+2% YoY) and EPS of $2.18 (+10% YoY). "
        "International sales represent 66% of revenue."
    )

    filing_date = datetime(2025, 1, 15, 21, 30, 0, tzinfo=timezone.utc)

    # Convert to NewsItem
    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="AAPL",
        filing_date=filing_date,
    )

    # Verify the NewsItem is ready for pipeline processing
    assert news_item.ticker == "AAPL"
    assert news_item.source == "sec_8k"
    assert news_item.ts_utc == filing_date

    # Summary should be the LLM output (NOT raw filing text)
    assert news_item.summary == llm_summary
    assert "119.6B" in news_item.summary
    assert "EPS of $2.18" in news_item.summary

    # Title should be human-readable for Discord
    assert "AAPL 8-K Item 2.02" in news_item.title

    # Raw data should preserve original for debugging
    assert news_item.raw["item_code"] == "2.02"
    assert news_item.raw["catalyst_type"] == "earnings"


def test_filing_to_newsitem_negative_catalyst():
    """Test conversion of negative catalyst (dilution, offering)."""
    filing = FilingSection(
        item_code="3.02",
        item_title="Unregistered Sales of Equity Securities",
        text="""
        On January 10, 2025, the Company entered into a securities purchase
        agreement for a registered direct offering of 5,000,000 shares of
        common stock at $2.50 per share for gross proceeds of $12.5 million.
        """,
        catalyst_type="offering",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
    )

    llm_summary = "Registered direct offering: 5M shares at $2.50 ($12.5M gross proceeds)"

    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="DILUTE",
        filing_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
    )

    # Should still convert successfully
    assert news_item.ticker == "DILUTE"
    assert news_item.source == "sec_8k"
    assert news_item.summary == llm_summary
    assert "offering" in news_item.raw["catalyst_type"]


def test_filing_to_newsitem_empty_text():
    """Test handling of filing with empty text field."""
    filing = FilingSection(
        item_code="9.01",
        item_title="Financial Statements and Exhibits",
        text="",  # Empty text
        catalyst_type="financial_statements",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
    )

    llm_summary = "Filing includes updated financial exhibits"

    news_item = filing_to_newsitem(
        filing,
        llm_summary=llm_summary,
        ticker="TEST",
        filing_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
    )

    # Should still work with LLM summary
    assert news_item.summary == llm_summary
    # Raw data should handle empty text gracefully
    assert news_item.raw["text_preview"] == ""


def test_newsitem_timestamp_is_timezone_aware():
    """Test that NewsItem timestamp is always timezone-aware UTC."""
    filing = FilingSection(
        item_code="test",
        item_title="Test",
        text="Test",
        catalyst_type="news",
        filing_type="8-K",
        filing_url="https://www.sec.gov/test.htm",
    )

    # Test with explicit UTC datetime
    filing_date_utc = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    news_item = filing_to_newsitem(
        filing,
        llm_summary="Test",
        ticker="TEST",
        filing_date=filing_date_utc,
    )

    assert news_item.ts_utc.tzinfo == timezone.utc

    # Test with implicit (current time should be UTC)
    news_item_implicit = filing_to_newsitem(
        filing,
        llm_summary="Test",
        ticker="TEST",
    )

    assert news_item_implicit.ts_utc.tzinfo == timezone.utc
