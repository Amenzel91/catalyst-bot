from datetime import datetime, timedelta, timezone

import pandas as pd


def _intraday_5m(start_utc: datetime, bars=40):
    idx = [start_utc + timedelta(minutes=5 * i) for i in range(bars)]
    df = pd.DataFrame(
        {
            "Open": [10.0 + 0.1 * i for i in range(bars)],
            "High": [10.2 + 0.1 * i for i in range(bars)],
            "Low": [9.8 + 0.1 * i for i in range(bars)],
            "Close": [10.1 + 0.1 * i for i in range(bars)],
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )
    return df


def test_simulator_converts_events_and_runs(monkeypatch):
    import catalyst_bot.backtest.simulator as sim
    import catalyst_bot.market as market

    # Patch resolve->intraday function used by tradesim
    start = datetime(2025, 9, 8, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        market,
        "get_intraday",
        lambda _t, **_k: _intraday_5m(start, bars=60),
        raising=False,
    )

    ev = {
        "id": "evt1",
        "title": "News for CHEAP",
        "link": "https://example/evt1",
        "ticker": "CHEAP",
        "ts": start.isoformat(),
    }
    results = sim.simulate_events([ev])
    # Default config 3*3 = 9 result rows expected
    assert isinstance(results, list) and len(results) == 9
    # Summarize to a dataframe for quick sanity
    df = sim.summarize_results(results)
    assert not df.empty and {
        "ticker",
        "entry_offset",
        "hold_duration",
        "return",
    } <= set(df.columns)
