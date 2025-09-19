from datetime import datetime, timedelta, timezone

import pytest


def test_classify_offering_and_contract():
    """SEC digester should classify offerings as bearish and contracts as bullish."""
    from catalyst_bot.sec_digester import classify_filing

    # Dilutive offering via 8‑K
    score, label, reason = classify_filing(
        "sec_8k", "Company Announces Registered Direct Offering", ""
    )
    assert label == "Bearish"
    assert reason and "offering" in reason.lower()
    assert score == -1.0

    # Positive contract news
    score, label, reason = classify_filing(
        "sec_8k", "ABC Inc. signs contract with major partner", ""
    )
    assert label == "Bullish"
    assert score == 1.0


def test_classify_ownership_and_dilution():
    """13D/G filings should default to neutral unless indicating a stake increase."""
    from catalyst_bot.sec_digester import classify_filing

    # Neutral beneficial ownership
    score, label, reason = classify_filing("sec_13d", "Schedule 13D filed", "")
    assert label == "Neutral"
    assert score == 0.0
    # Stake increase triggers bullish
    score, label, reason = classify_filing(
        "sec_13d", "Investor increases stake in XYZ Corp", ""
    )
    assert label == "Bullish"
    assert score == 1.0


def test_aggregate_sentiment_tie_break():
    """Aggregation should return neutral when bullish and bearish counts tie."""
    from catalyst_bot.sec_digester import (
        _SEC_CACHE,
        get_combined_sentiment,
        record_filing,
    )

    # Clear global cache for the test
    _SEC_CACHE.clear()
    now = datetime.now(timezone.utc)
    # One bullish and one bearish filing
    record_filing("XYZ", now, "Bullish", "contract")
    record_filing("XYZ", now, "Bearish", "offering")
    score, lbl = get_combined_sentiment("XYZ")
    # mean of [1, -1] = 0; tie → Neutral
    assert pytest.approx(score, abs=1e-9) == 0.0
    assert lbl == "Neutral"


def test_aggregate_sentiment_majority():
    """Majority label should prevail when counts differ."""
    from catalyst_bot.sec_digester import (
        _SEC_CACHE,
        get_combined_sentiment,
        record_filing,
    )

    _SEC_CACHE.clear()
    now = datetime.now(timezone.utc)
    # Two bullish, one bearish
    record_filing("AAA", now, "Bullish", "contract")
    record_filing("AAA", now + timedelta(minutes=1), "Bullish", "contract")
    record_filing("AAA", now + timedelta(minutes=2), "Bearish", "offering")
    score, lbl = get_combined_sentiment("AAA")
    # average of [1, 1, -1] = 0.333..., label Bullish
    assert score > 0
    assert lbl == "Bullish"
