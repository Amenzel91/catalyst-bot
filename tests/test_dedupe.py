import pytest
import time
from catalyst_bot.feeds import dedupe
from catalyst_bot.dedupe import signature_from, temporal_dedup_key, normalize_title


def test_dedupe_stable():
    items = [{"id": "a"}, {"id": "a"}, {"id": "b"}]
    out = dedupe(items)
    assert len(out) == 2


def test_signature_includes_ticker():
    """Test that signature includes ticker to prevent cross-ticker dedup."""
    title = "Company announces Q3 earnings beat"
    url = "https://example.com/earnings"

    sig_aapl = signature_from(title, url, ticker="AAPL")
    sig_tsla = signature_from(title, url, ticker="TSLA")

    # Same title/URL but different tickers should have DIFFERENT signatures
    assert sig_aapl != sig_tsla


def test_signature_backwards_compatible():
    """Test that signature_from() still works without ticker parameter."""
    title = "Breaking news alert"
    url = "https://example.com/news"

    # Should work without ticker (backward compatibility)
    sig_old = signature_from(title, url)
    assert sig_old is not None
    assert len(sig_old) == 40  # SHA1 hex length

    # Same call should produce same signature
    sig_old_2 = signature_from(title, url)
    assert sig_old == sig_old_2


def test_temporal_dedup_key():
    """Test temporal dedup with 30-minute buckets."""
    ticker = "AAPL"
    title = "Apple announces new product"

    # Timestamps 10 minutes apart (same 30-min bucket)
    # Use a timestamp at the start of a bucket to ensure adding 10 min doesn't cross boundary
    ts1 = 1729778400  # Exactly on 30-min boundary (divisible by 1800)
    ts2 = ts1 + (10 * 60)  # +10 minutes

    key1 = temporal_dedup_key(ticker, title, ts1)
    key2 = temporal_dedup_key(ticker, title, ts2)

    # Should be SAME (within same 30-min bucket)
    assert key1 == key2

    # Timestamp 35 minutes apart (different 30-min buckets)
    ts3 = ts1 + (35 * 60)  # +35 minutes
    key3 = temporal_dedup_key(ticker, title, ts3)

    # Should be DIFFERENT (different 30-min bucket)
    assert key1 != key3


def test_temporal_dedup_different_tickers():
    """Test that temporal dedup distinguishes tickers."""
    title = "Earnings beat announced"
    timestamp = int(time.time())

    key_aapl = temporal_dedup_key("AAPL", title, timestamp)
    key_tsla = temporal_dedup_key("TSLA", title, timestamp)

    # Different tickers should have different keys
    assert key_aapl != key_tsla
