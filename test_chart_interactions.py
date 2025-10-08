"""
Test Chart Interactions Module
================================

Tests for Discord select menu interactions and chart indicator toggles.

Phase 2: WeBull Chart Enhancement Plan

Test Coverage:
1. Select menu building
2. Indicator parsing from interactions
3. Chart regeneration with different indicator combos
4. Session state management
5. Error handling and edge cases
6. Performance benchmarks

Run with:
    pytest test_chart_interactions.py -v
    python -m pytest test_chart_interactions.py --cov=src/catalyst_bot/commands/chart_interactions
"""

import os
import time
from unittest.mock import patch

import pytest

# Set environment variables before importing modules
os.environ["CHART_ENABLE_DROPDOWNS"] = "1"
os.environ["CHART_DROPDOWN_MAX_OPTIONS"] = "5"
os.environ["CHART_DEFAULT_INDICATORS"] = "sr,bollinger"
os.environ["CHART_SESSION_TTL"] = "3600"
os.environ["CHART_SESSION_AUTO_CLEANUP"] = "0"  # Disable auto cleanup in tests

from src.catalyst_bot.chart_sessions import (  # noqa: E402
    clear_user_sessions,
    force_cleanup,
    get_session_stats,
    get_user_indicator_preferences,
    set_user_indicator_preferences,
)
from src.catalyst_bot.commands.chart_interactions import (  # noqa: E402
    build_chart_select_menu,
    get_default_indicators,
    handle_chart_indicator_toggle,
    parse_indicator_selection,
    regenerate_chart_with_indicators,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_ticker():
    """Sample ticker for testing."""
    return "AAPL"


@pytest.fixture
def sample_timeframe():
    """Sample timeframe for testing."""
    return "1D"


@pytest.fixture
def sample_user_id():
    """Sample Discord user ID for testing."""
    return "123456789"


@pytest.fixture
def sample_indicators():
    """Sample indicator list for testing."""
    return ["sr", "bollinger"]


@pytest.fixture
def sample_interaction(sample_ticker, sample_timeframe, sample_user_id):
    """Sample Discord interaction payload."""
    return {
        "type": 3,  # MESSAGE_COMPONENT
        "data": {
            "custom_id": f"chart_toggle_{sample_ticker}_{sample_timeframe}",
            "values": ["sr", "fibonacci"],
        },
        "user": {"id": sample_user_id},
    }


@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Clean up session state after each test."""
    yield
    # Clear all sessions after test
    from src.catalyst_bot.chart_sessions import _SESSION_STORE, _STORE_LOCK

    with _STORE_LOCK:
        _SESSION_STORE.clear()


# ============================================================================
# Test Select Menu Building
# ============================================================================


def test_build_chart_select_menu_basic(sample_ticker, sample_timeframe):
    """Test basic select menu creation."""
    menu = build_chart_select_menu(sample_ticker, sample_timeframe)

    # Should return list with one action row
    assert isinstance(menu, list)
    assert len(menu) == 1

    # Check action row structure
    action_row = menu[0]
    assert action_row["type"] == 1  # Action Row

    # Check select menu component
    select_menu = action_row["components"][0]
    assert select_menu["type"] == 3  # Select Menu
    assert (
        select_menu["custom_id"] == f"chart_toggle_{sample_ticker}_{sample_timeframe}"
    )
    assert select_menu["placeholder"] == "📊 Toggle Indicators"
    assert select_menu["min_values"] == 0
    assert select_menu["max_values"] == 5

    # Check options
    assert len(select_menu["options"]) == 5
    assert all("label" in opt for opt in select_menu["options"])
    assert all("value" in opt for opt in select_menu["options"])


def test_build_chart_select_menu_with_defaults(sample_ticker, sample_timeframe):
    """Test select menu with default indicators."""
    default_indicators = ["sr", "bollinger"]
    menu = build_chart_select_menu(sample_ticker, sample_timeframe, default_indicators)

    select_menu = menu[0]["components"][0]
    options = select_menu["options"]

    # Check that sr and bollinger are marked as default
    sr_option = next(opt for opt in options if opt["value"] == "sr")
    assert sr_option["default"] is True

    bollinger_option = next(opt for opt in options if opt["value"] == "bollinger")
    assert bollinger_option["default"] is True

    fibonacci_option = next(opt for opt in options if opt["value"] == "fibonacci")
    assert fibonacci_option["default"] is False


def test_build_chart_select_menu_disabled():
    """Test select menu when dropdowns are disabled."""
    with patch.dict(os.environ, {"CHART_ENABLE_DROPDOWNS": "0"}):
        menu = build_chart_select_menu("AAPL", "1D")
        assert menu == []


def test_build_chart_select_menu_with_user_preferences(
    sample_ticker, sample_timeframe, sample_user_id
):
    """Test select menu loads user preferences."""
    # Set user preferences
    set_user_indicator_preferences(
        sample_user_id, sample_ticker, ["fibonacci", "volume_profile"]
    )

    # Build menu - should use user preferences
    menu = build_chart_select_menu(
        sample_ticker, sample_timeframe, user_id=sample_user_id
    )

    select_menu = menu[0]["components"][0]
    options = select_menu["options"]

    # Check that fibonacci and volume_profile are marked as default
    fib_option = next(opt for opt in options if opt["value"] == "fibonacci")
    assert fib_option["default"] is True

    vp_option = next(opt for opt in options if opt["value"] == "volume_profile")
    assert vp_option["default"] is True


# ============================================================================
# Test Indicator Parsing
# ============================================================================


def test_parse_indicator_selection(sample_interaction):
    """Test parsing indicators from interaction data."""
    ticker, timeframe, indicators = parse_indicator_selection(
        sample_interaction["data"]
    )

    assert ticker == "AAPL"
    assert timeframe == "1D"
    assert indicators == ["sr", "fibonacci"]


def test_parse_indicator_selection_empty():
    """Test parsing when no indicators selected."""
    interaction_data = {
        "custom_id": "chart_toggle_TSLA_5D",
        "values": [],
    }

    ticker, timeframe, indicators = parse_indicator_selection(interaction_data)

    assert ticker == "TSLA"
    assert timeframe == "5D"
    assert indicators == []


def test_parse_indicator_selection_complex_timeframe():
    """Test parsing with complex timeframe (underscore in name)."""
    interaction_data = {
        "custom_id": "chart_toggle_MSFT_1M_extended",
        "values": ["bollinger"],
    }

    ticker, timeframe, indicators = parse_indicator_selection(interaction_data)

    assert ticker == "MSFT"
    assert timeframe == "1M_extended"
    assert indicators == ["bollinger"]


# ============================================================================
# Test Chart Regeneration
# ============================================================================


@patch("src.catalyst_bot.commands.chart_interactions.get_quickchart_url")
@patch("src.catalyst_bot.commands.chart_interactions.get_last_price_change")
def test_regenerate_chart_with_indicators_success(
    mock_price, mock_chart, sample_ticker, sample_timeframe, sample_indicators
):
    """Test successful chart regeneration."""
    # Mock responses
    mock_chart.return_value = "https://example.com/chart.png"
    mock_price.return_value = (150.25, 2.5)

    chart_url, price_data = regenerate_chart_with_indicators(
        sample_ticker, sample_timeframe, sample_indicators
    )

    # Verify results
    assert chart_url == "https://example.com/chart.png"
    assert price_data["price"] == 150.25
    assert price_data["change_pct"] == 2.5

    # Verify mock calls
    mock_chart.assert_called_once_with(
        sample_ticker, timeframe=sample_timeframe, indicators=sample_indicators
    )


@patch("src.catalyst_bot.commands.chart_interactions.get_quickchart_url")
def test_regenerate_chart_with_indicators_failure(
    mock_chart, sample_ticker, sample_timeframe, sample_indicators
):
    """Test chart regeneration when chart generation fails."""
    mock_chart.return_value = None

    chart_url, price_data = regenerate_chart_with_indicators(
        sample_ticker, sample_timeframe, sample_indicators
    )

    assert chart_url is None
    assert price_data is None


@patch("src.catalyst_bot.commands.chart_interactions.get_quickchart_url")
@patch("src.catalyst_bot.commands.chart_interactions.get_last_price_change")
def test_regenerate_chart_saves_user_preferences(
    mock_price, mock_chart, sample_ticker, sample_timeframe, sample_user_id
):
    """Test that chart regeneration saves user preferences."""
    mock_chart.return_value = "https://example.com/chart.png"
    mock_price.return_value = (100.0, 1.0)

    indicators = ["sr", "volume_profile"]

    regenerate_chart_with_indicators(
        sample_ticker, sample_timeframe, indicators, user_id=sample_user_id
    )

    # Verify preferences were saved
    saved_prefs = get_user_indicator_preferences(sample_user_id, sample_ticker)
    assert saved_prefs == indicators


# ============================================================================
# Test Interaction Handling
# ============================================================================


@patch("src.catalyst_bot.commands.chart_interactions.regenerate_chart_with_indicators")
@patch("src.catalyst_bot.commands.chart_interactions.create_chart_embed")
def test_handle_chart_indicator_toggle_success(
    mock_embed, mock_regen, sample_interaction
):
    """Test successful interaction handling."""
    # Mock regeneration
    mock_regen.return_value = (
        "https://example.com/chart.png",
        {"price": 100.0, "change_pct": 2.0},
    )

    # Mock embed creation
    mock_embed.return_value = {
        "type": 4,
        "data": {
            "embeds": [{"title": "AAPL Chart"}],
            "components": [],
        },
    }

    response = handle_chart_indicator_toggle(sample_interaction)

    # Should return type 7 (update message)
    assert response["type"] == 7
    assert "data" in response

    # Verify mocks were called
    mock_regen.assert_called_once()
    mock_embed.assert_called_once()


@patch("src.catalyst_bot.commands.chart_interactions.regenerate_chart_with_indicators")
def test_handle_chart_indicator_toggle_failure(mock_regen, sample_interaction):
    """Test interaction handling when regeneration fails."""
    mock_regen.return_value = (None, None)

    response = handle_chart_indicator_toggle(sample_interaction)

    # Should return error response
    assert response["type"] == 4
    assert "content" in response["data"]
    assert "Failed to regenerate" in response["data"]["content"]


def test_handle_chart_indicator_toggle_exception(sample_interaction):
    """Test interaction handling with exception."""
    # Invalid interaction data to trigger exception
    invalid_interaction = {"type": 3, "data": {}}

    response = handle_chart_indicator_toggle(invalid_interaction)

    # Should return error response
    assert response["type"] == 4
    assert "content" in response["data"]


# ============================================================================
# Test Session State Management
# ============================================================================


def test_session_save_and_load(sample_user_id, sample_ticker):
    """Test saving and loading user preferences."""
    indicators = ["sr", "bollinger", "fibonacci"]

    set_user_indicator_preferences(sample_user_id, sample_ticker, indicators)
    loaded = get_user_indicator_preferences(sample_user_id, sample_ticker)

    assert loaded == indicators


def test_session_expiration(sample_user_id, sample_ticker):
    """Test session expiration."""
    import os

    # Set with very short TTL via environment
    with patch.dict(os.environ, {"CHART_SESSION_TTL": "1"}):
        indicators = ["sr"]
        set_user_indicator_preferences(sample_user_id, sample_ticker, indicators)

        # Should be available immediately
        loaded = get_user_indicator_preferences(sample_user_id, sample_ticker)
        assert loaded == indicators

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired
        loaded = get_user_indicator_preferences(sample_user_id, sample_ticker)
        assert loaded is None


def test_session_clear_specific_ticker(sample_user_id):
    """Test clearing preferences for a specific user (note: ticker-specific clear not implemented)."""  # noqa: E501
    set_user_indicator_preferences(sample_user_id, "AAPL", ["sr"])
    set_user_indicator_preferences(sample_user_id, "TSLA", ["bollinger"])

    # Clear all for user
    count = clear_user_sessions(sample_user_id)
    assert count == 2

    # Both should be gone
    assert get_user_indicator_preferences(sample_user_id, "AAPL") is None
    assert get_user_indicator_preferences(sample_user_id, "TSLA") is None


def test_session_clear_all_for_user(sample_user_id):
    """Test clearing all preferences for a user."""
    set_user_indicator_preferences(sample_user_id, "AAPL", ["sr"])
    set_user_indicator_preferences(sample_user_id, "TSLA", ["bollinger"])
    set_user_indicator_preferences(sample_user_id, "MSFT", ["fibonacci"])

    # Clear all
    count = clear_user_sessions(sample_user_id)
    assert count == 3

    # All should be gone
    assert get_user_indicator_preferences(sample_user_id, "AAPL") is None
    assert get_user_indicator_preferences(sample_user_id, "TSLA") is None
    assert get_user_indicator_preferences(sample_user_id, "MSFT") is None


def test_session_cleanup_expired():
    """Test cleanup of expired sessions."""
    import os

    user1 = "user1"
    user2 = "user2"

    # Create sessions with short TTL
    with patch.dict(os.environ, {"CHART_SESSION_TTL": "1"}):
        set_user_indicator_preferences(user1, "AAPL", ["sr"])  # Will expire

        # Wait for first to expire
        time.sleep(1.5)

        # Create second session with longer TTL
        with patch.dict(os.environ, {"CHART_SESSION_TTL": "3600"}):
            set_user_indicator_preferences(user2, "TSLA", ["bollinger"])  # Won't expire

        # Run cleanup
        count = force_cleanup()
        assert count >= 1  # At least user1's session should be expired

        # Check results
        assert get_user_indicator_preferences(user1, "AAPL") is None
        assert get_user_indicator_preferences(user2, "TSLA") == ["bollinger"]


def test_session_stats():
    """Test session statistics."""
    set_user_indicator_preferences("user1", "AAPL", ["sr"])
    set_user_indicator_preferences("user1", "TSLA", ["bollinger"])
    set_user_indicator_preferences("user2", "MSFT", ["fibonacci"])

    stats = get_session_stats()

    assert stats["total_sessions"] == 3
    assert stats["unique_users"] == 2
    assert stats["unique_tickers"] == 3
    assert "ttl_seconds" in stats
    assert "oldest_session_age_seconds" in stats


# ============================================================================
# Test Default Indicators
# ============================================================================


def test_get_default_indicators():
    """Test getting default indicators from environment."""
    with patch.dict(os.environ, {"CHART_DEFAULT_INDICATORS": "sr,bollinger,fibonacci"}):
        indicators = get_default_indicators()
        assert indicators == ["sr", "bollinger", "fibonacci"]


def test_get_default_indicators_invalid():
    """Test filtering invalid indicators."""
    with patch.dict(
        os.environ, {"CHART_DEFAULT_INDICATORS": "sr,invalid,bollinger,fake"}
    ):
        indicators = get_default_indicators()
        # Should only include valid indicators
        assert "sr" in indicators
        assert "bollinger" in indicators
        assert "invalid" not in indicators
        assert "fake" not in indicators


# ============================================================================
# Performance Benchmarks
# ============================================================================


@pytest.mark.benchmark
@patch("src.catalyst_bot.commands.chart_interactions.get_quickchart_url")
@patch("src.catalyst_bot.commands.chart_interactions.get_last_price_change")
def test_chart_regeneration_performance(mock_price, mock_chart):
    """Benchmark chart regeneration speed."""
    mock_chart.return_value = "https://example.com/chart.png"
    mock_price.return_value = (100.0, 1.0)

    start_time = time.time()
    regenerate_chart_with_indicators("AAPL", "1D", ["sr", "bollinger"])
    elapsed = time.time() - start_time

    # Should complete in < 2 seconds (requirement from plan)
    assert elapsed < 2.0, f"Chart regeneration took {elapsed:.2f}s (should be < 2s)"


# ============================================================================
# Integration Tests
# ============================================================================


@patch("src.catalyst_bot.commands.chart_interactions.get_quickchart_url")
@patch("src.catalyst_bot.commands.chart_interactions.get_last_price_change")
def test_full_interaction_flow(mock_price, mock_chart, sample_user_id):
    """Test complete interaction flow from start to finish."""
    mock_chart.return_value = "https://example.com/chart.png"
    mock_price.return_value = (150.0, 2.5)

    # 1. Build initial menu with defaults
    menu = build_chart_select_menu(
        "AAPL", "1D", ["sr", "bollinger"], user_id=sample_user_id
    )
    assert len(menu) == 1

    # 2. User selects different indicators
    interaction = {
        "type": 3,
        "data": {
            "custom_id": "chart_toggle_AAPL_1D",
            "values": ["fibonacci", "volume_profile"],
        },
        "user": {"id": sample_user_id},
    }

    # 3. Handle interaction
    with patch(
        "src.catalyst_bot.commands.chart_interactions.create_chart_embed"
    ) as mock_embed:
        mock_embed.return_value = {
            "type": 4,
            "data": {"embeds": [{"title": "AAPL Chart"}], "components": []},
        }
        response = handle_chart_indicator_toggle(interaction)

    # 4. Verify response
    assert response["type"] == 7  # Update message

    # 5. Verify preferences were saved
    saved_prefs = get_user_indicator_preferences(sample_user_id, "AAPL")
    assert saved_prefs == ["fibonacci", "volume_profile"]

    # 6. Build menu again - should use saved preferences
    menu2 = build_chart_select_menu("AAPL", "1D", user_id=sample_user_id)
    options = menu2[0]["components"][0]["options"]

    fib_opt = next(opt for opt in options if opt["value"] == "fibonacci")
    assert fib_opt["default"] is True


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
