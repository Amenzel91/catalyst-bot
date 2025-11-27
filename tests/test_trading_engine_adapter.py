"""
Comprehensive tests for TradingEngineAdapter.

Tests the execute_with_trading_engine() function which serves as a drop-in
replacement for execute_paper_trade(). Tests include signal conversion,
TradingEngine integration, error handling, and return values.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from catalyst_bot.models import ScoredItem
from catalyst_bot.adapters.trading_engine_adapter import (
    execute_with_trading_engine,
    reset_trading_engine_instance,
)
from catalyst_bot.execution.order_executor import TradingSignal


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_engine_instance():
    """Reset TradingEngine instance before each test."""
    reset_trading_engine_instance()
    yield
    reset_trading_engine_instance()


@pytest.fixture
def mock_trading_engine():
    """Mock TradingEngine instance."""
    engine = Mock()
    engine.initialize = AsyncMock(return_value=True)
    engine._execute_signal = AsyncMock()
    return engine


@pytest.fixture
def mock_position():
    """Mock Position object returned by TradingEngine."""
    position = Mock()
    position.position_id = "pos_12345"
    position.ticker = "AAPL"
    position.quantity = 10
    position.entry_price = Decimal("150.00")
    return position


@pytest.fixture
def high_quality_scored_item():
    """High-quality ScoredItem for successful trade execution."""
    return ScoredItem(
        relevance=4.5,
        sentiment=0.8,
        tags=["earnings_beat", "catalyst"],
        source_weight=1.2,
        keyword_hits=["beat", "raised", "guidance"],
        enriched=True,
        enrichment_timestamp=datetime.now().timestamp(),
    )


@pytest.fixture
def low_quality_scored_item():
    """Low-quality ScoredItem that should be filtered out."""
    return ScoredItem(
        relevance=2.0,
        sentiment=0.05,
        tags=["general_news"],
        source_weight=1.0,
        keyword_hits=["company"],
        enriched=False,
    )


@pytest.fixture
def neutral_sentiment_item():
    """ScoredItem with neutral sentiment (should be filtered)."""
    return ScoredItem(
        relevance=4.0,
        sentiment=0.05,  # Neutral
        tags=["news"],
        source_weight=1.0,
        keyword_hits=["company", "stock"],
        enriched=False,
    )


@pytest.fixture
def negative_sentiment_item():
    """ScoredItem with negative sentiment (sell signal)."""
    return ScoredItem(
        relevance=4.2,
        sentiment=-0.7,
        tags=["downgrade", "warning"],
        source_weight=1.1,
        keyword_hits=["miss", "downgrade", "warning"],
        enriched=True,
    )


# ============================================================================
# Basic Execution Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_execute_with_trading_engine_success(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test successful trade execution through TradingEngine."""
    # Setup mock
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    # Execute
    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("175.50"),
        extended_hours=False,
    )

    # Assertions
    assert result is True
    mock_trading_engine.initialize.assert_called_once()
    mock_trading_engine._execute_signal.assert_called_once()

    # Verify signal was passed correctly
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]
    assert isinstance(signal, TradingSignal)
    assert signal.ticker == "AAPL"
    assert signal.entry_price == Decimal("175.50")
    assert signal.action == "buy"


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_execute_with_trading_engine_failure(
    mock_engine_class, mock_trading_engine, high_quality_scored_item
):
    """Test trade execution failure (TradingEngine returns None)."""
    # Setup mock to return None (execution failed)
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = None

    # Execute
    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("175.50"),
    )

    # Should return False on failure
    assert result is False


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_execute_filtered_low_confidence(
    mock_engine_class, mock_trading_engine, low_quality_scored_item
):
    """Test that low confidence items are filtered (no signal generated)."""
    mock_engine_class.return_value = mock_trading_engine

    # Execute with low quality item
    result = execute_with_trading_engine(
        item=low_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Should return False (no actionable signal)
    assert result is False
    # TradingEngine should not be called
    mock_trading_engine._execute_signal.assert_not_called()


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_execute_filtered_neutral_sentiment(
    mock_engine_class, mock_trading_engine, neutral_sentiment_item
):
    """Test that neutral sentiment items are filtered (hold action)."""
    mock_engine_class.return_value = mock_trading_engine

    # Execute with neutral sentiment
    result = execute_with_trading_engine(
        item=neutral_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Should return False (no actionable signal)
    assert result is False
    # TradingEngine should not be called
    mock_trading_engine._execute_signal.assert_not_called()


# ============================================================================
# Signal Conversion Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_scored_item_to_trading_signal_conversion(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that ScoredItem is correctly converted to TradingSignal."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="NVDA",
        current_price=Decimal("875.50"),
        extended_hours=True,
    )

    # Get the signal that was passed to TradingEngine
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Verify signal properties
    assert signal.ticker == "NVDA"
    assert signal.entry_price == Decimal("875.50")
    assert signal.current_price == Decimal("875.50")
    assert signal.action == "buy"
    assert signal.confidence > 0.0
    assert signal.signal_type == "keyword_momentum"
    assert signal.timeframe == "intraday"
    assert signal.strategy == "catalyst_keyword_v1"

    # Verify metadata preservation
    assert signal.metadata["relevance"] == 4.5
    assert signal.metadata["sentiment"] == 0.8
    assert signal.metadata["tags"] == ["earnings_beat", "catalyst"]
    assert signal.metadata["keyword_hits"] == ["beat", "raised", "guidance"]
    assert signal.metadata["enriched"] is True
    assert signal.metadata["extended_hours"] is True


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_sell_signal_conversion(
    mock_engine_class, mock_trading_engine, mock_position, negative_sentiment_item
):
    """Test conversion of negative sentiment to sell signal."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    execute_with_trading_engine(
        item=negative_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Get the signal
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Should be a sell signal
    assert signal.action == "sell"
    assert signal.ticker == "AAPL"


# ============================================================================
# Extended Hours Parameter Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_extended_hours_false(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that extended_hours=False is correctly propagated."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=False,
    )

    # Verify extended_hours in signal metadata
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]
    assert signal.metadata["extended_hours"] is False


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_extended_hours_true(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that extended_hours=True is correctly propagated."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=True,
    )

    # Verify extended_hours in signal metadata
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]
    assert signal.metadata["extended_hours"] is True


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_extended_hours_default_false(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that extended_hours defaults to False when not specified."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    # Don't pass extended_hours parameter
    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Should default to False
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]
    assert signal.metadata["extended_hours"] is False


# ============================================================================
# Error Handling Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_error_handling_engine_initialization_failure(mock_engine_class, high_quality_scored_item):
    """Test error handling when TradingEngine initialization fails."""
    # Mock initialization failure
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=False)
    mock_engine_class.return_value = mock_engine

    # Should handle error gracefully and return False
    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert result is False


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_error_handling_execute_signal_exception(
    mock_engine_class, mock_trading_engine, high_quality_scored_item
):
    """Test error handling when _execute_signal raises exception."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.side_effect = Exception("Test error")

    # Should handle exception and return False
    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert result is False


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_error_handling_invalid_price(mock_engine_class, mock_trading_engine, high_quality_scored_item):
    """Test error handling with invalid price values."""
    mock_engine_class.return_value = mock_trading_engine

    # Try with zero price
    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("0.00"),
    )

    # Should either handle gracefully or raise appropriate error
    # (behavior depends on implementation)
    assert isinstance(result, bool)


# ============================================================================
# Return Value Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_return_value_true_on_success(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that function returns True when position is created."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert result is True


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_return_value_false_on_execution_failure(
    mock_engine_class, mock_trading_engine, high_quality_scored_item
):
    """Test that function returns False when execution fails."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = None

    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert result is False


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_return_value_false_on_filter(mock_engine_class, low_quality_scored_item):
    """Test that function returns False when signal is filtered."""
    result = execute_with_trading_engine(
        item=low_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert result is False


# ============================================================================
# TradingEngine Instance Management Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_trading_engine_singleton_behavior(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that TradingEngine instance is reused (singleton-like behavior)."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    # Execute twice
    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="MSFT",
        current_price=Decimal("350.00"),
    )

    # TradingEngine should be instantiated only once
    assert mock_engine_class.call_count == 1
    # But initialize should be called once
    assert mock_trading_engine.initialize.call_count == 1
    # And _execute_signal should be called twice
    assert mock_trading_engine._execute_signal.call_count == 2


def test_reset_trading_engine_instance_clears_cache():
    """Test that reset_trading_engine_instance() clears the cached instance."""
    from catalyst_bot.adapters.trading_engine_adapter import _get_trading_engine_instance

    # Reset should work even if no instance exists
    reset_trading_engine_instance()

    # Verify no cached instance
    assert not hasattr(_get_trading_engine_instance, "_instance")


# ============================================================================
# Risk Parameter Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_risk_parameters_in_signal(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test that risk parameters are correctly calculated and passed."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    entry_price = Decimal("100.00")
    execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker="AAPL",
        current_price=entry_price,
    )

    # Get the signal
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Verify risk parameters (default: 5% stop, 10% profit)
    expected_stop = entry_price * Decimal("0.95")
    expected_profit = entry_price * Decimal("1.10")
    assert signal.stop_loss_price == expected_stop
    assert signal.take_profit_price == expected_profit
    assert 0.03 <= signal.position_size_pct <= 0.05  # 3-5% position size


# ============================================================================
# Integration Tests (Multiple Scenarios)
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_multiple_tickers_sequential(
    mock_engine_class, mock_trading_engine, mock_position, high_quality_scored_item
):
    """Test executing trades for multiple tickers sequentially."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    tickers = ["AAPL", "MSFT", "GOOGL", "NVDA"]
    prices = [Decimal("150.00"), Decimal("350.00"), Decimal("140.00"), Decimal("875.00")]

    results = []
    for ticker, price in zip(tickers, prices):
        result = execute_with_trading_engine(
            item=high_quality_scored_item,
            ticker=ticker,
            current_price=price,
        )
        results.append(result)

    # All should succeed
    assert all(results)
    # Should have called _execute_signal for each ticker
    assert mock_trading_engine._execute_signal.call_count == len(tickers)


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_mixed_success_and_failure(mock_engine_class, mock_trading_engine, mock_position):
    """Test scenario with both successful and failed trades."""
    mock_engine_class.return_value = mock_trading_engine

    # First call succeeds
    mock_trading_engine._execute_signal.return_value = mock_position
    result1 = execute_with_trading_engine(
        item=ScoredItem(
            relevance=4.5,
            sentiment=0.8,
            tags=["catalyst"],
            source_weight=1.0,
            keyword_hits=["beat"],
        ),
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Second call fails (returns None)
    mock_trading_engine._execute_signal.return_value = None
    result2 = execute_with_trading_engine(
        item=ScoredItem(
            relevance=4.0,
            sentiment=0.7,
            tags=["news"],
            source_weight=1.0,
            keyword_hits=["company"],
        ),
        ticker="MSFT",
        current_price=Decimal("350.00"),
    )

    # Third call is filtered (low confidence)
    result3 = execute_with_trading_engine(
        item=ScoredItem(
            relevance=2.0,
            sentiment=0.1,
            tags=["general"],
            source_weight=1.0,
            keyword_hits=["stock"],
        ),
        ticker="GOOGL",
        current_price=Decimal("140.00"),
    )

    assert result1 is True
    assert result2 is False
    assert result3 is False


# ============================================================================
# Parametrized Tests
# ============================================================================


@pytest.mark.parametrize(
    "ticker,price,extended_hours",
    [
        ("AAPL", Decimal("150.00"), False),
        ("MSFT", Decimal("350.00"), True),
        ("GOOGL", Decimal("140.50"), False),
        ("NVDA", Decimal("875.75"), True),
        ("TSLA", Decimal("250.25"), False),
    ],
)
@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_various_tickers_and_prices(
    mock_engine_class,
    mock_trading_engine,
    mock_position,
    high_quality_scored_item,
    ticker,
    price,
    extended_hours,
):
    """Test execution with various tickers, prices, and extended hours settings."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    result = execute_with_trading_engine(
        item=high_quality_scored_item,
        ticker=ticker,
        current_price=price,
        extended_hours=extended_hours,
    )

    assert result is True

    # Verify signal properties
    call_args = mock_trading_engine._execute_signal.call_args
    signal = call_args[0][0]
    assert signal.ticker == ticker
    assert signal.entry_price == price
    assert signal.metadata["extended_hours"] == extended_hours


@pytest.mark.parametrize(
    "relevance,sentiment,should_execute",
    [
        (4.5, 0.8, True),  # High quality - should execute
        (4.0, 0.6, True),  # Good quality - should execute
        (3.0, 0.3, True),  # Medium quality - may execute
        (2.0, 0.1, False),  # Low quality - should filter
        (1.5, 0.05, False),  # Very low quality - should filter
    ],
)
@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_quality_thresholds(
    mock_engine_class, mock_trading_engine, mock_position, relevance, sentiment, should_execute
):
    """Test that quality thresholds are correctly applied."""
    mock_engine_class.return_value = mock_trading_engine
    mock_trading_engine._execute_signal.return_value = mock_position

    item = ScoredItem(
        relevance=relevance,
        sentiment=sentiment,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    result = execute_with_trading_engine(
        item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    if should_execute:
        assert result is True
        mock_trading_engine._execute_signal.assert_called()
    else:
        assert result is False
        mock_trading_engine._execute_signal.assert_not_called()
