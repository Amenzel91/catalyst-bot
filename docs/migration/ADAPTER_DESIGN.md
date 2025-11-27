# SignalAdapter Design Specification

## Overview

The `SignalAdapter` converts `ScoredItem` objects from the classification system into `TradingSignal` objects consumable by the `TradingEngine`. This adapter serves as the integration layer between the existing keyword-based alert system and the new paper trading infrastructure.

## Design Principles

1. **Zero Data Loss**: All meaningful data from `ScoredItem` must be preserved in the `TradingSignal`
2. **Clean Separation**: Adapter should have no dependencies on broker or execution logic
3. **Extended Hours Support**: Preserve and propagate extended hours trading parameters
4. **Configurable Risk**: Support default stop-loss and take-profit calculations
5. **Testability**: Pure function design for easy unit testing

## Class Design

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
from uuid import uuid4

from catalyst_bot.classify import ScoredItem
from catalyst_bot.execution.order_executor import TradingSignal


@dataclass
class SignalAdapterConfig:
    """Configuration for signal adapter risk defaults."""

    # Stop-loss defaults (as percentage from entry)
    default_stop_loss_pct: float = 0.05  # 5% stop-loss

    # Take-profit defaults (as percentage from entry)
    default_take_profit_pct: float = 0.10  # 10% take-profit

    # Position sizing
    base_position_size_pct: float = 0.03  # 3% of portfolio
    max_position_size_pct: float = 0.05   # 5% of portfolio

    # Confidence thresholds
    min_confidence_for_trade: float = 0.60  # Minimum 60% confidence
    high_confidence_threshold: float = 0.80  # Above 80% increases position size


class SignalAdapter:
    """
    Converts ScoredItem (alert data) to TradingSignal (trading data).

    This adapter bridges the classification system and trading engine,
    translating keyword-based scoring into actionable trading signals
    with appropriate risk management parameters.
    """

    def __init__(self, config: Optional[SignalAdapterConfig] = None):
        """
        Initialize signal adapter with configuration.

        Args:
            config: Adapter configuration (uses defaults if None)
        """
        self.config = config or SignalAdapterConfig()

    def from_scored_item(
        self,
        scored_item: ScoredItem,
        ticker: str,
        current_price: Decimal,
        extended_hours: bool = False,
    ) -> Optional[TradingSignal]:
        """
        Convert ScoredItem to TradingSignal with risk parameters.

        Args:
            scored_item: Scored item from classification system
            ticker: Stock ticker symbol (uppercase)
            current_price: Current market price
            extended_hours: Whether to enable extended hours trading

        Returns:
            TradingSignal if actionable, None if below thresholds
        """
        # Calculate confidence from scored item
        confidence = self._calculate_confidence(scored_item)

        # Check minimum confidence threshold
        if confidence < self.config.min_confidence_for_trade:
            return None

        # Determine trading action from sentiment
        action = self._determine_action(scored_item.sentiment)

        # Skip if action is "hold"
        if action == "hold":
            return None

        # Calculate position size based on confidence
        position_size_pct = self._calculate_position_size(confidence)

        # Calculate stop-loss and take-profit prices
        stop_loss_price = self._calculate_stop_loss(
            current_price,
            action,
            self.config.default_stop_loss_pct
        )
        take_profit_price = self._calculate_take_profit(
            current_price,
            action,
            self.config.default_take_profit_pct
        )

        # Generate unique signal ID
        signal_id = f"catalyst_{ticker}_{uuid4().hex[:12]}"

        # Build metadata preserving all ScoredItem data
        metadata = {
            "relevance": scored_item.relevance,
            "sentiment": scored_item.sentiment,
            "source_weight": scored_item.source_weight,
            "tags": scored_item.tags,
            "keyword_hits": scored_item.keyword_hits,
            "enriched": scored_item.enriched,
            "enrichment_timestamp": scored_item.enrichment_timestamp,
            "extended_hours": extended_hours,
        }

        # Create trading signal
        return TradingSignal(
            signal_id=signal_id,
            ticker=ticker,
            timestamp=datetime.now(),
            action=action,
            confidence=confidence,
            entry_price=current_price,
            current_price=current_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            position_size_pct=position_size_pct,
            signal_type="keyword_momentum",
            timeframe="intraday",
            strategy="catalyst_keyword_v1",
            metadata=metadata,
        )

    def _calculate_confidence(self, scored_item: ScoredItem) -> float:
        """
        Calculate trading confidence from scored item.

        Combines relevance score, sentiment, and source weight.

        Args:
            scored_item: Scored item data

        Returns:
            Confidence value between 0.0 and 1.0
        """
        # Normalize relevance to 0-1 range (assume max relevance is 5.0)
        normalized_relevance = min(scored_item.relevance / 5.0, 1.0)

        # Normalize sentiment to 0-1 range (sentiment is -1 to +1)
        normalized_sentiment = (abs(scored_item.sentiment) + 1.0) / 2.0

        # Combine factors (weighted average)
        confidence = (
            normalized_relevance * 0.60 +      # 60% weight on relevance
            normalized_sentiment * 0.30 +       # 30% weight on sentiment strength
            min(scored_item.source_weight, 1.0) * 0.10  # 10% weight on source
        )

        return min(confidence, 1.0)

    def _determine_action(self, sentiment: float) -> str:
        """
        Determine trading action from sentiment.

        Args:
            sentiment: Sentiment score (-1.0 to +1.0)

        Returns:
            Action: "buy", "sell", or "hold"
        """
        # Positive sentiment = buy signal
        if sentiment > 0.1:
            return "buy"

        # Negative sentiment = sell signal (short)
        elif sentiment < -0.1:
            return "sell"

        # Neutral sentiment = no action
        else:
            return "hold"

    def _calculate_position_size(self, confidence: float) -> float:
        """
        Calculate position size based on confidence.

        Args:
            confidence: Confidence level (0.0 to 1.0)

        Returns:
            Position size as percentage of portfolio
        """
        # Base position size
        position_size = self.config.base_position_size_pct

        # Increase for high confidence signals
        if confidence >= self.config.high_confidence_threshold:
            # Scale up to max position size for very high confidence
            confidence_factor = (confidence - self.config.high_confidence_threshold) / (1.0 - self.config.high_confidence_threshold)
            position_size = self.config.base_position_size_pct + (
                (self.config.max_position_size_pct - self.config.base_position_size_pct) * confidence_factor
            )

        return min(position_size, self.config.max_position_size_pct)

    def _calculate_stop_loss(
        self,
        entry_price: Decimal,
        action: str,
        stop_pct: float
    ) -> Decimal:
        """
        Calculate stop-loss price.

        Args:
            entry_price: Entry price
            action: Trading action ("buy" or "sell")
            stop_pct: Stop-loss percentage

        Returns:
            Stop-loss price
        """
        if action == "buy":
            # For long positions, stop below entry
            return entry_price * Decimal(str(1.0 - stop_pct))
        else:
            # For short positions, stop above entry
            return entry_price * Decimal(str(1.0 + stop_pct))

    def _calculate_take_profit(
        self,
        entry_price: Decimal,
        action: str,
        profit_pct: float
    ) -> Decimal:
        """
        Calculate take-profit price.

        Args:
            entry_price: Entry price
            action: Trading action ("buy" or "sell")
            profit_pct: Take-profit percentage

        Returns:
            Take-profit price
        """
        if action == "buy":
            # For long positions, profit above entry
            return entry_price * Decimal(str(1.0 + profit_pct))
        else:
            # For short positions, profit below entry
            return entry_price * Decimal(str(1.0 - profit_pct))
```

## Field Mapping Table

| ScoredItem Field | TradingSignal Field | Transformation |
|-----------------|---------------------|----------------|
| `relevance` | `metadata['relevance']` | Direct copy (preserved) |
| `sentiment` | `metadata['sentiment']` | Direct copy (preserved) |
| `sentiment` | `action` | Mapped: >0.1→"buy", <-0.1→"sell", else→"hold" |
| `sentiment` | `confidence` | Contributes 30% to confidence calculation |
| `tags` | `metadata['tags']` | Direct copy (preserved) |
| `source_weight` | `metadata['source_weight']` | Direct copy + contributes 10% to confidence |
| `keyword_hits` | `metadata['keyword_hits']` | Direct copy (preserved) |
| `enriched` | `metadata['enriched']` | Direct copy (preserved) |
| `enrichment_timestamp` | `metadata['enrichment_timestamp']` | Direct copy (preserved) |
| N/A (parameter) | `ticker` | Passed as method parameter |
| N/A (parameter) | `current_price` | Passed as method parameter |
| N/A (parameter) | `metadata['extended_hours']` | Passed as method parameter |
| N/A (generated) | `signal_id` | Generated: `catalyst_{ticker}_{uuid12}` |
| N/A (generated) | `timestamp` | Generated: `datetime.now()` |
| N/A (calculated) | `stop_loss_price` | Calculated: entry ± (entry × stop_pct) |
| N/A (calculated) | `take_profit_price` | Calculated: entry ± (entry × profit_pct) |
| N/A (calculated) | `position_size_pct` | Calculated: 3-5% based on confidence |
| N/A (constant) | `signal_type` | Constant: "keyword_momentum" |
| N/A (constant) | `timeframe` | Constant: "intraday" |
| N/A (constant) | `strategy` | Constant: "catalyst_keyword_v1" |

## Example Usage

```python
from decimal import Decimal
from catalyst_bot.classify import ScoredItem
from catalyst_bot.trading.signal_adapter import SignalAdapter, SignalAdapterConfig

# Configure adapter with custom risk parameters
config = SignalAdapterConfig(
    default_stop_loss_pct=0.04,      # 4% stop
    default_take_profit_pct=0.08,    # 8% target
    min_confidence_for_trade=0.65,   # 65% minimum
)
adapter = SignalAdapter(config)

# Create scored item from classification system
scored_item = ScoredItem(
    relevance=3.5,
    sentiment=0.75,
    tags=["earnings_beat", "guidance_raise"],
    source_weight=1.2,
    keyword_hits=["beat", "raised", "guidance"],
    enriched=True,
)

# Convert to trading signal
signal = adapter.from_scored_item(
    scored_item=scored_item,
    ticker="AAPL",
    current_price=Decimal("175.50"),
    extended_hours=False,
)

if signal:
    print(f"Signal: {signal.action} {signal.ticker}")
    print(f"Confidence: {signal.confidence:.2%}")
    print(f"Entry: ${signal.entry_price}")
    print(f"Stop: ${signal.stop_loss_price}")
    print(f"Target: ${signal.take_profit_price}")
    print(f"Position Size: {signal.position_size_pct:.1%}")
else:
    print("No actionable signal (below thresholds)")
```

## Integration Points

### 1. TradingEngine Integration
```python
# In trading_engine.py
from catalyst_bot.trading.signal_adapter import SignalAdapter

class TradingEngine:
    def __init__(self, config):
        # ... existing code ...
        self.signal_adapter = SignalAdapter()

    async def process_scored_item(
        self,
        scored_item: ScoredItem,
        ticker: str,
        current_price: Decimal,
    ) -> Optional[str]:
        # Convert to signal
        signal = self.signal_adapter.from_scored_item(
            scored_item=scored_item,
            ticker=ticker,
            current_price=current_price,
            extended_hours=is_extended_hours(),
        )

        if not signal:
            return None

        # Execute signal (existing logic)
        position = await self._execute_signal(signal)
        return position.position_id if position else None
```

### 2. Runner.py Integration
```python
# In runner.py - no changes needed!
# TradingEngine.process_scored_item() already accepts ScoredItem
await trading_engine.process_scored_item(
    scored_item=scored_item,
    ticker=ticker,
    current_price=current_price,
)
```

## Testing Strategy

```python
# tests/test_signal_adapter.py
def test_high_confidence_signal():
    """Test high confidence positive signal conversion."""
    adapter = SignalAdapter()
    scored_item = ScoredItem(
        relevance=4.5,
        sentiment=0.85,
        tags=["catalyst"],
        source_weight=1.0,
        keyword_hits=["beat", "raised"],
    )

    signal = adapter.from_scored_item(
        scored_item=scored_item,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    assert signal.action == "buy"
    assert signal.confidence > 0.80
    assert signal.stop_loss_price < Decimal("150.00")
    assert signal.take_profit_price > Decimal("150.00")
    assert "relevance" in signal.metadata
```

## Implementation Checklist

- [ ] Create `src/catalyst_bot/trading/signal_adapter.py`
- [ ] Implement `SignalAdapterConfig` dataclass
- [ ] Implement `SignalAdapter` class
- [ ] Add unit tests in `tests/test_signal_adapter.py`
- [ ] Integrate into `TradingEngine._generate_signal_stub()`
- [ ] Test with extended hours parameter
- [ ] Verify all ScoredItem fields preserved in metadata
- [ ] Document in MASTER-ROADMAP-paper-trading-bot.md
