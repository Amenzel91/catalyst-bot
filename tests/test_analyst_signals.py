"""Unit tests for the analyst signals module.

These tests verify the classification logic and gating behaviour of
``get_analyst_signal``.  The helper should return None when the feature
is disabled, and should correctly compute the implied return and label
when enabled and provided with mocked price targets and last prices.
"""

from __future__ import annotations

import pytest

from catalyst_bot.analyst_signals import get_analyst_signal


def test_get_analyst_signal_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that the implied return and label are computed correctly.

    We monkeypatch the FMP fetcher and price snapshot to return known
    values.  With a mean target of 11 and last price of 10, the implied
    return is 10 %, which meets the default threshold and should
    classify as Bullish.
    """

    # Patch the FMP fetcher to return deterministic values (mean=11, high=12, low=8, n=5)
    monkeypatch.setattr(
        "catalyst_bot.analyst_signals._fetch_fmp_target",
        lambda ticker, api_key, timeout=8: (11.0, 12.0, 8.0, 5),
    )
    # Patch the price snapshot to return last=10 (and ignore prev)
    monkeypatch.setattr(
        "catalyst_bot.analyst_signals.get_last_price_snapshot",
        lambda ticker: (10.0, 9.5),
    )
    # Stub settings object with feature enabled, threshold=10, provider=fmp
    class StubSettings:
        feature_analyst_signals = True
        analyst_return_threshold = 10.0
        analyst_provider = "fmp"
        analyst_api_key = "dummy"

    monkeypatch.setattr(
        "catalyst_bot.analyst_signals.get_settings", lambda: StubSettings
    )
    res = get_analyst_signal("XYZ")
    assert res is not None
    # Check numeric fields
    assert res["target_mean"] == 11.0
    assert res["implied_return"] == pytest.approx(10.0)
    # Implied return of exactly the threshold should classify as Bullish
    assert res["analyst_label"] == "Bullish"


def test_get_analyst_signal_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure that the helper returns None when the feature flag is off."""

    class StubSettings:
        feature_analyst_signals = False

    monkeypatch.setattr(
        "catalyst_bot.analyst_signals.get_settings", lambda: StubSettings
    )
    # Even if we monkeypatch the fetchers, the function should short‑circuit
    res = get_analyst_signal("XYZ")
    assert res is None