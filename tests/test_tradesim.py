"""Tests for the trade simulator."""

from catalyst_bot.tradesim import simulate_trades, TradeSimConfig
from catalyst_bot.models import NewsItem
from datetime import datetime


def test_simulate_trades_returns_empty_for_missing_ticker() -> None:
    # Without a ticker, intraday data cannot be fetched; expect empty result
    item = NewsItem(
        ts_utc=datetime.utcnow(),
        title="Some news", canonical_url="", source_host="", ticker=None
    )
    results = simulate_trades(item)
    assert results == []