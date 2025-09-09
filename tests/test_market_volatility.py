import pandas as pd


def test_get_volatility_averages_daily_ranges(monkeypatch):
    """
    Use a tiny 3-day OHLC set to check:
      avg( (H-L)/C ) * 100 is returned.
    """
    import catalyst_bot.market as market

    data = {
        "High": [12.0, 15.0, 10.0],
        "Low": [10.0, 12.0, 9.0],
        "Close": [11.0, 14.0, 9.5],
    }
    df = pd.DataFrame(data)
    # attach a dummy DatetimeIndex (not used by the function)
    df.index = pd.date_range("2025-09-01", periods=3, freq="D")

    class FakeTicker:
        def history(self, *a, **k):
            return df

    class FakeYF:
        def Ticker(self, _t):
            return FakeTicker()

    monkeypatch.setattr(market, "yf", FakeYF(), raising=False)

    v = market.get_volatility("CHEAP", days=3)
    # Manual: ( (2/11)+(3/14)+(1/9.5) ) / 3 * 100 ≈ 16.7
    assert v is not None and abs(v - 16.7) < 0.5
