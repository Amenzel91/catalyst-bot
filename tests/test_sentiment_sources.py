import os
import types


def test_combined_sentiment_weighting(monkeypatch):
    """The aggregator should compute a weighted mean across providers."""
    from catalyst_bot import sentiment_sources as ss

    # Stub out provider fetchers to return predictable values.
    monkeypatch.setattr(
        ss, "_fetch_alpha_sentiment", lambda ticker, key: (0.5, "Bullish", 3, {})
    )
    monkeypatch.setattr(
        ss, "_fetch_marketaux_sentiment", lambda ticker, key: (0.2, "Neutral", 2, {})
    )
    monkeypatch.setattr(
        ss, "_fetch_stocknews_sentiment", lambda ticker, key: (-0.4, "Bearish", 1, {})
    )
    monkeypatch.setattr(ss, "_fetch_finnhub_sentiment", lambda ticker, key: None)
    # Force get_settings() to raise to ensure env overrides are used.
    monkeypatch.setattr(
        ss,
        "get_settings",
        lambda: (_ for _ in ()).throw(Exception("no settings")),
    )
    # Enable news sentiment and providers via environment
    monkeypatch.setenv("FEATURE_NEWS_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_ALPHA_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_MARKETAUX_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_STOCKNEWS_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_FINNHUB_SENTIMENT", "0")
    # Provide dummy API keys
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "x")
    monkeypatch.setenv("MARKETAUX_API_KEY", "y")
    monkeypatch.setenv("STOCKNEWS_API_KEY", "z")
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    # Set weights explicitly
    monkeypatch.setenv("SENTIMENT_WEIGHT_ALPHA", "0.4")
    monkeypatch.setenv("SENTIMENT_WEIGHT_MARKETAUX", "0.3")
    monkeypatch.setenv("SENTIMENT_WEIGHT_STOCKNEWS", "0.3")
    monkeypatch.setenv("SENTIMENT_WEIGHT_FINNHUB", "0.0")
    monkeypatch.setenv("SENTIMENT_MIN_ARTICLES", "2")

    res = ss.get_combined_sentiment_for_ticker("TEST")
    assert res is not None, "Expected a result when providers return data"
    score, label, details = res
    # Weighted average: 0.5*0.4 + 0.2*0.3 + (-0.4)*0.3 = 0.14
    assert abs(score - 0.14) < 1e-6
    # Score 0.14 should produce a Bullish label
    assert label == "Bullish"
    # Details should include all three providers
    assert set(details.keys()) == {"alpha", "marketaux", "stocknews"}


def test_combined_sentiment_gating(monkeypatch):
    """Aggregator should return None when total article count is below minimum."""
    from catalyst_bot import sentiment_sources as ss

    # Only one provider returns a single article; others return nothing.
    monkeypatch.setattr(
        ss, "_fetch_alpha_sentiment", lambda ticker, key: (0.8, "Bullish", 1, {})
    )
    monkeypatch.setattr(ss, "_fetch_marketaux_sentiment", lambda ticker, key: None)
    monkeypatch.setattr(ss, "_fetch_stocknews_sentiment", lambda ticker, key: None)
    monkeypatch.setattr(ss, "_fetch_finnhub_sentiment", lambda ticker, key: None)
    # Disable settings to force env usage
    monkeypatch.setattr(
        ss,
        "get_settings",
        lambda: (_ for _ in ()).throw(Exception("no settings")),
    )
    # Enable only alpha provider
    monkeypatch.setenv("FEATURE_NEWS_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_ALPHA_SENTIMENT", "1")
    monkeypatch.setenv("FEATURE_MARKETAUX_SENTIMENT", "0")
    monkeypatch.setenv("FEATURE_STOCKNEWS_SENTIMENT", "0")
    monkeypatch.setenv("FEATURE_FINNHUB_SENTIMENT", "0")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "x")
    monkeypatch.setenv("SENTIMENT_WEIGHT_ALPHA", "1.0")
    monkeypatch.setenv("SENTIMENT_MIN_ARTICLES", "2")
    res = ss.get_combined_sentiment_for_ticker("TEST")
    # Only one article < SENTIMENT_MIN_ARTICLES=2; should return None
    assert res is None