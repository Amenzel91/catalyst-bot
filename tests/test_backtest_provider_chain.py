"""Tests for backtest provider chain and usage metrics.

These tests verify that the backtest simulator picks the correct
provider based on the BACKTEST_PROVIDER_ORDER environment variable
and that the provider usage counts reflect the chosen provider for
each simulated result. The market helpers are monkeypatched to
return deterministic values so we can control which provider
matches first.
"""

from datetime import datetime, timezone


def _make_event(ticker: str) -> dict:
    return {
        "id": f"evt_{ticker}",
        "title": f"News for {ticker}",
        "link": f"https://example/{ticker}",
        "ticker": ticker,
        "ts": datetime(2025, 9, 10, 14, 0, tzinfo=timezone.utc).isoformat(),
    }


def test_backtest_provider_prefers_tiingo(monkeypatch):
    """When Tiingo returns data and is ordered first, all results use Tiingo."""
    import catalyst_bot.backtest.simulator as sim
    import catalyst_bot.market as market

    # Patch market providers: Tiingo returns data; AV returns none; yfinance not invoked
    monkeypatch.setattr(market, "_tiingo_last_prev", lambda t, key, timeout=8: (10.0, 9.0))
    monkeypatch.setattr(market, "_alpha_last_prev_cached", lambda t, key, timeout=8: (None, None))
    # Ensure yfinance is not consulted by ordering; even if consulted it returns none
    monkeypatch.setattr(sim, "yf", None, raising=False)
    monkeypatch.setenv("BACKTEST_PROVIDER_ORDER", "tiingo,av,yf")

    ev = _make_event("AAA")
    results = sim.simulate_events([ev])
    usage = sim.summarize_provider_usage(results)
    # All simulation results should be attributed to tiingo
    total = sum(usage.values())
    assert usage.get("tiingo") == total and total == len(results)


def test_backtest_provider_falls_back_to_av(monkeypatch):
    """When Tiingo yields no data but AV does, provider should be AV."""
    import catalyst_bot.backtest.simulator as sim
    import catalyst_bot.market as market

    # Tiingo returns none; AV returns data
    monkeypatch.setattr(market, "_tiingo_last_prev", lambda t, key, timeout=8: (None, None))
    monkeypatch.setattr(market, "_alpha_last_prev_cached", lambda t, key, timeout=8: (20.0, 19.0))
    monkeypatch.setattr(sim, "yf", None, raising=False)
    monkeypatch.setenv("BACKTEST_PROVIDER_ORDER", "tiingo,av,yf")

    ev = _make_event("BBB")
    results = sim.simulate_events([ev])
    usage = sim.summarize_provider_usage(results)
    total = sum(usage.values())
    assert usage.get("av") == total and total == len(results)


def test_backtest_provider_uses_yfinance(monkeypatch):
    """If both Tiingo and AV return no data, yfinance is used."""
    import catalyst_bot.backtest.simulator as sim
    import catalyst_bot.market as market

    # Force providers to return none
    monkeypatch.setattr(market, "_tiingo_last_prev", lambda t, key, timeout=8: (None, None))
    monkeypatch.setattr(market, "_alpha_last_prev_cached", lambda t, key, timeout=8: (None, None))

    # Mock yfinance to return non-empty history via fast_info
    class DummyTicker:
        def __init__(self, _):
            self.fast_info = {"last_price": 5.0, "previous_close": 4.0}

        def history(self, *args, **kwargs):
            import pandas as pd

            return pd.DataFrame({"close": [5.0]}, index=[datetime.now(timezone.utc)])

    monkeypatch.setattr(sim, "yf", type("DummyMod", (), {"Ticker": DummyTicker}))
    monkeypatch.setenv("BACKTEST_PROVIDER_ORDER", "tiingo,av,yf")

    ev = _make_event("CCC")
    results = sim.simulate_events([ev])
    usage = sim.summarize_provider_usage(results)
    total = sum(usage.values())
    assert usage.get("yf") == total and total == len(results)
