"""
Paper Trading Module - DEPRECATED (2025-11-26)
===============================================

⚠️  DEPRECATED: This module has been replaced by TradingEngine.
⚠️  DO NOT USE THIS MODULE FOR NEW CODE.

This module is kept for reference only. All trading now goes through:
    src.catalyst_bot.adapters.trading_engine_adapter.execute_with_trading_engine()

Migration Details:
    - Backup: paper_trader.py.LEGACY_BACKUP_2025-11-26
    - New System: TradingEngine with OrderExecutor, PositionManager, and risk management
    - Adapter: SignalAdapter converts ScoredItem → TradingSignal
    - Extended Hours: Fully supported with DAY limit orders
    - Tests: 85 tests passing in tests/test_*_adapter.py

For migration documentation, see:
    - docs/LEGACY-TO-TRADINGENGINE-MIGRATION-PLAN.md
    - docs/migration/INTEGRATION_MAP.md
    - docs/migration/ADAPTER_DESIGN.md

Old Usage (DEPRECATED):
    from .paper_trader import execute_paper_trade
    execute_paper_trade(ticker="AAPL", price=150.00, alert_id="abc123")

New Usage:
    from .adapters.trading_engine_adapter import execute_with_trading_engine
    from .market_hours import is_extended_hours
    from decimal import Decimal

    success = execute_with_trading_engine(
        item=scored_item,  # ScoredItem from classify()
        ticker="AAPL",
        current_price=Decimal("150.00"),
        extended_hours=is_extended_hours(),
        settings=get_settings()
    )
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

# Position manager (Phase 2: Position Management)
_position_manager = None
_position_manager_lock = threading.Lock()
_monitor_thread = None
_monitor_stop_event = threading.Event()


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


def _get_position_manager():
    """Get or create position manager (thread-safe, lazy init)."""
    global _position_manager

    if _position_manager is not None:
        return _position_manager

    with _position_manager_lock:
        if _position_manager is not None:
            return _position_manager

        client = _get_client()
        if client is None:
            return None

        try:
            from .broker.alpaca_wrapper import AlpacaBrokerWrapper
            from .position_manager_sync import PositionManagerSync

            broker_wrapper = AlpacaBrokerWrapper(client=client)
            _position_manager = PositionManagerSync(broker=broker_wrapper)
            log.info("position_manager_initialized")
            return _position_manager

        except Exception as e:
            log.error("position_manager_init_failed error=%s", str(e))
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
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
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

        # Check if market is open to determine order type
        is_market_open = True
        try:
            clock = client.get_clock()
            is_market_open = clock.is_open
            if not clock.is_open:
                log.info(
                    "paper_trade_extended_hours ticker=%s qty=%d reason=market_closed "
                    "next_open=%s",
                    ticker, qty, clock.next_open
                )
        except Exception as clock_err:
            log.debug("clock_check_failed error=%s", str(clock_err))

        # Create order request
        # Extended hours orders MUST be DAY limit orders per Alpaca requirements
        # During regular hours, use market orders for better fill rates
        if is_market_open:
            # Regular hours: Use market order with GTC
            order_request = MarketOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
                extended_hours=False,
            )
        else:
            # Extended hours: Use DAY limit order
            # Set limit price 2% above current price to ensure fill in volatile pre-market/after-hours
            if not price or price <= 0:
                log.warning(
                    "paper_trade_skipped ticker=%s reason=no_price_extended_hours",
                    ticker
                )
                return None

            limit_price = round(price * 1.02, 2)  # 2% above current price
            order_request = LimitOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
                extended_hours=True,
            )

        # Submit order
        order = client.submit_order(order_data=order_request)

        # Determine order type for logging
        order_type = "limit_day_ext" if not is_market_open else "market_gtc"
        limit_price_log = f" limit=${limit_price:.2f}" if not is_market_open else ""

        log.info(
            "paper_trade_executed ticker=%s qty=%d price=%.2f%s order_id=%s "
            "alert_id=%s source=%s catalyst=%s status=%s type=%s",
            ticker,
            qty,
            price or 0,
            limit_price_log,
            order.id,
            alert_id or "unknown",
            source or "unknown",
            catalyst_type or "unknown",
            order.status,
            order_type,
        )

        # Phase 2: Track position with automated exit rules
        try:
            manager = _get_position_manager()
            if manager and price and price > 0:
                # Calculate stop-loss and take-profit prices
                stop_loss_pct = float(os.getenv("PAPER_TRADE_STOP_LOSS_PCT", "0.05"))  # 5%
                take_profit_pct = float(os.getenv("PAPER_TRADE_TAKE_PROFIT_PCT", "0.15"))  # 15%

                entry_price = Decimal(str(price))
                stop_loss_price = entry_price * Decimal(str(1 - stop_loss_pct))
                take_profit_price = entry_price * Decimal(str(1 + take_profit_pct))

                # Open position in manager
                manager.open_position(
                    ticker=ticker,
                    quantity=qty,
                    entry_price=entry_price,
                    entry_order_id=str(order.id),
                    signal_id=alert_id,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                )

                log.debug(
                    "position_tracked ticker=%s stop=$%.2f target=$%.2f",
                    ticker, stop_loss_price, take_profit_price
                )

        except Exception as track_err:
            log.error("position_tracking_failed ticker=%s error=%s", ticker, str(track_err))

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


# ============================================================================
# Phase 2: Position Monitoring (Automated Exits)
# ============================================================================

def _position_monitor_loop():
    """
    Background thread that monitors positions and executes automated exits.

    Runs continuously until stop event is set.
    Checks market hours and pauses monitoring outside trading hours.
    """
    import time

    check_interval = int(os.getenv("PAPER_TRADE_MONITOR_INTERVAL", "60"))  # 60s default
    max_hold_hours = int(os.getenv("PAPER_TRADE_MAX_HOLD_HOURS", "24"))  # 24h default

    log.info(
        "position_monitor_started interval=%ds max_hold=%dh",
        check_interval, max_hold_hours
    )

    while not _monitor_stop_event.is_set():
        try:
            manager = _get_position_manager()
            if not manager:
                time.sleep(check_interval)
                continue

            # Check if market is open
            if not manager.broker.is_market_open():
                log.debug("position_monitor_paused reason=market_closed")
                time.sleep(check_interval)
                continue

            # Update all positions with current prices
            updated_count = manager.update_position_prices()

            # Check and execute automated exits
            closed_positions = manager.check_and_execute_exits(max_hold_hours=max_hold_hours)

            if closed_positions:
                log.info("position_monitor_cycle updated=%d closed=%d",
                        updated_count, len(closed_positions))

                # Log each closed position
                for closed in closed_positions:
                    log.info(
                        "position_auto_closed ticker=%s pnl=$%.2f pnl_pct=%.1f%% "
                        "reason=%s hold_hours=%.1f",
                        closed.ticker,
                        closed.realized_pnl,
                        closed.realized_pnl_pct * 100,
                        closed.exit_reason,
                        closed.hold_duration_seconds / 3600,
                    )

        except Exception as e:
            log.error("position_monitor_error error=%s", str(e))

        # Sleep until next check
        time.sleep(check_interval)

    log.info("position_monitor_stopped")


def start_position_monitor():
    """
    Start the background position monitoring thread.

    This should be called once at bot startup if paper trading is enabled.
    """
    global _monitor_thread

    if _monitor_thread is not None and _monitor_thread.is_alive():
        log.warning("position_monitor_already_running")
        return

    # Reset stop event
    _monitor_stop_event.clear()

    # Start monitoring thread
    _monitor_thread = threading.Thread(
        target=_position_monitor_loop,
        name="PositionMonitor",
        daemon=True,
    )
    _monitor_thread.start()

    log.info("position_monitor_thread_started")


def stop_position_monitor():
    """
    Stop the background position monitoring thread.

    This should be called at bot shutdown.
    """
    global _monitor_thread

    if _monitor_thread is None or not _monitor_thread.is_alive():
        log.warning("position_monitor_not_running")
        return

    # Signal thread to stop
    _monitor_stop_event.set()

    # Wait for thread to finish (with timeout)
    _monitor_thread.join(timeout=10.0)

    if _monitor_thread.is_alive():
        log.error("position_monitor_failed_to_stop")
    else:
        log.info("position_monitor_stopped")
        _monitor_thread = None
