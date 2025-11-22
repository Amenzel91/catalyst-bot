# Narrow deprecation filter for tests only.
# Keeps application logging intact while preventing noisy utcnow warnings during pytest runs.
import sys
import types
import warnings

import pytest


def pytest_configure(config):
    # Previously suppressed datetime.utcnow() warnings, now fixed with timezone-aware datetime.
    pass


def pytest_collection_modifyitems(config, items):
    """Skip trio backend tests since trio is not installed."""
    skip_trio = pytest.mark.skip(reason="trio backend not installed")
    for item in items:
        if "trio" in item.nodeid:
            item.add_marker(skip_trio)


@pytest.fixture(autouse=True, scope="session")
def _stub_feedparser_module():
    """
    Ensure catalyst_bot.feeds imports without external dependency.
    We inject a minimal 'feedparser' module whose parse() returns an object
    with an empty 'entries' list by default. Individual tests can monkeypatch
    parse() to return custom entries.
    """
    if "feedparser" not in sys.modules:
        m = types.SimpleNamespace()

        def _parse(_text):
            class _R:
                pass

            _R.entries = []
            return _R

        m.parse = _parse
        sys.modules["feedparser"] = m
    yield


@pytest.fixture(autouse=True, scope="session")
def _ensure_market_db(tmp_path_factory):
    """
    Ensure that a SQLite database with the expected schema exists under the
    ``data`` directory for tests that depend on it.

    Tests such as ``test_db_integrity`` expect ``data/market.db`` to be present
    with a table named ``finviz_filings``.  This fixture creates that file and
    table if they do not already exist.
    """
    import os
    import sqlite3

    data_dir = os.path.join(os.getcwd(), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    db_path = os.path.join(data_dir, "market.db")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS finviz_filings ("
            "ticker TEXT, filing_type TEXT, filing_date TEXT, title TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS finviz_screener_snapshots ("
            "ticker TEXT, ts TEXT, preset TEXT)"
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    yield


# ============================================================================
# Paper Trading Bot Test Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def test_config():
    """Trading bot test configuration."""
    return {
        "mode": "paper",
        "alpaca": {
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "base_url": "https://paper-api.alpaca.markets",
        },
        "risk": {
            "max_position_size": 0.10,  # 10% of portfolio
            "max_daily_loss": 0.02,  # 2% max daily loss
            "max_portfolio_risk": 0.06,  # 6% total portfolio risk
            "position_size_method": "kelly",
        },
        "execution": {
            "default_order_type": "market",
            "use_bracket_orders": True,
            "atr_stop_multiplier": 2.0,
            "atr_target_multiplier": 3.0,
        },
    }


@pytest.fixture
def test_db(tmp_path):
    """
    Create a temporary trading database for testing.

    Returns a SQLite connection with trading schema initialized.
    Database is cleaned up after test completes.
    """
    import sqlite3

    db_path = tmp_path / "test_trading.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Create trading tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            entry_time TEXT NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            status TEXT DEFAULT 'open',
            exit_price REAL,
            exit_time TEXT,
            exit_reason TEXT,
            realized_pnl REAL DEFAULT 0,
            unrealized_pnl REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            order_type TEXT NOT NULL,
            limit_price REAL,
            stop_price REAL,
            status TEXT NOT NULL,
            filled_qty INTEGER DEFAULT 0,
            filled_avg_price REAL,
            submitted_at TEXT NOT NULL,
            filled_at TEXT,
            canceled_at TEXT,
            failed_at TEXT,
            failure_reason TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            positions_value REAL NOT NULL,
            daily_pnl REAL DEFAULT 0,
            total_pnl REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            pnl REAL NOT NULL,
            pnl_pct REAL NOT NULL,
            hold_time_minutes INTEGER,
            exit_reason TEXT,
            signal_type TEXT,
            metadata TEXT
        )
    """)

    conn.commit()

    yield conn

    conn.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_account():
    """Mock Alpaca account object."""
    from unittest.mock import Mock

    account = Mock()
    account.account_number = "test-account-001"
    account.cash = 100000.00
    account.portfolio_value = 100000.00
    account.buying_power = 400000.00  # 4x margin
    account.equity = 100000.00
    account.last_equity = 100000.00
    account.long_market_value = 0.00
    account.short_market_value = 0.00
    account.initial_margin = 0.00
    account.maintenance_margin = 0.00
    account.daytrade_count = 0
    account.pattern_day_trader = False
    account.trading_blocked = False
    account.transfers_blocked = False
    account.account_blocked = False
    account.status = "ACTIVE"

    return account


@pytest.fixture
def mock_position():
    """Mock Alpaca position object."""
    from unittest.mock import Mock

    position = Mock()
    position.symbol = "AAPL"
    position.qty = 100
    position.side = "long"
    position.market_value = 17500.00
    position.cost_basis = 17000.00
    position.unrealized_pl = 500.00
    position.unrealized_plpc = 0.0294
    position.avg_entry_price = 170.00
    position.current_price = 175.00
    position.lastday_price = 172.00
    position.change_today = 0.0174

    return position


@pytest.fixture
def mock_order():
    """Mock Alpaca order object."""
    from datetime import datetime, timezone
    from unittest.mock import Mock

    order = Mock()
    order.id = "order-test-12345"
    order.client_order_id = "client-order-001"
    order.symbol = "AAPL"
    order.side = "buy"
    order.qty = 100
    order.type = "market"
    order.time_in_force = "day"
    order.limit_price = None
    order.stop_price = None
    order.status = "filled"
    order.filled_qty = 100
    order.filled_avg_price = 175.00
    order.submitted_at = datetime.now(timezone.utc).isoformat()
    order.filled_at = datetime.now(timezone.utc).isoformat()
    order.canceled_at = None
    order.failed_at = None
    order.replaced_by = None
    order.replaces = None

    return order


@pytest.fixture
def sample_alert():
    """Sample trading alert for testing."""
    from datetime import datetime, timezone

    return {
        "id": "alert-test-001",
        "ticker": "AAPL",
        "signal_type": "breakout",
        "score": 8.5,
        "price": 175.00,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "catalyst": "earnings_beat",
        "metadata": {
            "rvol": 3.2,
            "atr": 4.50,
            "volume": 52000000,
            "sentiment_score": 0.75,
        },
    }


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta, timezone

    # Generate 30 days of realistic OHLCV data
    dates = pd.date_range(
        end=datetime.now(timezone.utc), periods=30, freq="D"
    )

    base_price = 170.0
    returns = np.random.RandomState(42).normal(0.001, 0.02, 30)
    close_prices = base_price * (1 + returns).cumprod()

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": close_prices * np.random.RandomState(43).uniform(0.99, 1.01, 30),
            "high": close_prices * np.random.RandomState(44).uniform(1.00, 1.03, 30),
            "low": close_prices * np.random.RandomState(45).uniform(0.97, 1.00, 30),
            "close": close_prices,
            "volume": np.random.RandomState(46).randint(30000000, 80000000, 30),
        }
    )

    return df


@pytest.fixture(scope="function")
def reset_random_seed():
    """Reset random seed for deterministic tests."""
    import random
    import numpy as np

    random.seed(42)
    np.random.seed(42)

    yield

    # Reset to random state after test
    random.seed()
    np.random.seed()
