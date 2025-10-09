# 📊 Alert Channel Commands

**Channel Purpose:** Stock alerts, ticker research, and market analysis

---

## Slash Commands

### `/check <ticker>`
Quick ticker lookup with price and recent alerts
- **ticker** (required): Stock symbol (e.g., AAPL, TSLA)
- **Example:** `/check AAPL`
- **Returns:**
  - Current price & % change
  - Recent alerts (last 7 days)
  - Alert count and average confidence

### `/research <ticker> [question]`
LLM-powered deep dive analysis of a ticker
- **ticker** (required): Stock symbol
- **question** (optional): Specific question about the ticker
- **Example:**
  - `/research TSLA`
  - `/research NVDA "What are the main catalysts?"`
- **Returns:**
  - SEC filing analysis (8-K, S-1, 10-Q)
  - Sentiment breakdown
  - Recent news summary
  - Custom answer (if question provided)

### `/ask <question>`
Ask the bot a natural language question
- **question** (required): Your market or stock question
- **Example:**
  - `/ask "Is the tech sector bullish?"`
  - `/ask "What are the top penny stock catalysts today?"`
- **Returns:** LLM-generated answer based on recent alerts and market data

### `/compare <ticker1> <ticker2>`
Compare two tickers side-by-side
- **ticker1** (required): First ticker
- **ticker2** (required): Second ticker
- **Example:** `/compare AAPL MSFT`
- **Returns:**
  - Price comparison
  - % change comparison
  - Recent alert counts
  - Sentiment scores
  - Relative performance

---

## Alert Features

### **Stock Alert Structure**
Each alert posted includes:
- **Ticker** - Stock symbol (e.g., $AAPL)
- **Price** - Current price and % change
- **Confidence** - Classification confidence (0-100%)
- **Sentiment** - Bullish/neutral/bearish gauge
- **Keywords** - Catalyst categories (merger, earnings, FDA, etc.)
- **Source** - News source
- **Chart** - Interactive price chart with indicators

### **Interactive Chart Buttons**
Stock alerts include chart timeframe buttons:
- **1D** - 1-day intraday chart
- **5D** - 5-day chart
- **1M** - 1-month chart
- **3M** - 3-month chart
- **1Y** - 1-year chart

Click a button to refresh the chart with a new timeframe.

---

## What Triggers Alerts?

The bot monitors multiple sources and alerts on:

### **Catalysts**
- SEC filings (8-K, S-1, 10-Q, 10-K)
- Earnings announcements & beats
- FDA approvals/trials
- Mergers & acquisitions
- Contract awards
- Product launches
- Analyst upgrades
- Insider buying

### **Technical Signals**
- 52-week lows (value opportunities)
- Breakout scans (volume + price action)
- High relative volume (>1.5x avg)
- Unusual options activity

### **Filters Applied**
- **Price range:** $0.10 - $10.00
- **Sentiment:** Positive bias preferred
- **Confidence:** Minimum score 0.25
- **Exchanges:** NASDAQ, NYSE, AMEX only
- **Deduplication:** No duplicate alerts

---

## Bot Status & Health

### **Heartbeat** (Every 60 minutes)
The bot posts a heartbeat to confirm it's running:
- Cycle count
- Alerts posted (24hr)
- System status

### **System Features**
- ✅ Real-time price feeds (Tiingo, Alpha Vantage)
- ✅ Multi-source sentiment (Alpha Vantage, Marketaux)
- ✅ LLM analysis (Mistral 7B via Ollama)
- ✅ Advanced charting (QuickChart + Matplotlib)
- ✅ Breakout feedback loop (self-learning)
- ✅ Watchlist cascade (HOT → WARM → COOL)

---

## Tips & Tricks

**Best practices:**
1. **Use `/check` first** - Quick overview before deep research
2. **Ask specific questions** - Better LLM responses with `/research TICKER "specific question"`
3. **Compare competitors** - Use `/compare` to see relative performance
4. **Check alert history** - `/check` shows 7-day alert count for trending tickers
5. **Monitor timeframes** - Click chart buttons to analyze different periods

**Command cooldowns:**
- `/check`: Instant
- `/research`: ~5-10s (LLM processing)
- `/ask`: ~3-7s (depends on question complexity)
- `/compare`: ~2-3s

---

**Market Disclaimer:** Alerts are informational only. This bot does not provide financial advice. Always do your own research (DYOR) and consult a licensed financial advisor before making investment decisions.

---

**Bot Version:** Catalyst-Bot v1.0 | **Support:** Admin channel for issues
