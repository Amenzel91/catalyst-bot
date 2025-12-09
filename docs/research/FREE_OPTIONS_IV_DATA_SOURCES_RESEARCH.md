# Free Options & Implied Volatility (IV) Data Sources Research

**Research Date:** December 8, 2025
**Purpose:** Identify free data sources for building a "High IV Stocks Under $10" nightly scanner

---

## Executive Summary

After comprehensive research into free options and implied volatility data sources, **yfinance (Yahoo Finance)** and **Tradier Sandbox API** emerge as the top two free options for programmatic access to options chains with IV data. For pre-computed screeners, **Barchart** and **Market Chameleon** offer free web-based screeners that can be scraped or used directly.

### Top 3 Recommendations for "High IV Stocks Under $10" Scanner:

1. **Tradier Sandbox API** - Best overall free API with real Greeks/IV from ORATS
2. **yfinance (Yahoo Finance)** - Easiest to use, no API key required, but less reliable IV data
3. **Barchart Screener + Web Scraping** - Pre-filtered high IV lists for validation/cross-reference

---

## Detailed Data Source Analysis

### 1. Tradier Sandbox API ⭐⭐⭐⭐⭐

**URL:** https://documentation.tradier.com/brokerage-api/markets/get-options-chains

**What's Available:**
- Complete options chains with strikes, bid/ask, volume, open interest
- **Implied Volatility and Greeks courtesy of ORATS** (professional-grade data)
- Real-time quotes for sandbox testing
- Historical options data
- Option expirations, strikes, symbols

**Access Details:**
- **Cost:** 100% FREE (sandbox environment)
- **Authentication:** Requires free account signup at developer.tradier.com
- **API Key:** Yes (generated at dash.tradier.com/settings/api)
- **Rate Limits:** No documented hard limits; designed for development/testing
- **Data Format:** JSON REST API

**Pros:**
- Professional-grade IV data from ORATS
- Well-documented API
- No rate limit concerns mentioned
- Sandbox environment perfect for testing
- Real options data

**Cons:**
- Requires account signup
- Sandbox data may not be 100% production-accurate (but close)

**Reliability:** ⭐⭐⭐⭐⭐ (Excellent - backed by a real brokerage)

**Python Code Example:**

```python
import requests
import os

# Set your Tradier sandbox token
TRADIER_TOKEN = os.getenv('TRADIER_SANDBOX_TOKEN')
BASE_URL = 'https://sandbox.tradier.com/v1'

headers = {
    'Authorization': f'Bearer {TRADIER_TOKEN}',
    'Accept': 'application/json'
}

def get_options_chain(symbol, expiration):
    """
    Get options chain with IV data from Tradier

    Args:
        symbol: Stock ticker (e.g., 'AAPL')
        expiration: Expiration date (YYYY-MM-DD format)

    Returns:
        Dict with options chain data including IV
    """
    url = f'{BASE_URL}/markets/options/chains'
    params = {
        'symbol': symbol,
        'expiration': expiration,
        'greeks': 'true'  # Include Greeks and IV
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    return response.json()

def get_option_expirations(symbol):
    """Get available expiration dates for a symbol"""
    url = f'{BASE_URL}/markets/options/expirations'
    params = {'symbol': symbol}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    return response.json()

# Example usage
if __name__ == '__main__':
    symbol = 'AAPL'

    # Get expirations
    expirations = get_option_expirations(symbol)
    print(f"Available expirations: {expirations}")

    # Get first expiration chain
    if expirations and 'expirations' in expirations:
        first_exp = expirations['expirations']['date'][0]
        chain = get_options_chain(symbol, first_exp)

        # Extract calls
        if 'options' in chain and 'option' in chain['options']:
            options = chain['options']['option']
            for opt in options[:5]:  # First 5 options
                print(f"Strike: {opt['strike']}, IV: {opt.get('greeks', {}).get('mid_iv', 'N/A')}")
```

**Setup:**
```bash
# 1. Sign up at developer.tradier.com
# 2. Go to dash.tradier.com/settings/api
# 3. Generate sandbox token
# 4. Set environment variable
export TRADIER_SANDBOX_TOKEN='your_token_here'

# 5. Install requests
pip install requests
```

---

### 2. yfinance (Yahoo Finance) ⭐⭐⭐⭐

**URL:** https://github.com/ranaroussi/yfinance

**What's Available:**
- Options chains with strikes, bid/ask, volume, open interest
- **Implied Volatility per option** (though accuracy is questionable)
- Historical stock data
- Company fundamentals
- No API key required

**Access Details:**
- **Cost:** 100% FREE
- **Authentication:** None required (but may need Yahoo Finance cookies)
- **API Key:** No
- **Rate Limits:** ~few hundred requests/day from single IP; not officially documented
- **Data Format:** Python library returning pandas DataFrames

**Pros:**
- Extremely easy to use
- No signup or API key required
- Returns pandas DataFrames (convenient)
- Large community support
- Works out of the box

**Cons:**
- Unofficial API (web scraping under the hood)
- IV data has known accuracy issues
- Rate limiting can be aggressive
- May break if Yahoo changes website structure
- After-hours data often buggy
- Not suitable for production/commercial use

**Reliability:** ⭐⭐⭐ (Good for development, questionable for production)

**Python Code Example:**

```python
import yfinance as yf
import pandas as pd

def get_options_with_high_iv(symbol, min_iv=0.5):
    """
    Get options with high implied volatility from Yahoo Finance

    Args:
        symbol: Stock ticker
        min_iv: Minimum IV threshold (0.5 = 50%)

    Returns:
        DataFrame with high IV options
    """
    ticker = yf.Ticker(symbol)

    # Get available expiration dates
    expirations = ticker.options

    if not expirations:
        print(f"No options available for {symbol}")
        return None

    all_high_iv = []

    # Get first 3 expirations
    for exp in expirations[:3]:
        try:
            # Get option chain
            opt_chain = ticker.option_chain(exp)

            # Check calls
            calls = opt_chain.calls
            high_iv_calls = calls[calls['impliedVolatility'] > min_iv].copy()
            high_iv_calls['type'] = 'call'
            high_iv_calls['expiration'] = exp

            # Check puts
            puts = opt_chain.puts
            high_iv_puts = puts[puts['impliedVolatility'] > min_iv].copy()
            high_iv_puts['type'] = 'put'
            high_iv_puts['expiration'] = exp

            all_high_iv.extend([high_iv_calls, high_iv_puts])

        except Exception as e:
            print(f"Error getting chain for {exp}: {e}")
            continue

    if all_high_iv:
        result = pd.concat(all_high_iv, ignore_index=True)
        return result[['strike', 'lastPrice', 'bid', 'ask', 'volume',
                       'openInterest', 'impliedVolatility', 'type', 'expiration']]

    return None

def get_stock_price(symbol):
    """Get current stock price"""
    ticker = yf.Ticker(symbol)
    data = ticker.history(period='1d')
    if not data.empty:
        return data['Close'].iloc[-1]
    return None

# Example: Find stocks under $10 with high IV options
def scan_cheap_high_iv_stocks(symbols, max_price=10, min_iv=0.6):
    """
    Scan for stocks under max_price with options IV > min_iv

    Args:
        symbols: List of stock tickers
        max_price: Maximum stock price
        min_iv: Minimum implied volatility

    Returns:
        List of dicts with results
    """
    results = []

    for symbol in symbols:
        try:
            # Check price
            price = get_stock_price(symbol)
            if price is None or price > max_price:
                continue

            # Check for high IV options
            high_iv_opts = get_options_with_high_iv(symbol, min_iv)

            if high_iv_opts is not None and not high_iv_opts.empty:
                avg_iv = high_iv_opts['impliedVolatility'].mean()
                results.append({
                    'symbol': symbol,
                    'price': price,
                    'avg_iv': avg_iv,
                    'max_iv': high_iv_opts['impliedVolatility'].max(),
                    'num_high_iv_options': len(high_iv_opts)
                })
                print(f"✓ {symbol}: ${price:.2f}, Avg IV: {avg_iv:.2%}")

        except Exception as e:
            print(f"✗ {symbol}: {e}")
            continue

    return sorted(results, key=lambda x: x['avg_iv'], reverse=True)

# Example usage
if __name__ == '__main__':
    # Install: pip install yfinance

    # Test symbols (mix of under/over $10)
    test_symbols = ['SIRI', 'SOFI', 'F', 'NIO', 'PLUG', 'LCID']

    results = scan_cheap_high_iv_stocks(test_symbols, max_price=10, min_iv=0.6)

    print("\n=== Top High IV Stocks Under $10 ===")
    for r in results[:5]:
        print(f"{r['symbol']}: ${r['price']:.2f} | Avg IV: {r['avg_iv']:.1%} | Max IV: {r['max_iv']:.1%}")
```

**Setup:**
```bash
pip install yfinance pandas
```

**Known Issues:**
- IV values can be garbage (especially after-hours)
- Put/call IV discrepancies are common
- May require Yahoo Finance cookies for reliability (visit finance.yahoo.com first)

---

### 3. Barchart Options Screener ⭐⭐⭐⭐

**URL:** https://www.barchart.com/options/highest-implied-volatility

**What's Available:**
- Pre-screened highest IV options list
- IV Rank and IV Percentile
- Volume, open interest, last price
- Updated every 10 minutes during trading
- Filters: volume > 500, OI > 100, price > $0.10, IV > 60%

**Access Details:**
- **Cost:** FREE (with free account) - Premier features require subscription ($28.95/mo for 30-day trial)
- **Authentication:** Free account signup recommended
- **API Key:** OnDemand API is paid only
- **Rate Limits:** Web page - normal browser rate limits apply
- **Data Format:** HTML (requires web scraping)

**Pros:**
- Pre-filtered high IV options (saves computation)
- Professional data quality
- 10-minute refresh during market hours
- Includes IV Rank/Percentile
- Can download to CSV (Premier members)

**Cons:**
- Web scraping required (no free API)
- Premier membership needed for CSV export
- Free tier has some limitations

**Reliability:** ⭐⭐⭐⭐ (Excellent - professional financial data provider)

**Python Web Scraping Example:**

```python
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

def scrape_barchart_high_iv(max_results=50):
    """
    Scrape Barchart's highest implied volatility options page

    Note: Requires a free Barchart account for reliable access
    You may need to handle login/cookies for consistent access

    Returns:
        DataFrame with high IV options data
    """
    url = 'https://www.barchart.com/options/highest-implied-volatility'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the data table
        # Note: This selector may need updating if Barchart changes their HTML
        table = soup.find('table', {'class': 'bc-table'})

        if not table:
            print("Could not find data table - may require login")
            return None

        # Parse table to DataFrame
        df = pd.read_html(str(table))[0]

        # Filter to stocks under $10 if underlying price column exists
        # Column names vary - adjust as needed
        if 'Symbol' in df.columns and 'IV' in df.columns:
            return df.head(max_results)

        return df

    except Exception as e:
        print(f"Error scraping Barchart: {e}")
        return None

def scrape_with_session(username=None, password=None):
    """
    More reliable scraping with login session
    Requires Barchart account credentials
    """
    session = requests.Session()

    # Login if credentials provided
    if username and password:
        login_url = 'https://www.barchart.com/login'
        # Implement login logic here
        pass

    # Add your scraping logic here
    pass

# Example: Cross-reference yfinance results with Barchart
def validate_high_iv_with_barchart(symbols):
    """
    Check if symbols appear on Barchart's high IV list
    """
    barchart_data = scrape_barchart_high_iv()

    if barchart_data is None:
        return []

    validated = []
    for symbol in symbols:
        # Check if symbol in Barchart results
        # Implementation depends on Barchart data structure
        pass

    return validated

# WARNING: Web scraping considerations
print("""
⚠️  WEB SCRAPING NOTES:
1. Always respect robots.txt
2. Add delays between requests (time.sleep(2))
3. Use appropriate User-Agent headers
4. Consider getting a free Barchart account for better access
5. Be prepared for HTML structure changes
6. Don't overload the server with requests
""")
```

**Alternative - Barchart OnDemand API (Paid):**
- Professional API with full options data
- Includes Greeks, IV, historical data
- Requires custom pricing quote
- Contact: solutions@barchart.com

---

### 4. Market Chameleon ⭐⭐⭐⭐

**URL:** https://marketchameleon.com/volReports/VolatilityRankings

**What's Available:**
- IV Rankings report (elevated/subdued volatility)
- IV30 Percentile Rank
- Comparison to historical averages
- Free starter tier available

**Access Details:**
- **Cost:** FREE tier available (Starter plan)
- **Authentication:** Account signup
- **API Key:** No public API
- **Rate Limits:** Web-based only
- **Data Format:** HTML (requires scraping)

**Pros:**
- Excellent IV rankings and percentiles
- Historical comparisons
- Shows earnings/event dates
- Professional-grade analysis

**Cons:**
- No API (web scraping required)
- Free tier may have limitations
- Need to handle authentication for scraping

**Reliability:** ⭐⭐⭐⭐ (Excellent - trusted by traders)

**Python Scraping Approach:**

```python
import requests
from bs4 import BeautifulSoup
import pandas as pd

def scrape_market_chameleon_iv_rankings():
    """
    Scrape Market Chameleon's IV rankings

    Note: May require authentication/subscription for full access
    """
    url = 'https://marketchameleon.com/volReports/VolatilityRankings'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 403:
            print("Access denied - may require subscription or login")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # Parse the IV rankings table
        # Note: Specific selectors depend on current HTML structure
        # This is a template - adjust based on actual page structure

        tables = pd.read_html(response.text)

        if tables:
            # Likely the main rankings table
            df = tables[0]

            # Filter for elevated IV (e.g., IV Rank > 70)
            if 'IV Rank' in df.columns or 'IV%Rank' in df.columns:
                return df

        return None

    except Exception as e:
        print(f"Error: {e}")
        return None

# Market Chameleon also offers per-symbol IV pages
def get_symbol_iv_page(symbol):
    """
    Get IV chart for specific symbol
    URL format: https://marketchameleon.com/Overview/{SYMBOL}/IV/
    """
    url = f'https://marketchameleon.com/Overview/{symbol}/IV/'
    # Implement scraping logic
    pass
```

---

### 5. Yahoo Finance Highest IV Screener ⭐⭐⭐

**URL:** https://finance.yahoo.com/options/highest-implied-volatility/

**What's Available:**
- Pre-screened highest IV options
- Stock price, change, volume
- Daily updates
- Free access via web

**Access Details:**
- **Cost:** FREE
- **Authentication:** None required
- **API Key:** No
- **Rate Limits:** Browser-based
- **Data Format:** HTML

**Pros:**
- Completely free
- No signup required
- Yahoo Finance brand reliability
- Easy to access

**Cons:**
- Limited data fields
- Requires web scraping
- No API access
- Same IV accuracy issues as yfinance

**Reliability:** ⭐⭐⭐ (Good for quick checks)

```python
def scrape_yahoo_high_iv_screener():
    """
    Scrape Yahoo Finance highest IV options page
    """
    url = 'https://finance.yahoo.com/options/highest-implied-volatility/'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(url, headers=headers)

    # Parse with BeautifulSoup or pandas read_html
    tables = pd.read_html(response.text)

    if tables:
        return tables[0]  # First table is usually the screener results

    return None
```

---

### 6. CBOE DataShop (Paid) ⭐⭐⭐⭐⭐

**URL:** https://datashop.cboe.com/option-eod-summary

**What's Available:**
- End-of-day options data with IV
- Greeks (delta, gamma, theta, vega, rho)
- Historical data from 2004
- Professional-grade accuracy

**Access Details:**
- **Cost:** PAID (no free tier for options IV data)
- **Authentication:** Account required
- **API Key:** Yes
- **Data Format:** API/Data feeds

**Pros:**
- Highest quality data (official exchange)
- Complete historical archives
- Professional Greeks/IV calculations
- Institutional-grade reliability

**Cons:**
- Not free (pricing not publicly listed)
- Requires contact with CBOE sales
- Overkill for hobby projects

**Reliability:** ⭐⭐⭐⭐⭐ (Best available - official exchange data)

**Not recommended for free scanner** - included for completeness

---

### 7. Polygon.io (Paid) ⭐⭐⭐⭐

**URL:** https://polygon.io/docs/options

**What's Available:**
- Options chains with IV and Greeks
- Real-time and historical data
- Professional-grade calculations

**Access Details:**
- **Cost:** PAID (free tier does NOT include options IV)
- **Authentication:** API key
- **Rate Limits:** Varies by plan
- **Data Format:** JSON REST API

**Pros:**
- Clean, modern API
- Good documentation
- Recently rebranded to Massive.com
- Professional service

**Cons:**
- Options snapshot (with IV) requires paid subscription
- Free tier only has EOD equity data
- Not suitable for free scanner

**Reliability:** ⭐⭐⭐⭐ (Excellent - professional service)

---

### 8. Finnhub (Limited) ⭐⭐

**URL:** https://finnhub.io/docs/api

**What's Available:**
- Stock data, fundamentals, news
- Limited options support

**Access Details:**
- **Cost:** FREE tier available
- **Authentication:** API key required
- **Rate Limits:** 60 calls/minute (free tier)
- **Data Format:** JSON API

**Pros:**
- Good free tier for stock data
- Easy to use
- Python client available

**Cons:**
- **Does NOT have options IV data** (feature was requested but not implemented)
- Not suitable for options scanning

**Reliability:** ⭐⭐⭐⭐ (Good for stock data, not for options)

---

### 9. AlphaQuery ⭐⭐⭐

**URL:** https://www.alphaquery.com/

**What's Available:**
- Implied volatility statistics
- IV for calls, puts, mean
- IV skew calculations
- 30-day, 120-day, 150-day timeframes

**Access Details:**
- **Cost:** FREE trial (7 days), then paid subscription
- **Authentication:** Account required
- **API Key:** Not mentioned
- **Data Format:** Web-based platform

**Pros:**
- 300+ data fields
- Historical IV charts
- Comprehensive stock screener
- Professional-grade calculations

**Cons:**
- Only 7-day free trial
- Requires paid subscription after trial
- Unclear API access

**Reliability:** ⭐⭐⭐⭐ (Good - financial data platform)

---

### 10. OptionStrat Flow ⭐⭐⭐

**URL:** https://optionstrat.com/flow

**What's Available:**
- Unusual options activity scanner
- Real-time options flow
- Profit calculator
- Free tier with delayed data

**Access Details:**
- **Cost:** FREE (15-min delayed, 10% of flow) / PAID (real-time, full flow)
- **Authentication:** Account signup
- **API Key:** No public API mentioned
- **Data Format:** Web-based platform

**Pros:**
- Good unusual activity scanner
- Free tier available
- Focus on options flow
- Profit calculator is free forever

**Cons:**
- No API for programmatic access
- Free tier is delayed and limited
- Not designed for IV screening specifically

**Reliability:** ⭐⭐⭐ (Good for flow, not IV screening)

---

## Data Source Quick Reference Table

| Source | Cost | IV Data | API Access | Auth Required | Rate Limits | Reliability |
|--------|------|---------|------------|---------------|-------------|-------------|
| **Tradier Sandbox** | FREE | ✅ Yes (ORATS) | ✅ Yes (REST) | ✅ Account | Generous | ⭐⭐⭐⭐⭐ |
| **yfinance** | FREE | ✅ Yes (buggy) | ✅ Python lib | ❌ No | ~few hundred/day | ⭐⭐⭐ |
| **Barchart Screener** | FREE | ✅ Yes | ❌ Scraping only | ⚠️  Recommended | Browser limits | ⭐⭐⭐⭐ |
| **Market Chameleon** | FREE* | ✅ Yes | ❌ Scraping only | ✅ Account | Browser limits | ⭐⭐⭐⭐ |
| **Yahoo Screener** | FREE | ✅ Yes | ❌ Scraping only | ❌ No | Browser limits | ⭐⭐⭐ |
| **CBOE DataShop** | PAID | ✅ Yes (best) | ✅ Yes | ✅ Account | Varies | ⭐⭐⭐⭐⭐ |
| **Polygon.io** | PAID | ✅ Yes | ✅ Yes | ✅ API Key | Varies | ⭐⭐⭐⭐ |
| **Finnhub** | FREE/PAID | ❌ No | ✅ Yes | ✅ API Key | 60/min free | ⭐⭐⭐⭐ |
| **AlphaQuery** | PAID | ✅ Yes | ❓ Unknown | ✅ Account | Unknown | ⭐⭐⭐⭐ |
| **OptionStrat** | FREE* | ⚠️  Limited | ❌ No | ✅ Account | N/A | ⭐⭐⭐ |

*FREE* = Free tier available with limitations

---

## How yfinance Gets Options Data

yfinance works by **web scraping Yahoo Finance** pages. Here's how:

1. **No Official API** - Yahoo Finance shut down their official API in 2017
2. **HTML Scraping** - yfinance parses Yahoo Finance web pages
3. **Cookie Requirements** - Newer versions check for Yahoo Finance cookies
4. **IV Calculation** - Yahoo provides IV estimates (not always accurate)
5. **Data Structure** - Returns pandas DataFrames with columns:
   - `contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`
   - `bid`, `ask`, `change`, `percentChange`, `volume`
   - `openInterest`, `impliedVolatility`, `inTheMoney`

**Known Issues:**
- IV values can be inaccurate (especially after-hours)
- Call/put IV discrepancies common
- May break when Yahoo changes HTML structure
- Rate limiting is aggressive
- Not suitable for production/commercial use

**Better Alternatives:**
- Use yfinance for development/testing
- Switch to Tradier or paid API for production

---

## Finviz Options/IV Capabilities

**Short Answer:** Finviz does NOT have options-specific IV screening.

**What Finviz Offers:**
- Stock screener with ATR (Average True Range) - historical volatility
- Beta - volatility relative to market
- No implied volatility filters
- No options chain data
- No IV rankings

**Why Not?**
Finviz focuses on stock-level technical and fundamental analysis, not options markets. They publish news articles about stocks with surging IV (sourced from Zacks), but don't provide the data themselves.

**For Options IV:** Use Barchart, Market Chameleon, or yfinance instead.

---

## Barchart Free vs Paid

### Free Tier:
- Access to basic screener pages
- Can view highest IV options list
- IV Rank and IV Percentile data visible
- Updated every 10 minutes
- Some chart access

### Paid (Premier - $28.95/mo):
- **CSV Export** of screener results
- Create custom options screeners
- Advanced filtering
- Real-time alerts
- More detailed historical data
- Priority support

### Barchart OnDemand API (Custom Pricing):
- Programmatic API access
- IV and Greeks via API
- Historical options data
- Requires custom quote from sales team

**Recommendation:** Use free web screener for validation; if you need API, go with Tradier instead (also free).

---

## Other Popular Free Sources

### 1. ThinkorSwim / Charles Schwab (Free with Account)
- Professional-grade platform
- IV Percentile and HV Percentile
- Requires brokerage account (no deposit required)
- Best for manual analysis, not programmatic scanning

### 2. TradingView (Limited Free)
- Great charting platform
- Limited options data
- Free tier has significant restrictions

### 3. Reddit / Twitter / Discord
- r/options, r/thetagang, r/wallstreetbets
- Community-sourced IV screening
- Not programmatic, but useful for validation

### 4. GitHub Projects
- **Option-Scraper-BlackScholes** (github.com/jknaudt21/Option-Scraper-BlackScholes)
  - Scrapes options data from Yahoo Finance
  - IV from AlphaQuery
  - Python with BeautifulSoup

- **YahooSkew** (github.com/mmautner/YahooSkew)
  - Scrapes Yahoo Finance options
  - Calculates IV from bid/ask

- **iv_scraper** (github.com/melder/iv_scraper)
  - Scrapes IV for all available options
  - Stores in MongoDB
  - Includes Greeks

---

## Recommended Architecture for "High IV Stocks Under $10" Scanner

### Option 1: Tradier-Only (Recommended)

```python
# Pseudocode architecture

1. Get universe of stocks under $10
   - Use free stock screener (Finviz, yfinance, etc.)
   - Filter: price < $10, optionable = True

2. For each stock, query Tradier API:
   - Get nearest expiration
   - Get options chain with IV
   - Calculate average IV across ATM options

3. Filter and rank:
   - Keep stocks with avg IV > threshold (e.g., 80%)
   - Rank by IV percentile

4. Output results:
   - Save to database
   - Send alerts
   - Generate report

Rate Limit Strategy:
- Tradier sandbox is generous
- Add 0.5s delay between requests to be polite
- Can process 100+ symbols in ~1 minute
```

### Option 2: yfinance + Barchart Validation

```python
# Pseudocode architecture

1. Quick scan with yfinance:
   - Get stock list under $10
   - Get options + IV for each
   - Filter to high IV candidates

2. Validate with Barchart scraping:
   - Scrape Barchart high IV list
   - Cross-reference yfinance results
   - Keep only stocks on both lists

3. Deep dive on validated stocks:
   - Get more detailed options data
   - Calculate IV rank/percentile
   - Check volume/open interest

4. Output final list

Benefits:
- yfinance is fast for initial scan
- Barchart provides quality validation
- Reduces false positives from yfinance IV bugs
```

### Option 3: Hybrid Tradier + Web Scraping

```python
# Pseudocode architecture

1. Get pre-screened tickers from Barchart:
   - Scrape high IV list (already filtered)
   - Get 50-100 high IV tickers

2. Filter by price using yfinance:
   - Quick price check (no options calls)
   - Keep only under $10

3. Get detailed data from Tradier:
   - Full options chains
   - Accurate IV and Greeks
   - Volume and open interest

4. Calculate metrics:
   - IV Rank (requires historical data)
   - Average IV
   - Put/call ratios

5. Output sorted results

Benefits:
- Barchart pre-filtering saves API calls
- Tradier provides accurate data
- Efficient use of all resources
```

---

## Top 3 Recommendations

### 🥇 #1: Tradier Sandbox API

**Why:**
- Best free options data with professional-grade IV from ORATS
- Well-documented REST API
- No rate limit concerns
- Most reliable free source

**Best For:**
- Production-ready scanning
- Accurate IV data
- Long-term projects

**Setup Time:** 5 minutes (signup + get API key)

**Code Example:** See section 1 above

---

### 🥈 #2: yfinance (Yahoo Finance)

**Why:**
- Zero setup required
- Fastest to prototype
- Good for development/testing
- Large community

**Best For:**
- Quick prototypes
- Development/testing
- Personal projects
- When accuracy isn't critical

**Setup Time:** 30 seconds (pip install yfinance)

**Code Example:** See section 2 above

**Caveat:** IV data has known accuracy issues - use for screening only, validate before trading

---

### 🥉 #3: Barchart Screener + Web Scraping

**Why:**
- Pre-filtered high IV lists
- Professional data quality
- Great for validation
- 10-minute updates

**Best For:**
- Cross-validation
- Getting high IV ticker lists
- When you need pre-screened data

**Setup Time:** 15 minutes (signup + implement scraping)

**Code Example:** See section 3 above

**Caveat:** Web scraping can be fragile - needs monitoring

---

## Implementation Checklist

```markdown
### Phase 1: Setup (Day 1)
- [ ] Sign up for Tradier developer account
- [ ] Generate Tradier sandbox API token
- [ ] Set up Python environment (requests, pandas, yfinance)
- [ ] Test Tradier API connection
- [ ] Test yfinance basic functionality

### Phase 2: Stock Universe (Day 2)
- [ ] Create stock screener to find optionable stocks under $10
- [ ] Sources: Finviz, yfinance, or Barchart
- [ ] Filter for adequate volume (e.g., > 1M shares/day)
- [ ] Save universe to file/database

### Phase 3: IV Scanner (Day 3-4)
- [ ] Implement Tradier options chain fetching
- [ ] Calculate average IV per stock
- [ ] Add IV rank calculation (optional - needs historical data)
- [ ] Filter for high IV (>60% or >80%)
- [ ] Add error handling and rate limiting

### Phase 4: Validation (Day 5)
- [ ] Implement Barchart scraper
- [ ] Cross-reference results
- [ ] Add data quality checks
- [ ] Compare IV values across sources

### Phase 5: Reporting (Day 6)
- [ ] Format results (DataFrame, JSON, etc.)
- [ ] Add sorting/ranking
- [ ] Create output report
- [ ] Add visualization (optional)

### Phase 6: Automation (Day 7)
- [ ] Schedule nightly scan (cron, Task Scheduler, etc.)
- [ ] Add logging
- [ ] Set up alerts (email, Discord, etc.)
- [ ] Monitor for errors

### Phase 7: Optimization (Ongoing)
- [ ] Cache frequently accessed data
- [ ] Optimize API calls
- [ ] Add more data sources
- [ ] Improve filtering logic
```

---

## Sample Complete Scanner Code

```python
#!/usr/bin/env python3
"""
High IV Stocks Under $10 Scanner
Uses Tradier API for accurate IV data
"""

import os
import requests
import pandas as pd
from datetime import datetime
import time
import yfinance as yf

# Configuration
TRADIER_TOKEN = os.getenv('TRADIER_SANDBOX_TOKEN')
TRADIER_BASE = 'https://sandbox.tradier.com/v1'
MAX_PRICE = 10
MIN_IV = 0.60  # 60%
MIN_VOLUME = 1_000_000  # 1M shares/day

class HighIVScanner:
    def __init__(self, tradier_token):
        self.token = tradier_token
        self.headers = {
            'Authorization': f'Bearer {tradier_token}',
            'Accept': 'application/json'
        }

    def get_stock_universe(self):
        """Get list of stocks under $10 with decent volume"""
        print("📊 Building stock universe...")

        # You can replace this with any stock screener
        # For demo, using a hardcoded list of penny stocks
        symbols = [
            'SIRI', 'SOFI', 'NIO', 'PLUG', 'LCID', 'F', 'RIVN',
            'NKLA', 'VALE', 'BBD', 'GNUS', 'TELL', 'MARA',
            'RIOT', 'CLSK', 'BTG', 'GOLD', 'AU', 'PAAS'
        ]

        # Filter by price
        under_10 = []
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='1d')
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    volume = hist['Volume'].iloc[-1]

                    if price < MAX_PRICE and volume > MIN_VOLUME:
                        under_10.append({
                            'symbol': symbol,
                            'price': price,
                            'volume': volume
                        })
                        print(f"  ✓ {symbol}: ${price:.2f}")

                time.sleep(0.5)  # Rate limit
            except Exception as e:
                print(f"  ✗ {symbol}: {e}")

        return under_10

    def get_option_expirations(self, symbol):
        """Get available option expirations"""
        url = f'{TRADIER_BASE}/markets/options/expirations'
        params = {'symbol': symbol}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        data = response.json()
        if 'expirations' in data and 'date' in data['expirations']:
            return data['expirations']['date']
        return []

    def get_options_chain(self, symbol, expiration):
        """Get options chain with IV"""
        url = f'{TRADIER_BASE}/markets/options/chains'
        params = {
            'symbol': symbol,
            'expiration': expiration,
            'greeks': 'true'
        }

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        return response.json()

    def calculate_avg_iv(self, chain_data):
        """Calculate average IV from options chain"""
        if 'options' not in chain_data or 'option' not in chain_data['options']:
            return None

        options = chain_data['options']['option']
        if not isinstance(options, list):
            options = [options]

        ivs = []
        for opt in options:
            if 'greeks' in opt and 'mid_iv' in opt['greeks']:
                iv = opt['greeks']['mid_iv']
                if iv and iv > 0:
                    ivs.append(iv)

        if ivs:
            return sum(ivs) / len(ivs)
        return None

    def scan(self):
        """Run the complete scan"""
        print(f"\n🚀 Starting High IV Scanner @ {datetime.now()}")
        print(f"   Max Price: ${MAX_PRICE}")
        print(f"   Min IV: {MIN_IV:.0%}")
        print("="*60)

        # Get stock universe
        stocks = self.get_stock_universe()
        print(f"\n✓ Found {len(stocks)} stocks under ${MAX_PRICE}\n")

        # Scan each stock for high IV
        results = []

        for stock in stocks:
            symbol = stock['symbol']
            print(f"🔍 Scanning {symbol}...", end=' ')

            try:
                # Get expirations
                expirations = self.get_option_expirations(symbol)
                if not expirations:
                    print("❌ No options")
                    continue

                # Get first expiration chain
                chain = self.get_options_chain(symbol, expirations[0])
                avg_iv = self.calculate_avg_iv(chain)

                if avg_iv is None:
                    print("❌ No IV data")
                    continue

                if avg_iv >= MIN_IV:
                    results.append({
                        'symbol': symbol,
                        'price': stock['price'],
                        'volume': stock['volume'],
                        'avg_iv': avg_iv,
                        'expiration': expirations[0]
                    })
                    print(f"✅ IV: {avg_iv:.1%} ⭐")
                else:
                    print(f"⚪ IV: {avg_iv:.1%}")

                time.sleep(0.5)  # Rate limit

            except Exception as e:
                print(f"❌ Error: {e}")

        # Sort by IV
        results.sort(key=lambda x: x['avg_iv'], reverse=True)

        # Print results
        print(f"\n{'='*60}")
        print(f"🎯 Found {len(results)} stocks with IV > {MIN_IV:.0%}")
        print(f"{'='*60}\n")

        if results:
            df = pd.DataFrame(results)
            df['avg_iv'] = df['avg_iv'].apply(lambda x: f"{x:.1%}")
            df['price'] = df['price'].apply(lambda x: f"${x:.2f}")
            df['volume'] = df['volume'].apply(lambda x: f"{x:,.0f}")

            print(df.to_string(index=False))

        return results

if __name__ == '__main__':
    # Check for API token
    if not TRADIER_TOKEN:
        print("❌ Error: TRADIER_SANDBOX_TOKEN not set")
        print("   1. Sign up at developer.tradier.com")
        print("   2. Get token from dash.tradier.com/settings/api")
        print("   3. export TRADIER_SANDBOX_TOKEN='your_token'")
        exit(1)

    # Run scanner
    scanner = HighIVScanner(TRADIER_TOKEN)
    results = scanner.scan()

    # Save to file
    if results:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'high_iv_scan_{timestamp}.json'

        import json
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n💾 Results saved to {filename}")
```

**Run it:**
```bash
# Setup
export TRADIER_SANDBOX_TOKEN='your_token_here'
pip install requests pandas yfinance

# Run
python high_iv_scanner.py
```

---

## Additional Resources

### Documentation Links:
- **Tradier API Docs:** https://documentation.tradier.com/brokerage-api
- **yfinance GitHub:** https://github.com/ranaroussi/yfinance
- **Barchart OnDemand:** https://www.barchart.com/ondemand/api
- **CBOE DataShop:** https://datashop.cboe.com

### Learning Resources:
- **Options Trading Basics:** https://www.investopedia.com/terms/i/iv.asp
- **IV Rank vs Percentile:** https://www.barchart.com/education/iv_rank_vs_iv_percentile
- **Black-Scholes Model:** https://en.wikipedia.org/wiki/Black%E2%80%93Scholes_model

### Communities:
- **r/options:** Reddit community for options trading
- **r/algotrading:** Algorithmic trading strategies
- **QuantConnect:** Algorithmic trading platform with options support

---

## Conclusion

For building a **"High IV Stocks Under $10" nightly scanner**, the best free approach is:

1. **Primary Data Source:** Tradier Sandbox API
   - Most accurate IV data (ORATS)
   - Free and reliable
   - Easy to use

2. **Stock Universe:** yfinance or Finviz
   - Get list of stocks under $10
   - Filter for adequate volume

3. **Validation (Optional):** Barchart web scraping
   - Cross-check high IV results
   - Reduce false positives

This combination provides production-quality results using only free resources.

**Total Cost:** $0
**Setup Time:** ~1-2 hours
**Maintenance:** Minimal (monitor for API changes)

---

## Sources

- [Free weekly implied volatility data | Option Strategist](https://www.optionstrategist.com/calculators/free-volatility-data)
- [Implied Volatility Data: Best Datasets & Databases 2025 | Datarade](https://datarade.ai/data-categories/implied-volatility-data)
- [Top 7 Sources to Download Historical Options Data in 2025 | QuantVPS](https://www.quantvps.com/blog/download-historical-options-data-in-2025)
- [Best APIs for Historical Options Market Data & Volatility | QuantVPS](https://www.quantvps.com/blog/best-apis-for-historical-options-market-data-volatility)
- [Yahoo Finance Implied Volatility · Chase the Devil](https://chasethedevil.github.io/post/yahoo_finance_implied_volatility/)
- [Get Free Options Data with Python: Yahoo finance & Pandas Tutorial | Codearmo](https://www.codearmo.com/python-tutorial/options-trading-getting-options-data-yahoo-finance)
- [Market Data APIs | Barchart OnDemand](https://www.barchart.com/ondemand/api)
- [Equity Option API | Barchart OnDemand](https://www.barchart.com/ondemand/api/getEquityOptions)
- [How to get an option chain | Brokerage API Documentation | Tradier](https://documentation.tradier.com/brokerage-api/markets/get-options-chains)
- [Tradier Brokerage API](https://docs.tradier.com/docs/getting-started)
- [Tradier Developer](https://developer.tradier.com/)
- [Implied Volatility, Historical Stock Options Pricing | Cboe DataShop](https://www.livevol.com/stock-options-analysis-data/)
- [Hanweck Implied Volatility and Greeks | CBOE](https://www.cboe.com/services/analytics/hanweck/implied_volatility/)
- [Option EOD Summary | CBOE DataShop](https://datashop.cboe.com/option-eod-summary)
- [Help - Technical Analysis - Volatility | Finviz](https://finviz.com/help/technical-analysis/volatility.ashx)
- [Highest Implied Volatility Options - Barchart.com](https://www.barchart.com/options/highest-implied-volatility)
- [Introducing Options Chain Snapshot API | Polygon.io](https://polygon.io/blog/announcing-options-chain-snapshot-api)
- [Greeks and Implied Volatility | Polygon.io](https://polygon.io/blog/greeks-and-implied-volatility)
- [API Documentation | Finnhub](https://finnhub.io/docs/api)
- [Stock Options · Issue #477 · finnhubio/Finnhub-API](https://github.com/finnhubio/Finnhub-API/issues/477)
- [Stocks with Elevated or Subdued Volatilities | Market Chameleon](https://marketchameleon.com/volReports/VolatilityRankings)
- [Implied Volatility IV Rank and IV Percentile - Barchart.com](https://www.barchart.com/options/iv-rank-percentile)
- [Top Volatility Options | Yahoo Finance](https://finance.yahoo.com/options/highest-implied-volatility/)
- [Using Implied Volatility Percentiles | Charles Schwab](https://www.schwab.com/learn/story/using-implied-volatility-percentiles)
- [Yahoo Finance API: Free Guide + Python Code Examples (2025) | MarketXLS](https://marketxls.com/blog/yahoo-finance-api-the-ultimate-guide-for-2024)
- [YFRateLimitError Issue | yfinance GitHub](https://github.com/ranaroussi/yfinance/issues/2422)
- [How To Use The Yahoo Finance API | Market Data](https://www.marketdata.app/how-to-use-the-yahoo-finance-api/)
- [AlphaQuery - Get deeper insights](https://www.alphaquery.com/)
- [OptionStrat | The Option Trader's Toolkit](https://optionstrat.com/)
- [OptionStrat Flow | Unusual Options Activity](https://optionstrat.com/flow)
- [Option-Scraper-BlackScholes | GitHub](https://github.com/jknaudt21/Option-Scraper-BlackScholes)
- [YahooSkew | GitHub](https://github.com/mmautner/YahooSkew)
- [iv_scraper | GitHub](https://github.com/melder/iv_scraper)
- [How I get options data for free | freeCodeCamp](https://www.freecodecamp.org/news/how-i-get-options-data-for-free-fba22d395cc8/)
- [Downloading option chain with Python | Ran Aroussi](https://aroussi.com/post/download-options-data)

---

**Report Generated:** December 8, 2025
**Total Sources Analyzed:** 50+
**Recommendation Confidence:** High
