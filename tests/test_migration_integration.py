"""
End-to-end integration tests for TradingEngine migration.

Tests the complete flow from ScoredItem → SignalAdapter → TradingEngine,
including extended hours handling, Alpaca API mocking, and realistic
SEC filing scenarios.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from catalyst_bot.models import ScoredItem
from catalyst_bot.adapters.signal_adapter import SignalAdapter, SignalAdapterConfig
from catalyst_bot.adapters.trading_engine_adapter import (
    execute_with_trading_engine,
    reset_trading_engine_instance,
)
from catalyst_bot.execution.order_executor import TradingSignal


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_engine():
    """Reset TradingEngine instance before and after each test."""
    reset_trading_engine_instance()
    yield
    reset_trading_engine_instance()


@pytest.fixture
def mock_alpaca_client():
    """Mock Alpaca API client."""
    client = Mock()

    # Mock account
    mock_account = Mock()
    mock_account.equity = "100000.00"
    mock_account.cash = "100000.00"
    mock_account.buying_power = "100000.00"
    client.get_account = Mock(return_value=mock_account)

    # Mock clock
    mock_clock = Mock()
    mock_clock.is_open = True
    mock_clock.timestamp = datetime.now()
    client.get_clock = Mock(return_value=mock_clock)

    # Mock order submission
    mock_order = Mock()
    mock_order.id = "order_12345"
    mock_order.symbol = "AAPL"
    mock_order.qty = "10"
    mock_order.filled_qty = "10"
    mock_order.status = "filled"
    client.submit_order = Mock(return_value=mock_order)

    # Mock get_order
    client.get_order = Mock(return_value=mock_order)

    # Mock positions
    client.list_positions = Mock(return_value=[])
    client.get_position = Mock(side_effect=Exception("Position not found"))

    return client


@pytest.fixture
def realistic_sec_filing_item():
    """Realistic SEC filing ScoredItem (merger announcement)."""
    return ScoredItem(
        relevance=4.8,
        sentiment=0.85,
        tags=["merger_acquisition", "sec_filing", "8-K", "catalyst"],
        source_weight=1.5,  # High credibility (SEC.gov)
        keyword_hits=["merger", "acquisition", "definitive agreement", "SEC", "8-K"],
        enriched=True,
        enrichment_timestamp=datetime.now().timestamp(),
    )


@pytest.fixture
def earnings_beat_item():
    """Earnings beat ScoredItem."""
    return ScoredItem(
        relevance=4.5,
        sentiment=0.75,
        tags=["earnings_beat", "guidance_raise", "catalyst"],
        source_weight=1.3,
        keyword_hits=["beat", "exceeds", "raised", "guidance"],
        enriched=True,
        enrichment_timestamp=datetime.now().timestamp(),
    )


@pytest.fixture
def downgrade_item():
    """Analyst downgrade ScoredItem (negative sentiment)."""
    return ScoredItem(
        relevance=4.2,
        sentiment=-0.7,
        tags=["analyst_downgrade", "price_target_cut"],
        source_weight=1.2,
        keyword_hits=["downgrade", "cut", "lowered", "target"],
        enriched=True,
    )


# ============================================================================
# End-to-End Integration Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_end_to_end_scored_item_to_execution(
    mock_engine_class, mock_alpaca_client, realistic_sec_filing_item
):
    """Test complete flow: ScoredItem → SignalAdapter → TradingEngine → Order."""
    # Setup TradingEngine mock
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)

    # Create mock position that would be returned
    mock_position = Mock()
    mock_position.position_id = "pos_sec_merger_123"
    mock_position.ticker = "NVDA"
    mock_position.quantity = 10
    mock_position.entry_price = Decimal("875.50")
    mock_position.current_price = Decimal("875.50")
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)

    mock_engine_class.return_value = mock_engine

    # Execute the complete flow
    result = execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="NVDA",
        current_price=Decimal("875.50"),
        extended_hours=False,
    )

    # Verify success
    assert result is True

    # Verify TradingEngine was initialized
    mock_engine.initialize.assert_called_once()

    # Verify signal was passed to TradingEngine
    mock_engine._execute_signal.assert_called_once()

    # Get the signal that was passed
    call_args = mock_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Verify signal correctness
    assert isinstance(signal, TradingSignal)
    assert signal.ticker == "NVDA"
    assert signal.entry_price == Decimal("875.50")
    assert signal.action == "buy"
    assert signal.confidence > 0.85  # High confidence for quality SEC filing

    # Verify metadata preservation (zero data loss)
    assert signal.metadata["relevance"] == 4.8
    assert signal.metadata["sentiment"] == 0.85
    assert signal.metadata["tags"] == ["merger_acquisition", "sec_filing", "8-K", "catalyst"]
    assert "merger" in signal.metadata["keyword_hits"]
    assert signal.metadata["enriched"] is True
    assert signal.metadata["extended_hours"] is False


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_end_to_end_with_extended_hours(mock_engine_class, earnings_beat_item):
    """Test end-to-end flow with extended hours enabled."""
    # Setup mock
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)

    mock_position = Mock()
    mock_position.position_id = "pos_ext_hours_456"
    mock_position.ticker = "AAPL"
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)

    mock_engine_class.return_value = mock_engine

    # Execute with extended hours
    result = execute_with_trading_engine(
        item=earnings_beat_item,
        ticker="AAPL",
        current_price=Decimal("175.50"),
        extended_hours=True,  # Extended hours enabled
    )

    assert result is True

    # Get signal
    call_args = mock_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Verify extended hours flag propagated
    assert signal.metadata["extended_hours"] is True


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_end_to_end_sell_signal(mock_engine_class, downgrade_item):
    """Test end-to-end flow with negative sentiment (sell signal)."""
    # Setup mock
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)

    mock_position = Mock()
    mock_position.position_id = "pos_sell_789"
    mock_position.ticker = "TSLA"
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)

    mock_engine_class.return_value = mock_engine

    # Execute
    result = execute_with_trading_engine(
        item=downgrade_item,
        ticker="TSLA",
        current_price=Decimal("250.00"),
        extended_hours=False,
    )

    assert result is True

    # Get signal
    call_args = mock_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Should be a sell signal
    assert signal.action == "sell"
    assert signal.ticker == "TSLA"

    # Verify stop-loss for sell (above entry)
    assert signal.stop_loss_price > signal.entry_price
    # Verify take-profit for sell (below entry)
    assert signal.take_profit_price < signal.entry_price


# ============================================================================
# Extended Hours Behavior Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_extended_hours_vs_regular_hours_flag_propagation(mock_engine_class, realistic_sec_filing_item):
    """Test that extended_hours flag correctly propagates in both modes."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_position = Mock()
    mock_position.position_id = "pos_test"
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)
    mock_engine_class.return_value = mock_engine

    # Reset engine instance to ensure fresh start
    reset_trading_engine_instance()

    # Test regular hours (extended_hours=False)
    result_regular = execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=False,
    )

    # Test extended hours (extended_hours=True) - same instance should be reused
    result_extended = execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=True,
    )

    assert result_regular is True
    assert result_extended is True

    # Both should have been called (2 execute_signal calls)
    assert mock_engine._execute_signal.call_count == 2

    # Get both signals
    calls = mock_engine._execute_signal.call_args_list
    signal_regular = calls[0][0][0]
    signal_extended = calls[1][0][0]

    # Verify flags
    assert signal_regular.metadata["extended_hours"] is False
    assert signal_extended.metadata["extended_hours"] is True


# ============================================================================
# Data Preservation Tests (Zero Data Loss)
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_metadata_preservation_complete(mock_engine_class, realistic_sec_filing_item):
    """Verify ALL ScoredItem fields are preserved in TradingSignal metadata."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_position = Mock()
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)
    mock_engine_class.return_value = mock_engine

    execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="NVDA",
        current_price=Decimal("875.50"),
        extended_hours=True,
    )

    # Get signal
    call_args = mock_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Verify EVERY field from ScoredItem is in metadata
    assert "relevance" in signal.metadata
    assert "sentiment" in signal.metadata
    assert "source_weight" in signal.metadata
    assert "tags" in signal.metadata
    assert "keyword_hits" in signal.metadata
    assert "enriched" in signal.metadata
    assert "enrichment_timestamp" in signal.metadata
    assert "extended_hours" in signal.metadata

    # Verify exact values
    assert signal.metadata["relevance"] == realistic_sec_filing_item.relevance
    assert signal.metadata["sentiment"] == realistic_sec_filing_item.sentiment
    assert signal.metadata["source_weight"] == realistic_sec_filing_item.source_weight
    assert signal.metadata["tags"] == realistic_sec_filing_item.tags
    assert signal.metadata["keyword_hits"] == realistic_sec_filing_item.keyword_hits
    assert signal.metadata["enriched"] == realistic_sec_filing_item.enriched
    assert signal.metadata["enrichment_timestamp"] == realistic_sec_filing_item.enrichment_timestamp


# ============================================================================
# Realistic SEC Filing Scenarios
# ============================================================================


@pytest.mark.parametrize(
    "filing_type,relevance,sentiment,expected_confidence_range",
    [
        ("8-K merger", 4.8, 0.85, (0.85, 1.0)),  # High confidence
        ("10-Q earnings beat", 4.5, 0.75, (0.80, 0.95)),  # High confidence
        ("8-K guidance raise", 4.6, 0.80, (0.82, 0.95)),  # High confidence
        ("SC 13D activist", 4.3, 0.70, (0.78, 0.92)),  # Good confidence
        ("10-K annual report", 3.5, 0.50, (0.65, 0.85)),  # Medium confidence
    ],
)
@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_realistic_sec_filing_scenarios(
    mock_engine_class,
    filing_type,
    relevance,
    sentiment,
    expected_confidence_range,
):
    """Test various realistic SEC filing scenarios with expected confidence levels."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_position = Mock()
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)
    mock_engine_class.return_value = mock_engine

    # Create ScoredItem for this filing type
    item = ScoredItem(
        relevance=relevance,
        sentiment=sentiment,
        tags=[filing_type, "sec_filing"],
        source_weight=1.5,  # SEC.gov is high credibility
        keyword_hits=[filing_type.split()[0]],
        enriched=True,
    )

    result = execute_with_trading_engine(
        item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    assert result is True

    # Get signal and verify confidence range
    call_args = mock_engine._execute_signal.call_args
    signal = call_args[0][0]

    min_conf, max_conf = expected_confidence_range
    assert min_conf <= signal.confidence <= max_conf, (
        f"{filing_type} confidence {signal.confidence:.2%} "
        f"not in expected range [{min_conf:.2%}, {max_conf:.2%}]"
    )


# ============================================================================
# Signal Quality Filtering Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_low_quality_signal_filtered(mock_engine_class):
    """Test that low-quality signals are filtered (don't reach TradingEngine)."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_engine._execute_signal = AsyncMock()
    mock_engine_class.return_value = mock_engine

    # Low quality item
    low_quality_item = ScoredItem(
        relevance=2.0,  # Low relevance
        sentiment=0.05,  # Neutral sentiment
        tags=["general_news"],
        source_weight=1.0,
        keyword_hits=["company"],
        enriched=False,
    )

    result = execute_with_trading_engine(
        item=low_quality_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Should be filtered
    assert result is False
    # TradingEngine should not be called
    mock_engine._execute_signal.assert_not_called()


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_neutral_sentiment_filtered(mock_engine_class):
    """Test that neutral sentiment (hold action) is filtered."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_engine_class.return_value = mock_engine

    # High relevance but neutral sentiment
    neutral_item = ScoredItem(
        relevance=4.5,  # High relevance
        sentiment=0.05,  # Neutral sentiment
        tags=["news"],
        source_weight=1.0,
        keyword_hits=["company", "stock"],
        enriched=True,
    )

    result = execute_with_trading_engine(
        item=neutral_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Should be filtered (no actionable signal)
    assert result is False


# ============================================================================
# Risk Management Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_risk_parameters_calculation(mock_engine_class, realistic_sec_filing_item):
    """Test that risk parameters (stop-loss, take-profit) are correctly calculated."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_position = Mock()
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)
    mock_engine_class.return_value = mock_engine

    entry_price = Decimal("100.00")

    execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="TEST",
        current_price=entry_price,
    )

    # Get signal
    call_args = mock_engine._execute_signal.call_args
    signal = call_args[0][0]

    # Verify risk parameters (default: 5% stop, 10% profit)
    expected_stop = entry_price * Decimal("0.95")
    expected_profit = entry_price * Decimal("1.10")

    assert signal.stop_loss_price == expected_stop
    assert signal.take_profit_price == expected_profit

    # Verify position sizing (3-5% based on confidence)
    assert 0.03 <= signal.position_size_pct <= 0.05


# ============================================================================
# Multiple Concurrent Signals Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_multiple_signals_different_tickers(mock_engine_class, realistic_sec_filing_item, earnings_beat_item):
    """Test executing multiple signals for different tickers."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)

    # Create different mock positions for each ticker
    def create_position(signal):
        pos = Mock()
        pos.position_id = f"pos_{signal.ticker}"
        pos.ticker = signal.ticker
        return pos

    mock_engine._execute_signal = AsyncMock(side_effect=lambda sig: create_position(sig))
    mock_engine_class.return_value = mock_engine

    # Execute multiple trades
    tickers_and_items = [
        ("NVDA", realistic_sec_filing_item, Decimal("875.50")),
        ("AAPL", earnings_beat_item, Decimal("175.50")),
        ("MSFT", realistic_sec_filing_item, Decimal("380.00")),
    ]

    results = []
    for ticker, item, price in tickers_and_items:
        result = execute_with_trading_engine(
            item=item,
            ticker=ticker,
            current_price=price,
        )
        results.append(result)

    # All should succeed
    assert all(results)

    # Should have executed 3 signals
    assert mock_engine._execute_signal.call_count == 3

    # Verify each signal had correct ticker
    calls = mock_engine._execute_signal.call_args_list
    executed_tickers = [call[0][0].ticker for call in calls]
    assert executed_tickers == ["NVDA", "AAPL", "MSFT"]


# ============================================================================
# Error Recovery Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_graceful_failure_handling(mock_engine_class, realistic_sec_filing_item):
    """Test graceful handling of TradingEngine failures."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)

    # First call succeeds
    mock_position = Mock()
    mock_position.position_id = "pos_success"

    # Second call fails (returns None)
    # Third call raises exception
    mock_engine._execute_signal = AsyncMock(
        side_effect=[
            mock_position,  # Success
            None,  # Failure (no position)
            Exception("Market closed"),  # Exception
        ]
    )
    mock_engine_class.return_value = mock_engine

    # Execute 3 trades
    result1 = execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    result2 = execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="MSFT",
        current_price=Decimal("350.00"),
    )

    result3 = execute_with_trading_engine(
        item=realistic_sec_filing_item,
        ticker="GOOGL",
        current_price=Decimal("140.00"),
    )

    # Verify results
    assert result1 is True  # Success
    assert result2 is False  # Failure (None returned)
    assert result3 is False  # Failure (exception handled)


# ============================================================================
# Confidence Calculation Integration Tests
# ============================================================================


def test_confidence_calculation_integration():
    """Test confidence calculation across the full integration."""
    adapter = SignalAdapter()

    # Test case 1: High relevance + high sentiment = high confidence
    high_item = ScoredItem(
        relevance=4.8,
        sentiment=0.85,
        tags=["catalyst"],
        source_weight=1.5,
        keyword_hits=["merger"],
    )

    signal_high = adapter.from_scored_item(
        scored_item=high_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    assert signal_high is not None
    assert signal_high.confidence > 0.85

    # Test case 2: Medium relevance + medium sentiment = medium confidence
    medium_item = ScoredItem(
        relevance=3.5,
        sentiment=0.50,
        tags=["news"],
        source_weight=1.0,
        keyword_hits=["company"],
    )

    signal_medium = adapter.from_scored_item(
        scored_item=medium_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    assert signal_medium is not None
    assert 0.60 <= signal_medium.confidence <= 0.80

    # Test case 3: Low relevance + low sentiment = low confidence (filtered)
    low_item = ScoredItem(
        relevance=2.0,
        sentiment=0.1,
        tags=["general"],
        source_weight=1.0,
        keyword_hits=["stock"],
    )

    signal_low = adapter.from_scored_item(
        scored_item=low_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Should be filtered (below 60% threshold or neutral sentiment)
    assert signal_low is None


# ============================================================================
# Position Sizing Integration Tests
# ============================================================================


@patch("catalyst_bot.trading.trading_engine.TradingEngine")
def test_position_sizing_based_on_confidence(mock_engine_class):
    """Test that position size scales with confidence level."""
    mock_engine = Mock()
    mock_engine.initialize = AsyncMock(return_value=True)
    mock_position = Mock()
    mock_engine._execute_signal = AsyncMock(return_value=mock_position)
    mock_engine_class.return_value = mock_engine

    # High confidence item
    high_conf_item = ScoredItem(
        relevance=4.8,
        sentiment=0.85,
        tags=["catalyst"],
        source_weight=1.5,
        keyword_hits=["merger"],
    )

    # Medium confidence item
    medium_conf_item = ScoredItem(
        relevance=3.5,
        sentiment=0.50,
        tags=["news"],
        source_weight=1.0,
        keyword_hits=["company"],
    )

    # Execute both
    execute_with_trading_engine(
        item=high_conf_item,
        ticker="HIGH",
        current_price=Decimal("100.00"),
    )

    execute_with_trading_engine(
        item=medium_conf_item,
        ticker="MED",
        current_price=Decimal("100.00"),
    )

    # Get signals
    calls = mock_engine._execute_signal.call_args_list
    signal_high = calls[0][0][0]
    signal_medium = calls[1][0][0]

    # High confidence should have larger position size
    assert signal_high.position_size_pct >= signal_medium.position_size_pct
    # Both should be within valid range (3-5%)
    assert 0.03 <= signal_high.position_size_pct <= 0.05
    assert 0.03 <= signal_medium.position_size_pct <= 0.05
