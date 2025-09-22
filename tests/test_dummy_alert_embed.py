"""
This file is generated for patch application only. It is a copy of
``catalyst-bot-main/tests/test_dummy_alert_embed.py`` and will be
overwritten into the repository when applying this patch.  See that
file for full documentation and tests.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest

from catalyst_bot import alerts


def test_dummy_alert_embed_features(monkeypatch: pytest.MonkeyPatch) -> None:
    # Define a simple namespace with the attributes used by _build_discord_embed.
    class DummySettings:
        feature_bullishness_gauge = True
        feature_earnings_alerts = True
        feature_sentiment_logging = False
        sentiment_weight_local = 0.4
        sentiment_weight_ext = 0.3
        sentiment_weight_sec = 0.2
        sentiment_weight_analyst = 0.1
        sentiment_weight_earnings = 0.2
        analyst_return_threshold = 10.0
        sentiment_weight_alpha = 0.0
        sentiment_weight_marketaux = 0.0
        sentiment_weight_stocknews = 0.0
        sentiment_weight_finnhub = 0.0

    monkeypatch.setattr(alerts, "get_settings", lambda: DummySettings)
    next_earnings = datetime.now(timezone.utc) + timedelta(days=5)
    dummy_event: Dict[str, Any] = {
        "title": "Test headline with bullish sentiments",
        "link": "https://example.com/test",
        "ticker": "TST",
        "tickers": ["TST"],
        "sentiment_local": 0.8,
        "sentiment_ext_score": (0.7, "Bullish", 3, {}),
        "sentiment_ext_details": {
            "alpha": {"score": 0.7},
            "sec": {"score": 0.5},
            "earnings": {"score": 0.6},
        },
        "analyst_implied_return": 20.0,
        "next_earnings_date": next_earnings,
        "earnings_eps_estimate": 1.23,
        "earnings_reported_eps": 1.30,
        "earnings_surprise_pct": 0.057,
        "earnings_label": "Beat",
    }
    embed = alerts._build_discord_embed(
        item_dict=dummy_event, scored=None, last_price=None, last_change_pct=None
    )
    assert embed is not None and isinstance(embed, dict)
    fields = embed.get("fields") or []
    field_names = [f.get("name") for f in fields if isinstance(f, dict)]
    assert "Bullishness" in field_names
    assert "Earnings" in field_names
    bull_field: Optional[Dict[str, Any]] = next(
        (f for f in fields if f.get("name") == "Bullishness"), None
    )
    assert bull_field is not None
    bull_val = str(bull_field.get("value"))
    assert "•" in bull_val and any(
        lbl in bull_val for lbl in {"Bullish", "Neutral", "Bearish"}
    )
    earn_field: Optional[Dict[str, Any]] = next(
        (f for f in fields if f.get("name") == "Earnings"), None
    )
    assert earn_field is not None
    earn_val = str(earn_field.get("value"))
    assert "Next:" in earn_val and "Est/Rep:" in earn_val
