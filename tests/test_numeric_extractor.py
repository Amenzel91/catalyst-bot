"""Tests for numeric value extractor."""

import pytest
from pydantic import ValidationError

from catalyst_bot.numeric_extractor import (
    EPSData,
    GuidanceRange,
    MarginData,
    NumericMetrics,
    RevenueData,
    extract_all_metrics,
    extract_eps,
    extract_guidance,
    extract_margins,
    extract_revenue,
)


def test_revenue_data_model():
    """Test RevenueData Pydantic model."""
    revenue = RevenueData(value=150.5, unit="millions", period="Q1 2025", yoy_change_pct=25.0)

    assert revenue.value == 150.5
    assert revenue.unit == "millions"
    assert revenue.to_usd() == 150_500_000
    assert "150.5M" in str(revenue)
    assert "+25.0% YoY" in str(revenue)


def test_revenue_data_validation():
    """Test RevenueData validation rules."""
    # Invalid: negative value
    with pytest.raises(ValidationError):
        RevenueData(value=-100, unit="millions")

    # Invalid: bad unit
    with pytest.raises(ValidationError):
        RevenueData(value=100, unit="invalid")


def test_eps_data_model():
    """Test EPSData Pydantic model."""
    eps = EPSData(value=1.25, period="Q4 2024", is_gaap=True, yoy_change_pct=15.0)

    assert eps.value == 1.25
    assert eps.is_gaap is True
    assert "GAAP" in str(eps)
    assert "$1.25" in str(eps)


def test_margin_data_model():
    """Test MarginData Pydantic model."""
    margin = MarginData(margin_type="gross", value=45.5, period="Q1 2025")

    assert margin.margin_type == "gross"
    assert margin.value == 45.5
    assert "Gross Margin: 45.5%" in str(margin)


def test_margin_data_validation():
    """Test MarginData validation rules."""
    # Invalid: margin > 100%
    with pytest.raises(ValidationError):
        MarginData(margin_type="gross", value=150.0)

    # Invalid: negative margin
    with pytest.raises(ValidationError):
        MarginData(margin_type="gross", value=-10.0)


def test_guidance_range_model():
    """Test GuidanceRange Pydantic model."""
    guidance = GuidanceRange(
        metric="revenue",
        low=150.0,
        high=175.0,
        unit="millions",
        period="Q1 2025",
    )

    assert guidance.low == 150.0
    assert guidance.high == 175.0
    assert "REVENUE Q1 2025: $150.0M - $175.0M" in str(guidance)


def test_guidance_range_validation():
    """Test GuidanceRange validation rules."""
    # Invalid: high < low
    with pytest.raises(ValidationError):
        GuidanceRange(
            metric="revenue",
            low=175.0,
            high=150.0,
            unit="millions",
            period="Q1 2025",
        )


def test_extract_revenue_simple():
    """Test extracting revenue from simple text."""
    text = "The company reported revenue of $150 million in Q1 2025, up 25% year-over-year."

    revenues = extract_revenue(text)

    assert len(revenues) == 1
    assert revenues[0].value == 150.0
    assert revenues[0].unit == "millions"
    assert revenues[0].period == "Q1 2025"
    assert revenues[0].yoy_change_pct == 25.0


def test_extract_revenue_billion():
    """Test extracting billion-scale revenue."""
    text = "Total revenue was $1.5B for FY2024, down 10% from prior year."

    revenues = extract_revenue(text)

    assert len(revenues) == 1
    assert revenues[0].value == 1.5
    assert revenues[0].unit == "billions"
    assert revenues[0].to_usd() == 1_500_000_000
    assert revenues[0].yoy_change_pct == -10.0


def test_extract_revenue_multiple():
    """Test extracting multiple revenue mentions."""
    text = """
    Q1 2025 revenue: $50M
    Q2 2025 revenue: $60M
    Full year revenue of $200 million
    """

    revenues = extract_revenue(text)

    assert len(revenues) >= 2
    assert revenues[0].value == 50.0
    assert revenues[1].value == 60.0


def test_extract_eps_simple():
    """Test extracting EPS from simple text."""
    text = "Diluted EPS of $0.50 for Q1 2025 beat estimates."

    eps_list = extract_eps(text)

    assert len(eps_list) == 1
    assert eps_list[0].value == 0.50
    assert eps_list[0].is_gaap is True


def test_extract_eps_non_gaap():
    """Test detecting non-GAAP EPS."""
    text = "Non-GAAP adjusted earnings per share of $1.25 excludes one-time charges."

    eps_list = extract_eps(text)

    assert len(eps_list) == 1
    assert eps_list[0].value == 1.25
    assert eps_list[0].is_gaap is False


def test_extract_margins():
    """Test extracting margin data."""
    text = "Gross margin of 45.5% and operating margin: 20.3% in Q1 2025."

    margins = extract_margins(text)

    assert len(margins) == 2
    assert margins[0].margin_type == "gross"
    assert margins[0].value == 45.5
    assert margins[1].margin_type == "operating"
    assert margins[1].value == 20.3


def test_extract_guidance_revenue():
    """Test extracting revenue guidance."""
    text = "The company expects revenue of $150M to $175M for Q2 2025."

    guidance_list = extract_guidance(text)

    assert len(guidance_list) == 1
    assert guidance_list[0].metric == "revenue"
    assert guidance_list[0].low == 150.0
    assert guidance_list[0].high == 175.0
    assert guidance_list[0].unit == "millions"
    assert guidance_list[0].period == "Q2 2025"


def test_extract_guidance_eps():
    """Test extracting EPS guidance."""
    text = "Management forecasts EPS of $0.75 to $0.85 per share for Q3 2025."

    guidance_list = extract_guidance(text)

    assert len(guidance_list) == 1
    assert guidance_list[0].metric == "eps"
    assert guidance_list[0].low == 0.75
    assert guidance_list[0].high == 0.85


def test_extract_all_metrics_comprehensive():
    """Test extracting all metrics from comprehensive text."""
    text = """
    Acme Corporation announced Q1 2025 financial results:
    - Revenue of $150 million, up 25% year-over-year
    - Diluted EPS of $0.50 beat estimates
    - Gross margin of 45.5%
    - Operating margin: 20.3%
    - Q2 2025 guidance: $160M to $180M
    """

    metrics = extract_all_metrics(text)

    assert len(metrics.revenue) >= 1
    assert len(metrics.eps) >= 1
    assert len(metrics.margins) >= 2
    assert len(metrics.guidance) >= 1
    assert not metrics.is_empty()

    summary = metrics.summary()
    assert "Revenue:" in summary
    assert "EPS:" in summary


def test_extract_all_metrics_empty():
    """Test extracting from text with no metrics."""
    text = "The company announced a partnership with Beta Corp."

    metrics = extract_all_metrics(text)

    assert metrics.is_empty()


def test_numeric_metrics_summary():
    """Test NumericMetrics summary method."""
    metrics = NumericMetrics(
        revenue=[RevenueData(value=150, unit="millions", period="Q1 2025")],
        eps=[EPSData(value=0.50, period="Q1 2025", is_gaap=True)],
    )

    summary = metrics.summary()
    assert "Revenue:" in summary
    assert "150.0M" in summary
    assert "EPS:" in summary
    assert "$0.50" in summary


def test_revenue_to_usd_conversion():
    """Test converting different units to USD."""
    rev_thousands = RevenueData(value=500, unit="thousands")
    assert rev_thousands.to_usd() == 500_000

    rev_millions = RevenueData(value=150, unit="millions")
    assert rev_millions.to_usd() == 150_000_000

    rev_billions = RevenueData(value=1.5, unit="billions")
    assert rev_billions.to_usd() == 1_500_000_000


def test_extract_revenue_no_period():
    """Test revenue extraction when period is not mentioned."""
    text = "Revenue was $100M this quarter."

    revenues = extract_revenue(text)

    assert len(revenues) == 1
    assert revenues[0].value == 100.0
    # Period should be None if not found
    assert revenues[0].period is None or revenues[0].period


def test_extract_complex_filing_text():
    """Test extracting from realistic SEC filing text."""
    text = """
    RESULTS OF OPERATIONS

    For the three months ended March 31, 2025, we reported:

    - Total revenues of $156.3 million, compared to $124.8 million in Q1 2024,
      representing an increase of 25.2% year-over-year
    - Net income of $18.5 million, or $0.62 per diluted share (GAAP)
    - Adjusted non-GAAP earnings per share of $0.75
    - Gross margin of 48.2%, compared to 45.1% in the prior year period
    - Operating margin of 22.7%

    OUTLOOK

    For Q2 2025, we expect revenue in the range of $165 million to $180 million.
    """

    metrics = extract_all_metrics(text)

    # Should extract revenue
    assert len(metrics.revenue) >= 1
    assert metrics.revenue[0].value == 156.3

    # Should extract EPS (both GAAP and non-GAAP)
    assert len(metrics.eps) >= 2

    # Should extract margins
    assert len(metrics.margins) >= 2

    # Should extract guidance
    assert len(metrics.guidance) >= 1
    assert metrics.guidance[0].low == 165.0
    assert metrics.guidance[0].high == 180.0
