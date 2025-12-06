# Fundamental Data Collection System

## Overview

The `fundamental_data.py` module provides a robust data collection system for critical fundamental metrics that predict stock volatility in catalyst trading:

- **Float Shares**: The strongest volatility predictor (4.2x impact vs other factors)
- **Short Interest**: Indicates squeeze potential (>15% suggests high risk)

## Architecture

### Data Source: FinViz Elite

**Important**: FinViz does not provide an official REST API. This module scrapes data from FinViz Elite web pages using authenticated HTTP requests. You must have:

1. Active FinViz Elite subscription ($24.96/month or $39.50/month)
2. Valid Elite authentication cookie

### Caching Strategy

To minimize API calls and respect rate limits, the module implements intelligent SQLite caching:

- **Float Shares**: 30-day cache (quarterly updates sufficient as float changes slowly)
- **Short Interest**: 14-day cache (bi-weekly updates to capture position changes)

Cache location: `data/cache/fundamentals.db`

### Rate Limiting

- Minimum 1 second between requests
- Exponential backoff on failures (2s, 4s, 8s)
- Maximum 3 retry attempts per request

## API Endpoints

The module scrapes these FinViz Elite pages:

```
https://finviz.com/quote.ashx?t={TICKER}
```

**Scraped Fields**:
- `Shs Float`: Total shares available for trading
- `Short Float`: Percentage of float shares sold short

## Installation & Setup

### 1. Install Dependencies

The module requires:
- `requests`: HTTP client
- `beautifulsoup4`: HTML parsing
- Standard library: `sqlite3`, `pathlib`, etc.

Already included in catalyst-bot requirements.

### 2. Configure Authentication

Set your FinViz Elite authentication cookie:

```bash
# Preferred method
export FINVIZ_API_KEY="your_elite_cookie_value"

# Alternative environment variables (backward compatible)
export FINVIZ_ELITE_AUTH="your_elite_cookie_value"
export FINVIZ_AUTH_TOKEN="your_elite_cookie_value"
```

**How to get your Elite cookie**:

1. Log in to FinViz Elite in your browser
2. Open Developer Tools (F12)
3. Go to Application → Cookies → https://finviz.com
4. Copy the value of the `elite` cookie
5. Set it as `FINVIZ_API_KEY` environment variable

### 3. Optional: Configure Cache Location

```bash
export FUNDAMENTALS_CACHE_DB="data/cache/fundamentals.db"
```

## Usage

### Basic Usage

```python
from catalyst_bot.fundamental_data import get_float_shares, get_short_interest

# Get float shares
float_shares = get_float_shares("AAPL")
if float_shares:
    print(f"Float: {float_shares:,.0f} shares")

# Get short interest percentage
short_pct = get_short_interest("GME")
if short_pct and short_pct > 15.0:
    print(f"High squeeze potential: {short_pct:.1f}%")
```

### Efficient Batch Fetching

```python
from catalyst_bot.fundamental_data import get_fundamentals

# Get both metrics in one call (single page fetch)
float_shares, short_pct = get_fundamentals("TSLA")
if float_shares and short_pct:
    print(f"Float: {float_shares:,.0f}, Short: {short_pct:.2f}%")
```

### Volatility Scoring Example

```python
from catalyst_bot.fundamental_data import get_fundamentals

def calculate_volatility_score(ticker: str) -> int:
    """Calculate volatility score (0-6) based on fundamentals."""
    float_shares, short_pct = get_fundamentals(ticker)

    score = 0

    # Float component (0-3 points)
    if float_shares:
        if float_shares < 10_000_000:
            score += 3  # Very low float
        elif float_shares < 50_000_000:
            score += 2  # Low float
        elif float_shares < 100_000_000:
            score += 1  # Medium float

    # Short interest component (0-3 points)
    if short_pct:
        if short_pct > 20.0:
            score += 3  # Very high short
        elif short_pct > 15.0:
            score += 2  # High short
        elif short_pct > 10.0:
            score += 1  # Moderate short

    return score

# Example usage
score = calculate_volatility_score("GME")
if score >= 5:
    print("EXTREME volatility potential!")
elif score >= 3:
    print("High volatility potential")
```

### Cache Management

```python
from catalyst_bot.fundamental_data import clear_cache

# Clear cache for specific ticker
clear_cache("AAPL")

# Clear specific metric for ticker
clear_cache("AAPL", "short_interest")

# Clear all cache (force fresh data)
clear_cache()
```

## Function Reference

### `get_float_shares(ticker: str) -> Optional[float]`

Retrieve float shares for a ticker.

**Parameters**:
- `ticker`: Stock ticker symbol (case-insensitive)

**Returns**:
- Float shares count, or `None` if unavailable

**Caching**: 30 days

**Example**:
```python
float_shares = get_float_shares("AAPL")
if float_shares and float_shares < 10_000_000:
    print("Low float - explosive potential!")
```

---

### `get_short_interest(ticker: str) -> Optional[float]`

Retrieve short interest percentage for a ticker.

**Parameters**:
- `ticker`: Stock ticker symbol (case-insensitive)

**Returns**:
- Short interest as percentage (e.g., 25.5 for 25.5%), or `None` if unavailable

**Caching**: 14 days

**Example**:
```python
short_pct = get_short_interest("GME")
if short_pct and short_pct > 15.0:
    print("High squeeze potential!")
```

---

### `get_fundamentals(ticker: str) -> Tuple[Optional[float], Optional[float]]`

Get both float shares and short interest in a single call.

More efficient than calling `get_float_shares()` and `get_short_interest()` separately, as it fetches the quote page only once.

**Parameters**:
- `ticker`: Stock ticker symbol (case-insensitive)

**Returns**:
- Tuple of `(float_shares, short_interest_pct)`
- Either value may be `None` if unavailable

**Example**:
```python
float_shares, short_pct = get_fundamentals("TSLA")
if float_shares and short_pct:
    print(f"Float: {float_shares:,.0f}, Short: {short_pct:.1f}%")
```

---

### `clear_cache(ticker: Optional[str] = None, metric: Optional[str] = None) -> int`

Clear cached fundamental data.

**Parameters**:
- `ticker`: If provided, clear only this ticker's cache
- `metric`: If provided, clear only this metric (requires `ticker`)

**Returns**:
- Number of cache entries cleared

**Examples**:
```python
# Clear all cache
count = clear_cache()

# Clear cache for specific ticker
count = clear_cache("AAPL")

# Clear specific metric for ticker
count = clear_cache("AAPL", "short_interest")
```

## Error Handling

The module implements comprehensive error handling:

1. **Authentication Errors**: Returns `None` if auth token is missing or invalid
2. **Network Errors**: Retries with exponential backoff (up to 3 attempts)
3. **Rate Limiting**: Automatic rate limiting (1 second minimum between requests)
4. **Parse Errors**: Returns `None` if data cannot be parsed
5. **Cache Errors**: Falls back to live fetch if cache is corrupted

All errors are logged with structured telemetry:

```python
log.error("finviz_auth_failed ticker=%s status=%d", ticker, status_code)
log.warning("finviz_timeout ticker=%s attempt=%d", ticker, attempt)
log.info("float_shares_fetched ticker=%s value=%.0f", ticker, value)
```

## Performance Considerations

### Cache Hit Rates

- **First fetch**: ~1-2 seconds (HTTP request + parsing)
- **Cache hit**: <1ms (SQLite query)

### Batch Processing

For processing multiple tickers:

```python
# GOOD: Use get_fundamentals() for efficiency
for ticker in tickers:
    float_shares, short_pct = get_fundamentals(ticker)
    # Single HTTP request per ticker

# AVOID: Separate calls waste requests
for ticker in tickers:
    float_shares = get_float_shares(ticker)
    short_pct = get_short_interest(ticker)
    # Two HTTP requests per ticker (2x slower!)
```

### Rate Limiting Impact

With 1-second minimum between requests:
- 10 tickers: ~10 seconds (first fetch)
- 10 tickers: <10ms (cache hits)

## Limitations

1. **No Official API**: Relies on web scraping, which may break if FinViz changes their HTML structure
2. **Elite Subscription Required**: Free FinViz does not provide float/short data
3. **Rate Limits**: FinViz may implement stricter rate limits or CAPTCHA if abuse is detected
4. **Data Freshness**: Short interest updates bi-weekly (from exchanges), so cache may be stale
5. **No Historical Data**: Module only provides current values, not historical trends

## Integration with Catalyst Bot

### In Analyzer

```python
from catalyst_bot.fundamental_data import get_fundamentals

def analyze_event(event):
    ticker = event.get("ticker")
    float_shares, short_pct = get_fundamentals(ticker)

    # Boost score for low float
    if float_shares and float_shares < 10_000_000:
        event["score"] *= 1.5
        event["tags"].append("LOW_FLOAT")

    # Flag squeeze potential
    if short_pct and short_pct > 15.0:
        event["squeeze_risk"] = "HIGH"
        event["tags"].append("SQUEEZE_CANDIDATE")

    return event
```

### In Screener

```python
from catalyst_bot.fundamental_data import get_fundamentals

def screen_tickers(tickers):
    """Filter for low float, high short interest stocks."""
    candidates = []

    for ticker in tickers:
        float_shares, short_pct = get_fundamentals(ticker)

        if not float_shares or not short_pct:
            continue

        # Criteria: <50M float AND >15% short
        if float_shares < 50_000_000 and short_pct > 15.0:
            candidates.append({
                "ticker": ticker,
                "float": float_shares,
                "short_pct": short_pct,
                "volatility_score": calculate_score(float_shares, short_pct),
            })

    # Sort by volatility score
    candidates.sort(key=lambda x: x["volatility_score"], reverse=True)
    return candidates
```

## Troubleshooting

### Problem: "RuntimeError: FinViz Elite authentication token not found"

**Solution**: Set the `FINVIZ_API_KEY` environment variable with your Elite cookie.

```bash
export FINVIZ_API_KEY="your_elite_cookie_value"
```

### Problem: Getting `None` for all tickers

**Possible causes**:
1. Invalid/expired Elite cookie
2. FinViz changed their HTML structure
3. Network connectivity issues

**Debug steps**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

from catalyst_bot.fundamental_data import get_float_shares
result = get_float_shares("AAPL")
# Check logs for specific error
```

### Problem: Slow performance

**Solution**: Ensure cache is being used. Check cache hit logs:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from catalyst_bot.fundamental_data import get_float_shares
get_float_shares("AAPL")  # First call: should see "cache_miss"
get_float_shares("AAPL")  # Second call: should see "cache_hit"
```

### Problem: "finviz_rate_limit" errors

**Solution**: You're making too many requests. The module implements rate limiting, but if you're running multiple instances:

1. Reduce concurrent instances
2. Increase `MIN_REQUEST_INTERVAL_SEC` in `fundamental_data.py`
3. Use batch processing with `get_fundamentals()` instead of separate calls

## Future Enhancements

Potential improvements for future versions:

1. **Historical Data**: Store historical float/short values for trend analysis
2. **Additional Metrics**: Parse more fundamentals (market cap, P/E, etc.)
3. **Async Support**: Add async variants for concurrent fetching
4. **Proxy Support**: Rotate proxies to avoid rate limits
5. **Browser Automation**: Use Selenium for CAPTCHA handling
6. **Data Validation**: Cross-reference with other sources (Yahoo Finance, etc.)

## License & Disclaimer

This module is part of the Catalyst Bot project and is intended for personal use only.

**Disclaimer**: Web scraping may violate FinViz's Terms of Service. Use at your own risk. The authors are not responsible for any service interruptions or account suspensions resulting from use of this module.

**Recommendation**: Contact FinViz directly about enterprise data access or API partnerships for production use.
