"""Tests for SEC filing integration into main alert system (Wave 3).

This test suite verifies that:
1. SEC filing alerts include both standard metrics AND SEC-specific fields
2. Regular news alerts remain unchanged (backward compatibility)
3. Priority color coding is applied correctly
4. Missing SEC data is handled gracefully
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_sec_metrics():
    """Mock NumericMetrics object with revenue, EPS, and margins."""
    class MockMetric:
        def __init__(self, value, yoy_change=None):
            self.value = value
            self.yoy_change = yoy_change

    class MockMargins:
        gross_margin = 45.2
        operating_margin = 28.5

    class MockNumericMetrics:
        revenue = MockMetric(125000, 25.5)
        eps = MockMetric(1.85, 15.2)
        margins = MockMargins()

    return MockNumericMetrics()


@pytest.fixture
def mock_sec_guidance():
    """Mock GuidanceAnalysis object with raised revenue guidance."""
    class MockGuidanceItem:
        guidance_type = "revenue"
        change_direction = "raised"
        target_low = 150_000_000
        target_high = 175_000_000
        confidence_level = "high"

    class MockGuidanceAnalysis:
        has_guidance = True
        guidance_items = [MockGuidanceItem()]

    return MockGuidanceAnalysis()


@pytest.fixture
def mock_sec_sentiment():
    """Mock SECSentimentOutput object with bullish sentiment."""
    class MockSentimentOutput:
        score = 0.75
        weighted_score = 0.82
        justification = "Strong revenue beat with positive forward guidance and margin expansion"
        confidence = 0.9

    return MockSentimentOutput()


@pytest.fixture
def mock_sec_priority():
    """Mock PriorityScore object with critical priority."""
    class MockPriorityScore:
        urgency = 0.9
        impact = 0.85
        relevance = 1.0
        total = 0.88
        tier = "critical"
        reasons = [
            "Urgency: 8-K Item 2.02 (earnings) - very time-sensitive",
            "Impact: Strong bullish sentiment (+0.8), Guidance raised (revenue)",
            "Relevance: On watchlist",
        ]

    return MockPriorityScore()


@pytest.fixture
def sec_filing_item(mock_sec_metrics, mock_sec_guidance, mock_sec_sentiment, mock_sec_priority):
    """Complete SEC filing item dict with all enhancements."""
    return {
        "ticker": "AAPL",
        "title": "Apple Inc. Reports Strong Q4 Results",
        "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193",
        "source": "sec_earnings",  # Source starts with "sec_"
        "ts": datetime.now(timezone.utc).isoformat(),
        "filing_type": "8-K",
        "item_code": "2.02",
        "sec_metrics": mock_sec_metrics,
        "sec_guidance": mock_sec_guidance,
        "sec_sentiment": mock_sec_sentiment,
        "sec_priority": mock_sec_priority,
        "summary": "Apple Inc. reported strong Q4 2024 earnings with revenue of $125B...",
    }


@pytest.fixture
def regular_news_item():
    """Regular news item (non-SEC) for backward compatibility testing."""
    return {
        "ticker": "TSLA",
        "title": "Tesla Announces New Model Launch",
        "link": "https://example.com/news/tesla-model",
        "source": "benzinga",  # Non-SEC source
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": "Tesla unveiled its latest electric vehicle model...",
    }


# ============================================================================
# SEC Alert Enhancement Tests
# ============================================================================


def test_sec_alert_includes_standard_metrics(sec_filing_item):
    """Test that SEC alerts include standard metrics (price, sentiment, score)."""
    from catalyst_bot.alerts import _build_discord_embed

    # Build embed with SEC filing
    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={"relevance": 0.9, "sentiment": 0.8, "score": 0.85},
        last_price=150.25,
        last_change_pct=2.5,
    )

    # Check standard fields are present
    field_names = [f["name"] for f in embed["fields"]]
    assert "Price / Change" in field_names, "Standard price field missing"
    assert "Sentiment" in field_names, "Standard sentiment field missing"
    assert "Score" in field_names, "Standard score field missing"

    # Check price value
    price_field = next(f for f in embed["fields"] if "Price / Change" in f["name"])
    assert "$150.25" in price_field["value"]
    assert "2.5%" in price_field["value"] or "2.50%" in price_field["value"]


def test_sec_alert_includes_sec_specific_fields(sec_filing_item):
    """Test that SEC alerts include SEC-specific fields (metrics, guidance, sentiment)."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={"relevance": 0.9, "sentiment": 0.8},
        last_price=150.25,
        last_change_pct=2.5,
    )

    field_names = [f["name"] for f in embed["fields"]]

    # Check SEC-specific fields are present
    assert "📄 SEC Filing Type" in field_names, "Filing type badge missing"
    assert "🎯 Priority" in field_names, "Priority tier missing"
    assert "💰 Key Metrics" in field_names, "Financial metrics missing"
    assert "📈 Forward Guidance" in field_names, "Guidance field missing"
    assert "🎯 SEC Sentiment" in field_names, "SEC sentiment missing"


def test_sec_alert_filing_type_badge(sec_filing_item):
    """Test that filing type badge shows filing type and item code."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={},
        last_price=150.25,
        last_change_pct=2.5,
    )

    # Find filing type field
    filing_field = next(f for f in embed["fields"] if "SEC Filing Type" in f["name"])
    assert "8-K" in filing_field["value"]
    assert "Item 2.02" in filing_field["value"]


def test_sec_alert_priority_tier_display(sec_filing_item):
    """Test that priority tier is displayed with emoji and score."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={},
        last_price=150.25,
        last_change_pct=2.5,
    )

    # Find priority field
    priority_field = next(f for f in embed["fields"] if "Priority" in f["name"])
    assert "CRITICAL" in priority_field["value"], "Priority label missing"
    assert "0.88" in priority_field["value"], "Priority score missing"
    assert "🔴" in priority_field["value"], "Priority emoji missing (critical = red)"


def test_sec_alert_financial_metrics(sec_filing_item):
    """Test that financial metrics are formatted correctly."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={},
        last_price=150.25,
        last_change_pct=2.5,
    )

    # Find metrics field
    metrics_field = next(f for f in embed["fields"] if "Key Metrics" in f["name"])

    # Check revenue with YoY change
    assert "Revenue" in metrics_field["value"]
    assert "$125,000M" in metrics_field["value"]
    assert "+25.5%" in metrics_field["value"]
    assert "📈" in metrics_field["value"], "Growth emoji missing for positive YoY"

    # Check EPS with YoY change
    assert "EPS" in metrics_field["value"]
    assert "$1.85" in metrics_field["value"]
    assert "+15.2%" in metrics_field["value"]

    # Check margins
    assert "Gross Margin" in metrics_field["value"]
    assert "45.2%" in metrics_field["value"]
    assert "Operating Margin" in metrics_field["value"]
    assert "28.5%" in metrics_field["value"]


def test_sec_alert_forward_guidance(sec_filing_item):
    """Test that forward guidance is formatted correctly."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={},
        last_price=150.25,
        last_change_pct=2.5,
    )

    # Find guidance field
    guidance_field = next(f for f in embed["fields"] if "Forward Guidance" in f["name"])

    # Check guidance details
    assert "✅" in guidance_field["value"], "Raised emoji missing"
    assert "Raised" in guidance_field["value"]
    assert "Revenue" in guidance_field["value"]
    assert "150" in guidance_field["value"], "Target low missing"
    assert "175" in guidance_field["value"], "Target high missing"
    assert "(high)" in guidance_field["value"], "Confidence level missing"


def test_sec_alert_sec_sentiment(sec_filing_item):
    """Test that SEC sentiment is displayed separately from standard sentiment."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={"sentiment": 0.5},  # Standard sentiment
        last_price=150.25,
        last_change_pct=2.5,
    )

    field_names = [f["name"] for f in embed["fields"]]

    # Both standard sentiment AND SEC sentiment should be present
    assert "Sentiment" in field_names, "Standard sentiment missing"
    assert "🎯 SEC Sentiment" in field_names, "SEC sentiment missing"

    # Find SEC sentiment field
    sec_sent_field = next(f for f in embed["fields"] if "SEC Sentiment" in f["name"])
    assert "🟢" in sec_sent_field["value"], "Bullish emoji missing"
    assert "Bullish" in sec_sent_field["value"]
    assert "+0.75" in sec_sent_field["value"], "SEC sentiment score missing"
    assert "Strong revenue beat" in sec_sent_field["value"], "Justification missing"


def test_sec_alert_priority_color_coding(sec_filing_item):
    """Test that embed color is set based on priority tier."""
    from catalyst_bot.alerts import _build_discord_embed
    from catalyst_bot.sec_filing_alerts import PRIORITY_CONFIG

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored={},
        last_price=150.25,
        last_change_pct=2.5,
    )

    # Color should match critical tier (red)
    assert embed["color"] == PRIORITY_CONFIG["critical"]["color"]


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


def test_regular_news_alert_unchanged(regular_news_item):
    """Test that regular news alerts are NOT modified (backward compatibility)."""
    from catalyst_bot.alerts import _build_discord_embed

    embed = _build_discord_embed(
        item_dict=regular_news_item,
        scored={"relevance": 0.8, "sentiment": 0.7},
        last_price=200.50,
        last_change_pct=1.5,
    )

    field_names = [f["name"] for f in embed["fields"]]

    # Check standard fields are present
    assert "Price / Change" in field_names
    assert "Sentiment" in field_names
    assert "Score" in field_names

    # Check SEC-specific fields are NOT present
    assert "📄 SEC Filing Type" not in field_names, "SEC filing badge should not appear"
    assert "🎯 Priority" not in field_names, "SEC priority should not appear"
    assert "💰 Key Metrics" not in field_names, "SEC metrics should not appear"
    assert "📈 Forward Guidance" not in field_names, "SEC guidance should not appear"
    assert "🎯 SEC Sentiment" not in field_names, "SEC sentiment should not appear"


def test_sec_source_detection():
    """Test that source detection correctly identifies SEC sources."""
    from catalyst_bot.alerts import _build_discord_embed

    # SEC source (starts with "sec_")
    sec_item = {
        "ticker": "AAPL",
        "title": "Test Filing",
        "source": "sec_earnings",
        "ts": datetime.now(timezone.utc).isoformat(),
        "filing_type": "8-K",
    }

    embed = _build_discord_embed(
        item_dict=sec_item,
        scored={},
        last_price=100,
        last_change_pct=1.0,
    )

    field_names = [f["name"] for f in embed["fields"]]
    assert "📄 SEC Filing Type" in field_names, "SEC source not detected"

    # Non-SEC source
    news_item = {
        "ticker": "AAPL",
        "title": "Test News",
        "source": "benzinga",
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    embed = _build_discord_embed(
        item_dict=news_item,
        scored={},
        last_price=100,
        last_change_pct=1.0,
    )

    field_names = [f["name"] for f in embed["fields"]]
    assert "📄 SEC Filing Type" not in field_names, "Non-SEC source incorrectly detected as SEC"


# ============================================================================
# Graceful Degradation Tests
# ============================================================================


def test_sec_alert_missing_metrics():
    """Test that SEC alert works when metrics are missing."""
    from catalyst_bot.alerts import _build_discord_embed

    sec_item = {
        "ticker": "AAPL",
        "title": "Test Filing",
        "source": "sec_earnings",
        "ts": datetime.now(timezone.utc).isoformat(),
        "filing_type": "8-K",
        # No sec_metrics provided
    }

    # Should not raise an exception
    embed = _build_discord_embed(
        item_dict=sec_item,
        scored={},
        last_price=100,
        last_change_pct=1.0,
    )

    # Should still have filing type but not metrics
    field_names = [f["name"] for f in embed["fields"]]
    assert "📄 SEC Filing Type" in field_names
    assert "💰 Key Metrics" not in field_names


def test_sec_alert_missing_guidance():
    """Test that SEC alert works when guidance is missing."""
    from catalyst_bot.alerts import _build_discord_embed

    sec_item = {
        "ticker": "AAPL",
        "title": "Test Filing",
        "source": "sec_earnings",
        "ts": datetime.now(timezone.utc).isoformat(),
        "filing_type": "10-Q",
        # No sec_guidance provided
    }

    embed = _build_discord_embed(
        item_dict=sec_item,
        scored={},
        last_price=100,
        last_change_pct=1.0,
    )

    field_names = [f["name"] for f in embed["fields"]]
    assert "📄 SEC Filing Type" in field_names
    assert "📈 Forward Guidance" not in field_names


def test_sec_alert_missing_priority():
    """Test that SEC alert works when priority is missing."""
    from catalyst_bot.alerts import _build_discord_embed

    sec_item = {
        "ticker": "AAPL",
        "title": "Test Filing",
        "source": "sec_earnings",
        "ts": datetime.now(timezone.utc).isoformat(),
        "filing_type": "8-K",
        # No sec_priority provided
    }

    embed = _build_discord_embed(
        item_dict=sec_item,
        scored={},
        last_price=100,
        last_change_pct=1.0,
    )

    field_names = [f["name"] for f in embed["fields"]]
    assert "📄 SEC Filing Type" in field_names
    assert "🎯 Priority" not in field_names


def test_sec_alert_partial_metrics(mock_sec_metrics):
    """Test that SEC alert works with partial metrics (only revenue, no EPS)."""
    from catalyst_bot.alerts import _build_discord_embed

    class PartialMetrics:
        revenue = mock_sec_metrics.revenue
        eps = None  # Missing EPS
        margins = None  # Missing margins

    sec_item = {
        "ticker": "AAPL",
        "title": "Test Filing",
        "source": "sec_earnings",
        "ts": datetime.now(timezone.utc).isoformat(),
        "filing_type": "8-K",
        "sec_metrics": PartialMetrics(),
    }

    embed = _build_discord_embed(
        item_dict=sec_item,
        scored={},
        last_price=100,
        last_change_pct=1.0,
    )

    # Should have metrics field with only revenue
    metrics_field = next(f for f in embed["fields"] if "Key Metrics" in f["name"])
    assert "Revenue" in metrics_field["value"]
    assert "EPS" not in metrics_field["value"]


# ============================================================================
# Integration with Standard Alert Features Tests
# ============================================================================


def test_sec_alert_with_float_and_short_interest(sec_filing_item):
    """Test that SEC alerts include standard float and short interest when available."""
    from catalyst_bot.alerts import _build_discord_embed

    # Add float data to scored item
    scored = {
        "relevance": 0.9,
        "sentiment": 0.8,
        "float_shares": 15_000_000,  # 15M float
        "short_interest_pct": 12.5,
    }

    embed = _build_discord_embed(
        item_dict=sec_filing_item,
        scored=scored,
        last_price=150.25,
        last_change_pct=2.5,
    )

    field_names = [f["name"] for f in embed["fields"]]

    # Should have BOTH standard metrics AND SEC-specific fields
    assert "Float" in field_names, "Standard float field missing"
    assert "💰 Key Metrics" in field_names, "SEC metrics missing"
    assert "🎯 SEC Sentiment" in field_names, "SEC sentiment missing"


def test_sec_alert_priority_tiers():
    """Test that different priority tiers produce correct colors."""
    from catalyst_bot.alerts import _build_discord_embed
    from catalyst_bot.sec_filing_alerts import PRIORITY_CONFIG

    tiers = [
        ("critical", PRIORITY_CONFIG["critical"]["color"]),
        ("high", PRIORITY_CONFIG["high"]["color"]),
        ("medium", PRIORITY_CONFIG["medium"]["color"]),
        ("low", PRIORITY_CONFIG["medium"]["color"]),  # Low falls back to medium
    ]

    for tier, expected_color in tiers:
        class MockPriority:
            urgency = 0.5
            impact = 0.5
            relevance = 0.5
            total = 0.5
            reasons = []

        MockPriority.tier = tier

        sec_item = {
            "ticker": "AAPL",
            "title": "Test Filing",
            "source": "sec_earnings",
            "ts": datetime.now(timezone.utc).isoformat(),
            "filing_type": "8-K",
            "sec_priority": MockPriority(),
        }

        embed = _build_discord_embed(
            item_dict=sec_item,
            scored={},
            last_price=100,
            last_change_pct=1.0,
        )

        # Check color matches tier (unless tier is low)
        if tier != "low":
            assert embed["color"] == expected_color, f"Color mismatch for {tier} tier"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
