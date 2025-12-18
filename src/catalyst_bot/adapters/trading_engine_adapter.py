"""
Trading Engine Adapter Module

Provides a wrapper function to replace execute_paper_trade() with TradingEngine.
This adapter enables alerts.py to use the modern TradingEngine infrastructure
while maintaining backward compatibility with the existing interface.

This is the drop-in replacement for the legacy paper_trader.execute_paper_trade().
"""

from __future__ import annotations

from decimal import Decimal

from ..logging_utils import get_logger
from ..models import ScoredItem
from ..trading.signal_generator import SignalGenerator
from ..utils.event_loop_manager import run_async

# Legacy imports kept for backward compatibility (may be used by external code)
from .signal_adapter import SignalAdapter, SignalAdapterConfig  # noqa: F401

logger = get_logger(__name__)

# Module-level SignalGenerator instance (singleton)
_signal_generator: SignalGenerator = None


def _get_signal_generator() -> SignalGenerator:
    """Get or create SignalGenerator singleton."""
    global _signal_generator
    if _signal_generator is None:
        _signal_generator = SignalGenerator()
        from ..trading.signal_generator import BUY_KEYWORDS

        logger.info(
            f"SignalGenerator initialized: {len(BUY_KEYWORDS)} buy keywords, "
            f"min_score={_signal_generator.min_score}"
        )
    return _signal_generator


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
        pass

        # Get SignalGenerator instance (unified signal generation)
        signal_generator = _get_signal_generator()

        # Generate signal using keyword-based SignalGenerator
        # This provides:
        # - Keyword-specific risk parameters (FDA=92% conf, Merger=95% conf, etc.)
        # - AVOID keyword handling (offering, dilution → skip trade)
        # - CLOSE keyword handling (bankruptcy, fraud → exit positions)
        signal = signal_generator.generate_signal(
            scored_item=item,
            ticker=ticker,
            current_price=current_price,
        )

        # If no actionable signal, return False
        if signal is None:
            logger.info(
                f"No actionable signal generated for {ticker} "
                f"(below threshold, neutral keywords, or AVOID keyword detected)"
            )
            return False

        # Get or create TradingEngine instance
        trading_engine = _get_trading_engine_instance(settings)

        # Execute signal using TradingEngine (async call wrapped in run_async)
        position = run_async(
            trading_engine._execute_signal(signal),
            timeout=60.0,  # Allow 60s for order execution
        )

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

        # Initialize the engine (async operation wrapped in run_async)
        initialized = run_async(
            engine.initialize(), timeout=30.0  # Allow 30s for broker connection
        )

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
