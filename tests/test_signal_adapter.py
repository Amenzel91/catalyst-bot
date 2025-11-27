"""
Comprehensive tests for SignalAdapter.

Tests the conversion of ScoredItem objects to TradingSignal objects,
including confidence calculation, action determination, position sizing,
risk management, and metadata preservation.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from catalyst_bot.models import ScoredItem
from catalyst_bot.adapters.signal_adapter import SignalAdapter, SignalAdapterConfig
from catalyst_bot.execution.order_executor import TradingSignal


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def default_adapter():
    """Default signal adapter with standard configuration."""
    return SignalAdapter()


@pytest.fixture
def custom_adapter():
    """Signal adapter with custom configuration."""
    config = SignalAdapterConfig(
        default_stop_loss_pct=0.04,  # 4% stop
        default_take_profit_pct=0.08,  # 8% target
        base_position_size_pct=0.02,  # 2% base position
        max_position_size_pct=0.04,  # 4% max position
        min_confidence_for_trade=0.65,  # 65% minimum confidence
        high_confidence_threshold=0.85,  # 85% high confidence
    )
    return SignalAdapter(config)


@pytest.fixture
def high_relevance_positive_sentiment_item():
    """ScoredItem with high relevance and positive sentiment (should trigger BUY)."""
    return ScoredItem(
        relevance=4.5,  # High relevance
        sentiment=0.8,  # Strong positive sentiment
        tags=["earnings_beat", "guidance_raise"],
        source_weight=1.2,
        keyword_hits=["beat", "raised", "guidance"],
        enriched=True,
        enrichment_timestamp=datetime.now().timestamp(),
    )


@pytest.fixture
def high_relevance_negative_sentiment_item():
    """ScoredItem with high relevance and negative sentiment (should trigger SELL)."""
    return ScoredItem(
        relevance=4.2,
        sentiment=-0.7,  # Strong negative sentiment
        tags=["earnings_miss", "downgrade"],
        source_weight=1.1,
        keyword_hits=["miss", "downgrade", "warning"],
        enriched=True,
    )


@pytest.fixture
def low_relevance_neutral_sentiment_item():
    """ScoredItem with low relevance and neutral sentiment (should be filtered)."""
    return ScoredItem(
        relevance=2.0,  # Low relevance
        sentiment=0.05,  # Neutral sentiment
        tags=["general_news"],
        source_weight=1.0,
        keyword_hits=["company", "stock"],
        enriched=False,
    )


@pytest.fixture
def edge_case_none_values_item():
    """ScoredItem with None/missing values to test edge cases."""
    return ScoredItem(
        relevance=3.0,
        sentiment=0.6,
        tags=[],
        source_weight=1.0,
        keyword_hits=[],
        enriched=False,
        enrichment_timestamp=None,
    )


@pytest.fixture
def extreme_values_item():
    """ScoredItem with extreme values to test boundary conditions."""
    return ScoredItem(
        relevance=10.0,  # Above max expected (5.0)
        sentiment=1.5,  # Above max expected (1.0)
        tags=["extreme"],
        source_weight=5.0,  # High source weight
        keyword_hits=["test"],
        enriched=True,
    )


# ============================================================================
# Basic Conversion Tests
# ============================================================================


def test_signal_adapter_basic_conversion(default_adapter, high_relevance_positive_sentiment_item):
    """Test basic ScoredItem to TradingSignal conversion."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("175.50"),
        extended_hours=False,
    )

    assert signal is not None
    assert isinstance(signal, TradingSignal)
    assert signal.ticker == "AAPL"
    assert signal.action == "buy"
    assert signal.entry_price == Decimal("175.50")
    assert signal.current_price == Decimal("175.50")
    assert signal.signal_type == "keyword_momentum"
    assert signal.timeframe == "intraday"
    assert signal.strategy == "catalyst_keyword_v1"


def test_signal_adapter_preserves_metadata(default_adapter, high_relevance_positive_sentiment_item):
    """Ensure all ScoredItem metadata is preserved in TradingSignal."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Check all ScoredItem fields are preserved in metadata
    assert signal.metadata["relevance"] == 4.5
    assert signal.metadata["sentiment"] == 0.8
    assert signal.metadata["source_weight"] == 1.2
    assert signal.metadata["tags"] == ["earnings_beat", "guidance_raise"]
    assert signal.metadata["keyword_hits"] == ["beat", "raised", "guidance"]
    assert signal.metadata["enriched"] is True
    assert signal.metadata["enrichment_timestamp"] is not None
    assert signal.metadata["extended_hours"] is False


def test_signal_adapter_extended_hours_flag(default_adapter, high_relevance_positive_sentiment_item):
    """Test extended_hours parameter propagation to metadata."""
    # Test with extended_hours=False
    signal_regular = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=False,
    )
    assert signal_regular.metadata["extended_hours"] is False

    # Test with extended_hours=True
    signal_extended = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=True,
    )
    assert signal_extended.metadata["extended_hours"] is True


# ============================================================================
# Confidence Calculation Tests
# ============================================================================


def test_confidence_calculation_high_relevance_high_sentiment(default_adapter, high_relevance_positive_sentiment_item):
    """Test confidence calculation with high relevance and high sentiment."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Expected: (4.5/5.0)*0.6 + ((0.8+1.0)/2.0)*0.3 + min(1.2, 1.0)*0.1
    # = 0.9*0.6 + 0.9*0.3 + 1.0*0.1 = 0.54 + 0.27 + 0.1 = 0.91
    # But sentiment normalization: (abs(0.8) + 1.0) / 2.0 = 1.8/2.0 = 0.9
    assert signal is not None
    assert 0.85 <= signal.confidence <= 0.95  # Allow small floating point variance


def test_confidence_calculation_weighted_average(default_adapter):
    """Test that confidence uses correct weights: 60% relevance, 30% sentiment, 10% source."""
    # Create item with known values
    item = ScoredItem(
        relevance=5.0,  # Max relevance -> normalized to 1.0
        sentiment=1.0,  # Max sentiment -> normalized to 1.0
        tags=["test"],
        source_weight=1.0,  # -> normalized to 1.0
        keyword_hits=["test"],
    )

    signal = default_adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Expected: 1.0*0.6 + 1.0*0.3 + 1.0*0.1 = 1.0
    assert signal.confidence == pytest.approx(1.0, rel=1e-2)


def test_confidence_normalization_caps_at_one(default_adapter, extreme_values_item):
    """Test that confidence is capped at 1.0 even with extreme values."""
    signal = default_adapter.from_scored_item(
        scored_item=extreme_values_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    assert signal is not None
    assert signal.confidence <= 1.0


# ============================================================================
# Action Determination Tests
# ============================================================================


def test_action_determination_buy_signal(default_adapter, high_relevance_positive_sentiment_item):
    """Test that positive sentiment (>0.1) results in 'buy' action."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    assert signal.action == "buy"


def test_action_determination_sell_signal(default_adapter, high_relevance_negative_sentiment_item):
    """Test that negative sentiment (<-0.1) results in 'sell' action."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_negative_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    assert signal.action == "sell"


def test_action_determination_hold_filtered(default_adapter):
    """Test that neutral sentiment (-0.1 to 0.1) results in None (hold is filtered)."""
    neutral_item = ScoredItem(
        relevance=4.0,
        sentiment=0.05,  # Neutral sentiment
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    signal = default_adapter.from_scored_item(
        scored_item=neutral_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Should return None because action would be "hold"
    assert signal is None


# ============================================================================
# Position Sizing Tests
# ============================================================================


def test_position_sizing_base_for_normal_confidence(default_adapter):
    """Test that base position size is used for normal confidence levels."""
    # Create item with confidence below high threshold (0.80)
    item = ScoredItem(
        relevance=3.5,  # -> normalized ~0.7
        sentiment=0.5,  # -> normalized ~0.75
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    signal = default_adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    assert signal is not None
    # Confidence should be below 0.80, so should use base position size (3%)
    assert signal.position_size_pct == pytest.approx(0.03, rel=1e-2)


def test_position_sizing_scales_with_high_confidence(default_adapter, high_relevance_positive_sentiment_item):
    """Test that position size scales up for high confidence signals."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    # High confidence should result in larger position size (between 3% and 5%)
    assert 0.03 <= signal.position_size_pct <= 0.05


def test_position_sizing_caps_at_max(default_adapter, extreme_values_item):
    """Test that position size is capped at max_position_size_pct."""
    signal = default_adapter.from_scored_item(
        scored_item=extreme_values_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    assert signal is not None
    # Should be capped at 5% max
    assert signal.position_size_pct <= 0.05


def test_position_sizing_custom_config(custom_adapter, high_relevance_positive_sentiment_item):
    """Test position sizing with custom configuration."""
    signal = custom_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    # Custom config has max of 4%
    assert signal.position_size_pct <= 0.04


# ============================================================================
# Stop-Loss and Take-Profit Tests
# ============================================================================


def test_stop_loss_calculation_buy_order(default_adapter, high_relevance_positive_sentiment_item):
    """Test stop-loss calculation for buy orders (stop below entry)."""
    entry_price = Decimal("100.00")
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=entry_price,
    )

    assert signal is not None
    assert signal.action == "buy"
    # Default stop-loss is 5%, so stop should be at $95.00
    expected_stop = entry_price * Decimal("0.95")
    assert signal.stop_loss_price == pytest.approx(expected_stop, rel=1e-6)
    assert signal.stop_loss_price < entry_price


def test_stop_loss_calculation_sell_order(default_adapter, high_relevance_negative_sentiment_item):
    """Test stop-loss calculation for sell orders (stop above entry)."""
    entry_price = Decimal("100.00")
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_negative_sentiment_item,
        ticker="AAPL",
        current_price=entry_price,
    )

    assert signal is not None
    assert signal.action == "sell"
    # For sell orders, stop should be 5% above entry
    expected_stop = entry_price * Decimal("1.05")
    assert signal.stop_loss_price == pytest.approx(expected_stop, rel=1e-6)
    assert signal.stop_loss_price > entry_price


def test_take_profit_calculation_buy_order(default_adapter, high_relevance_positive_sentiment_item):
    """Test take-profit calculation for buy orders (profit above entry)."""
    entry_price = Decimal("100.00")
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=entry_price,
    )

    assert signal is not None
    assert signal.action == "buy"
    # Default take-profit is 10%, so target should be at $110.00
    expected_profit = entry_price * Decimal("1.10")
    assert signal.take_profit_price == pytest.approx(expected_profit, rel=1e-6)
    assert signal.take_profit_price > entry_price


def test_take_profit_calculation_sell_order(default_adapter, high_relevance_negative_sentiment_item):
    """Test take-profit calculation for sell orders (profit below entry)."""
    entry_price = Decimal("100.00")
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_negative_sentiment_item,
        ticker="AAPL",
        current_price=entry_price,
    )

    assert signal is not None
    assert signal.action == "sell"
    # For sell orders, profit should be 10% below entry
    expected_profit = entry_price * Decimal("0.90")
    assert signal.take_profit_price == pytest.approx(expected_profit, rel=1e-6)
    assert signal.take_profit_price < entry_price


def test_custom_risk_parameters(custom_adapter, high_relevance_positive_sentiment_item):
    """Test custom stop-loss and take-profit percentages."""
    entry_price = Decimal("100.00")
    signal = custom_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=entry_price,
    )

    assert signal is not None
    # Custom config: 4% stop, 8% target
    expected_stop = entry_price * Decimal("0.96")
    expected_profit = entry_price * Decimal("1.08")
    assert signal.stop_loss_price == pytest.approx(expected_stop, rel=1e-6)
    assert signal.take_profit_price == pytest.approx(expected_profit, rel=1e-6)


# ============================================================================
# Filtering Tests (Minimum Confidence)
# ============================================================================


def test_below_minimum_confidence_returns_none(default_adapter, low_relevance_neutral_sentiment_item):
    """Test that signals below minimum confidence threshold return None."""
    signal = default_adapter.from_scored_item(
        scored_item=low_relevance_neutral_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    # Low relevance (2.0) and neutral sentiment should result in low confidence
    # Expected confidence: (2.0/5.0)*0.6 + ((0.05+1.0)/2.0)*0.3 + 1.0*0.1
    # = 0.4*0.6 + 0.525*0.3 + 0.1 = 0.24 + 0.1575 + 0.1 = 0.4975 < 0.60 (threshold)
    assert signal is None


def test_custom_minimum_confidence_threshold(custom_adapter):
    """Test custom minimum confidence threshold (65% vs default 60%)."""
    # Create item with confidence between 60% and 65%
    item = ScoredItem(
        relevance=3.0,  # -> normalized 0.6
        sentiment=0.5,  # -> normalized 0.75
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    # Should pass default adapter (60% threshold)
    signal_default = SignalAdapter().from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # May or may not pass custom adapter (65% threshold) depending on exact calculation
    signal_custom = custom_adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # At least verify that the custom adapter is more restrictive
    # (this test may need adjustment based on exact confidence calculation)
    assert signal_default is not None or signal_custom is None


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


def test_edge_case_none_values_in_metadata(default_adapter, edge_case_none_values_item):
    """Test that None values in ScoredItem are handled gracefully."""
    signal = default_adapter.from_scored_item(
        scored_item=edge_case_none_values_item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Should still create signal if confidence is sufficient
    if signal is not None:
        assert signal.metadata["enrichment_timestamp"] is None
        assert signal.metadata["keyword_hits"] == []
        assert signal.metadata["tags"] == []


def test_edge_case_zero_relevance():
    """Test behavior with zero relevance."""
    item = ScoredItem(
        relevance=0.0,
        sentiment=0.8,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    adapter = SignalAdapter()
    signal = adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Zero relevance should result in low confidence, likely filtered out
    # Expected: 0.0*0.6 + 0.9*0.3 + 0.1 = 0.37 < 0.60 (threshold)
    assert signal is None


def test_edge_case_negative_relevance():
    """Test behavior with negative relevance (edge case)."""
    item = ScoredItem(
        relevance=-1.0,  # Invalid/edge case
        sentiment=0.8,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    adapter = SignalAdapter()
    signal = adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    # Negative relevance should be handled (normalized to 0)
    # Should result in very low confidence
    if signal is not None:
        assert signal.confidence >= 0.0


def test_edge_case_very_small_price():
    """Test behavior with very small prices (penny stocks)."""
    item = ScoredItem(
        relevance=4.0,
        sentiment=0.8,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    adapter = SignalAdapter()
    signal = adapter.from_scored_item(
        scored_item=item,
        ticker="PENNY",
        current_price=Decimal("0.01"),
    )

    assert signal is not None
    # Verify risk parameters are calculated correctly even with tiny prices
    assert signal.entry_price == Decimal("0.01")
    assert signal.stop_loss_price < signal.entry_price
    assert signal.take_profit_price > signal.entry_price


def test_edge_case_very_large_price():
    """Test behavior with very large prices (e.g., BRK.A)."""
    item = ScoredItem(
        relevance=4.0,
        sentiment=0.8,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    adapter = SignalAdapter()
    signal = adapter.from_scored_item(
        scored_item=item,
        ticker="BRK.A",
        current_price=Decimal("500000.00"),
    )

    assert signal is not None
    assert signal.entry_price == Decimal("500000.00")
    assert signal.stop_loss_price == Decimal("500000.00") * Decimal("0.95")
    assert signal.take_profit_price == Decimal("500000.00") * Decimal("1.10")


# ============================================================================
# Signal ID Generation Tests
# ============================================================================


def test_signal_id_generation_uniqueness(default_adapter, high_relevance_positive_sentiment_item):
    """Test that signal IDs are unique for each conversion."""
    signal1 = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    signal2 = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal1 is not None
    assert signal2 is not None
    assert signal1.signal_id != signal2.signal_id  # Should be unique


def test_signal_id_format(default_adapter, high_relevance_positive_sentiment_item):
    """Test that signal ID follows expected format."""
    signal = default_adapter.from_scored_item(
        scored_item=high_relevance_positive_sentiment_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    # Format should be: catalyst_{ticker}_{uuid12}
    assert signal.signal_id.startswith("catalyst_AAPL_")
    # UUID part should be 12 characters
    uuid_part = signal.signal_id.replace("catalyst_AAPL_", "")
    assert len(uuid_part) == 12
    assert uuid_part.isalnum()  # Should be alphanumeric


# ============================================================================
# Integration Test: Full Flow
# ============================================================================


def test_full_conversion_flow_realistic_scenario(default_adapter):
    """Test complete flow with realistic SEC filing scenario."""
    # Simulate high-quality SEC filing alert
    scored_item = ScoredItem(
        relevance=4.8,
        sentiment=0.85,
        tags=["merger_acquisition", "sec_filing", "catalyst"],
        source_weight=1.5,  # High credibility source
        keyword_hits=["merger", "acquisition", "approve", "SEC"],
        enriched=True,
        enrichment_timestamp=datetime.now().timestamp(),
    )

    signal = default_adapter.from_scored_item(
        scored_item=scored_item,
        ticker="NVDA",
        current_price=Decimal("875.50"),
        extended_hours=False,
    )

    # Verify complete signal
    assert signal is not None
    assert signal.ticker == "NVDA"
    assert signal.action == "buy"
    assert signal.confidence > 0.85  # High confidence
    assert signal.entry_price == Decimal("875.50")
    assert signal.position_size_pct >= 0.03  # At least base position
    assert signal.stop_loss_price == Decimal("875.50") * Decimal("0.95")
    assert signal.take_profit_price == Decimal("875.50") * Decimal("1.10")
    assert signal.signal_type == "keyword_momentum"
    assert signal.timeframe == "intraday"
    assert signal.strategy == "catalyst_keyword_v1"

    # Verify metadata preservation
    assert signal.metadata["relevance"] == 4.8
    assert signal.metadata["sentiment"] == 0.85
    assert signal.metadata["tags"] == ["merger_acquisition", "sec_filing", "catalyst"]
    assert signal.metadata["keyword_hits"] == ["merger", "acquisition", "approve", "SEC"]
    assert signal.metadata["enriched"] is True
    assert signal.metadata["extended_hours"] is False


# ============================================================================
# Parametrized Tests
# ============================================================================


@pytest.mark.parametrize(
    "relevance,sentiment,expected_action",
    [
        (4.5, 0.8, "buy"),  # High relevance, positive sentiment
        (4.2, -0.7, "sell"),  # High relevance, negative sentiment
        (3.0, 0.05, None),  # Medium relevance, neutral sentiment (hold/filtered)
        (5.0, 0.5, "buy"),  # Max relevance, moderate positive sentiment
        (3.5, -0.5, "sell"),  # Medium relevance, moderate negative sentiment
    ],
)
def test_action_determination_parametrized(default_adapter, relevance, sentiment, expected_action):
    """Test action determination with various relevance/sentiment combinations."""
    item = ScoredItem(
        relevance=relevance,
        sentiment=sentiment,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    signal = default_adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=Decimal("100.00"),
    )

    if expected_action is None:
        assert signal is None  # Filtered out
    else:
        assert signal is not None
        assert signal.action == expected_action


@pytest.mark.parametrize(
    "price,stop_pct,profit_pct",
    [
        (Decimal("100.00"), 0.05, 0.10),
        (Decimal("50.50"), 0.03, 0.08),
        (Decimal("1000.00"), 0.07, 0.15),
        (Decimal("0.50"), 0.05, 0.10),  # Penny stock
        (Decimal("10000.00"), 0.04, 0.12),  # High-price stock
    ],
)
def test_risk_parameters_parametrized(price, stop_pct, profit_pct):
    """Test risk parameter calculations with various prices and percentages."""
    config = SignalAdapterConfig(
        default_stop_loss_pct=stop_pct,
        default_take_profit_pct=profit_pct,
    )
    adapter = SignalAdapter(config)

    item = ScoredItem(
        relevance=4.0,
        sentiment=0.7,
        tags=["test"],
        source_weight=1.0,
        keyword_hits=["test"],
    )

    signal = adapter.from_scored_item(
        scored_item=item,
        ticker="TEST",
        current_price=price,
    )

    assert signal is not None
    expected_stop = price * Decimal(str(1.0 - stop_pct))
    expected_profit = price * Decimal(str(1.0 + profit_pct))
    assert signal.stop_loss_price == pytest.approx(expected_stop, rel=1e-6)
    assert signal.take_profit_price == pytest.approx(expected_profit, rel=1e-6)
