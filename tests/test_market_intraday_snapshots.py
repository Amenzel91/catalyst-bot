from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


def _bars(et_times, base_open=10.0):
    rows = []
    for i, t in enumerate(et_times):
        o = base_open + i * 0.1
        h = o + 0.5
        low = o - 0.5
        c = o + 0.2
        rows.append((t, o, h, low, c))
    idx = [t for (t, *_) in rows]
    df = pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
        },
        index=pd.DatetimeIndex(idx, tz=ZoneInfo("America/New_York")),
    )
    return df


def test_get_intraday_snapshots_segments(monkeypatch):
    """
    Build 1m bars across:
      premarket: 08:00, 09:00
      intraday : 09:30, 12:00, 16:00
      afterhrs : 16:00, 19:00, 20:00
    and verify per-segment OHLC extraction.
    """
    # Times in America/New_York for a given day
    d = datetime(2025, 9, 8, tzinfo=ZoneInfo("America/New_York"))
    et_times = [
        d.replace(hour=8, minute=0),
        d.replace(hour=9, minute=0),
        d.replace(hour=9, minute=30),
        d.replace(hour=12, minute=0),
        d.replace(hour=16, minute=0),
        d.replace(hour=19, minute=0),
        d.replace(hour=20, minute=0),
    ]
    df = _bars(et_times, base_open=10.0)

    class FakeYF:
        def download(self, *a, **k):
            return df

    import catalyst_bot.market as market

    monkeypatch.setattr(market, "yf", FakeYF(), raising=False)

    snaps = market.get_intraday_snapshots("CHEAP", target_date=d.date())
    assert snaps is not None

    # Premarket should include 08:00 -> 09:00
    pm = snaps["premarket"]
    assert pm["open"] == float(df.loc[et_times[0]]["Open"])
    assert pm["close"] == float(df.loc[et_times[1]]["Close"])

    # Intraday includes 09:30 -> 16:00
    reg = snaps["intraday"]
    assert reg["open"] == float(df.loc[et_times[2]]["Open"])
    assert reg["close"] == float(df.loc[et_times[4]]["Close"])

    # After-hours includes 16:00 -> 20:00 (note 16:00 appears in both by design)
    ah = snaps["afterhours"]
    assert ah["open"] == float(df.loc[et_times[4]]["Open"])
    assert ah["close"] == float(df.loc[et_times[6]]["Close"])
