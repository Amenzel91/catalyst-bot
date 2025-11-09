"""Tests for SEC filing-specific Discord alerts."""

import asyncio
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check if aiohttp is available
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from catalyst_bot.sec_filing_alerts import (
    PRIORITY_CONFIG,
    SENTIMENT_EMOJIS,
    create_sec_filing_buttons,
    create_sec_filing_embed,
    get_min_priority_tier,
    handle_dig_deeper_interaction,
    is_sec_filing_alerts_enabled,
    send_daily_digest,
    send_sec_filing_alert,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_filing_section():
    """Mock FilingSection object."""

    class MockFilingSection:
        ticker = "AAPL"
        filing_type = "8-K"
        item_code = "2.02"
        catalyst_type = "earnings"
        filing_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193"
        text = "Apple Inc. reported strong Q4 2024 earnings..."

    return MockFilingSection()


@pytest.fixture
def mock_sentiment_output():
    """Mock SECSentimentOutput object."""

    class MockSentimentOutput:
        score = 0.75
        weighted_score = 0.82
        justification = "Strong revenue beat with positive forward guidance"
        confidence = 0.9

    return MockSentimentOutput()


@pytest.fixture
def mock_guidance_analysis():
    """Mock GuidanceAnalysis object."""

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
def mock_numeric_metrics():
    """Mock NumericMetrics object."""

    class MockMetric:
        def __init__(self, value, yoy_change=None):
            self.value = value
            self.yoy_change = yoy_change

    class MockMargins:
        gross_margin = 45.2
        operating_margin = 28.5

    class MockNumericMetrics:
        revenue = MockMetric(125_000, 25.5)
        eps = MockMetric(1.85, 15.2)
        margins = MockMargins()

    return MockNumericMetrics()


@pytest.fixture
def mock_priority_score():
    """Mock PriorityScore object."""

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

        def should_alert(self, user_status="offline"):
            return self.tier == "critical"

    return MockPriorityScore()


# ============================================================================
# Embed Creation Tests
# ============================================================================


def test_create_sec_filing_embed_basic(
    mock_filing_section,
    mock_sentiment_output,
    mock_priority_score,
):
    """Test basic embed creation with minimal data."""
    embed = create_sec_filing_embed(
        filing_section=mock_filing_section,
        sentiment_output=mock_sentiment_output,
        priority_score=mock_priority_score,
        llm_summary="Strong Q4 results with 25% revenue growth.",
        keywords=["earnings_beat", "revenue_growth"],
    )

    # Check title includes ticker and filing type
    assert "AAPL" in embed["title"]
    assert "8-K" in embed["title"]
    assert "Item 2.02" in embed["title"]
    assert "🔴" in embed["title"]  # Critical emoji

    # Check color matches priority (critical = red)
    assert embed["color"] == PRIORITY_CONFIG["critical"]["color"]

    # Check description has summary
    assert "Strong Q4 results" in embed["description"]

    # Check fields exist
    assert "fields" in embed
    assert len(embed["fields"]) >= 3  # Priority, Sentiment, Keywords

    # Check priority field
    priority_field = next(f for f in embed["fields"] if "Priority" in f["name"])
    assert "CRITICAL" in priority_field["value"]
    assert "0.88" in priority_field["value"]

    # Check sentiment field
    sentiment_field = next(f for f in embed["fields"] if "Sentiment" in f["name"])
    assert "Bullish" in sentiment_field["value"]
    assert SENTIMENT_EMOJIS["bullish"] in sentiment_field["value"]

    # Check keywords field
    keywords_field = next(f for f in embed["fields"] if "Keywords" in f["name"])
    assert "earnings_beat" in keywords_field["value"]
    assert "revenue_growth" in keywords_field["value"]


def test_create_sec_filing_embed_with_metrics(
    mock_filing_section,
    mock_sentiment_output,
    mock_numeric_metrics,
    mock_priority_score,
):
    """Test embed creation with financial metrics."""
    embed = create_sec_filing_embed(
        filing_section=mock_filing_section,
        sentiment_output=mock_sentiment_output,
        numeric_metrics=mock_numeric_metrics,
        priority_score=mock_priority_score,
    )

    # Check metrics field exists
    metrics_field = next((f for f in embed["fields"] if "Key Metrics" in f["name"]), None)
    assert metrics_field is not None

    # Check revenue with YoY change
    assert "$125,000M" in metrics_field["value"]
    assert "+25.5%" in metrics_field["value"]

    # Check EPS with YoY change
    assert "$1.85" in metrics_field["value"]
    assert "+15.2%" in metrics_field["value"]

    # Check margins (bold formatting)
    assert "Gross Margin:**" in metrics_field["value"] or "Gross Margin:" in metrics_field["value"]
    assert "45.2%" in metrics_field["value"]
    assert "Operating Margin:**" in metrics_field["value"] or "Operating Margin:" in metrics_field["value"]
    assert "28.5%" in metrics_field["value"]


def test_create_sec_filing_embed_with_guidance(
    mock_filing_section,
    mock_sentiment_output,
    mock_guidance_analysis,
    mock_priority_score,
):
    """Test embed creation with forward guidance."""
    embed = create_sec_filing_embed(
        filing_section=mock_filing_section,
        sentiment_output=mock_sentiment_output,
        guidance_analysis=mock_guidance_analysis,
        priority_score=mock_priority_score,
    )

    # Check guidance field exists
    guidance_field = next((f for f in embed["fields"] if "Forward Guidance" in f["name"]), None)
    assert guidance_field is not None

    # Check guidance details
    assert "✅" in guidance_field["value"]  # Raised emoji
    assert "Raised" in guidance_field["value"]
    assert "Revenue" in guidance_field["value"]
    # Check numbers are present (formatting may vary with commas)
    assert "150" in guidance_field["value"]
    assert "175" in guidance_field["value"]
    assert "(high)" in guidance_field["value"]  # Confidence


def test_create_sec_filing_embed_priority_tiers(mock_filing_section, mock_sentiment_output):
    """Test embed colors for different priority tiers."""
    tiers = ["critical", "high", "medium", "low"]

    for tier in tiers:

        class MockPriority:
            urgency = 0.5
            impact = 0.5
            relevance = 0.5
            total = 0.5

        MockPriority.tier = tier
        MockPriority.reasons = []

        embed = create_sec_filing_embed(
            filing_section=mock_filing_section,
            sentiment_output=mock_sentiment_output,
            priority_score=MockPriority(),
        )

        # Check color matches tier
        assert embed["color"] == PRIORITY_CONFIG[tier]["color"]

        # Check emoji in title
        assert PRIORITY_CONFIG[tier]["emoji"] in embed["title"]


def test_create_sec_filing_embed_sentiment_variations(
    mock_filing_section,
    mock_priority_score,
):
    """Test embed sentiment field for different sentiment scores."""
    test_cases = [
        (0.75, "bullish", SENTIMENT_EMOJIS["bullish"]),
        (-0.75, "bearish", SENTIMENT_EMOJIS["bearish"]),
        (0.1, "neutral", SENTIMENT_EMOJIS["neutral"]),
    ]

    for score, expected_label, expected_emoji in test_cases:

        class MockSentiment:
            pass

        MockSentiment.score = score
        MockSentiment.weighted_score = score
        MockSentiment.justification = "Test justification"

        embed = create_sec_filing_embed(
            filing_section=mock_filing_section,
            sentiment_output=MockSentiment(),
            priority_score=mock_priority_score,
        )

        sentiment_field = next(f for f in embed["fields"] if "Sentiment" in f["name"])
        assert expected_emoji in sentiment_field["value"]
        assert expected_label.capitalize() in sentiment_field["value"]


# ============================================================================
# Button Creation Tests
# ============================================================================


def test_create_sec_filing_buttons_all_enabled():
    """Test button creation with all features enabled."""
    buttons = create_sec_filing_buttons(
        ticker="AAPL",
        filing_url="https://sec.gov/filing",
        enable_rag=True,
        enable_chart=True,
    )

    # Should return one action row
    assert len(buttons) == 1
    assert buttons[0]["type"] == 1  # Action row

    # Should have 3 buttons
    components = buttons[0]["components"]
    assert len(components) == 3

    # Check View Filing button (link button)
    view_btn = components[0]
    assert view_btn["type"] == 2  # Button
    assert view_btn["style"] == 5  # Link button
    assert view_btn["label"] == "View Filing"
    assert view_btn["url"] == "https://sec.gov/filing"
    assert view_btn["emoji"]["name"] == "📄"

    # Check Dig Deeper button
    dig_btn = components[1]
    assert dig_btn["type"] == 2
    assert dig_btn["style"] == 1  # Primary
    assert dig_btn["label"] == "Dig Deeper"
    assert dig_btn["custom_id"] == "rag_query_AAPL"
    assert dig_btn["emoji"]["name"] == "🔍"

    # Check Chart button
    chart_btn = components[2]
    assert chart_btn["type"] == 2
    assert chart_btn["style"] == 2  # Secondary
    assert chart_btn["label"] == "Chart"
    assert chart_btn["custom_id"] == "chart_AAPL_1D"
    assert chart_btn["emoji"]["name"] == "📊"


def test_create_sec_filing_buttons_rag_disabled():
    """Test button creation with RAG disabled."""
    buttons = create_sec_filing_buttons(
        ticker="AAPL",
        filing_url="https://sec.gov/filing",
        enable_rag=False,
        enable_chart=True,
    )

    components = buttons[0]["components"]
    assert len(components) == 2  # Only View Filing and Chart

    # Check no RAG button
    assert not any(btn.get("custom_id", "").startswith("rag_query") for btn in components)


def test_create_sec_filing_buttons_chart_disabled():
    """Test button creation with chart disabled."""
    buttons = create_sec_filing_buttons(
        ticker="AAPL",
        filing_url="https://sec.gov/filing",
        enable_rag=True,
        enable_chart=False,
    )

    components = buttons[0]["components"]
    assert len(components) == 2  # Only View Filing and Dig Deeper

    # Check no chart button
    assert not any(btn.get("custom_id", "").startswith("chart") for btn in components)


# ============================================================================
# Alert Sending Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not AIOHTTP_AVAILABLE, reason="aiohttp not installed")
async def test_send_sec_filing_alert_success(
    mock_filing_section,
    mock_sentiment_output,
    mock_priority_score,
):
    """Test successful SEC filing alert sending."""
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"id": "123456789", "channel_id": "987654321"}

        mock_session.post.return_value = mock_response

        result = await send_sec_filing_alert(
            filing_section=mock_filing_section,
            sentiment_output=mock_sentiment_output,
            priority_score=mock_priority_score,
            llm_summary="Strong Q4 results",
            keywords=["earnings_beat"],
            webhook_url="https://discord.com/api/webhooks/test",
            enable_buttons=True,
        )

        assert result is not None
        assert result["id"] == "123456789"
        assert result["channel_id"] == "987654321"

        # Verify webhook was called
        mock_session.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_sec_filing_alert_priority_filtering(
    mock_filing_section,
    mock_sentiment_output,
):
    """Test that low priority alerts are filtered."""

    class LowPriority:
        tier = "low"
        total = 0.2
        reasons = []

    with patch.dict("os.environ", {"SEC_ALERT_MIN_PRIORITY": "high"}):
        result = await send_sec_filing_alert(
            filing_section=mock_filing_section,
            sentiment_output=mock_sentiment_output,
            priority_score=LowPriority(),
            webhook_url="https://discord.com/api/webhooks/test",
        )

        # Should return None (filtered out)
        assert result is None


@pytest.mark.asyncio
async def test_send_sec_filing_alert_disabled(
    mock_filing_section,
    mock_sentiment_output,
    mock_priority_score,
):
    """Test that alerts are skipped when disabled."""
    with patch.dict("os.environ", {"SEC_FILING_ALERTS_ENABLED": "false"}):
        result = await send_sec_filing_alert(
            filing_section=mock_filing_section,
            sentiment_output=mock_sentiment_output,
            priority_score=mock_priority_score,
            webhook_url="https://discord.com/api/webhooks/test",
        )

        assert result is None


@pytest.mark.asyncio
async def test_send_sec_filing_alert_no_webhook():
    """Test error handling when no webhook URL is provided."""
    from catalyst_bot.sec_filing_alerts import send_sec_filing_alert

    class MockFiling:
        ticker = "AAPL"
        filing_type = "8-K"
        filing_url = "https://sec.gov"

    class MockSentiment:
        score = 0.5
        weighted_score = 0.5

    with patch.dict("os.environ", {}, clear=True):  # Clear all env vars
        result = await send_sec_filing_alert(
            filing_section=MockFiling(),
            sentiment_output=MockSentiment(),
            webhook_url=None,  # No webhook
        )

        assert result is None


# ============================================================================
# RAG Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not AIOHTTP_AVAILABLE, reason="aiohttp not installed")
async def test_handle_dig_deeper_interaction_success():
    """Test successful Dig Deeper interaction handling."""
    with patch("catalyst_bot.rag_system.get_rag") as mock_get_rag:
        mock_rag = AsyncMock()
        mock_rag.answer_question.return_value = "The acquisition was valued at $500M..."
        mock_get_rag.return_value = mock_rag

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.patch.return_value = mock_response

            result = await handle_dig_deeper_interaction(
                ticker="AAPL",
                user_question="What were the acquisition terms?",
                interaction_token="test_token",
                webhook_url="https://discord.com/api/webhooks/test",
            )

            assert result is True
            mock_rag.answer_question.assert_called_once_with(
                "What were the acquisition terms?", "AAPL"
            )


@pytest.mark.asyncio
async def test_handle_dig_deeper_interaction_rag_unavailable():
    """Test Dig Deeper when RAG system is unavailable."""
    with patch("catalyst_bot.rag_system.get_rag") as mock_get_rag:
        mock_get_rag.return_value = None  # RAG not available

        result = await handle_dig_deeper_interaction(
            ticker="AAPL",
            user_question="What were the terms?",
            interaction_token="test_token",
            webhook_url="https://discord.com/api/webhooks/test",
        )

        assert result is False


# ============================================================================
# Daily Digest Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not AIOHTTP_AVAILABLE, reason="aiohttp not installed")
async def test_send_daily_digest_success():
    """Test successful daily digest sending."""
    filings = [
        {
            "ticker": "AAPL",
            "filing_type": "10-Q",
            "summary": "Quarterly results with strong revenue growth",
            "priority": 0.5,
        },
        {
            "ticker": "MSFT",
            "filing_type": "8-K",
            "summary": "Leadership change announcement",
            "priority": 0.4,
        },
        {
            "ticker": "AAPL",
            "filing_type": "8-K",
            "summary": "Material agreement disclosure",
            "priority": 0.45,
        },
    ]

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"id": "123456789", "channel_id": "987654321"}

        mock_session.post.return_value = mock_response

        result = await send_daily_digest(
            filings=filings,
            webhook_url="https://discord.com/api/webhooks/test",
        )

        assert result is not None
        assert result["id"] == "123456789"
        assert result["channel_id"] == "987654321"

        # Verify post was called
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "https://discord.com/api/webhooks/test"
        assert "json" in call_args[1]
        assert "embeds" in call_args[1]["json"]


@pytest.mark.asyncio
async def test_send_daily_digest_empty_filings():
    """Test daily digest with no filings."""
    result = await send_daily_digest(
        filings=[],
        webhook_url="https://discord.com/api/webhooks/test",
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.skipif(not AIOHTTP_AVAILABLE, reason="aiohttp not installed")
async def test_send_daily_digest_groups_by_ticker():
    """Test that digest correctly groups filings by ticker."""
    filings = [
        {"ticker": "AAPL", "filing_type": "10-Q", "summary": "Q1 results", "priority": 0.5},
        {"ticker": "AAPL", "filing_type": "8-K", "summary": "Acquisition", "priority": 0.4},
        {"ticker": "MSFT", "filing_type": "10-K", "summary": "Annual report", "priority": 0.3},
    ]

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"id": "123456789", "channel_id": "987654321"}

        mock_session.post.return_value = mock_response

        result = await send_daily_digest(
            filings=filings,
            webhook_url="https://discord.com/api/webhooks/test",
        )

        assert result is not None

        # Check embed payload
        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        embed = payload["embeds"][0]

        # Should have 2 ticker fields (AAPL with 2 filings, MSFT with 1)
        assert len(embed["fields"]) == 2

        # Check AAPL field shows 2 filings
        aapl_field = next(f for f in embed["fields"] if "AAPL" in f["name"])
        assert "2 filings" in aapl_field["name"] or "10-Q, 8-K" in aapl_field["value"]


# ============================================================================
# Configuration Helper Tests
# ============================================================================


def test_is_sec_filing_alerts_enabled():
    """Test SEC filing alerts enabled check."""
    with patch.dict("os.environ", {"SEC_FILING_ALERTS_ENABLED": "true"}):
        assert is_sec_filing_alerts_enabled() is True

    with patch.dict("os.environ", {"SEC_FILING_ALERTS_ENABLED": "false"}):
        assert is_sec_filing_alerts_enabled() is False

    with patch.dict("os.environ", {}, clear=True):
        # Default is true
        assert is_sec_filing_alerts_enabled() is True


def test_get_min_priority_tier():
    """Test minimum priority tier configuration."""
    with patch.dict("os.environ", {"SEC_ALERT_MIN_PRIORITY": "critical"}):
        assert get_min_priority_tier() == "critical"

    with patch.dict("os.environ", {"SEC_ALERT_MIN_PRIORITY": "medium"}):
        assert get_min_priority_tier() == "medium"

    with patch.dict("os.environ", {}, clear=True):
        # Default is high
        assert get_min_priority_tier() == "high"

    with patch.dict("os.environ", {"SEC_ALERT_MIN_PRIORITY": "invalid"}):
        # Invalid value defaults to high
        assert get_min_priority_tier() == "high"


# ============================================================================
# Integration Tests
# ============================================================================


def test_priority_config_completeness():
    """Test that all priority tiers have complete configuration."""
    required_tiers = ["critical", "high", "medium", "low"]

    for tier in required_tiers:
        assert tier in PRIORITY_CONFIG
        assert "emoji" in PRIORITY_CONFIG[tier]
        assert "color" in PRIORITY_CONFIG[tier]
        assert "label" in PRIORITY_CONFIG[tier]


def test_sentiment_emojis_completeness():
    """Test that all sentiment types have emojis."""
    required_sentiments = ["bullish", "bearish", "neutral", "mixed"]

    for sentiment in required_sentiments:
        assert sentiment in SENTIMENT_EMOJIS
        assert isinstance(SENTIMENT_EMOJIS[sentiment], str)
