"""
Broker Integration Package

This package provides broker integration for paper and live trading.

Components:
- broker_interface: Abstract base class and type definitions
- alpaca_client: Alpaca Markets broker implementation

Usage:
    from catalyst_bot.broker import AlpacaBrokerClient, OrderSide, OrderType

    # Initialize broker
    broker = AlpacaBrokerClient(paper_trading=True)
    await broker.connect()

    # Place order
    order = await broker.place_order(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
    )
"""

from .alpaca_client import AlpacaBrokerClient
from .broker_interface import (
    Account,
    AccountStatus,
    BracketOrder,
    BracketOrderParams,
    BrokerError,
    BrokerInterface,
    InsufficientFundsError,
    Order,
    OrderNotFoundError,
    OrderRejectedError,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionNotFoundError,
    PositionSide,
    RateLimitError,
    TimeInForce,
)

__all__ = [
    # Broker implementations
    "AlpacaBrokerClient",
    "BrokerInterface",
    # Data types
    "Account",
    "Order",
    "Position",
    "BracketOrder",
    "BracketOrderParams",
    # Enums
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "TimeInForce",
    "PositionSide",
    "AccountStatus",
    # Exceptions
    "BrokerError",
    "InsufficientFundsError",
    "OrderRejectedError",
    "OrderNotFoundError",
    "PositionNotFoundError",
    "RateLimitError",
]
