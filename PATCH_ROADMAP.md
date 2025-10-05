# Catalyst-Bot Patch Roadmap

**Last Updated:** October 4, 2025
**Status:** Post-Foundation - Interactive Charts & Buttons Working

---

## Current State (Completed - Tier 1)

✅ **Production Stability**
- 100% alert delivery rate
- Sentiment gauge generation and display
- Advanced charts with VWAP, RSI, MACD, volume
- Interactive timeframe buttons (1D, 5D, 1M, 3M, 1Y)
- Deduplication system working
- Pre-commit hooks and pytest suite passing

✅ **GPU Optimizations**
- ML model caching (30-50% faster after first load)
- Skip ML for earnings events (50% GPU reduction)
- Volume reduction controls (MAX_ALERTS_PER_CYCLE)
- 45% faster cycle times with dedup

✅ **Data Infrastructure**
- Finnhub integration (news, earnings calendar)
- Tiingo real-time price data
- SEC filings feeds (8-K, 424B5, FWP, 13D/G)
- GlobeNewswire public feed
- Multi-provider fallback (Tiingo → Alpha Vantage → yfinance)

---

## WAVE 0: Critical Fixes & Enhancements ⚡ IN PROGRESS

**Goal:** Address immediate issues and polish existing features.

### 0.1 Smart Earnings Scorer
**Patches:** Earnings calendar vs results detection
**Status:** Quick fix applied, full implementation pending
**Implementation:**
- **DONE**: Block earnings calendar alerts (SKIP_SOURCES=Finnhub Earnings)
- **TODO**: Detect actual earnings RESULTS vs calendar announcements
- **TODO**: Parse EPS actual vs estimate from titles/API
- **TODO**: Assign sentiment based on beat/miss:
  - Beat by >10%: +0.7 to +1.0
  - Beat by <10%: +0.3 to +0.7
  - Miss: -0.3 to -1.0
- **TODO**: Historical earnings data integration (8 quarters lookback)
- **TODO**: Calculate beat rate per ticker for confidence scoring
- **TODO**: LLM earnings predictor (optional, future enhancement)

**Dependencies:** None (standalone enhancement)
**Estimated Time:** 2-3 days for full scorer, 1 day for basic results detection
**GPU Impact:** None (or minimal if LLM predictor added)
**Research Docs:**
- `EARNINGS_ALERTS_FIX.md` (implementation proposal)
- Finnhub API docs for earnings calendar vs actual results

---

## WAVE 1: Admin Controls & Self-Learning Foundation 🎯 PRIORITY

**Goal:** Enable the bot to learn from market feedback and self-optimize alert parameters.

### 1.1 Admin Controls Testing & Expansion
**Patches:** Admin reporting system (existing), External Control Panel, Trading disciplines
**Status:** Partially implemented, needs testing
**Implementation:**
- Test existing nightly admin report system
- Implement button handlers for "Approve Changes" and "View Details"
- Add parameter change validation and rollback
- Create admin command: `/admin report` to trigger on-demand
- Add `/admin apply <param> <value>` for manual overrides
- Integrate trading discipline rules (max daily alerts, confidence cooldowns)

**Dependencies:** Discord interaction server (✅ working)
**Estimated Time:** 2-3 days
**GPU Impact:** None
**Research Docs:**
- `External Control Panel for Bot Configuration.pdf`
- `Trading disciplines research.pdf`

---

### 1.2 Real-Time Breakout Feedback Loop
**Patches:** Adding Real-Time Breakout Feedback, Improving Backtesting
**Status:** New feature
**Implementation:**
- Track alert performance 15min, 1hr, 4hr, 1day after posting
- Measure: price change %, volume change %, breakout confirmation
- Store results in SQLite: `alert_id`, `ticker`, `timestamp`, `outcome_15m`, `outcome_1hr`, etc.
- Backfeed into keyword weight adjustments
- Generate weekly "best/worst catalyst types" report
- Integrate with admin system to auto-suggest parameter changes

**Dependencies:** Wave 1.1 (admin system)
**Estimated Time:** 3-4 days
**GPU Impact:** Minimal (periodic background checks)
**Research Docs:**
- `Adding Real-Time Breakout Feedback to Your Trading Bot.pdf`
- `Improving Backtesting and Analysis for More Accurate Bot Alerts.pdf`

---

### 1.3 Backtesting Engine Enhancement
**Patches:** Improving Backtesting and Analysis
**Status:** Enhance existing analyzer
**Implementation:**
- Add slippage modeling (5-10% on penny stocks)
- Volume-weighted fill simulation
- Catalyst type tagging (earnings vs news vs filing)
- Historical alert replay system
- Monte Carlo simulations for parameter sensitivity
- Generate backtest reports with Sharpe, max drawdown, win rate

**Dependencies:** Wave 1.2 (feedback data)
**Estimated Time:** 4-5 days
**GPU Impact:** Can run overnight (not real-time)
**Research Docs:**
- `Improving Backtesting and Analysis for More Accurate Bot Alerts.pdf`
- `Penny_Stocks_Trading_Playbook_v2` (strategy reference)

---

## WAVE 2: Performance & Infrastructure Optimization ⚡ PRIORITY

**Goal:** Reduce GPU load, speed up charts, ensure 24/7 reliability.

### 2.1 Chart Generation Optimization
**Patches:** Self-Hosting QuickChart, Chart.js v3 plugins
**Status:** Currently using Tiingo charts, need to optimize
**Implementation:**
- Self-host QuickChart in Docker container
- Implement Chart.js v3 financial plugin (candlesticks, indicators)
- Add chart caching strategy (aggressive TTL for intraday charts)
- Lazy-load advanced indicators (only generate on button click)
- Parallelize chart generation for multi-alert cycles
- Implement chart pre-warming (generate popular tickers during idle)

**Dependencies:** Docker setup
**Estimated Time:** 3-4 days
**GPU Impact:** 🔥 **High reduction** - offload matplotlib rendering
**Research Docs:**
- `Self-Hosting QuickChart with Docker and Minimizing Chart URL Length.pdf`
- `Adding Financial Charts Plugin to QuickChart (Chart.js v3).pdf`
- `Stock Charting with QuickChart and Alternatives.pdf`

---

### 2.2 GPU Usage Fine-Tuning
**Patches:** Continued optimization
**Status:** Ongoing refinement
**Implementation:**
- Profile ML model inference (identify bottlenecks)
- Investigate lightweight sentiment models (DistilBERT vs current)
- Batch sentiment scoring (process multiple alerts in one GPU pass)
- Implement GPU memory pooling
- Add CUDA stream optimization
- Monitor GPU temp/power with alerts if >90% sustained

**Dependencies:** None
**Estimated Time:** 2-3 days
**GPU Impact:** 🔥 **Target: <50% utilization on first cycle**
**Research Docs:** Internal profiling

---

### 2.3 24/7 Deployment Infrastructure
**Patches:** Remote Access Guide, Hosting Options
**Status:** Currently manual dev rig operation
**Implementation:**
- Document remote access setup (RDP/TeamViewer)
- Configure Windows to auto-restart bot on crash
- Set up systemd-equivalent (NSSM or Task Scheduler)
- Implement health monitoring endpoint (already exists at :8080)
- Add UptimeRobot or similar external monitoring
- Create deployment checklist and rollback procedures

**Dependencies:** None
**Estimated Time:** 1-2 days
**GPU Impact:** None
**Research Docs:**
- `Remote Access Guide for a Windows Development Machine.pdf`
- `Hosting Options for a 24/7 Python Discord Bot under $15/month.pdf`

---

## WAVE 3: Enhanced Charting & Visualization 📊

**Goal:** Professional-grade charts with technical levels and live updates.

### 3.1 Advanced Chart Indicators
**Patches:** Candlestick Charting & TA, Chart.js v3
**Status:** Have basic VWAP/RSI/MACD, expand
**Implementation:**
- Add Bollinger Bands, Fibonacci retracements
- Support/resistance level detection (auto-draw on charts)
- Volume profile overlays
- Multiple timeframe analysis (show 1D + 1W patterns)
- Dark theme refinement (current charts are good, polish)

**Dependencies:** Wave 2.1 (self-hosted QuickChart)
**Estimated Time:** 2-3 days
**GPU Impact:** Low (offloaded to QuickChart)
**Research Docs:**
- `Candlestick Charting & Technical Analysis – Tools, Libraries, and Data Sources.pdf`
- `Adding Financial Charts Plugin to QuickChart (Chart.js v3).pdf`

---

### 3.2 Post-Breakout Technical Level Mapping
**Patches:** Mapping Technical Levels After Breakouts
**Status:** New feature
**Implementation:**
- Detect breakout levels (price at alert time)
- Map resistance zones: R1 (recent high), R2 (52-week high)
- Map support zones: S1 (recent low), S2 (breakout level)
- Display levels on charts as horizontal lines
- Add to Discord embed: "Resistance: $X.XX | Support: $Y.YY"
- Track breakout success vs failure at each level

**Dependencies:** Wave 3.1 (chart rendering)
**Estimated Time:** 2-3 days
**GPU Impact:** Low (technical calculation only)
**Research Docs:**
- `Mapping Technical Levels After News-Driven Breakouts.pdf`

---

### 3.3 Live-Updating Discord Embeds
**Patches:** Updating Discord Bot Embed Messages
**Status:** Currently static after post
**Implementation:**
- Send initial alert instantly (text only, placeholder chart)
- Async update with chart + sentiment gauge (1-2s later)
- Add "⏱️ Updating..." indicator during chart generation
- Implement chart refresh on demand via button
- Price/volume auto-refresh every 5min for active alerts (configurable)

**Dependencies:** Discord bot API (already working)
**Estimated Time:** 2-3 days
**GPU Impact:** None
**Research Docs:**
- `Updating Discord Bot Embed Messages: Feasibility and Best Practices.pdf`

---

## WAVE 4: Data Feed Expansion 📡

**Goal:** Add premium data sources and expand catalyst coverage.

### 4.1 Finnhub Premium Integration
**Patches:** Enhancing Catalyst Bot with Finnhub API Data
**Status:** Using free tier (news + earnings), expand to premium
**Implementation:**
- Add Finnhub insider trades feed
- Add Finnhub analyst upgrades/downgrades
- Add Finnhub IPO calendar
- Add Finnhub stock splits/dividends
- Implement Finnhub social sentiment scores
- Rate limit management (API quota tracking)

**Dependencies:** Finnhub Premium API key ($)
**Estimated Time:** 2-3 days
**GPU Impact:** None
**Research Docs:**
- `Enhancing Catalyst Bot with Finnhub API Data.pdf`

---

### 4.2 1-Minute OHLCV Intraday Data
**Patches:** Best 1-Minute OHLCV Data Sources, Tiingo Priority
**Status:** Currently using Tiingo for 5-min intraday
**Implementation:**
- Evaluate IEX Cloud vs Tiingo for 1-min bars
- Implement 1-min data caching (reduce API calls)
- Add intraday momentum detection (5-min volume spikes)
- Create "scalp alert" tier for rapid moves (optional channel)
- Compare cost/reliability between providers

**Dependencies:** API subscriptions
**Estimated Time:** 2-3 days
**GPU Impact:** None
**Research Docs:**
- `Best 1-Minute OHLCV Data Sources Under $50 for a Trading Bot.pdf`
- `Tiingo API Usage and Priority in Catalyst-Bot Price Data.pdf`

---

### 4.3 Finviz Elite Screener Integration
**Patches:** Finviz Screener Integration
**Status:** Using Finviz export for price, expand to automation
**Implementation:**
- Automate CSV export pulls (using existing auth token)
- Parse screener results into candidate universe
- Add pre-market screener (gap scanners)
- Intraday unusual volume scanner
- Low float + high relative volume combo scanner
- Schedule nightly screener imports

**Dependencies:** Finviz Elite subscription (✅ have token)
**Estimated Time:** 2-3 days
**GPU Impact:** None
**Research Docs:**
- `Finviz Screener Integration Patch Series.pdf`

---

### 4.4 Broker Signals Integration
**Patches:** Broker Signals Integration
**Status:** New feature
**Implementation:**
- Integrate Alpaca halt/resume notifications
- Add IBKR short availability changes
- Monitor Unusual Whales-style order flow (if API available)
- Broker upgrade/downgrade alerts (Finnhub + manual sources)
- Create "broker signals" category in classification

**Dependencies:** Broker API access
**Estimated Time:** 3-4 days
**GPU Impact:** None
**Research Docs:**
- `Catalyst-Bot — Broker Signals Integration.pdf`
- `Best Paper Trading Systems for a Low-Priced Stock Trading Bot.pdf`

---

## WAVE 5: Advanced Sentiment & Market Intelligence 🧠

**Goal:** Layer in market-wide context and detect hidden whale activity.

### 5.1 Market & Sector Sentiment Integration
**Patches:** Integrating Market and Sector Sentiment
**Status:** Currently ticker-only sentiment
**Implementation:**
- Pull SPY/QQQ sentiment as market baseline
- Sector ETF sentiment (XLF, XLE, XLK, etc.)
- Adjust ticker confidence score based on alignment:
  - Bullish ticker + bullish sector + bullish market = +10% confidence
  - Bullish ticker + bearish sector + bearish market = -20% confidence
- Display market/sector context in Discord embed
- Create "swimming against tide" alerts (contrarian opportunities)

**Dependencies:** None
**Estimated Time:** 2-3 days
**GPU Impact:** Minimal (additional sentiment checks)
**Research Docs:**
- `Integrating Market and Sector Sentiment into the Aggregate Score.pdf`

---

### 5.2 Dark Pool & Institutional Activity
**Patches:** Dark-pool Sentiment Integration, AntiMM Alert System
**Status:** New feature
**Implementation:**
- Integrate dark pool print data (Quiver Quant, FinTel, or scraping)
- Detect unusual block trades (>50k shares for penny stocks)
- Monitor short interest changes (FINRA data)
- Flag "anti-market maker" scenarios (spoofing, wash trading patterns)
- Add "🐋 Whale Activity" badge to alerts when detected
- Create risk warning system for MM games

**Dependencies:** Data sources (APIs or scraping)
**Estimated Time:** 4-5 days
**GPU Impact:** None
**Research Docs:**
- `_Dark-pool Sentiment Integration for Catalyst-Bot.pdf`
- `AntiMM_Alert_System_Guide.pdf`

---

### 5.3 Short Squeeze Detection Module
**Patches:** Short activity and sentiment
**Status:** New feature
**Implementation:**
- Monitor short interest via FINRA/S3 Partners/Ortex
- Track borrow rate changes (high borrow = squeeze potential)
- Social sentiment spike detection (WSB, StockTwits)
- Combine: high short interest + rising price + positive sentiment = squeeze alert
- Add "🚀 Short Squeeze Setup" tier
- Track historical squeeze success rate

**Dependencies:** Short interest data sources
**Estimated Time:** 3-4 days
**GPU Impact:** None
**Research Docs:**
- `Short activity and sentiment.pdf`

---

### 5.4 LLM-Powered Fundamental Analysis
**Patches:** Mistral LLM for SEC Filings, Local LLM for Earnings Calls
**Status:** New advanced feature
**Implementation:**
- Deploy Mistral/Llama 3 locally (Ollama already installed)
- Parse SEC filings (8-K, 424B5, 13D) into summaries
- Score filing sentiment (-100 to +100)
- Extract key facts: deal size, warrants, dilution %, catalysts
- Parse earnings call transcripts (if available)
- Generate "Smart Summary" embed field
- GPU-aware: run LLM inference during low-alert periods

**Dependencies:** Ollama (installed), GPU memory management
**Estimated Time:** 5-7 days
**GPU Impact:** 🔥 **High** - schedule during idle times
**Research Docs:**
- `Implementing Mistral LLM for SEC Filing Analysis in Catalyst-Bot.pdf`
- `Using a Local LLM for Earnings Call Sentiment Analysis.pdf`

---

## WAVE 6: Strategy-Specific Modules 📈

**Goal:** Implement proven penny stock trading strategies as automated scanners.

### 6.1 Gap Detection & Trading
**Patches:** Gap Detection and Gap Filling
**Status:** New feature
**Implementation:**
- Detect gap-ups (>5% from prior close before open)
- Detect gap-downs (capitulation setups)
- Classify gap types: earnings, news, technical breakout
- Predict gap fill probability (based on catalyst type + volume)
- Alert types: "Gap & Go" vs "Gap Fill" plays
- Track gap statistics (% that filled, timeframe to fill)

**Dependencies:** Pre-market data (Tiingo supports)
**Estimated Time:** 3-4 days
**GPU Impact:** Low
**Research Docs:**
- `Gap Detection and Gap Filling in Stock Trading.pdf`

---

### 6.2 Capitulation Recovery Scanner
**Patches:** Automating a Capitulation Trading Strategy
**Status:** New feature
**Implementation:**
- Detect panic selling: sharp dip (>10%) on 2x volume
- Monitor RSI collapse (<30) + VWAP breakdown
- Flag oversold bounce candidates
- Create "🩹 Capitulation Recovery" alert tier
- Track recovery success rate (% that bounce within 3 days)
- Backtest against historical panic sells

**Dependencies:** Intraday volume data
**Estimated Time:** 2-3 days
**GPU Impact:** Low
**Research Docs:**
- `Automating a Capitulation Trading Strategy with a Bot.pdf`
- `Penny_Stocks_Trading_Playbook_v2.pdf`

---

### 6.3 FDA Trial Calendar Integration (Biotech)
**Patches:** FDA_Trial_Integration_Patches
**Status:** New niche feature
**Implementation:**
- Scrape FDA calendar for trial results, PDUFA dates
- Alert on: trial start, interim results, FDA decisions
- Create "💊 Biotech Catalyst" alert tier
- Track trial outcome history (approval % by phase)
- Focus on penny biotech (<$10 stocks)

**Dependencies:** FDA.gov scraping or BiopharmCatalyst API
**Estimated Time:** 2-3 days
**GPU Impact:** None
**Research Docs:**
- `FDA_Trial_Integration_Patches.md`

---

### 6.4 Feature Checklist Completion
**Patches:** Feature Checklist for Comprehensive Trading Bot
**Status:** Ongoing validation
**Implementation:**
- Audit all features from comprehensive checklist
- Identify gaps vs current implementation
- Prioritize missing critical features
- Create "feature coverage" report

**Dependencies:** All prior waves
**Estimated Time:** 1-2 days (audit only)
**GPU Impact:** None
**Research Docs:**
- `Feature Checklist for a Comprehensive Trading Bot (Sub-$10 Stocks Focus).pdf`

---

## WAVE 7: User Interface & Advanced Interactions 🎮

**Goal:** Enable Discord-based control and visualization without touching code.

### 7.1 Discord Slash Commands & Embeds
**Patches:** Discord commands and embeds
**Status:** Partially implemented (buttons working), expand
**Implementation:**
- `/chart <ticker> [timeframe]` - Generate chart on demand
- `/watchlist add <ticker>` - Add to watchlist
- `/watchlist remove <ticker>` - Remove from watchlist
- `/stats [period]` - Show bot performance stats
- `/backtest <ticker>` - Run quick backtest
- `/sentiment <ticker>` - Get current sentiment score
- `/admin report` - Trigger admin report
- `/admin set <param> <value>` - Override parameter
- Add dropdown selectors for multi-option commands

**Dependencies:** Discord interaction server (✅ working)
**Estimated Time:** 3-4 days
**GPU Impact:** None
**Research Docs:**
- `Discord commands and embeds.pdf`

---

### 7.2 Interactive Web Dashboard
**Patches:** Interactive Web Dashboard, External Control Panel
**Status:** New advanced feature
**Implementation:**
- Flask/FastAPI web server (separate from Discord)
- Dashboard views:
  - Real-time alerts feed
  - Filing summaries and sentiment
  - Alert performance tracking
  - Backtest results visualization
  - Parameter control panel
  - Health monitoring (GPU, API quotas, uptime)
- Embed charts with Plotly/D3.js
- Add authentication (basic auth or OAuth)

**Dependencies:** Web framework, deployment
**Estimated Time:** 5-7 days
**GPU Impact:** None
**Research Docs:**
- `Interactive Web Dashboard for Filings, Embeddings & Sentiment Analysis.pdf`
- `External Control Panel for Bot Configuration.pdf`

---

### 7.3 ClaudeCode Integration (Self-Modifying Bot)
**Patches:** Integrating ClaudeCode with Discord Bot
**Status:** Experimental future feature
**Implementation:**
- Create `/code <instruction>` command
- Pipe instruction to ClaudeCode via API
- ClaudeCode edits bot files directly
- Auto-restart bot after code changes
- Git commit changes with "(edited via Discord)"
- Add approval gate for safety
- **Warning:** Powerful but risky - implement with extreme caution

**Dependencies:** ClaudeCode API access, git integration
**Estimated Time:** 4-5 days
**GPU Impact:** None
**Research Docs:**
- `Integrating ClaudeCode with a Discord Bot (Bidirectional Communication).pdf`

---

## Summary by Priority

### 🔴 CRITICAL (Start This Weekend)
1. **Wave 1.1** - Admin Controls Testing (2-3 days)
2. **Wave 2.1** - Chart Generation Optimization (3-4 days)
3. **Wave 2.2** - GPU Fine-Tuning (2-3 days)

### 🟡 HIGH (Next Week)
4. **Wave 1.2** - Real-Time Breakout Feedback (3-4 days)
5. **Wave 2.3** - 24/7 Deployment (1-2 days)
6. **Wave 4.1** - Finnhub Premium (2-3 days)
7. **Wave 7.1** - Discord Slash Commands (3-4 days)

### 🟢 MEDIUM (Following Weeks)
- Wave 1.3, 3.1-3.3, 4.2-4.4, 5.1-5.3, 6.1-6.2

### ⚪ LOW (Future Enhancements)
- Wave 5.4 (LLM), 6.3 (FDA), 7.2-7.3 (Dashboard, ClaudeCode)

---

## Estimated Timeline

- **Weekend (Oct 5-6):** Wave 1.1 + Wave 2.1 kickoff
- **Week 1 (Oct 7-13):** Complete Waves 1.1, 2.1, 2.2, 2.3
- **Week 2 (Oct 14-20):** Waves 1.2, 4.1, 7.1
- **Week 3 (Oct 21-27):** Waves 1.3, 3.1, 3.2
- **Month 2+:** Remaining waves based on priority

---

## Success Metrics

### Wave 1 Success Criteria:
- [ ] Admin reports generating nightly with parameter recommendations
- [ ] Admin buttons functional (approve/reject changes)
- [ ] Breakout feedback tracked for 100+ alerts
- [ ] Backtest engine producing Sharpe ratio + win rate reports

### Wave 2 Success Criteria:
- [ ] Chart generation time <2s per chart
- [ ] GPU utilization <50% on first cycle, <30% on subsequent
- [ ] Bot auto-restarts on crash within 5min
- [ ] 99%+ uptime over 7 days

---

## Notes

- **GPU Optimization is Critical:** Your dev rig is under stress, this must be addressed early
- **Admin System Unlocks Self-Learning:** Once Wave 1 is complete, the bot can start improving itself
- **Modular Approach:** Each wave can be developed independently
- **Rollback Strategy:** Keep git tags for each wave completion for easy rollback
- **Testing:** Each wave should have pytest coverage before merging to main

---

**Next Action:** Review this roadmap, prioritize first weekend tasks, and begin Wave 1.1 + 2.1 implementation.
