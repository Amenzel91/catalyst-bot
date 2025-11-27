"""
Signal Adapter Module

Converts ScoredItem objects from the classification system into TradingSignal
objects consumable by the TradingEngine. This adapter serves as the integration
layer between the keyword-based alert system and the paper trading infrastructure.

Design Principles:
- Zero Data Loss: All meaningful data from ScoredItem is preserved
- Clean Separation: No dependencies on broker or execution logic
- Extended Hours Support: Preserves and propagates extended hours parameters
- Configurable Risk: Supports default stop-loss and take-profit calculations
- Testability: Pure function design for easy unit testing
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
from uuid import uuid4

from ..models import ScoredItem
from ..execution.order_executor import TradingSignal
from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class SignalAdapterConfig:
    """Configuration for signal adapter risk defaults."""

    # Stop-loss defaults (as percentage from entry)
    default_stop_loss_pct: float = 0.05  # 5% stop-loss

    # Take-profit defaults (as percentage from entry)
    default_take_profit_pct: float = 0.10  # 10% take-profit

    # Position sizing
    base_position_size_pct: float = 0.03  # 3% of portfolio
    max_position_size_pct: float = 0.05  # 5% of portfolio

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
        self.logger = get_logger(__name__)

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
            self.logger.debug(
                f"Signal for {ticker} below minimum confidence threshold: "
                f"{confidence:.2%} < {self.config.min_confidence_for_trade:.2%}"
            )
            return None

        # Determine trading action from sentiment
        action = self._determine_action(scored_item.sentiment)

        # Skip if action is "hold"
        if action == "hold":
            self.logger.debug(
                f"Signal for {ticker} resulted in 'hold' action (sentiment: {scored_item.sentiment:.2f})"
            )
            return None

        # Calculate position size based on confidence
        position_size_pct = self._calculate_position_size(confidence)

        # Calculate stop-loss and take-profit prices
        stop_loss_price = self._calculate_stop_loss(
            current_price, action, self.config.default_stop_loss_pct
        )
        take_profit_price = self._calculate_take_profit(
            current_price, action, self.config.default_take_profit_pct
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
        signal = TradingSignal(
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

        self.logger.info(
            f"Created trading signal for {ticker}: action={action}, "
            f"confidence={confidence:.2%}, position_size={position_size_pct:.2%}, "
            f"entry=${current_price}, stop=${stop_loss_price}, target=${take_profit_price}"
        )

        return signal

    def _calculate_confidence(self, scored_item: ScoredItem) -> float:
        """
        Calculate trading confidence from scored item.

        Combines relevance score, sentiment, and source weight using a weighted average:
        - 60% weight on relevance (normalized to 0-1)
        - 30% weight on sentiment strength (absolute value, normalized)
        - 10% weight on source credibility

        Args:
            scored_item: Scored item data

        Returns:
            Confidence value between 0.0 and 1.0
        """
        # Normalize relevance to 0-1 range (assume max relevance is 5.0)
        normalized_relevance = min(scored_item.relevance / 5.0, 1.0)

        # Normalize sentiment to 0-1 range (sentiment is -1 to +1)
        # Use absolute value for strength, then normalize to 0-1
        normalized_sentiment = (abs(scored_item.sentiment) + 1.0) / 2.0

        # Normalize source weight to 0-1 range (cap at 1.0)
        normalized_source = min(scored_item.source_weight, 1.0)

        # Combine factors (weighted average: 60% relevance, 30% sentiment, 10% source)
        confidence = (
            normalized_relevance * 0.60
            + normalized_sentiment * 0.30
            + normalized_source * 0.10
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

        For confidence below the high threshold, uses base position size.
        For confidence above the high threshold, scales linearly up to max position size.

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
            confidence_factor = (confidence - self.config.high_confidence_threshold) / (
                1.0 - self.config.high_confidence_threshold
            )
            position_size = self.config.base_position_size_pct + (
                (self.config.max_position_size_pct - self.config.base_position_size_pct)
                * confidence_factor
            )

        return min(position_size, self.config.max_position_size_pct)

    def _calculate_stop_loss(
        self, entry_price: Decimal, action: str, stop_pct: float
    ) -> Decimal:
        """
        Calculate stop-loss price.

        For buy orders: stop is below entry (entry * (1 - stop_pct))
        For sell orders: stop is above entry (entry * (1 + stop_pct))

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
        self, entry_price: Decimal, action: str, profit_pct: float
    ) -> Decimal:
        """
        Calculate take-profit price.

        For buy orders: target is above entry (entry * (1 + profit_pct))
        For sell orders: target is below entry (entry * (1 - profit_pct))

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
