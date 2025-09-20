"""Tests for Wave‑4 sentiment components.

This test suite validates that the new options scanner and sector/session
enrichment features integrate correctly with the bullishness gauge.  When
the corresponding feature flags are enabled and the components return
deterministic values, the gauge should include those values in the final
score and classification.  The tests monkey‑patch the helpers to avoid
external dependencies and set up fresh settings per test to ensure
environment variables take effect.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import pytest

from catalyst_bot import alerts, config


@pytest.fixture
def dummy_settings(monkeypatch: pytest.MonkeyPatch) -> config.Settings:
    """Return a Settings instance with all Wave‑4 features enabled.

    The environment variables are patched so that a fresh Settings
    instance will reflect the desired feature flags and weight values.
    This fixture also patches ``alerts.get_settings`` to return the
    constructed instance, ensuring that calls inside ``_build_discord_embed``
    see the updated configuration.
    """
    # Enable all components and specify weights
    monkeypatch.setenv("FEATURE_OPTIONS_SCANNER", "1")
    monkeypatch.setenv("FEATURE_SECTOR_INFO", "1")
    monkeypatch.setenv("FEATURE_MARKET_TIME", "1")
    monkeypatch.setenv("FEATURE_BULLISHNESS_GAUGE", "1")
    monkeypatch.setenv("FEATURE_SENTIMENT_LOGGING", "0")
    # Assign weights for local, external, sector, session, options
    monkeypatch.setenv("SENTIMENT_WEIGHT_LOCAL", "0.4")
    monkeypatch.setenv("SENTIMENT_WEIGHT_EXT", "0.3")
    monkeypatch.setenv("SENTIMENT_WEIGHT_SEC", "0.0")
    monkeypatch.setenv("SENTIMENT_WEIGHT_ANALYST", "0.0")
    monkeypatch.setenv("SENTIMENT_WEIGHT_EARNINGS", "0.0")
    monkeypatch.setenv("SENTIMENT_WEIGHT_OPTIONS", "0.05")
    monkeypatch.setenv("SENTIMENT_WEIGHT_SECTOR", "0.05")
    monkeypatch.setenv("SENTIMENT_WEIGHT_SESSION", "0.05")
    # Fresh settings reflecting the environment
    settings = config.Settings()
    # Patch alerts.get_settings to return this instance.  Because
    # ``alerts._build_discord_embed`` imports get_settings from
    # ``config`` directly, we also patch the config module to return
    # this fresh settings instance.  Without this, the module would
    # continue to use the cached Settings() created at import time and
    # ignore our patched environment variables.
    monkeypatch.setattr(alerts, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "SETTINGS", settings)
    return settings


def _mock_options_scan(
    ticker: str, settings: config.Settings
) -> Tuple[float, str, Dict[str, float]]:
    """Return a deterministic bullish options score for testing.

    This helper mimics a real options scan by returning a positive score
    irrespective of the ticker.  It allows the test to focus on gauge
    aggregation rather than the scanning logic.
    """
    return (0.5, "Bullish", {"mock_score": 0.5})


def _mock_sector_info(ticker: str) -> Tuple[str, str]:
    """Return a low‑beta sector for the given ticker."""
    return ("Utilities", "Water Utilities")


def _mock_session(dt: datetime, timezone: str = "America/New_York") -> str:
    """Return a pre‑market session regardless of input."""
    return "Pre‑Mkt"


def test_options_and_sector_gauge(
    monkeypatch: pytest.MonkeyPatch, dummy_settings: config.Settings
) -> None:
    """Verify that options, sector and session scores contribute to the gauge.

    The test patches the options scanner and sector/session helpers to
    return known values.  A dummy event with a local and external score
    is passed to the embed builder.  The resulting "Bullishness" field
    should reflect the weighted average of all enabled components.
    """
    # Patch the options scanner and sector/session helpers
    from catalyst_bot import options_scanner as opt_scan
    from catalyst_bot import sector_info as s_info

    monkeypatch.setattr(opt_scan, "scan_options", _mock_options_scan)
    monkeypatch.setattr(s_info, "get_sector_info", _mock_sector_info)
    monkeypatch.setattr(s_info, "get_session", _mock_session)

    # Construct a dummy event
    now_iso = datetime.now(timezone.utc).isoformat()
    dummy_event: Dict[str, Any] = {
        "title": "Test headline for Wave‑4 components",
        "link": "https://example.com/test",
        "ticker": "ABC",
        "tickers": ["ABC"],
        "ts": now_iso,
        # Local sentiment (0.5) and external sentiment (0.2)
        "sentiment_local": 0.5,
        "sentiment_ext_score": (0.2, "Bullish", 2, {}),
    }
    # Call embed builder
    embed = alerts._build_discord_embed(
        item_dict=dummy_event,
        scored=None,
        last_price=None,
        last_change_pct=None,
    )
    assert embed and isinstance(embed, dict)
    fields = embed.get("fields") or []
    # Extract the Bullishness value
    for fld in fields:
        if isinstance(fld, dict) and fld.get("name") == "Bullishness":
            value = fld.get("value")
            break
    else:
        pytest.fail("Bullishness field missing in embed")
    # Parse the score (format "+0.35 • Bullish")
    assert isinstance(value, str) and "•" in value
    score_str = value.split("•")[0].strip()
    # Remove the leading sign and convert to float
    try:
        computed = float(score_str)
    except Exception:
        pytest.fail(f"Could not parse score: {value}")
    # Compute expected weighted score manually
    weights = {
        "local": 0.4,
        "ext": 0.3,
        "options": 0.05,
        "sector": 0.05,
        "session": 0.05,
    }
    comps = {
        "local": 0.5,
        "ext": 0.2,
        "options": 0.5,
        "sector": 0.2,  # Utilities -> low beta (0.2)
        "session": 0.1,  # Pre‑Mkt -> +0.1
    }
    total_w = sum(weights.values())
    weighted_sum = sum(comps[k] * weights[k] for k in weights)
    expected = weighted_sum / total_w
    # Allow a small tolerance due to floating‑point rounding
    assert abs(computed - expected) < 0.01
