"""
Order Execution Package

This package provides order execution and signal conversion.

Components:
- order_executor: Converts trading signals to broker orders

Usage:
    from catalyst_bot.execution import OrderExecutor, TradingSignal

    # Initialize executor
    executor = OrderExecutor(broker=broker)

    # Create signal
    signal = TradingSignal(
        signal_id="sig_001",
        ticker="AAPL",
        action="buy",
        confidence=0.85,
        current_price=Decimal("150.00"),
        stop_loss_price=Decimal("145.00"),
        take_profit_price=Decimal("160.00"),
    )

    # Execute signal
    result = await executor.execute_signal(signal)
"""

from .order_executor import (
    ExecutionResult,
    OrderExecutor,
    PositionSizingConfig,
    TradingSignal,
)

__all__ = [
    "OrderExecutor",
    "TradingSignal",
    "ExecutionResult",
    "PositionSizingConfig",
]
