"""
Paper Trading Module
====================

Executes paper trades on Alpaca based on bot alerts.
Designed for data collection - trades every alert to capture performance data.

Usage:
    from .paper_trader import execute_paper_trade

    # After an alert is generated:
    execute_paper_trade(ticker="AAPL", price=150.00, alert_id="abc123")
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .logging_utils import get_logger

log = get_logger("paper_trader")

# Thread-safe client initialization
_client = None
_client_lock = threading.Lock()


def _get_client():
    """Get or create Alpaca trading client (thread-safe, lazy init)."""
    global _client

    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        api_key = os.getenv("ALPACA_API_KEY", "").strip()
        api_secret = os.getenv("ALPACA_SECRET", "").strip()

        if not api_key or not api_secret:
            log.warning("paper_trader_disabled reason=missing_credentials")
            return None

        try:
            from alpaca.trading.client import TradingClient
            _client = TradingClient(api_key, api_secret, paper=True)
            log.info("paper_trader_initialized")
            return _client
        except ImportError:
            log.warning("paper_trader_disabled reason=alpaca_py_not_installed")
            return None
        except Exception as e:
            log.error("paper_trader_init_failed error=%s", str(e))
            return None


def is_enabled() -> bool:
    """Check if paper trading is enabled."""
    # Feature flag check
    if os.getenv("FEATURE_PAPER_TRADING", "1") != "1":
        return False

    # Credentials check
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_SECRET", "").strip()

    return bool(api_key and api_secret)


def execute_paper_trade(
    ticker: str,
    price: Optional[float] = None,
    alert_id: Optional[str] = None,
    source: Optional[str] = None,
    catalyst_type: Optional[str] = None,
) -> Optional[str]:
    """
    Execute a paper trade for an alert.

    This is the main entry point called from alerts.py after an alert is posted.

    Strategy (Phase 1 - Data Collection):
    - BUY every alert with fixed position size
    - No stop-loss or take-profit (manual tracking via feedback system)
    - Goal: Capture data on all alerts for ML training

    Args:
        ticker: Stock symbol to trade
        price: Current price (for logging)
        alert_id: Alert ID for tracking
        source: Alert source (e.g., "finviz", "businesswire")
        catalyst_type: Type of catalyst

    Returns:
        Order ID if successful, None otherwise
    """
    if not is_enabled():
        return None

    if not ticker or not ticker.strip():
        log.warning("paper_trade_skipped reason=missing_ticker")
        return None

    ticker = ticker.upper().strip()

    # Skip ETFs and indices for now (focus on stocks)
    etf_tickers = {"SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "ARKK", "TLT"}
    if ticker in etf_tickers:
        log.debug("paper_trade_skipped ticker=%s reason=etf", ticker)
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        # Phase 1: Simple fixed-dollar position sizing
        # $500 per trade (adjustable via env var)
        position_dollars = float(os.getenv("PAPER_TRADE_POSITION_SIZE", "500"))

        # Calculate shares based on price
        if price and price > 0:
            qty = max(1, int(position_dollars / price))
        else:
            # If no price, use a default qty of 10 shares
            qty = 10

        # Check if market is open (Alpaca will reject otherwise)
        try:
            clock = client.get_clock()
            if not clock.is_open:
                log.info(
                    "paper_trade_queued ticker=%s qty=%d reason=market_closed "
                    "next_open=%s",
                    ticker, qty, clock.next_open
                )
                # Still submit - Alpaca will queue DAY orders
        except Exception as clock_err:
            log.debug("clock_check_failed error=%s", str(clock_err))

        # Create order request with extended hours support
        # GTC (Good-Til-Canceled) allows trading in pre-market and after-hours
        # extended_hours=True enables execution outside regular market hours
        order_request = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            extended_hours=True,
        )

        # Submit order
        order = client.submit_order(order_data=order_request)

        log.info(
            "paper_trade_executed ticker=%s qty=%d price=%.2f order_id=%s "
            "alert_id=%s source=%s catalyst=%s status=%s",
            ticker,
            qty,
            price or 0,
            order.id,
            alert_id or "unknown",
            source or "unknown",
            catalyst_type or "unknown",
            order.status,
        )

        return str(order.id)

    except Exception as e:
        error_msg = str(e)

        # Common errors to handle gracefully
        if "asset is not tradable" in error_msg.lower():
            log.debug("paper_trade_skipped ticker=%s reason=not_tradable", ticker)
        elif "insufficient" in error_msg.lower():
            log.warning("paper_trade_failed ticker=%s reason=insufficient_funds", ticker)
        elif "fractionable" in error_msg.lower():
            log.debug("paper_trade_skipped ticker=%s reason=fractional_not_supported", ticker)
        else:
            log.error(
                "paper_trade_failed ticker=%s alert_id=%s error=%s",
                ticker, alert_id, error_msg
            )

        return None


def get_account_status() -> dict:
    """Get current paper trading account status."""
    client = _get_client()
    if client is None:
        return {"enabled": False, "error": "Not configured"}

    try:
        account = client.get_account()
        positions = client.get_all_positions()
        orders = client.get_orders()

        return {
            "enabled": True,
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "open_positions": len(positions),
            "open_orders": len(orders),
            "status": str(account.status),
        }
    except Exception as e:
        return {"enabled": True, "error": str(e)}


def get_open_positions() -> list:
    """Get list of open positions."""
    client = _get_client()
    if client is None:
        return []

    try:
        positions = client.get_all_positions()
        return [
            {
                "ticker": pos.symbol,
                "qty": int(pos.qty),
                "avg_entry": float(pos.avg_entry_price),
                "current_price": float(pos.current_price),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc),
            }
            for pos in positions
        ]
    except Exception as e:
        log.error("get_positions_failed error=%s", str(e))
        return []
