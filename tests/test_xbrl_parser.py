"""Tests for XBRL parser."""

import pytest

from catalyst_bot.xbrl_parser import (
    XBRLFinancials,
    _extract_filing_date,
    _extract_period,
    _extract_xbrl_value,
    clear_cache,
    parse_xbrl_from_filing,
)


def test_xbrl_financials_dataclass():
    """Test XBRLFinancials dataclass."""
    financials = XBRLFinancials(
        total_revenue=150_000_000,
        net_income=18_000_000,
        total_assets=500_000_000,
        total_liabilities=300_000_000,
        cash_and_equivalents=50_000_000,
        period="Q1 2025",
        filing_date="2025-05-01",
    )

    assert financials.total_revenue == 150_000_000
    assert financials.net_income == 18_000_000
    assert not financials.is_empty()

    summary = financials.summary()
    assert "Revenue: $150.0M" in summary
    assert "Net Income: $18.0M" in summary
    assert "Assets: $500.0M" in summary
    assert "Cash: $50.0M" in summary


def test_xbrl_financials_empty():
    """Test empty XBRLFinancials."""
    financials = XBRLFinancials()

    assert financials.is_empty()
    assert "No XBRL data extracted" in financials.summary()


def test_extract_xbrl_value_inline():
    """Test extracting XBRL value from inline format."""
    text = '''
    <ix:nonfraction name="us-gaap:Revenues" contextRef="Q1_2025" unitRef="usd">
        150000000
    </ix:nonfraction>
    '''

    value = _extract_xbrl_value(text, ["Revenues"])

    assert value == 150_000_000.0


def test_extract_xbrl_value_traditional():
    """Test extracting XBRL value from traditional format."""
    text = '''
    <us-gaap:Revenues contextRef="Q1_2025" unitRef="usd" decimals="-5">
        150000000
    </us-gaap:Revenues>
    '''

    value = _extract_xbrl_value(text, ["Revenues"])

    assert value == 150_000_000.0


def test_extract_xbrl_value_multiple_tags():
    """Test that multiple tag options are tried."""
    text = '<us-gaap:SalesRevenueNet>200000000</us-gaap:SalesRevenueNet>'

    value = _extract_xbrl_value(text, ["Revenues", "SalesRevenueNet", "RevenueFromContract"])

    assert value == 200_000_000.0


def test_extract_xbrl_value_not_found():
    """Test handling when XBRL tag is not found."""
    text = "<p>No XBRL data here</p>"

    value = _extract_xbrl_value(text, ["Revenues"])

    assert value is None


def test_extract_period_quarterly():
    """Test extracting quarterly period."""
    text = """
    FORM 10-Q
    For the three months ended March 31, 2025
    """

    period = _extract_period(text)

    assert period is not None
    assert "March 31, 2025" in period
    assert "Quarterly" in period


def test_extract_period_annual():
    """Test extracting annual period."""
    text = """
    FORM 10-K
    For the fiscal year ended December 31, 2024
    """

    period = _extract_period(text)

    assert period is not None
    assert "December 31, 2024" in period
    assert "Annual" in period


def test_extract_filing_date():
    """Test extracting filing date."""
    text = """
    <SEC-HEADER>
    <FILING-DATE>2025-05-01
    <ACCEPTANCE-DATETIME>20250501163045
    </SEC-HEADER>
    """

    filing_date = _extract_filing_date(text)

    assert filing_date == "2025-05-01"


def test_parse_xbrl_from_filing_comprehensive():
    """Test parsing comprehensive XBRL filing."""
    filing_text = """
    <FILING-DATE>2025-05-01
    For the three months ended March 31, 2025

    <ix:nonfraction name="us-gaap:Revenues" contextRef="Q1_2025" unitRef="usd">
        156300000
    </ix:nonfraction>

    <ix:nonfraction name="us-gaap:NetIncomeLoss" contextRef="Q1_2025" unitRef="usd">
        18500000
    </ix:nonfraction>

    <us-gaap:Assets contextRef="Q1_2025" unitRef="usd">
        500000000
    </us-gaap:Assets>

    <us-gaap:Liabilities contextRef="Q1_2025" unitRef="usd">
        300000000
    </us-gaap:Liabilities>

    <us-gaap:CashAndCashEquivalentsAtCarryingValue contextRef="Q1_2025" unitRef="usd">
        50000000
    </us-gaap:CashAndCashEquivalentsAtCarryingValue>
    """

    financials = parse_xbrl_from_filing(filing_text)

    assert financials.total_revenue == 156_300_000.0
    assert financials.net_income == 18_500_000.0
    assert financials.total_assets == 500_000_000.0
    assert financials.total_liabilities == 300_000_000.0
    assert financials.cash_and_equivalents == 50_000_000.0
    assert "March 31, 2025" in financials.period
    assert financials.filing_date == "2025-05-01"
    assert not financials.is_empty()


def test_parse_xbrl_from_filing_partial():
    """Test parsing with only some fields present."""
    filing_text = """
    <us-gaap:Revenues contextRef="Q1_2025">150000000</us-gaap:Revenues>
    <us-gaap:NetIncomeLoss contextRef="Q1_2025">18000000</us-gaap:NetIncomeLoss>
    """

    financials = parse_xbrl_from_filing(filing_text)

    assert financials.total_revenue == 150_000_000.0
    assert financials.net_income == 18_000_000.0
    assert financials.total_assets is None
    assert not financials.is_empty()


def test_parse_xbrl_from_filing_empty():
    """Test parsing filing with no XBRL data."""
    filing_text = """
    This is a text-only filing with no XBRL tags.
    """

    financials = parse_xbrl_from_filing(filing_text)

    assert financials.is_empty()


def test_parse_xbrl_with_caching(tmp_path, monkeypatch):
    """Test that XBRL data is cached properly."""
    # Mock the cache directory
    monkeypatch.setattr("catalyst_bot.xbrl_parser.CACHE_DIR", tmp_path)

    filing_text = """
    <us-gaap:Revenues>100000000</us-gaap:Revenues>
    """

    # First parse - should extract and cache
    financials1 = parse_xbrl_from_filing(filing_text, cik="1234567", accession="0001234567-25-000001")
    assert financials1.total_revenue == 100_000_000.0

    # Check cache file exists
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1

    # Second parse - should load from cache
    # Even with different text, should return cached data
    financials2 = parse_xbrl_from_filing("different text", cik="1234567", accession="0001234567-25-000001")
    assert financials2.total_revenue == 100_000_000.0


def test_clear_cache(tmp_path, monkeypatch):
    """Test clearing old cache files."""
    # Mock the cache directory
    monkeypatch.setattr("catalyst_bot.xbrl_parser.CACHE_DIR", tmp_path)

    # Create some cache files
    for i in range(5):
        cache_file = tmp_path / f"test_{i}.json"
        cache_file.write_text('{"total_revenue": 100000000}')

    # Clear cache
    removed = clear_cache(older_than_days=0)  # Remove all files

    assert removed == 5
    assert len(list(tmp_path.glob("*.json"))) == 0


def test_xbrl_financials_summary_with_nulls():
    """Test summary generation when some fields are None."""
    financials = XBRLFinancials(
        total_revenue=150_000_000,
        net_income=None,
        total_assets=500_000_000,
        cash_and_equivalents=None,
    )

    summary = financials.summary()
    assert "Revenue: $150.0M" in summary
    assert "Assets: $500.0M" in summary
    # Should not include Net Income or Cash since they're None
    assert "Net Income" not in summary
    assert "Cash:" not in summary


def test_extract_xbrl_value_case_insensitive():
    """Test that tag extraction is case-insensitive."""
    text = '<US-GAAP:REVENUES>100000000</US-GAAP:REVENUES>'

    value = _extract_xbrl_value(text, ["Revenues"])

    assert value == 100_000_000.0


def test_extract_xbrl_value_with_decimals():
    """Test extracting values with decimal points."""
    text = '<us-gaap:CashAndCashEquivalentsAtCarryingValue>1234567.89</us-gaap:CashAndCashEquivalentsAtCarryingValue>'

    value = _extract_xbrl_value(text, ["CashAndCashEquivalentsAtCarryingValue"])

    assert value == 1234567.89
