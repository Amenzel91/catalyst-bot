"""
Alpaca Broker Wrapper (Synchronous)

A lightweight synchronous wrapper around alpaca-py TradingClient
that implements the minimum interface needed for PositionManager.

This bridges the gap between the async BrokerInterface scaffold
and the current synchronous paper_trader.py implementation.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..logging_utils import get_logger

log = get_logger("alpaca_wrapper")


class AlpacaBrokerWrapper:
    """
    Synchronous wrapper around Alpaca TradingClient.

    Provides the minimal interface needed for PositionManager operations:
    - get_current_price(ticker) -> Decimal
    - close_position(ticker, quantity) -> order_id
    - get_clock() -> market hours info
    """

    def __init__(self, client=None):
        """
        Initialize wrapper.

        Args:
            client: Existing alpaca TradingClient instance (optional)
                   If None, creates a new client from environment variables
        """
        self.client = client

        if self.client is None:
            api_key = os.getenv("ALPACA_API_KEY", "").strip()
            api_secret = os.getenv("ALPACA_SECRET", "").strip()

            if not api_key or not api_secret:
                raise ValueError("Alpaca credentials not found in environment")

            try:
                from alpaca.trading.client import TradingClient
                self.client = TradingClient(api_key, api_secret, paper=True)
                log.info("alpaca_wrapper_initialized")
            except ImportError:
                raise ImportError("alpaca-py not installed")

    def get_current_price(self, ticker: str) -> Optional[Decimal]:
        """
        Get current price for a ticker using latest trade.

        Args:
            ticker: Stock symbol

        Returns:
            Current price as Decimal, or None if unavailable
        """
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest

            # Use data client for market data
            api_key = os.getenv("ALPACA_API_KEY", "").strip()
            api_secret = os.getenv("ALPACA_SECRET", "").strip()

            data_client = StockHistoricalDataClient(api_key, api_secret)

            request = StockLatestTradeRequest(symbol_or_symbols=ticker)
            latest_trade = data_client.get_stock_latest_trade(request)

            if ticker in latest_trade:
                price = float(latest_trade[ticker].price)
                return Decimal(str(price))

            return None

        except Exception as e:
            log.debug("get_current_price_failed ticker=%s error=%s", ticker, str(e))
            return None

    def close_position(self, ticker: str, quantity: Optional[int] = None) -> Optional[str]:
        """
        Close a position (or partial position).

        Args:
            ticker: Stock symbol
            quantity: Number of shares to close (None = close all)

        Returns:
            Order ID if successful, None otherwise
        """
        try:
            from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            # Get current position to determine quantity
            if quantity is None:
                try:
                    position = self.client.get_open_position(ticker)
                    quantity = abs(int(position.qty))
                except Exception:
                    log.warning("close_position_failed ticker=%s reason=no_position", ticker)
                    return None

            # Detect if we're in extended hours
            from ..market_hours import is_extended_hours
            from ..config import get_settings

            settings = get_settings()
            use_extended_hours = (
                settings.trading_extended_hours and
                is_extended_hours()
            )

            # Alpaca requires DAY limit orders for extended hours
            if use_extended_hours:
                # Get current price for limit order
                current_price = self.get_current_price(ticker)
                if not current_price:
                    log.error("close_position_failed ticker=%s reason=no_price_in_extended_hours", ticker)
                    return None

                # Use limit order at current price for immediate fill
                order_request = LimitOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,  # Required for extended hours
                    limit_price=float(current_price),
                    extended_hours=True,
                )
                log.info("close_position_extended_hours ticker=%s qty=%d limit_price=%s",
                         ticker, quantity, current_price)
            else:
                # Regular hours: use market order with GTC
                order_request = MarketOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    extended_hours=False,
                )

            order = self.client.submit_order(order_data=order_request)

            log.info(
                "position_closed ticker=%s qty=%d order_id=%s",
                ticker, quantity, order.id
            )

            return str(order.id)

        except Exception as e:
            log.error("close_position_failed ticker=%s error=%s", ticker, str(e))
            return None

    def get_clock(self):
        """
        Get market clock information.

        Returns:
            Alpaca Clock object with is_open, next_open, next_close
        """
        try:
            return self.client.get_clock()
        except Exception as e:
            log.error("get_clock_failed error=%s", str(e))
            return None

    def is_market_open(self) -> bool:
        """
        Check if market is currently open.

        Returns:
            True if market is open, False otherwise
        """
        try:
            clock = self.get_clock()
            return clock.is_open if clock else False
        except Exception:
            return False
