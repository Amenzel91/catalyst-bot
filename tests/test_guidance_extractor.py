"""Tests for forward guidance extractor."""

import pytest

from catalyst_bot.guidance_extractor import (
    ForwardGuidance,
    GuidanceAnalysis,
    _determine_change_direction,
    _determine_confidence_level,
    _extract_temporal_scope,
    _extract_value_text,
    extract_forward_guidance,
    has_lowered_guidance,
    has_raised_guidance,
    is_earnings_filing,
)


def test_extract_forward_guidance_raised():
    """Test extracting raised guidance."""
    text = """
    We are raising our full-year 2025 revenue guidance to $600M-$650M,
    up from our prior guidance of $550M-$600M. We expect strong growth
    in Q2 2025 driven by new product launches.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert len(analysis.guidance_items) >= 1
    assert analysis.overall_direction == "positive"
    assert any(g.change_direction == "raised" for g in analysis.guidance_items)


def test_extract_forward_guidance_lowered():
    """Test extracting lowered guidance."""
    text = """
    Due to market conditions, we are lowering our Q2 2025 EPS guidance
    to $0.50-$0.60 per share, down from $0.75-$0.85 previously.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert analysis.overall_direction == "negative"
    assert any(g.change_direction == "lowered" for g in analysis.guidance_items)


def test_extract_forward_guidance_maintained():
    """Test extracting maintained guidance."""
    text = """
    We are reaffirming our full-year revenue guidance of $500M and
    maintaining our gross margin target of 45%.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert any(g.change_direction == "maintained" for g in analysis.guidance_items)


def test_extract_forward_guidance_new():
    """Test extracting new guidance."""
    text = """
    For fiscal year 2026, we expect revenue in the range of $700M-$800M
    and anticipate operating margins of 20-25%.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert len(analysis.guidance_items) >= 1


def test_extract_forward_guidance_no_guidance():
    """Test filing with no forward guidance."""
    text = """
    The company completed the acquisition of XYZ Corp for $500 million.
    The transaction closed on May 15, 2025.
    """

    analysis = extract_forward_guidance(text)

    assert not analysis.has_guidance
    assert len(analysis.guidance_items) == 0
    assert analysis.overall_direction == "neutral"


def test_extract_forward_guidance_mixed():
    """Test guidance with mixed signals."""
    text = """
    We are raising our revenue guidance to $600M but lowering our
    margin guidance to 40% due to increased costs.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert analysis.overall_direction in ("mixed", "positive", "negative")
    raised = any(g.change_direction == "raised" for g in analysis.guidance_items)
    lowered = any(g.change_direction == "lowered" for g in analysis.guidance_items)
    assert raised or lowered  # At least one should be detected


def test_extract_temporal_scope():
    """Test temporal scope extraction."""
    assert _extract_temporal_scope("Q1 2025 revenue") == "Q1 2025"
    assert _extract_temporal_scope("FY2025 EPS") == "FY2025"
    assert _extract_temporal_scope("fiscal year 2025") == "fiscal year 2025"
    assert _extract_temporal_scope("H2 2025 outlook") == "H2 2025"
    assert _extract_temporal_scope("full-year guidance") == "full-year"
    assert _extract_temporal_scope("no temporal info here") is None


def test_extract_value_text_dollar_range():
    """Test extracting dollar amount ranges."""
    text = "expect revenue of $150M to $175M"
    value = _extract_value_text(text, "revenue")
    assert "$150M" in value or "150" in value


def test_extract_value_text_percentage():
    """Test extracting percentage values."""
    text = "targeting 45% gross margin"
    value = _extract_value_text(text, "margin")
    assert "45%" in value


def test_extract_value_text_eps():
    """Test extracting EPS values."""
    text = "anticipate $2.50 to $2.75 per share"
    value = _extract_value_text(text, "eps")
    assert "$2.50" in value or "2.50" in value


def test_determine_change_direction_raised():
    """Test detecting raised guidance."""
    assert _determine_change_direction("raising our guidance") == "raised"
    assert _determine_change_direction("increasing outlook") == "raised"
    assert _determine_change_direction("higher than expected") == "raised"
    assert _determine_change_direction("exceeding targets") == "raised"


def test_determine_change_direction_lowered():
    """Test detecting lowered guidance."""
    assert _determine_change_direction("lowering our forecast") == "lowered"
    assert _determine_change_direction("reducing expectations") == "lowered"
    assert _determine_change_direction("below prior guidance") == "lowered"


def test_determine_change_direction_maintained():
    """Test detecting maintained guidance."""
    assert _determine_change_direction("reaffirming guidance") == "maintained"
    assert _determine_change_direction("maintaining our outlook") == "maintained"
    assert _determine_change_direction("unchanged from prior") == "maintained"


def test_determine_change_direction_new():
    """Test detecting new guidance."""
    assert _determine_change_direction("we expect revenue of") == "new"


def test_determine_confidence_level():
    """Test confidence level detection."""
    assert _determine_confidence_level("we are confident") == "strong"
    assert _determine_confidence_level("we expect strong growth") == "strong"
    assert _determine_confidence_level("we anticipate moderate growth") == "moderate"
    assert _determine_confidence_level("this may result in") == "uncertain"
    assert _determine_confidence_level("could potentially achieve") == "uncertain"


def test_is_earnings_filing_10q():
    """Test detecting 10-Q as earnings filing."""
    assert is_earnings_filing("Some 10-Q text", "10-Q")


def test_is_earnings_filing_10k():
    """Test detecting 10-K as earnings filing."""
    assert is_earnings_filing("Some 10-K text", "10-K")


def test_is_earnings_filing_8k_item_202():
    """Test detecting 8-K with Item 2.02 as earnings filing."""
    text = "Item 2.02. Results of Operations and Financial Condition"
    assert is_earnings_filing(text, "8-K")


def test_is_earnings_filing_8k_no_item_202():
    """Test 8-K without Item 2.02 is not earnings filing."""
    text = "Item 1.01. Entry into Material Agreement"
    assert not is_earnings_filing(text, "8-K")


def test_has_raised_guidance():
    """Test convenience function for raised guidance."""
    text = "We are raising our full-year revenue guidance to $600M."
    assert has_raised_guidance(text)


def test_has_lowered_guidance():
    """Test convenience function for lowered guidance."""
    text = "We are lowering our Q2 EPS guidance due to market conditions."
    assert has_lowered_guidance(text)


def test_forward_guidance_dataclass():
    """Test ForwardGuidance dataclass."""
    guidance = ForwardGuidance(
        guidance_type="revenue",
        metric="Q1 2025 revenue",
        value_text="$150M-$175M",
        temporal_scope="Q1 2025",
        change_direction="raised",
        confidence_level="strong",
        source_text="We expect Q1 2025 revenue of $150M-$175M",
    )

    assert guidance.guidance_type == "revenue"
    assert guidance.change_direction == "raised"
    assert "Q1 2025" in guidance.metric


def test_guidance_analysis_dataclass():
    """Test GuidanceAnalysis dataclass."""
    guidance_item = ForwardGuidance(
        guidance_type="revenue",
        metric="revenue",
        value_text="$500M",
        temporal_scope="FY2025",
        change_direction="new",
        confidence_level="moderate",
        source_text="Text",
    )

    analysis = GuidanceAnalysis(
        has_guidance=True,
        guidance_items=[guidance_item],
        overall_direction="neutral",
        summary="Guidance provided",
    )

    assert analysis.has_guidance
    assert len(analysis.guidance_items) == 1
    assert analysis.overall_direction == "neutral"


def test_complex_guidance_text():
    """Test with complex real-world guidance text."""
    text = """
    Looking ahead, we expect Q3 2025 revenue to be in the range of $180M to $200M,
    representing growth of 20-25% year-over-year. We are raising our full-year
    revenue guidance to $650M-$700M from $600M-$650M previously. We anticipate
    gross margins to remain stable at 45-47%, and we are confident in achieving
    positive operating cash flow for the full year. For Q4 2025, we forecast
    EPS of $0.85 to $0.95 per share.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert len(analysis.guidance_items) >= 3  # Multiple guidance items
    assert analysis.overall_direction == "positive"  # Raised guidance mentioned

    # Check that we detected various types
    types_detected = {g.guidance_type for g in analysis.guidance_items}
    assert "revenue" in types_detected


def test_guidance_with_qualitative_terms():
    """Test guidance with qualitative language."""
    text = """
    We expect strong growth in the second half of 2025, driven by robust
    demand and improved operational efficiency. We remain confident in our
    ability to deliver solid results.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    # Should detect qualitative guidance even without specific numbers


def test_guidance_summary_generation():
    """Test that guidance summary is generated correctly."""
    text = """
    We are raising our revenue guidance and maintaining our margin guidance.
    We expect strong performance in Q2 2025.
    """

    analysis = extract_forward_guidance(text)

    assert analysis.has_guidance
    assert len(analysis.summary) > 20
    assert "raised" in analysis.summary.lower() or "positive" in analysis.summary.lower()
