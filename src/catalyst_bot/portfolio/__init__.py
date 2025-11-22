"""
Portfolio Management Package

This package provides position tracking and portfolio management.

Components:
- position_manager: Manages open positions and tracks P&L

Usage:
    from catalyst_bot.portfolio import PositionManager

    # Initialize manager
    manager = PositionManager(broker=broker)

    # Open position from filled order
    position = await manager.open_position(
        order=filled_order,
        signal_id="sig_001",
        stop_loss_price=Decimal("145.00"),
        take_profit_price=Decimal("160.00"),
    )

    # Update prices
    await manager.update_position_prices({"AAPL": Decimal("155.00")})

    # Get metrics
    metrics = manager.calculate_portfolio_metrics()
"""

from .position_manager import (
    ClosedPosition,
    ManagedPosition,
    PortfolioMetrics,
    PositionManager,
)

__all__ = [
    "PositionManager",
    "ManagedPosition",
    "ClosedPosition",
    "PortfolioMetrics",
]
