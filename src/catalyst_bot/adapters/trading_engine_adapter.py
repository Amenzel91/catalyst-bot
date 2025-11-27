"""
Trading Engine Adapter Module

Provides a wrapper function to replace execute_paper_trade() with TradingEngine.
This adapter enables alerts.py to use the modern TradingEngine infrastructure
while maintaining backward compatibility with the existing interface.

This is the drop-in replacement for the legacy paper_trader.execute_paper_trade().
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Optional

from ..models import ScoredItem
from ..logging_utils import get_logger
from .signal_adapter import SignalAdapter, SignalAdapterConfig

logger = get_logger(__name__)


def execute_with_trading_engine(
    item: ScoredItem,
    ticker: str,
    current_price: Decimal,
    extended_hours: bool = False,
    settings=None,
) -> bool:
    """
    Execute a trade using TradingEngine (drop-in replacement for execute_paper_trade).

    This function wraps the async TradingEngine flow and provides a synchronous
    interface that matches the legacy execute_paper_trade() signature.

    Flow:
    1. Convert ScoredItem to TradingSignal using SignalAdapter
    2. Call TradingEngine._execute_signal() (async, uses asyncio.run())
    3. Return True on success, False on failure

    Args:
        item: ScoredItem from classification system
        ticker: Stock ticker symbol (uppercase)
        current_price: Current market price
        extended_hours: Whether to enable extended hours trading
        settings: Optional settings object (used to get TradingEngine instance)

    Returns:
        True if trade executed successfully, False otherwise
    """
    try:
        # Import TradingEngine here to avoid circular dependency
        from ..trading.trading_engine import TradingEngine

        # Initialize signal adapter with default configuration
        adapter_config = SignalAdapterConfig(
            default_stop_loss_pct=0.05,  # 5% stop-loss
            default_take_profit_pct=0.10,  # 10% take-profit
            base_position_size_pct=0.03,  # 3% of portfolio
            max_position_size_pct=0.05,  # 5% of portfolio
            min_confidence_for_trade=0.60,  # Minimum 60% confidence
        )
        adapter = SignalAdapter(config=adapter_config)

        # Convert ScoredItem to TradingSignal
        signal = adapter.from_scored_item(
            scored_item=item,
            ticker=ticker,
            current_price=current_price,
            extended_hours=extended_hours,
        )

        # If no actionable signal, return False
        if signal is None:
            logger.info(
                f"No actionable signal generated for {ticker} "
                f"(below confidence threshold or neutral sentiment)"
            )
            return False

        # Get or create TradingEngine instance
        trading_engine = _get_trading_engine_instance(settings)

        # Execute signal using TradingEngine (async call wrapped in asyncio.run)
        position = asyncio.run(trading_engine._execute_signal(signal))

        # Return True if position was successfully created
        if position:
            logger.info(
                f"Successfully executed trade for {ticker} via TradingEngine: "
                f"position_id={position.position_id}"
            )
            return True
        else:
            logger.warning(
                f"Failed to execute trade for {ticker} via TradingEngine "
                f"(execution or fill failed)"
            )
            return False

    except Exception as e:
        logger.error(
            f"Error executing trade for {ticker} via TradingEngine: {e}",
            exc_info=True,
        )
        return False


def _get_trading_engine_instance(settings=None):
    """
    Get or create TradingEngine instance.

    This function manages a singleton-like TradingEngine instance to avoid
    recreating connections for each trade.

    Args:
        settings: Optional settings object

    Returns:
        TradingEngine instance
    """
    # Import here to avoid circular dependency
    from ..trading.trading_engine import TradingEngine

    # Check if we have a cached instance
    if not hasattr(_get_trading_engine_instance, "_instance"):
        logger.info("Creating new TradingEngine instance for adapter")

        # Create TradingEngine with default configuration
        engine = TradingEngine(
            config={
                "trading_enabled": True,
                "paper_trading": True,
                "send_discord_alerts": True,
            }
        )

        # Initialize the engine (async operation wrapped in sync call)
        initialized = asyncio.run(engine.initialize())

        if not initialized:
            raise RuntimeError("Failed to initialize TradingEngine")

        # Cache the instance
        _get_trading_engine_instance._instance = engine
        logger.info("TradingEngine instance created and initialized successfully")

    return _get_trading_engine_instance._instance


def reset_trading_engine_instance():
    """
    Reset the cached TradingEngine instance.

    This is primarily used for testing to ensure each test gets a fresh instance.
    """
    if hasattr(_get_trading_engine_instance, "_instance"):
        delattr(_get_trading_engine_instance, "_instance")
        logger.info("TradingEngine instance reset")
