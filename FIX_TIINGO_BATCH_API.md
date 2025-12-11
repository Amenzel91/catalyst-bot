# Fix: Implement Tiingo Batch API

> **Claude Code CLI Implementation Guide**
> Priority: P0 - Critical | Risk: Low | Estimated Impact: 93% API call reduction

---

## Problem Summary

| Metric | Current | After Fix |
|--------|---------|-----------|
| Tiingo API calls/hour | 1,380 | ~96 |
| Rate limit (paid tier) | 417/hour | 417/hour |
| Status | **3.3x OVER limit** | **76% UNDER limit** |
| Failure rate | 77% | <5% |

**Root Cause:** `batch_get_prices()` uses yfinance batch download, NOT Tiingo batch API. Tiingo is called individually per ticker via `_tiingo_last_prev()`.

---

## Implementation Tickets

### TICKET-1: Add Tiingo Batch Function

**File:** `src/catalyst_bot/market.py`
**Insert Location:** Lines 280-281 (between `_tiingo_last_prev()` and `_tiingo_intraday_series()`)

**Context:**
```
Line 279: End of _tiingo_last_prev()
Line 280: [BLANK - INSERT HERE]
Line 281: [BLANK - INSERT HERE]
Line 282: def _tiingo_intraday_series(...)
```

**Code to Insert:**

```python
def _tiingo_batch_prices(
    tickers: List[str],
    api_key: str,
    timeout: int = 10
) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """
    Fetch prices for multiple tickers in a single Tiingo API call.

    Parameters
    ----------
    tickers : List[str]
        List of ticker symbols (max 100 per call)
    api_key : str
        Tiingo API key
    timeout : int
        Request timeout in seconds

    Returns
    -------
    Dict[str, Tuple[Optional[float], Optional[float]]]
        Mapping of ticker → (last_price, change_pct)
    """
    if not tickers or not api_key:
        return {}

    try:
        url = "https://api.tiingo.com/iex"
        params = {
            "token": api_key.strip(),
            "tickers": ",".join(t.strip().upper() for t in tickers[:100]),
        }

        r = requests.get(url, params=params, timeout=timeout)

        # Handle rate limiting
        if r.status_code == 429:
            log.warning("tiingo_batch_rate_limited status=429")
            return {}

        if r.status_code != 200:
            log.warning("tiingo_batch_http_error status=%d", r.status_code)
            return {}

        try:
            data = r.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            log.warning("tiingo_batch_invalid_json err=%s", str(e))
            return {}

        if not isinstance(data, list):
            log.warning("tiingo_batch_unexpected_format type=%s", type(data).__name__)
            return {}

        # Parse IEX batch response
        results = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue

            ticker = entry.get("ticker")
            if not ticker:
                continue

            last_price = entry.get("last") or entry.get("tngoLast")
            prev_close = entry.get("prevClose")

            change_pct = None
            if last_price is not None and prev_close is not None and abs(prev_close) > 1e-9:
                change_pct = ((last_price - prev_close) / prev_close) * 100.0

            results[ticker.upper()] = (
                float(last_price) if last_price is not None else None,
                float(change_pct) if change_pct is not None else None
            )

        log.info(
            "tiingo_batch_success requested=%d fetched=%d",
            len(tickers),
            len(results)
        )

        return results

    except requests.exceptions.Timeout:
        log.warning("tiingo_batch_timeout")
        return {}
    except Exception as e:
        log.warning("tiingo_batch_error err=%s", e.__class__.__name__)
        return {}
```

---

### TICKET-2: Modify batch_get_prices() to Use Tiingo Batch

**File:** `src/catalyst_bot/market.py`
**Function:** `batch_get_prices()` (starts at line 701)
**Modify Location:** Insert after line 709 (after the empty tickers check)

**Current Code (lines 701-715):**
```python
def batch_get_prices(
    tickers: list[str],
) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Batch fetch prices for multiple tickers."""
    if not tickers:
        return {}

    # ... yfinance batch code follows ...
```

**New Code to Insert After Line 709:**

```python
    # OPTIMIZATION: Try Tiingo batch API first if enabled
    try:
        settings = get_settings()
        if settings and getattr(settings, "feature_tiingo", False):
            tiingo_key = getattr(settings, "tiingo_api_key", "")
            if tiingo_key:
                t0 = time.perf_counter()
                tiingo_results = _tiingo_batch_prices(tickers, tiingo_key)

                if tiingo_results:
                    success_rate = len(tiingo_results) / len(tickers)

                    if success_rate >= 0.8:
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        log.info(
                            "batch_fetch_tiingo_primary tickers=%d success_rate=%.1f%% t_ms=%.1f",
                            len(tickers),
                            success_rate * 100,
                            elapsed_ms
                        )

                        # Fill missing tickers with (None, None)
                        for ticker in tickers:
                            norm_t = ticker.strip().upper()
                            if norm_t and norm_t not in tiingo_results:
                                tiingo_results[norm_t] = (None, None)

                        return tiingo_results
                    else:
                        log.warning(
                            "tiingo_batch_low_success rate=%.1f%% falling_back_to_yf",
                            success_rate * 100
                        )
    except Exception as e:
        log.warning("tiingo_batch_attempt_failed err=%s using_yf", e.__class__.__name__)

    # FALLBACK: Continue to existing yfinance batch code below...
```

---

### TICKET-3: Add Rate Limit Detection to Individual Calls

**File:** `src/catalyst_bot/market.py`
**Function:** `get_last_price_snapshot()` (starts at line 417)
**Tiingo Section:** Lines 547-579
**Modify Location:** Line 574 (exception handling)

**Current Code (lines 574-577):**
```python
                    except Exception as e:
                        _log_provider(
                            "tiingo", t0, None, None, error=str(e.__class__.__name__)
                        )
```

**Replace With:**
```python
                    except Exception as e:
                        # Check for rate limiting (429)
                        if hasattr(e, 'response') and getattr(e.response, 'status_code', 0) == 429:
                            log.warning("tiingo_rate_limited_individual ticker=%s", nt)
                            break  # Stop retrying, move to next provider
                        _log_provider(
                            "tiingo", t0, None, None, error=str(e.__class__.__name__)
                        )
```

---

## Wiring Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         market.py                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Line 15: import requests                                        │
│                                                                  │
│  Lines 212-279: _tiingo_last_prev()  ← Individual ticker calls   │
│                                                                  │
│  Lines 280-281: [INSERT] _tiingo_batch_prices()  ← NEW FUNCTION  │
│                                                                  │
│  Lines 282-414: _tiingo_intraday_series()                        │
│                                                                  │
│  Lines 417-680: get_last_price_snapshot()                        │
│      └─ Lines 547-579: Tiingo provider block                     │
│          └─ Line 558: _tiingo_last_prev(nt, key) call            │
│          └─ Line 574: Exception handling ← MODIFY for 429        │
│                                                                  │
│  Lines 701-915: batch_get_prices()                               │
│      └─ Line 709: Empty check                                    │
│      └─ [INSERT] Tiingo batch call (after line 709)              │
│      └─ Line 753: yf.download() ← Existing yfinance fallback     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## CLI Implementation Steps

### Step 1: Open market.py and add the batch function

```bash
# Claude Code will:
# 1. Read src/catalyst_bot/market.py
# 2. Find line 280 (after _tiingo_last_prev ends)
# 3. Insert _tiingo_batch_prices() function
```

### Step 2: Modify batch_get_prices()

```bash
# Claude Code will:
# 1. Find batch_get_prices() at line 701
# 2. Insert Tiingo batch call after line 709
# 3. Preserve existing yfinance fallback
```

### Step 3: Add rate limit detection

```bash
# Claude Code will:
# 1. Find exception handling at line 574
# 2. Add 429 status code check
```

---

## Testing Plan

### Unit Test (create tests/test_tiingo_batch.py)

```python
import pytest
from unittest.mock import patch, MagicMock

def test_tiingo_batch_valid_response():
    """Test parsing of valid Tiingo IEX batch response."""
    from src.catalyst_bot.market import _tiingo_batch_prices

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"ticker": "AAPL", "last": 150.0, "prevClose": 148.0},
        {"ticker": "MSFT", "last": 300.0, "prevClose": 295.0},
    ]

    with patch("requests.get", return_value=mock_response):
        result = _tiingo_batch_prices(["AAPL", "MSFT"], "test_key")

    assert "AAPL" in result
    assert "MSFT" in result
    assert result["AAPL"][0] == 150.0  # last price

def test_tiingo_batch_rate_limit():
    """Test handling of 429 rate limit response."""
    from src.catalyst_bot.market import _tiingo_batch_prices

    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch("requests.get", return_value=mock_response):
        result = _tiingo_batch_prices(["AAPL"], "test_key")

    assert result == {}
```

### Integration Test

```bash
# Run full cycle with Tiingo batch enabled
FEATURE_TIINGO=1 python -m catalyst_bot.runner --once

# Check logs for:
grep "tiingo_batch_success" data/logs/bot.jsonl
grep "batch_fetch_tiingo_primary" data/logs/bot.jsonl
```

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| API calls/hour | 1,380 | ~96 |
| Call pattern | 30 individual/cycle | 1 batch/cycle |
| Rate limit usage | 330% | 23% |
| Error rate | 77% | <5% |
| Cycle speed | Slower (sequential) | Faster (batch) |

---

## Rollback Plan

**Option 1: Disable feature flag**
```bash
# In .env
FEATURE_TIINGO=0
```

**Option 2: Revert commit**
```bash
git revert <commit-hash>
```

**Risk: LOW** - All existing yfinance fallback logic preserved.

---

## Definition Reference

| Term | Definition |
|------|------------|
| `_tiingo_batch_prices()` | NEW function to fetch multiple tickers in one API call |
| `batch_get_prices()` | Existing function at line 701 that fetches prices for multiple tickers |
| `get_last_price_snapshot()` | Existing function at line 417 for single ticker price fetch |
| `_tiingo_last_prev()` | Existing function at lines 212-279 for individual Tiingo calls |
| `feature_tiingo` | Config flag in config.py (line 55) to enable/disable Tiingo |
| `tiingo_api_key` | Config setting in config.py (line 50) for API authentication |

---

**Created:** 2025-12-11
**Updated:** 2025-12-11 (corrected line numbers, added CLI instructions)
**Validated:** Cross-referenced with actual codebase
