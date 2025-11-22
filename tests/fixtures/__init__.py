"""Test fixtures and mock data for paper trading bot tests."""

from .mock_alpaca import MockAlpacaClient, MockAccount, MockPosition, MockOrder
from .mock_market_data import MockMarketDataProvider, generate_market_data
from .sample_alerts import create_sample_alert, create_breakout_alert, create_earnings_alert
from .test_data_generator import (
    generate_random_price,
    generate_order_book,
    generate_trade_history,
)

__all__ = [
    "MockAlpacaClient",
    "MockAccount",
    "MockPosition",
    "MockOrder",
    "MockMarketDataProvider",
    "generate_market_data",
    "create_sample_alert",
    "create_breakout_alert",
    "create_earnings_alert",
    "generate_random_price",
    "generate_order_book",
    "generate_trade_history",
]
