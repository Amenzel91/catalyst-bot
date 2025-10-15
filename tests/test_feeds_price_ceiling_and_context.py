import json
from datetime import datetime, timezone
from types import SimpleNamespace


def _make_entry(title, link, ts_iso, summary=""):
    e = SimpleNamespace()
    e.title = title
    e.link = link
    e.published = ts_iso
    e.id = link
    e.summary = summary
    return e


def test_price_ceiling_enrichment_and_intraday(monkeypatch, tmp_path):
    """
    Validates Phase-B feed pipeline:
      - PRICE_CEILING gating prefers Finviz universe, falls back to live price
      - Each kept item has cls, recent_headlines, volatility14d
      - When FEATURE_INTRADAY_SNAPSHOTS=1, intraday snapshots are attached
    """
    # Arrange working dir with finviz universe and recent events
    d = tmp_path / "repo"
    (d / "data" / "finviz").mkdir(parents=True)
    (d / "data").mkdir(exist_ok=True)
    (d / "data" / "events.jsonl").write_text(
        json.dumps(
            {
                "ticker": "CHEAP",
                "title": "Earlier headline",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (d / "data" / "finviz" / "universe.csv").write_text(
        "ticker\nCHEAP\n", encoding="utf-8"
    )
    monkeypatch.chdir(d)

    # Env flags
    monkeypatch.setenv("PRICE_CEILING", "5")
    monkeypatch.setenv("FEATURE_INTRADAY_SNAPSHOTS", "1")
    # Disable screener boost to ensure only Finviz universe and price checks are used
    monkeypatch.setenv("FEATURE_SCREENER_BOOST", "0")
    monkeypatch.setenv("SCREENER_CSV", "")

    # Build two entries:
    #  - allowed via universe (CHEAP)
    #  - rejected via price fallback (EXPEN)
    cheap = _make_entry(
        "Cheap Corp Announces Something (NASDAQ:CHEAP)",
        "https://x/1",
        "2025-09-08T12:00:00Z",
    )
    expen = _make_entry(
        "Expensive Co Update (NYSE:EXPEN)", "https://x/2", "2025-09-08T13:00:00Z"
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

    # Stub price check: CHEAP=3 (<=5), EXPEN=12 (>5)
    import catalyst_bot.market as market

    monkeypatch.setattr(
        market,
        "get_last_price_snapshot",
        lambda t: (3.0, 2.8) if t.upper() == "CHEAP" else (12.0, 11.5),
        raising=False,
    )

    # Stub volatility
    monkeypatch.setattr(
        feeds, "get_volatility", lambda _t, days=14: 18.5, raising=False
    )

    # Stub intraday snapshots
    monkeypatch.setattr(
        market,
        "get_intraday_snapshots",
        lambda _t, target_date=None: {
            "premarket": {"open": 1, "high": 2, "low": 1, "close": 2},
            "intraday": {"open": 2, "high": 3, "low": 2, "close": 2.5},
            "afterhours": {"open": 2.5, "high": 3, "low": 2.4, "close": 2.6},
        },
        raising=False,
    )

    # Act
    items = feeds.fetch_pr_feeds()

    # Assert: only CHEAP passes; enrichment fields present
    assert len(items) == 1
    it = items[0]
    assert it["ticker"] == "CHEAP"
    assert "cls" in it and isinstance(it["cls"], dict)
    assert "recent_headlines" in it and len(it["recent_headlines"]) >= 1
    assert it.get("volatility14d") in (18.5, 18.5) or it.get("volatility") in (18.5,)
    assert "intraday" in it and {"premarket", "intraday", "afterhours"} <= set(
        it["intraday"].keys()
    )
