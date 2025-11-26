"""
Trading Module

This module contains the trading engine and related components for
the Catalyst Bot paper trading system.

Components:
- TradingEngine: Orchestrates the complete trading workflow
- SignalGenerator: Converts scored items to trading signals (Agent 1)
- MarketDataFeed: Real-time price feeds (Agent 3)
"""

from .signal_generator import SignalGenerator

# TradingEngine import - handle gracefully if not available or has issues
try:
    from .trading_engine import TradingEngine
    __all__ = ["SignalGenerator", "TradingEngine"]
except Exception:
    # TradingEngine not yet implemented properly
    __all__ = ["SignalGenerator"]
