def test_earnings_sentiment_aggregation(monkeypatch):
    """The sentiment aggregator should include earnings sentiment when enabled."""
    from catalyst_bot import sentiment_sources as ss

    # Stub external providers to return None so that only earnings contribute.
    monkeypatch.setattr(ss, "_fetch_alpha_sentiment", lambda ticker, key: None)
    monkeypatch.setattr(ss, "_fetch_marketaux_sentiment", lambda ticker, key: None)
    monkeypatch.setattr(ss, "_fetch_stocknews_sentiment", lambda ticker, key: None)
    monkeypatch.setattr(ss, "_fetch_finnhub_sentiment", lambda ticker, key: None)

    # Stub get_earnings_sentiment to return a fixed score and label.
    def fake_earnings_sent(ticker: str):
        # Return a positive surprise of +0.3 (30%) labelled Bullish
        return 0.3, "Bullish", {"next_date": None, "surprise_pct": 0.3}

    # Disable settings lookup to force environment usage
    monkeypatch.setattr(
        ss, "get_settings", lambda: (_ for _ in ()).throw(Exception("no settings"))
    )
    # Enable news and earnings sentiment via env
    monkeypatch.setenv("FEATURE_NEWS_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_EARNINGS_ALERTS", "1")
    monkeypatch.setenv("SENTIMENT_WEIGHT_EARNINGS", "0.5")
    monkeypatch.setenv("SENTIMENT_MIN_ARTICLES", "1")
    # Provide dummy API keys (unused here but required by aggregator loops)
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "x")
    monkeypatch.setenv("MARKETAUX_API_KEY", "x")
    monkeypatch.setenv("STOCKNEWS_API_KEY", "x")
    monkeypatch.setenv("FINNHUB_API_KEY", "x")
    # Monkeypatch the earnings module directly.  Use raising=False to allow
    # creation of the attribute if it does not exist (e.g. when the
    # earnings module stub lacks get_earnings_sentiment in the test env).
    import catalyst_bot.earnings as earnings

    monkeypatch.setattr(
        earnings, "get_earnings_sentiment", fake_earnings_sent, raising=False
    )

    res = ss.get_combined_sentiment_for_ticker("TEST")
    assert res is not None, "Expected a result when earnings sentiment is enabled"
    score, label, details = res
    # Only earnings contributes with weight 0.5, so the score should equal 0.3
    assert abs(score - 0.3) < 1e-6
    assert label == "Bullish"
    # Provider results should include 'earnings' as key
    assert "earnings" in details
