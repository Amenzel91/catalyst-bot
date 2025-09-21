"""Tests for screener boost support in the feed pipeline.

This module verifies that when FEATURE_SCREENER_BOOST is enabled and a
valid screener CSV is provided, tickers appearing in that CSV bypass
the price ceiling filter during feed ingestion.  The test constructs
two synthetic feed entries: one cheap ticker and one expensive ticker.
Only the expensive ticker appears in the screener file; therefore it
should be retained despite exceeding the PRICE_CEILING when the
screener boost feature is on.
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest


def _make_entry(title: str, link: str, ts_iso: str, summary: str = "") -> Any:
    """Helper to construct a SimpleNamespace mimicking feedparser entries."""
    e = SimpleNamespace()
    e.title = title
    e.link = link
    e.published = ts_iso
    e.id = link
    e.summary = summary
    return e


def test_screener_boost_bypasses_price_ceiling(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """
    When FEATURE_SCREENER_BOOST=1 and a screener CSV contains a ticker,
    events for that ticker should bypass the price ceiling filter.  This
    test stubs out network and price lookups and verifies that both
    cheap and expensive items are returned when the expensive ticker
    appears in the screener CSV.
    """
    # Create a temporary repo structure with a screener file
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    screener_path = repo / "data" / "finviz.csv"
    screener_path.write_text("Ticker,Company\nEXPEN,Expensive Co\n", encoding="utf-8")
    # Switch working directory to the temp repo
    monkeypatch.chdir(repo)

    # Environment: enable screener boost, disable regular watchlist
    monkeypatch.setenv("FEATURE_SCREENER_BOOST", "1")
    monkeypatch.setenv("SCREENER_CSV", str(screener_path))
    monkeypatch.setenv("FEATURE_WATCHLIST", "0")
    # Apply a price ceiling of $10 to drop expensive tickers normally
    monkeypatch.setenv("PRICE_CEILING", "10")
    # Ensure Finviz news is disabled for the test (to avoid HTTP)
    monkeypatch.setenv("FEATURE_FINVIZ_NEWS", "0")

    # Build two feed entries: one cheap and one expensive
    cheap = _make_entry(
        "Cheap Corp Announces Something (NASDAQ:CHEAP)",
        "https://x/1",
        datetime.now(timezone.utc).isoformat(),
    )
    expen = _make_entry(
        "Expensive Co Update (NYSE:EXPEN)",
        "https://x/2",
        datetime.now(timezone.utc).isoformat(),
    )

    # Stub feedparser.parse to return our entries
    import feedparser

    def _parse(_txt):
        class R:
            pass

        R.entries = [cheap, expen]
        return R

    monkeypatch.setattr(feedparser, "parse", _parse, raising=True)

    # Patch network fetcher used by feeds to avoid HTTP
    import catalyst_bot.feeds as feeds

    monkeypatch.setattr(
        feeds, "_get_multi", lambda urls: (200, "<rss/>", urls[0]), raising=True
    )
    # Limit FEEDS to a single mock source for determinism
    feeds.FEEDS = {"mock": ["http://mock.local/rss"]}

    # Stub price check: CHEAP=3 (<=10), EXPEN=12 (>10)
    import catalyst_bot.market as market

    monkeypatch.setattr(
        market,
        "get_last_price_snapshot",
        lambda t: (3.0, 2.8) if t.upper() == "CHEAP" else (12.0, 11.5),
        raising=False,
    )

    # Stub volatility (unused but required by fetch)
    monkeypatch.setattr(
        feeds, "get_volatility", lambda _t, days=14: 18.5, raising=False
    )

    # Act: fetch feeds
    items = feeds.fetch_pr_feeds()

    # Assert: both tickers are returned; EXPEN bypasses the price ceiling
    assert len(items) == 2
    tickers = {it.get("ticker") for it in items}
    assert tickers == {"CHEAP", "EXPEN"}
    # The expensive ticker should be marked as being on the watchlist via screener
    for it in items:
        if it["ticker"] == "EXPEN":
            assert it.get("watchlist", False) is True
        else:
            assert it.get("watchlist", False) is False