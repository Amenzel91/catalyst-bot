# Fix: Implement Tiingo Batch API

## Problem
Current system makes **1,380 individual Tiingo API calls per hour**, exceeding rate limits by 3.3x (limit: 417/hour on paid tier). This causes 77% of calls to fail with `tiingo_invalid_json` errors.

## Root Cause
`batch_get_prices()` in `src/catalyst_bot/market.py` uses yfinance batch download, NOT Tiingo batch API. Tiingo is called individually for each ticker in `get_last_price_change()`.

**Current Flow:**
```
30 tickers/cycle × 46 cycles/hour = 1,380 individual Tiingo calls/hour
```

## Solution
Implement Tiingo batch endpoint to reduce API calls by 30x.

**Tiingo Batch Endpoint:**
```
GET https://api.tiingo.com/tiingo/daily/prices?tickers=AAPL,MSFT,GOOGL&token=XXX
```

**New Flow:**
```
1 batch call/cycle × 46 cycles/hour = 46 Tiingo calls/hour (safe!)
```

---

## Implementation Plan

### File: `src/catalyst_bot/market.py`

### Step 1: Add Tiingo Batch Function (Insert after line 280)

```python
def _tiingo_batch_prices(
    tickers: List[str],
    api_key: str,
    timeout: int = 10
) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """
    Fetch prices for multiple tickers in a single Tiingo API call.

    Returns
    -------
    Dict[str, Tuple[Optional[float], Optional[float]]]
        Mapping of ticker → (last_price, change_pct)
    """
    if not tickers or not api_key:
        return {}

    try:
        url = "https://api.tiingo.com/tiingo/daily/prices"
        params = {
            "token": api_key.strip(),
            "tickers": ",".join(t.strip().upper() for t in tickers[:100]),  # Max 100 tickers
            "startDate": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
            "endDate": datetime.now().strftime("%Y-%m-%d"),
        }

        r = requests.get(url, params=params, timeout=timeout)

        # Detect rate limiting
        if r.status_code == 429:
            log.warning("tiingo_rate_limited status=429 cooldown=5s")
            time.sleep(5)
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

        # Parse batch response
        results = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue

            ticker = entry.get("ticker")
            if not ticker:
                continue

            # Get ticker-specific price data (nested list)
            price_data = entry.get("priceData", [])
            if not price_data or not isinstance(price_data, list):
                continue

            # Sort by date descending to get most recent
            price_data.sort(key=lambda x: x.get("date", ""), reverse=True)

            if len(price_data) >= 1:
                last_day = price_data[0]
                close = last_day.get("close")

                # Calculate change from previous day
                change_pct = None
                if len(price_data) >= 2:
                    prev_day = price_data[1]
                    prev_close = prev_day.get("close")

                    if close is not None and prev_close is not None and abs(prev_close) > 1e-9:
                        change_pct = ((close - prev_close) / prev_close) * 100.0

                results[ticker] = (
                    float(close) if close is not None else None,
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

### Step 2: Modify `batch_get_prices()` (Line 701)

**BEFORE** (line 733-760):
```python
def batch_get_prices(tickers: list[str]) -> Dict[...]:
    """Batch fetch prices for multiple tickers."""
    if not tickers:
        return {}

    if yf is None:
        log.warning("yfinance_missing batch_fetch_skipped")
        return {ticker: (None, None) for ticker in tickers}

    # ... yfinance batch download code ...
```

**AFTER**:
```python
def batch_get_prices(tickers: list[str]) -> Dict[...]:
    """Batch fetch prices for multiple tickers (tries Tiingo batch first, then yfinance)."""
    if not tickers:
        return {}

    # OPTIMIZATION: Try Tiingo batch API first if enabled
    try:
        settings = get_settings()
        if settings and getattr(settings, "feature_tiingo", False):
            tiingo_key = getattr(settings, "tiingo_api_key", "")
            if tiingo_key:
                t0 = time.perf_counter()
                tiingo_results = _tiingo_batch_prices(tickers, tiingo_key)

                if tiingo_results:
                    # Check if we got most tickers (>80% success)
                    success_rate = len(tiingo_results) / len(tickers)

                    if success_rate >= 0.8:
                        # Good batch result - use Tiingo as primary
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        log.info(
                            "batch_fetch_tiingo_primary tickers=%d success_rate=%.1f%% t_ms=%.1f",
                            len(tickers),
                            success_rate * 100,
                            elapsed_ms
                        )

                        # Fill missing tickers with (None, None)
                        for ticker in tickers:
                            norm_t = _norm_ticker(ticker)
                            if norm_t and norm_t not in tiingo_results:
                                tiingo_results[norm_t] = (None, None)

                        return tiingo_results
                    else:
                        # Low success rate - fallback to yfinance
                        log.warning(
                            "tiingo_batch_low_success rate=%.1f%% falling_back_to_yf",
                            success_rate * 100
                        )
    except Exception as e:
        log.warning("tiingo_batch_attempt_failed err=%s using_yf", e.__class__.__name__)

    # FALLBACK: Use yfinance batch (existing code preserved)
    if yf is None:
        log.warning("yfinance_missing batch_fetch_skipped")
        return {ticker: (None, None) for ticker in tickers}

    # ... rest of existing yfinance batch code (line 751-849) ...
```

### Step 3: Add Rate Limit Detection to Individual Calls (Line 558)

**In `get_last_price_change()` Tiingo section:**

```python
# Around line 558
if use_tiingo and key:
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            t_last, t_prev = _tiingo_last_prev(nt, key)
            if t_last is not None:
                last = t_last
            if t_prev is not None:
                prev = t_prev
            _log_provider("tiingo", t0, t_last, t_prev)

            if last is not None and prev is not None:
                log.info(
                    "provider provider=tiingo ticker=%s role=PRIMARY last=%.2f prev=%.2f",
                    nt, last, prev,
                )
                return last, prev

        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                log.warning("tiingo_rate_limited_individual ticker=%s", nt)
                break  # Stop retrying, move to next provider
            _log_provider("tiingo", t0, None, None, error=str(e.__class__.__name__))
        except Exception as e:
            _log_provider("tiingo", t0, None, None, error=str(e.__class__.__name__))

        time.sleep(0.35 * (attempt + 1))
```

---

## Expected Impact

**Before:**
- 1,380 API calls/hour
- 77% failure rate
- Exceeds rate limit by 3.3x

**After:**
- 46 batch calls/hour (primary path)
- <50 individual fallback calls/hour
- Total: ~96 calls/hour (76% under limit)
- **API call reduction: 93%**

**Performance:**
- Faster: 1 batch call vs 30 individual calls
- More reliable: Well under rate limits
- Better fallback: yfinance preserved

---

## Testing Plan

### Unit Tests
```python
# tests/test_tiingo_batch.py

def test_tiingo_batch_valid_response():
    """Test parsing of valid Tiingo batch response."""
    tickers = ["AAPL", "MSFT"]
    # Mock Tiingo batch endpoint response
    # Assert correct parsing

def test_tiingo_batch_rate_limit():
    """Test handling of 429 rate limit response."""
    # Mock 429 response
    # Assert returns empty dict and logs warning

def test_batch_get_prices_tiingo_primary():
    """Test batch_get_prices uses Tiingo when enabled."""
    # Mock Tiingo batch success
    # Assert Tiingo called, yfinance not called

def test_batch_get_prices_fallback():
    """Test fallback to yfinance on Tiingo failure."""
    # Mock Tiingo failure
    # Assert yfinance called as fallback
```

### Integration Test
```bash
# Run full cycle with Tiingo batch enabled
FEATURE_TIINGO=1 python -m catalyst_bot.runner --loop --sleep-secs 60

# Monitor logs for:
# - "tiingo_batch_success"
# - "batch_fetch_tiingo_primary"
# - Reduced "tiingo_invalid_json" errors
```

---

## Rollback Plan

If issues arise:
1. Set `FEATURE_TIINGO=0` in `.env` (disables Tiingo entirely)
2. System falls back to yfinance (current fallback)
3. Or revert commit

**Risk: Low** - All existing fallback logic preserved.

---

## Monitoring

After deployment, track these metrics:

```python
# Add to cycle_metrics log
log.info(
    "cycle_metrics",
    tiingo_batch_calls=tiingo_batch_call_count,
    tiingo_batch_success_rate=batch_success / batch_calls,
    tiingo_individual_fallback_calls=individual_call_count,
    yfinance_fallback_calls=yf_fallback_count,
)
```

**Success Criteria:**
- Tiingo API calls: <100/hour
- Batch success rate: >80%
- Overall price fetch success: >95%

---

**Created:** 2025-12-11
**Priority:** P0 - Critical (fixes rate limiting)
**Estimated Impact:** 93% API call reduction
**Risk:** Low (fallback preserved)
