"""Tests for the classification module."""

from datetime import datetime

from catalyst_bot.classify import classify
from catalyst_bot.classify_bridge import classify_text
from catalyst_bot.models import NewsItem


def test_classify_detects_fda_keyword_and_sentiment() -> None:
    item = NewsItem(
        ts_utc=datetime.utcnow(),
        title="Biotech Co receives FDA approval for phase 3 trial",
        canonical_url="http://example.com",
        source_host="businesswire.com",
        ticker="ABC",
    )
    scored = classify(item)
    # Should hit the 'fda' category
    assert "fda" in scored.keyword_hits
    # Sentiment should be non‑negative
    assert scored.sentiment >= 0.0


def test_classify_bridge_min_contract() -> None:
    out = classify_text("Company receives FDA approval for new device")
    assert isinstance(out, dict)
    assert "tags" in out and isinstance(out["tags"], list)
    assert "keyword_hits" in out and isinstance(out["keyword_hits"], dict)
