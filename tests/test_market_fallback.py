import importlib


def _stub_empty_hist():
    # Minimal stub with .empty True (so code path won’t index into it)
    class _H:
        empty = True

    return _H()


def test_alpha_primary_short_circuits_yf(monkeypatch):
    """
    If Alpha returns (last, prev), we should return immediately and never touch yfinance.
    """
    import catalyst_bot.market as market

    importlib.reload(market)  # ensure clean state

    # Mock get_settings to return a simple config with Alpha first
    class FakeSettings:
        market_provider_order = "av,yf"
        feature_tiingo = False
        tiingo_api_key = ""

    monkeypatch.setattr(market, "get_settings", lambda: FakeSettings(), raising=False)

    # Force Alpha path on
    monkeypatch.setattr(market, "_AV_KEY", "demo", raising=False)
    monkeypatch.setattr(market, "_SKIP_ALPHA", False, raising=False)
    # Disable Alpha caching to ensure our mock is called
    monkeypatch.setattr(market, "_AV_CACHE_TTL", 0, raising=False)

    # Track whether yfinance fallback would be used
    def _boom(*a, **k):
        raise AssertionError(
            "yfinance should not be called when Alpha returns both values"
        )

    class FakeTicker:
        def __init__(self, t):
            pass

        fast_info = {}
        history = _boom

    class FakeYF:
        Ticker = FakeTicker

    monkeypatch.setattr(market, "yf", FakeYF(), raising=False)

    # Alpha returns a valid last+prev
    def fake_alpha(ticker, api_key, timeout=8):
        assert ticker == "MSFT"
        return 123.45, 120.00

    monkeypatch.setattr(market, "_alpha_last_prev", fake_alpha, raising=True)

    last, prev = market.get_last_price_snapshot("MSFT")
    assert last == 123.45
    assert prev == 120.00


def test_yfinance_fallback_when_alpha_none(monkeypatch):
    """
    If Alpha returns (None, None), we should fall back to yfinance fast_info/history.
    """
    import catalyst_bot.market as market

    importlib.reload(market)  # ensure clean state

    # Mock get_settings to return a simple config with Alpha first
    class FakeSettings:
        market_provider_order = "av,yf"
        feature_tiingo = False
        tiingo_api_key = ""

    monkeypatch.setattr(market, "get_settings", lambda: FakeSettings(), raising=False)

    # Force Alpha path on, but make it return nothing usable
    monkeypatch.setattr(market, "_AV_KEY", "demo", raising=False)
    monkeypatch.setattr(market, "_SKIP_ALPHA", False, raising=False)
    # Disable Alpha caching to ensure our mock is called
    monkeypatch.setattr(market, "_AV_CACHE_TTL", 0, raising=False)
    monkeypatch.setattr(
        market, "_alpha_last_prev", lambda *a, **k: (None, None), raising=True
    )

    # Provide a tiny yfinance stub
    class FakeFI(dict):
        # fast_info sometimes behaves attr-like, sometimes dict-like
        __getattr__ = dict.get

    class FakeTicker:
        def __init__(self, t):
            # Provide both last and previous via fast_info
            self.fast_info = FakeFI(last_price=9.87, previous_close=10.00)

        def history(self, *a, **k):
            # Not needed because fast_info supplies both, but keep a safe stub
            return _stub_empty_hist()

    class FakeYF:
        Ticker = FakeTicker

    monkeypatch.setattr(market, "yf", FakeYF(), raising=False)

    last, prev = market.get_last_price_snapshot("AAPL")
    assert last == 9.87
    assert prev == 10.00


def test_yfinance_history_fallback_when_fast_info_partial(monkeypatch):
    """
    If Alpha returns only last (prev None), and yfinance fast_info is missing prev,
    we should try history() next.
    """
    import catalyst_bot.market as market

    importlib.reload(market)  # ensure clean state

    # Mock get_settings to return a simple config with Alpha first
    class FakeSettings:
        market_provider_order = "av,yf"
        feature_tiingo = False
        tiingo_api_key = ""

    monkeypatch.setattr(market, "get_settings", lambda: FakeSettings(), raising=False)

    # Alpha gives partial (last only)
    monkeypatch.setattr(market, "_AV_KEY", "demo", raising=False)
    monkeypatch.setattr(market, "_SKIP_ALPHA", False, raising=False)
    # Disable Alpha caching to ensure our mock is called
    monkeypatch.setattr(market, "_AV_CACHE_TTL", 0, raising=False)
    monkeypatch.setattr(
        market, "_alpha_last_prev", lambda *a, **k: (50.0, None), raising=True
    )

    # yfinance fast_info missing prev, but history provides both days
    class FakeHist:
        empty = False

        def __len__(self):
            return 2

        # Mimic pandas indexing enough for our code path
        class _Close:
            def __init__(self):
                self._vals = [49.0, 51.0]

            def __getitem__(self, idx):
                return self._vals[idx]

            def iloc(self, idx):
                return self._vals[idx]

        Close = _Close()

        # Support hist["Close"].iloc[-1] pattern
        def __getitem__(self, name):
            if name == "Close":

                class _I:
                    def __init__(self, vals):
                        self._vals = vals

                    @property
                    def iloc(self):
                        class _IL:
                            def __init__(self, vals):
                                self._vals = vals

                            def __getitem__(self, i):
                                return self._vals[i]

                        return _IL([49.0, 51.0])

                return _I([49.0, 51.0])
            raise KeyError(name)

    class FakeTicker:
        def __init__(self, t):
            self.fast_info = {}  # missing prev

        def history(self, *a, **k):
            return FakeHist()

    class FakeYF:
        Ticker = FakeTicker

    monkeypatch.setattr(market, "yf", FakeYF(), raising=False)

    last, prev = market.get_last_price_snapshot("TSLA")
    # Alpha gave last=50.0; history gives last=51.0, prev=49.0; our code prioritizes latest fallback
    assert last == 51.0
    assert prev == 49.0
