"""
Tests for non-substantive news filter.

Verifies that meaningless press releases like "we don't know why our stock
moved" are correctly filtered out while substantive news passes through.
"""

import pytest
from catalyst_bot.classify import is_substantive_news


def test_substantive_news():
    """Test that real news is classified as substantive."""

    # Earnings announcement - SUBSTANTIVE
    assert is_substantive_news(
        "AAPL reports Q3 earnings beat with revenue of $85B"
    ) == True

    # Product launch - SUBSTANTIVE
    assert is_substantive_news(
        "Tesla unveils new Model 3 with improved range"
    ) == True

    # Acquisition - SUBSTANTIVE
    assert is_substantive_news(
        "Microsoft announces $10B acquisition of gaming company"
    ) == True

    # FDA approval - SUBSTANTIVE
    assert is_substantive_news(
        "FDA approves new cancer treatment drug from BioTech Inc"
    ) == True

    # Contract win - SUBSTANTIVE
    assert is_substantive_news(
        "Defense contractor wins $500M government contract"
    ) == True


def test_non_substantive_no_explanation():
    """Test detection of 'we don't know' press releases."""

    # Classic "we don't know" PR
    assert is_substantive_news(
        "Company not aware of any reason for recent price movement"
    ) == False

    # No explanation variant
    assert is_substantive_news(
        "Management has no explanation for trading activity"
    ) == False

    # Cannot account variant
    assert is_substantive_news(
        "We cannot account for unusual volume today"
    ) == False

    # Not aware of any variant
    assert is_substantive_news(
        "TOVX is not aware of any material change"
    ) == False

    # No knowledge variant
    assert is_substantive_news(
        "Company has no knowledge of reason for stock price fluctuation"
    ) == False


def test_non_substantive_no_material_changes():
    """Test detection of 'no material changes' announcements."""

    assert is_substantive_news(
        "Company reports no material changes to business operations"
    ) == False

    assert is_substantive_news(
        "No undisclosed material information at this time"
    ) == False

    assert is_substantive_news(
        "Management confirms no pending announcements"
    ) == False

    assert is_substantive_news(
        "Nothing to report regarding recent trading activity"
    ) == False


def test_non_substantive_generic_trading_update():
    """Test detection of generic trading updates."""

    # Too short
    assert is_substantive_news(
        "Trading Update"
    ) == False

    # Generic trading activity notice
    assert is_substantive_news(
        "TOVX Trading Activity Notice"
    ) == False

    # Generic price fluctuation statement
    assert is_substantive_news(
        "Notice on price fluctuation"
    ) == False

    # Wish to clarify (empty announcement)
    assert is_substantive_news(
        "Company wishes to clarify recent trading activity"
    ) == False


def test_non_substantive_short_titles():
    """Test rejection of very short titles (<20 chars)."""

    assert is_substantive_news("Short title") == False
    assert is_substantive_news("AAPL") == False
    assert is_substantive_news("News") == False
    assert is_substantive_news("XYZ announces") == False  # 13 chars


def test_edge_cases():
    """Test edge cases and false positives."""

    # Should NOT trigger on legitimate news containing "aware"
    assert is_substantive_news(
        "CEO becomes aware of major contract win worth $500M"
    ) == True

    # Should NOT trigger on "material" in different context
    assert is_substantive_news(
        "Company signs material supply agreement with major OEM"
    ) == True

    # Should NOT trigger on "trading" in different context
    assert is_substantive_news(
        "Stock trading at all-time high after breakthrough announcement"
    ) == True

    # Should NOT trigger on "activity" in different context
    assert is_substantive_news(
        "Merger and acquisition activity drives record quarterly revenue"
    ) == True

    # Should NOT reject longer trading updates with actual content
    assert is_substantive_news(
        "Trading Update: Q3 revenue exceeds guidance by 15% on strong demand"
    ) == True


def test_combined_title_and_text():
    """Test that both title and text are checked for patterns."""

    # Pattern in title only
    assert is_substantive_news(
        "Company not aware of any changes",
        "Some additional text here"
    ) == False

    # Pattern in text only
    assert is_substantive_news(
        "Company Announcement",
        "Management has no explanation for the recent price movement"
    ) == False

    # Pattern in both
    assert is_substantive_news(
        "Not aware of any material changes",
        "The company has no undisclosed information"
    ) == False

    # No pattern in either (but title too short)
    assert is_substantive_news(
        "Short",
        "This is substantive news about a product launch"
    ) == False


def test_case_insensitivity():
    """Test that pattern matching is case-insensitive."""

    # Uppercase
    assert is_substantive_news(
        "COMPANY NOT AWARE OF ANY REASON FOR PRICE MOVEMENT"
    ) == False

    # Mixed case
    assert is_substantive_news(
        "Company Not Aware Of Any Material Changes"
    ) == False

    # Title case
    assert is_substantive_news(
        "Management Has No Explanation For Trading Activity"
    ) == False


def test_tovx_example():
    """Test the original TOVX example that inspired this filter."""

    # TOVX-style "we don't know" announcement
    tovx_title = "TOVX: Company Not Aware of Material Change"
    tovx_text = """
    TeraVision Corporation (TOVX) wishes to clarify that it is not aware
    of any material changes in its business operations that would explain
    the recent unusual trading activity and price fluctuation.
    """

    assert is_substantive_news(tovx_title, tovx_text) == False


def test_oct28_examples():
    """Test the specific Oct 28 examples that inspired this fix."""

    # Example 1: "Why Chegg (CHGG) Shares Are Plunging Today"
    assert is_substantive_news(
        "Why Chegg (CHGG) Shares Are Plunging Today"
    ) == False

    # Example 2: "Why Denny's (DENN) Stock Is Down Today"
    assert is_substantive_news(
        "Why Denny's (DENN) Stock Is Down Today"
    ) == False

    # Example 3: Generic pattern - "Why [TICKER] Stock Is Down Today"
    assert is_substantive_news(
        "Why AAPL Stock Is Down Today"
    ) == False

    # Example 4: Similar pattern with "Up"
    assert is_substantive_news(
        "Why Tesla (TSLA) Stock Is Up Today"
    ) == False

    # Example 5: "Moving" variant
    assert is_substantive_news(
        "Why GameStop Stock Is Moving Today"
    ) == False


def test_summary_style_variations():
    """Test various summary-style headline patterns."""

    # "Shares are [verb]" patterns
    assert is_substantive_news(
        "Why AMD Shares Are Soaring Today"
    ) == False

    assert is_substantive_news(
        "Why Intel Shares Are Tumbling Today"
    ) == False

    assert is_substantive_news(
        "Why NVDA Shares Are Rallying"
    ) == False

    assert is_substantive_news(
        "Why Microsoft Shares Are Climbing Today"
    ) == False

    # "Stock is [direction]" patterns
    assert is_substantive_news(
        "Why Palantir Stock Is Higher Today"
    ) == False

    assert is_substantive_news(
        "Why Coinbase Stock Is Lower Today"
    ) == False

    # "What Investors Need to Know" standalone
    assert is_substantive_news(
        "Tesla Earnings Report: What Investors Need to Know"
    ) == False


def test_earnings_preview_filter():
    """Test that earnings previews are filtered but results are not."""

    # Earnings previews should be filtered
    assert is_substantive_news(
        "Earnings Preview: What to Expect from Apple"
    ) == False

    assert is_substantive_news(
        "AAPL Earnings Preview: Analysts Expect Strong Quarter"
    ) == False

    assert is_substantive_news(
        "What to expect from Tesla earnings next week"
    ) == False

    assert is_substantive_news(
        "MSFT Before Earnings: Stock Analysis"
    ) == False

    # But earnings RESULTS should pass through
    assert is_substantive_news(
        "Apple Reports Q3 Earnings Results Beat Expectations"
    ) == True

    assert is_substantive_news(
        "Tesla Q4 Earnings Results: Revenue Surges 40%"
    ) == True

    assert is_substantive_news(
        "Microsoft Announces Quarterly Earnings Beat"
    ) == True
