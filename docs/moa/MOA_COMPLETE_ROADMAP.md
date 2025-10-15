# MOA Complete Implementation Roadmap
**Version:** 3.0 (Enhanced with Historical Scraper + Intraday Tracking)
**Last Updated:** 2025-01-14
**Status:** Phase 2 Complete, Moving to Phase 2.5

---

## Table of Contents
1. [Visual Overview](#visual-overview)
2. [Phase Status Summary](#phase-status-summary)
3. [Detailed Phase Breakdown](#detailed-phase-breakdown)
4. [Timeline & Dependencies](#timeline--dependencies)
5. [Data Requirements](#data-requirements)
6. [Success Metrics](#success-metrics)

---

## Visual Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MOA SYSTEM ARCHITECTURE                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐
│  PHASE 0     │  ✅ COMPLETE (Week 0)
│  Backtest    │  - PostgreSQL + TimescaleDB
│  Foundation  │  - VectorBT framework
└──────┬───────┘  - Multi-metric scoring
       │          - dataphase0/ module
       │
       ▼
┌──────────────┐
│  PHASE 1     │  ✅ COMPLETE (Week 3-4)
│  Data        │  - rejected_items_logger.py
│  Capture     │  - Integrated into runner.py
└──────┬───────┘  - Logging 150+ items/cycle
       │          - JSONL storage
       │
       ▼
┌──────────────┐
│  PHASE 2     │  ✅ COMPLETE (Week 5-7)
│  Analysis    │  - moa_analyzer.py (550 lines)
│  Engine      │  - moa_price_tracker.py
└──────┬───────┘  - 47 tests passing
       │          - Statistical validation
       │
       ▼
┌──────────────┐
│  PHASE 2.5A  │  🔄 NEXT (1 hour)
│  Enhanced    │  - Add 15min/30min timeframes
│  Live Track  │  - Modify moa_price_tracker.py
└──────┬───────┘  - Flash catalyst detection
       │          - Start collecting NOW
       │
       ▼
┌──────────────┐
│  PHASE 2.5B  │  🔄 NEXT (6-7 hours)
│  Historical  │  - 6-12 month data scraper
│  Scraper     │  - SEC + Finviz historical
└──────┬───────┘  - ~108k rejected items
       │          - Bootstrap MOA system
       │
       ▼
┌──────────────┐
│  PHASE 2.6   │  ⏳ PENDING (2-3 hours)
│  Pattern     │  - Flash vs Sustained classifier
│  Classifier  │  - PUMP detection
└──────┬───────┘  - Enhanced recommendations
       │
       ▼
┌──────────────┐
│  PHASE 3     │  ⏳ PENDING (Week 8-10)
│  Discord     │  - Rich embeds
│  Integration │  - Interactive buttons
└──────┬───────┘  - Admin approval flow
       │          - Report formatting
       │
       ▼
┌──────────────┐
│  PHASE 4     │  ⏳ PENDING (Week 11-12)
│  Learning    │  - Auto-approval (>90% conf)
│  Loop        │  - A/B testing framework
└──────┬───────┘  - Auto-rollback (Sharpe drop >10%)
       │          - 7-day cooling period
       │
       ▼
┌──────────────┐
│  PHASE 5     │  ⏳ PENDING (Week 13-14)
│  Production  │  - Shadow mode
│  Deployment  │  - Monitoring
└──────────────┘  - Full automation
```

---

## Phase Status Summary

| Phase | Name | Status | Time Est. | Priority | Blockers |
|-------|------|--------|-----------|----------|----------|
| **0** | Backtest Infrastructure | ✅ **DONE** | 2 weeks | Critical | None |
| **1** | Data Capture | ✅ **DONE** | 2 weeks | Critical | None |
| **2** | Analysis Engine | ✅ **DONE** | 3 weeks | Critical | None |
| **2.5A** | Enhanced Live Tracking | 🔄 **NEXT** | 1 hour | High | None |
| **2.5B** | Historical Scraper | 🔄 **NEXT** | 6-7 hrs | High | None |
| **2.6** | Pattern Classifier | ⏳ Pending | 2-3 hrs | Medium | 2.5A/B data |
| **3** | Discord Integration | ⏳ Pending | 3 weeks | High | Phase 2.6 |
| **4** | Learning Loop | ⏳ Pending | 2 weeks | Medium | Phase 3 |
| **5** | Production Deploy | ⏳ Pending | 2 weeks | High | Phase 4 |

**Progress:** 3/8 phases complete (37.5%)
**Next Milestone:** Phase 2.5A+B (Bootstrap MOA with historical data)
**Estimated Time to Phase 3:** 1 day (8 hours work)

---

## Detailed Phase Breakdown

### ✅ Phase 0: Historical Backtesting Infrastructure
**Status:** COMPLETE
**Duration:** Week 0 (Oct 2024)
**Location:** `dataphase0/`

#### Deliverables Completed:
- [x] PostgreSQL + TimescaleDB setup
- [x] Database schema (backtests, trades, results, walk_forward_windows)
- [x] VectorBT integration (1000x speedup)
- [x] Multi-metric scoring (Sharpe, Sortino, Calmar, Omega, F1)
- [x] Transaction cost modeling (6-8% round-trip for penny stocks)
- [x] Walk-forward optimizer class
- [x] Bootstrap validator class
- [x] Documentation + unit tests

#### Key Metrics:
```
Database Tables: 7
Performance Metrics Tracked: 23
Validation Methods: 3 (Walk-forward, Bootstrap, CPCV)
Test Coverage: 90%+
```

#### Files Created:
```
dataphase0/
├── backtest_runner.py       (Main orchestrator)
├── strategy_simulator.py    (Strategy execution)
├── validators.py            (Walk-forward, Bootstrap, CPCV)
├── metrics_calculator.py    (23 performance metrics)
├── database.py              (PostgreSQL interface)
└── tests/                   (Unit + integration tests)
```

---

### ✅ Phase 1: MOA Data Capture
**Status:** COMPLETE
**Duration:** Week 3-4 (Nov 2024)
**Location:** `src/catalyst_bot/rejected_items_logger.py`

#### Deliverables Completed:
- [x] Rejected items logging (JSONL format)
- [x] Price range filter ($0.10-$10.00)
- [x] Integration into runner.py at 7 rejection points
- [x] Classification metadata capture (score, sentiment, keywords)
- [x] Performance overhead <10ms per item

#### Integration Points:
```python
# runner.py rejection points (all instrumented):
1. BY_SOURCE          (line 1023)
2. INSTRUMENT_LIKE    (line 1054)
3. HIGH_PRICE         (line 1127)
4. LOW_SCORE          (line 1145)
5. SENT_GATE          (line 1162)
6. CAT_GATE           (line 1181)
```

#### Current Data:
```
data/rejected_items.jsonl
- Format: JSONL (one item per line)
- Current items: 2 (just started)
- Fields: ts, ticker, title, source, price, cls, rejection_reason
- File size: ~1 KB (will grow to ~50 MB/month)
```

#### Example Entry:
```json
{
  "ts": "2025-10-11T04:51:13.018407+00:00",
  "ticker": "SNAL",
  "title": "Snail Games 旗下 Wandering Wizard...",
  "source": "globenewswire_public",
  "price": 1.03,
  "cls": {
    "score": 0.0,
    "sentiment": 0.0,
    "keywords": []
  },
  "rejected": true,
  "rejection_reason": "LOW_SCORE"
}
```

---

### ✅ Phase 2: Analysis Engine
**Status:** COMPLETE
**Duration:** Week 5-7 (Dec 2024)
**Location:** `src/catalyst_bot/moa_analyzer.py`, `src/catalyst_bot/moa_price_tracker.py`

#### Deliverables Completed:
- [x] MOA analyzer (550 lines, 9 public functions)
- [x] Price outcome tracker (1h, 4h, 1d, 7d)
- [x] Missed opportunity identification (>10% threshold)
- [x] Keyword extraction with TF-IDF
- [x] Statistical validation (min 5 occurrences)
- [x] Recommendation generation
- [x] Integration into runner.py
- [x] Comprehensive test suite (47 tests)

#### Key Functions:
```python
# moa_analyzer.py
load_rejected_items()              # Load from JSONL
identify_missed_opportunities()    # Find >10% gainers
extract_keywords_from_missed()     # TF-IDF analysis
calculate_weight_recommendations() # Generate suggestions
save_recommendations()             # Output to JSON
run_moa_analysis()                 # Main pipeline

# moa_price_tracker.py
track_pending_outcomes()           # Main loop
record_outcome()                   # Fetch & log price
get_pending_items()                # Find items needing tracking
is_missed_opportunity()            # Check >10% threshold
```

#### Test Coverage:
```
test_moa_analyzer.py:      20 tests ✅
test_moa_price_tracker.py: 27 tests ✅
Total:                     47 tests ✅
Coverage:                  85%+
```

#### Current Timeframes:
```
1h  → 3600 seconds
4h  → 14400 seconds
1d  → 86400 seconds
7d  → 604800 seconds
```

---

### 🔄 Phase 2.5A: Enhanced Live Tracking (15min/30min)
**Status:** NEXT UP
**Duration:** 1 hour
**Priority:** HIGH (Start collecting data NOW)

#### Objectives:
1. Add 15-minute and 30-minute timeframes to price tracking
2. Enable "flash catalyst" detection
3. Distinguish quick spikes from sustained moves
4. Start data collection immediately for future analysis

#### Technical Changes:

**File:** `src/catalyst_bot/moa_price_tracker.py`

```python
# BEFORE:
TIMEFRAMES = {
    '1h': 3600,
    '4h': 14400,
    '1d': 86400,
    '7d': 604800,
}

# AFTER:
TIMEFRAMES = {
    '15m': 900,     # NEW - flash catalyst detection
    '30m': 1800,    # NEW - momentum confirmation
    '1h': 3600,
    '4h': 14400,
    '1d': 86400,
    '7d': 604800,
}
```

**New Function:**
```python
def fetch_intraday_price(ticker: str, minutes_ago: int) -> Optional[float]:
    """
    Fetch price N minutes ago using 1-minute bars.

    Uses yfinance 1-minute data (available for last 7 days).

    Args:
        ticker: Stock symbol
        minutes_ago: 15, 30, 60, etc.

    Returns:
        Price at that time, or None if unavailable
    """
    try:
        # Fetch last 1 day of 1-minute bars
        hist = yf.Ticker(ticker).history(period='1d', interval='1m')

        if hist.empty:
            return None

        # Get price from N minutes ago
        target_idx = -minutes_ago if len(hist) > minutes_ago else 0
        price = float(hist.iloc[target_idx]['Close'])

        return price

    except Exception as e:
        log.debug(f"intraday_price_fetch_failed ticker={ticker} err={e}")
        return None
```

#### Use Cases Enabled:

**1. Flash Catalyst Detection:**
```
News: "XYZ announces partnership"
15m: +18% (flash spike)
30m: +12% (fading)
1h: +6% (mostly faded)
→ Pattern: FLASH (hype-driven, not sustained)
```

**2. Sustained Momentum:**
```
News: "ABC receives FDA approval"
15m: +8% (initial reaction)
30m: +14% (building)
1h: +22% (accelerating)
→ Pattern: SUSTAINED (genuine catalyst)
```

**3. Delayed Reaction:**
```
News: "DEF announces offering"
15m: -2% (initial confusion)
30m: +1% (digesting)
1h: +12% (realized it's bullish)
→ Pattern: DELAYED (requires analysis time)
```

#### Data Collection:
- Start immediately: Every rejected item gets 15m/30m tracking
- Storage: `data/moa/outcomes.jsonl` (same file, new timeframes)
- Volume: +2 outcomes per rejected item = +300 outcomes/day
- File growth: +60 KB/day

#### Testing Plan:
1. Add 2 test cases to `test_moa_price_tracker.py`
2. Test with live data (next bot cycle)
3. Verify 15m/30m outcomes recorded correctly
4. Monitor for 24 hours before proceeding to Phase 2.5B

---

### 🔄 Phase 2.5B: Historical Data Scraper (6-12 Months)
**Status:** NEXT UP
**Duration:** 6-7 hours
**Priority:** HIGH (Bootstrap MOA system)

#### Objectives:
1. Backfill 6-12 months of rejected items
2. Fetch historical outcomes for all timeframes
3. Generate immediate MOA recommendations (no waiting weeks)
4. Enable walk-forward validation
5. Test full MOA pipeline end-to-end

#### Target Dataset:
```
Time Period: 6-12 months (configurable)
Rejected Items: ~54,000 (6mo) to ~108,000 (12mo)
Outcomes: 6 timeframes × items = ~324k-648k records
Storage: ~100-200 MB total
Processing Time: ~6-7 hours (one-time)
```

#### Data Sources & Capabilities:

**1. SEC EDGAR Feeds** ✅ Unlimited History
```
Sources:
- 8-K filings (material events)
- 424B5 (prospectus filings)
- FWP (free writing prospectus)
- 13D/13G (ownership changes)

Access Method:
https://www.sec.gov/cgi-bin/browse-edgar?
  action=getcurrent&
  type=8-K&
  datea=20240101&    # Start date
  dateb=20240131&    # End date
  count=100&
  output=atom

Rate Limits: None (public data)
Historical Depth: Unlimited (back to 1995)
Coverage: All public companies
```

**2. Finviz News** ✅ 6-12 Months Available
```
Access: Via authenticated API (you have finviz_auth_token)
Method: CSV export for historical data
Rate Limits: Manageable (1 req/sec recommended)
Historical Depth: 12+ months with auth
Coverage: Major news sources
```

**3. GlobeNewswire** ⚠️ Limited (30-90 days)
```
Access: RSS feeds (limited history)
Workaround: May have API for deeper access
Alternative: Focus on SEC + Finviz
```

**4. Price Data (yfinance)** ✅ Unlimited History
```
Granularity by Age:
- Last 7 days:     1-minute bars  ✅ Perfect for 15m/30m
- Last 60 days:    5-minute bars  ✅ Can calculate 15m/30m
- 60d - 2 years:   Hourly bars    ⚠️  Skip 15m/30m, use 1h+
- 2+ years:        Daily bars     ⚠️  Skip intraday entirely

Strategy: Smart timeframe selection based on age
```

#### Architecture:

**New File:** `src/catalyst_bot/historical_bootstrapper.py`

```python
class HistoricalBootstrapper:
    """
    Backfill 6-12 months of rejected items and outcomes.

    Process:
    1. Fetch historical feeds month-by-month
    2. Run through current classification logic
    3. Identify rejections based on current thresholds
    4. Fetch historical prices at multiple timeframes
    5. Write to rejected_items.jsonl and outcomes.jsonl
    """

    def __init__(
        self,
        start_date: str,        # '2024-01-15'
        end_date: str,          # '2025-01-14'
        sources: List[str],     # ['sec_8k', 'sec_424b5', 'finviz']
        batch_size: int = 1000,
        resume_checkpoint: bool = True
    ):
        self.start_date = datetime.fromisoformat(start_date)
        self.end_date = datetime.fromisoformat(end_date)
        self.sources = sources
        self.batch_size = batch_size
        self.checkpoint_file = Path('data/moa/bootstrap_checkpoint.json')

    def run(self):
        """Main execution loop."""
        # Load checkpoint if exists
        last_processed = self._load_checkpoint()

        # Process month by month
        for month_start in self._month_range(self.start_date, self.end_date):
            if last_processed and month_start <= last_processed:
                continue  # Skip already processed

            month_end = month_start + timedelta(days=30)

            # Fetch historical feeds for this month
            items = self._fetch_month_feeds(month_start, month_end)

            # Classify and filter (simulate rejection logic)
            rejected = self._simulate_rejections(items)

            # Fetch outcomes for rejected items
            self._fetch_outcomes_batch(rejected)

            # Write to data files
            self._write_rejected_items(rejected)

            # Save checkpoint
            self._save_checkpoint(month_end)

            log.info(f"bootstrap_month_complete month={month_start.strftime('%Y-%m')} "
                    f"items={len(items)} rejected={len(rejected)}")

    def _fetch_month_feeds(self, start: datetime, end: datetime) -> List[Dict]:
        """Fetch all feeds for a given month."""
        all_items = []

        for source in self.sources:
            if source.startswith('sec_'):
                items = self._fetch_sec_historical(source, start, end)
            elif source == 'finviz':
                items = self._fetch_finviz_historical(start, end)
            else:
                continue

            all_items.extend(items)

        return all_items

    def _simulate_rejections(self, items: List[Dict]) -> List[Dict]:
        """
        Run items through current classification logic.
        Simulate rejection based on current thresholds.
        """
        rejected = []

        # Load current thresholds
        min_score = float(os.getenv('MIN_SCORE', 0))
        price_ceiling = float(os.getenv('PRICE_CEILING', 10.0))
        min_sent_abs = float(os.getenv('MIN_SENT_ABS', 0))

        for item in items:
            ticker = item.get('ticker', '').strip()
            if not ticker:
                continue

            # Get price at time of event
            price = self._get_historical_price(ticker, item['ts'])
            if not price or price < 0.10 or price > 10.00:
                continue  # Outside MOA range

            # Classify (reuse existing logic)
            scored = classify(item)
            score = scored.get('score', 0)
            sentiment = scored.get('sentiment', 0)

            # Determine rejection
            rejection_reason = None

            if score < min_score:
                rejection_reason = 'LOW_SCORE'
            elif price > price_ceiling:
                rejection_reason = 'HIGH_PRICE'
            elif abs(sentiment) < min_sent_abs:
                rejection_reason = 'SENT_GATE'

            if rejection_reason:
                rejected.append({
                    **item,
                    'price': price,
                    'cls': scored,
                    'rejection_reason': rejection_reason
                })

        return rejected

    def _fetch_outcomes_batch(self, rejected_items: List[Dict]):
        """
        Fetch outcomes for all rejected items.
        Uses smart timeframe selection based on item age.
        """
        for item in rejected_items:
            rejection_date = datetime.fromisoformat(item['ts'])
            age_days = (datetime.now(timezone.utc) - rejection_date).days

            # Smart timeframe selection
            if age_days <= 60:
                # Recent: Can use 5-min bars for 15m/30m
                timeframes = ['15m', '30m', '1h', '4h', '1d', '7d']
            else:
                # Older: Only hourly+ data available
                timeframes = ['1h', '4h', '1d', '7d']

            outcomes = {}
            for tf in timeframes:
                outcome = self._fetch_historical_outcome(
                    item['ticker'],
                    rejection_date,
                    tf
                )
                if outcome is not None:
                    outcomes[tf] = outcome

            item['outcomes'] = outcomes

    def _fetch_sec_historical(
        self,
        filing_type: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """
        Fetch SEC filings for date range.

        Example URL:
        https://www.sec.gov/cgi-bin/browse-edgar?
            action=getcurrent&
            type=8-K&
            datea=20240101&
            dateb=20240131&
            count=100&
            output=atom
        """
        base_url = "https://www.sec.gov/cgi-bin/browse-edgar"

        params = {
            'action': 'getcurrent',
            'type': filing_type.replace('sec_', '').upper(),
            'datea': start.strftime('%Y%m%d'),
            'dateb': end.strftime('%Y%m%d'),
            'count': 100,
            'output': 'atom'
        }

        # Fetch and parse (reuse existing logic from feeds.py)
        # ...
        pass

    def _get_historical_price(self, ticker: str, timestamp: datetime) -> Optional[float]:
        """Get price at specific historical timestamp."""
        try:
            # Fetch daily data around that date
            start = timestamp - timedelta(days=1)
            end = timestamp + timedelta(days=1)

            hist = yf.Ticker(ticker).history(start=start, end=end)
            if hist.empty:
                return None

            # Find closest price
            return float(hist.iloc[0]['Close'])
        except:
            return None

    def _fetch_historical_outcome(
        self,
        ticker: str,
        rejection_ts: datetime,
        timeframe: str
    ) -> Optional[float]:
        """
        Fetch price outcome at specific timeframe after rejection.

        Returns price change percentage.
        """
        tf_seconds = TIMEFRAMES[timeframe]
        target_ts = rejection_ts + timedelta(seconds=tf_seconds)

        try:
            # Determine appropriate yfinance interval
            if timeframe in ['15m', '30m']:
                interval = '5m'  # 5-min bars (last 60 days)
                period = '60d'
            elif timeframe in ['1h', '4h']:
                interval = '1h'
                period = '730d'  # 2 years
            else:
                interval = '1d'
                period = 'max'

            # Fetch data
            hist = yf.Ticker(ticker).history(period=period, interval=interval)
            if hist.empty:
                return None

            # Find closest price to target timestamp
            # (simplified - full implementation would use bisect)
            closest_row = hist.iloc[hist.index.get_indexer([target_ts], method='nearest')[0]]
            outcome_price = float(closest_row['Close'])

            # Calculate return
            rejection_price = self._get_historical_price(ticker, rejection_ts)
            if rejection_price:
                return_pct = ((outcome_price - rejection_price) / rejection_price) * 100
                return return_pct

            return None
        except:
            return None
```

#### CLI Interface:

```bash
# Run bootstrapper
python -m catalyst_bot.historical_bootstrapper \
    --start-date 2024-01-15 \
    --end-date 2025-01-14 \
    --sources sec_8k,sec_424b5,sec_fwp,finviz \
    --batch-size 1000 \
    --resume

# Options:
#   --start-date: Start of historical scraping (YYYY-MM-DD)
#   --end-date: End date (YYYY-MM-DD)
#   --sources: Comma-separated list of sources
#   --batch-size: Items per batch (default 1000)
#   --resume: Resume from checkpoint if interrupted
#   --dry-run: Don't write to files, just show stats
```

#### Execution Plan:

**Step 1: Configure & Test (30 min)**
```bash
# Dry run for 1 month
python -m catalyst_bot.historical_bootstrapper \
    --start-date 2024-12-01 \
    --end-date 2024-12-31 \
    --sources sec_8k \
    --dry-run
```

**Step 2: Run 6-Month Scrape (3 hours)**
```bash
# Full 6-month backfill
python -m catalyst_bot.historical_bootstrapper \
    --start-date 2024-07-15 \
    --end-date 2025-01-14 \
    --sources sec_8k,sec_424b5,sec_fwp,finviz \
    --resume
```

**Step 3: Validate Data (30 min)**
```bash
# Check data quality
python -c "
from catalyst_bot.moa_analyzer import load_rejected_items
items = load_rejected_items(since_days=180)
print(f'Total rejected items: {len(items)}')
print(f'With outcomes: {sum(1 for i in items if i.get(\"outcomes\"))}')
"
```

**Step 4: Run MOA Analysis (10 min)**
```bash
# Generate recommendations from historical data
python -c "
from catalyst_bot.moa_analyzer import run_moa_analysis
results = run_moa_analysis(since_days=180)
print(results)
"
```

#### Expected Results:

**6-Month Scrape:**
```
Total items scraped: ~50,000
Rejected items: ~54,000 (150/cycle × 60 cycles/mo × 6 mo)
With outcomes: ~54,000 (100% coverage)
Keywords discovered: 20-30
Statistically significant: 15-20 (p<0.05)
```

**12-Month Scrape:**
```
Total items scraped: ~100,000
Rejected items: ~108,000
With outcomes: ~108,000
Keywords discovered: 40-50
Statistically significant: 25-35 (p<0.05)
Walk-forward windows: 3-4 (train/test splits)
```

#### Risk Mitigation:

**1. Checkpoint System**
```json
// data/moa/bootstrap_checkpoint.json
{
  "last_processed_date": "2024-06-30",
  "items_processed": 25000,
  "rejected_count": 27000,
  "elapsed_seconds": 10800,
  "estimated_completion": "2025-01-14T18:00:00Z"
}
```

**2. Rate Limiting**
```python
# SEC: No rate limit (public data)
# Finviz: 1 req/sec
time.sleep(1.0)

# yfinance: 2 req/sec recommended
time.sleep(0.5)
```

**3. Error Recovery**
```python
@retry(max_attempts=3, backoff=2.0)
def fetch_with_backoff(url):
    """Exponential backoff on errors."""
    pass
```

**4. Data Validation**
```python
def validate_outcomes(item):
    """Ensure outcomes are reasonable."""
    for tf, return_pct in item['outcomes'].items():
        if abs(return_pct) > 1000:  # 10x = suspicious
            log.warning(f"suspicious_return ticker={item['ticker']} "
                       f"tf={tf} return={return_pct}%")
            return False
    return True
```

---

### ⏳ Phase 2.6: Pattern Classification
**Status:** PENDING (Requires Phase 2.5 data)
**Duration:** 2-3 hours
**Priority:** MEDIUM

#### Objectives:
1. Classify catalyst behavior patterns
2. Enhance keyword recommendations with pattern data
3. Detect pump & dump schemes
4. Provide actionable insights for trading

#### Pattern Types:

**1. FLASH (Quick spike, then fade)**
```python
def is_flash_catalyst(outcomes: Dict[str, float]) -> bool:
    """
    Signature: Strong 15m move, weak 1h move.

    Example:
    - 15m: +18%
    - 30m: +12%
    - 1h: +6%
    → Hype-driven, fades quickly
    """
    return (
        outcomes.get('15m', 0) > 8.0 and
        outcomes.get('1h', 0) < outcomes.get('15m', 0) * 0.5
    )
```

**2. SUSTAINED (Builds momentum)**
```python
def is_sustained_catalyst(outcomes: Dict[str, float]) -> bool:
    """
    Signature: Accelerates over time.

    Example:
    - 15m: +8%
    - 1h: +15%
    - 4h: +22%
    → Genuine interest, follow-through
    """
    return (
        outcomes.get('15m', 0) > 5.0 and
        outcomes.get('1h', 0) > outcomes.get('15m', 0) * 1.2 and
        outcomes.get('4h', 0) > outcomes.get('1h', 0)
    )
```

**3. DELAYED (Slow initial, accelerates later)**
```python
def is_delayed_catalyst(outcomes: Dict[str, float]) -> bool:
    """
    Signature: Weak 15m, strong 4h.

    Example:
    - 15m: +2%
    - 1h: +5%
    - 4h: +18%
    → Complex news requiring analysis
    """
    return (
        outcomes.get('15m', 0) < 3.0 and
        outcomes.get('4h', 0) > 10.0
    )
```

**4. PUMP (Suspicious extreme spike)**
```python
def is_pump_scheme(outcomes: Dict[str, float]) -> bool:
    """
    Signature: Extreme 15m spike (likely manipulation).

    Example:
    - 15m: +45%
    - 30m: +35%
    - 1h: +10%
    → Coordinated pump, avoid
    """
    return outcomes.get('15m', 0) > 30.0
```

#### Implementation:

**File:** `src/catalyst_bot/moa_pattern_classifier.py`

```python
class CatalystPatternClassifier:
    """
    Classify catalyst behavior patterns based on multi-timeframe outcomes.
    """

    PATTERNS = {
        'PUMP': {
            'priority': 1,  # Check first (most dangerous)
            'description': 'Extreme spike, likely manipulation',
            'signature': lambda o: o.get('15m', 0) > 30.0,
            'recommendation': 'AVOID - Suspicious activity'
        },
        'FLASH': {
            'priority': 2,
            'description': 'Quick spike, then fade',
            'signature': lambda o: (
                o.get('15m', 0) > 8.0 and
                o.get('1h', 0) < o.get('15m', 0) * 0.5
            ),
            'recommendation': 'CAUTION - Hype-driven, fades quickly'
        },
        'SUSTAINED': {
            'priority': 3,
            'description': 'Builds momentum over time',
            'signature': lambda o: (
                o.get('15m', 0) > 5.0 and
                o.get('1h', 0) > o.get('15m', 0) * 1.2 and
                o.get('4h', 0) > o.get('1h', 0)
            ),
            'recommendation': 'STRONG - Genuine catalyst with follow-through'
        },
        'DELAYED': {
            'priority': 4,
            'description': 'Slow initial reaction, accelerates later',
            'signature': lambda o: (
                o.get('15m', 0) < 3.0 and
                o.get('4h', 0) > 10.0
            ),
            'recommendation': 'MODERATE - Complex news, watch for confirmation'
        }
    }

    def classify(self, outcomes: Dict[str, float]) -> Dict[str, Any]:
        """
        Classify catalyst pattern.

        Args:
            outcomes: Dict of {timeframe: return_pct}
                     e.g. {'15m': 12.5, '1h': 8.2, '4h': 15.3}

        Returns:
            {
                'pattern': 'SUSTAINED',
                'confidence': 0.85,
                'description': 'Builds momentum over time',
                'recommendation': 'STRONG - ...'
            }
        """
        # Sort patterns by priority
        sorted_patterns = sorted(
            self.PATTERNS.items(),
            key=lambda x: x[1]['priority']
        )

        for pattern_name, pattern_def in sorted_patterns:
            if pattern_def['signature'](outcomes):
                confidence = self._calculate_confidence(outcomes, pattern_name)

                return {
                    'pattern': pattern_name,
                    'confidence': confidence,
                    'description': pattern_def['description'],
                    'recommendation': pattern_def['recommendation'],
                    'timeframe_data': outcomes
                }

        return {
            'pattern': 'UNKNOWN',
            'confidence': 0.0,
            'description': 'No clear pattern detected',
            'recommendation': 'NEUTRAL - Monitor for more data'
        }

    def _calculate_confidence(self, outcomes: Dict[str, float], pattern: str) -> float:
        """
        Calculate confidence score (0-1) for pattern match.

        Based on:
        - Data completeness (how many timeframes available)
        - Pattern strength (how well it matches)
        """
        # Data completeness
        expected_timeframes = ['15m', '30m', '1h', '4h', '1d']
        available = sum(1 for tf in expected_timeframes if tf in outcomes)
        completeness = available / len(expected_timeframes)

        # Pattern strength (simplified)
        strength = 1.0  # TODO: Calculate based on how strongly signature matches

        confidence = (completeness * 0.3) + (strength * 0.7)
        return round(confidence, 2)

    def analyze_keyword_patterns(
        self,
        missed_opportunities: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analyze patterns for each keyword.

        Returns:
        {
            'fda approval': {
                'pattern_distribution': {
                    'SUSTAINED': 12,
                    'DELAYED': 5,
                    'FLASH': 2
                },
                'dominant_pattern': 'SUSTAINED',
                'avg_15m_return': 8.5,
                'avg_1h_return': 15.2,
                'recommendation': 'STRONG - Sustained catalysts'
            }
        }
        """
        keyword_patterns = {}

        for opp in missed_opportunities:
            keywords = opp.get('cls', {}).get('keywords', [])
            outcomes = opp.get('outcomes', {})

            if not outcomes:
                continue

            # Classify pattern
            pattern_result = self.classify(outcomes)

            for keyword in keywords:
                if keyword not in keyword_patterns:
                    keyword_patterns[keyword] = {
                        'pattern_counts': {},
                        'outcomes_15m': [],
                        'outcomes_1h': [],
                        'outcomes_4h': []
                    }

                # Update pattern distribution
                pattern = pattern_result['pattern']
                keyword_patterns[keyword]['pattern_counts'][pattern] = \
                    keyword_patterns[keyword]['pattern_counts'].get(pattern, 0) + 1

                # Collect outcome data
                if '15m' in outcomes:
                    keyword_patterns[keyword]['outcomes_15m'].append(outcomes['15m'])
                if '1h' in outcomes:
                    keyword_patterns[keyword]['outcomes_1h'].append(outcomes['1h'])
                if '4h' in outcomes:
                    keyword_patterns[keyword]['outcomes_4h'].append(outcomes['4h'])

        # Aggregate statistics
        for keyword, data in keyword_patterns.items():
            # Dominant pattern
            if data['pattern_counts']:
                dominant = max(data['pattern_counts'].items(), key=lambda x: x[1])
                data['dominant_pattern'] = dominant[0]
            else:
                data['dominant_pattern'] = 'UNKNOWN'

            # Average returns
            data['avg_15m_return'] = np.mean(data['outcomes_15m']) if data['outcomes_15m'] else 0
            data['avg_1h_return'] = np.mean(data['outcomes_1h']) if data['outcomes_1h'] else 0
            data['avg_4h_return'] = np.mean(data['outcomes_4h']) if data['outcomes_4h'] else 0

            # Recommendation
            data['recommendation'] = self._keyword_recommendation(data)

        return keyword_patterns

    def _keyword_recommendation(self, keyword_data: Dict) -> str:
        """Generate recommendation for keyword based on pattern analysis."""
        dominant = keyword_data.get('dominant_pattern', 'UNKNOWN')
        avg_15m = keyword_data.get('avg_15m_return', 0)
        avg_1h = keyword_data.get('avg_1h_return', 0)

        if dominant == 'PUMP':
            return 'AVOID - High manipulation risk'
        elif dominant == 'FLASH':
            return 'CAUTION - Quick fades, requires fast execution'
        elif dominant == 'SUSTAINED':
            if avg_1h > 12.0:
                return 'STRONG INCREASE - Consistent sustained catalysts'
            else:
                return 'MODERATE INCREASE - Decent follow-through'
        elif dominant == 'DELAYED':
            return 'HOLD - Wait for confirmation before entering'
        else:
            return 'INSUFFICIENT DATA - Continue monitoring'
```

#### Integration with MOA Analyzer:

```python
# In moa_analyzer.py, enhance run_moa_analysis():

def run_moa_analysis(since_days: int = 30) -> Dict[str, Any]:
    """Run complete MOA analysis pipeline."""

    # ... existing code ...

    # NEW: Pattern classification
    from catalyst_bot.moa_pattern_classifier import CatalystPatternClassifier

    classifier = CatalystPatternClassifier()
    keyword_patterns = classifier.analyze_keyword_patterns(missed_opportunities)

    # Enhance recommendations with pattern data
    for rec in recommendations:
        keyword = rec['keyword']
        if keyword in keyword_patterns:
            pattern_data = keyword_patterns[keyword]
            rec['pattern_analysis'] = {
                'dominant_pattern': pattern_data['dominant_pattern'],
                'avg_15m_return': pattern_data['avg_15m_return'],
                'avg_1h_return': pattern_data['avg_1h_return'],
                'pattern_recommendation': pattern_data['recommendation']
            }

    return {
        # ... existing fields ...
        'pattern_analysis': keyword_patterns,
        'recommendations_enhanced': recommendations
    }
```

#### Example Enhanced Recommendation:

```json
{
  "keyword": "fda approval",
  "type": "weight_increase",
  "current_weight": 1.5,
  "recommended_weight": 2.0,
  "confidence": 0.88,
  "evidence": {
    "occurrences": 18,
    "success_rate": 0.72,
    "avg_return": 0.165
  },
  "pattern_analysis": {
    "dominant_pattern": "SUSTAINED",
    "avg_15m_return": 8.3,
    "avg_1h_return": 15.7,
    "avg_4h_return": 22.4,
    "pattern_distribution": {
      "SUSTAINED": 13,
      "DELAYED": 4,
      "FLASH": 1
    },
    "pattern_recommendation": "STRONG INCREASE - Consistent sustained catalysts"
  }
}
```

---

### ⏳ Phase 3: Discord Integration
**Status:** PENDING
**Duration:** 3 weeks (Week 8-10)
**Priority:** HIGH

#### Objectives:
1. Rich Discord embeds for MOA reports
2. Interactive approval buttons
3. Admin control integration
4. Automated scheduling (nightly 2 AM UTC)

#### Components:

**1. Discord Embed Builder**
```python
def build_moa_report_embed(analysis_results: Dict) -> Dict:
    """
    Create rich Discord embed from MOA analysis.

    Includes:
    - Summary statistics
    - Top keyword recommendations
    - Pattern analysis highlights
    - Approval buttons
    """

    embed = {
        "title": "🔍 Missed Opportunities Analysis",
        "color": 0x5865F2,  # Discord blurple
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {
                "name": "📊 Summary",
                "value": (
                    f"Analysis Period: {analysis_results['analysis_period']}\n"
                    f"Total Rejected: {analysis_results['total_rejected']:,}\n"
                    f"Missed Opportunities: {analysis_results['missed_opportunities']}\n"
                    f"Hit Rate: {analysis_results['hit_rate']:.1%}"
                ),
                "inline": False
            },
            {
                "name": "✨ New Keywords Discovered",
                "value": _format_keywords(analysis_results['new_keywords'][:5]),
                "inline": False
            },
            {
                "name": "⚖️ Weight Adjustments",
                "value": _format_adjustments(analysis_results['weight_adjustments'][:5]),
                "inline": False
            }
        ],
        "footer": {
            "text": "Click buttons below to approve/reject recommendations"
        }
    }

    return embed
```

**2. Interactive Approval Buttons**
```python
# Discord buttons for admin approval
buttons = [
    {
        "type": 2,  # Button
        "style": 3,  # Green (success)
        "label": "✅ Approve High Confidence (8)",
        "custom_id": "moa_approve_high"
    },
    {
        "type": 2,
        "style": 1,  # Blue (primary)
        "label": "👀 Review Medium (5)",
        "custom_id": "moa_review_medium"
    },
    {
        "type": 2,
        "style": 4,  # Red (danger)
        "label": "❌ Reject All",
        "custom_id": "moa_reject_all"
    }
]
```

**3. Scheduled Nightly Run**
```python
# In runner.py, add MOA scheduling
current_hour = datetime.now(timezone.utc).hour

if current_hour == 2 and not ran_moa_today:
    # Run MOA analysis
    results = run_moa_analysis(since_days=7)

    # Send Discord report
    send_moa_report(results)

    ran_moa_today = True
elif current_hour != 2:
    ran_moa_today = False
```

#### Deliverables:
- [ ] Discord embed builder
- [ ] Button interaction handler
- [ ] Admin approval workflow
- [ ] Nightly scheduling
- [ ] Error handling & logging

---

### ⏳ Phase 4: Learning Loop with Auto-Approval
**Status:** PENDING
**Duration:** 2 weeks (Week 11-12)
**Priority:** MEDIUM

#### Objectives:
1. Automated approval for high-confidence recommendations (>90%)
2. A/B testing framework for medium-confidence changes
3. Performance monitoring with auto-rollback
4. 7-day cooling period between changes

#### Safety Mechanisms:

**1. Confidence-Based Routing**
```python
def process_recommendations(recommendations: List[Dict]) -> Dict:
    """
    Route recommendations based on confidence level.

    High (>90%): Auto-approve
    Medium (70-90%): Manual review
    Low (<70%): A/B test
    """
    actions = {
        'auto_approved': [],
        'manual_review': [],
        'ab_test': []
    }

    for rec in recommendations:
        conf = rec['confidence']

        if conf >= 0.90:
            apply_weight_change(rec)
            actions['auto_approved'].append(rec)
        elif conf >= 0.70:
            queue_for_review(rec)
            actions['manual_review'].append(rec)
        else:
            setup_ab_test(rec)
            actions['ab_test'].append(rec)

    return actions
```

**2. Auto-Rollback Triggers**
```python
def monitor_performance():
    """
    Monitor post-change performance.

    Rollback if:
    - Sharpe drops >10%
    - Drawdown exceeds baseline by 2x
    - Win rate drops >15 percentage points
    """
    current_sharpe = calculate_current_sharpe()
    baseline_sharpe = get_baseline_sharpe()

    degradation = (baseline_sharpe - current_sharpe) / baseline_sharpe

    if degradation > 0.10:
        rollback("Sharpe degradation: {:.1%}".format(degradation))
```

**3. 7-Day Cooling Period**
```python
def can_make_changes() -> bool:
    """Enforce minimum 7 days between weight changes."""
    last_change = get_last_change_date()
    days_since = (datetime.now() - last_change).days

    return days_since >= 7
```

#### Deliverables:
- [ ] Auto-approval logic
- [ ] A/B testing framework
- [ ] Performance monitoring
- [ ] Auto-rollback implementation
- [ ] Change audit trail
- [ ] Cooling period enforcement

---

### ⏳ Phase 5: Production Deployment
**Status:** PENDING
**Duration:** 2 weeks (Week 13-14)
**Priority:** HIGH

#### Objectives:
1. Shadow mode (analysis only, no changes)
2. Monitor for errors and edge cases
3. Performance optimization
4. Enable auto-approval
5. Documentation & handoff

#### Deployment Stages:

**Stage 1: Shadow Mode (Week 13)**
```
- MOA runs nightly, generates reports
- Discord notifications sent
- NO weight changes applied
- Monitor for crashes, errors, anomalies
```

**Stage 2: Manual Approval Only (Week 13)**
```
- Admin reviews and approves changes manually
- MOA applies approved changes
- Monitor performance closely
- Verify no degradation
```

**Stage 3: Auto-Approval Enabled (Week 14)**
```
- High-confidence changes auto-applied
- Medium/low still require review
- Auto-rollback armed and monitoring
- Full production mode
```

#### Success Criteria:
- [ ] 7 days shadow mode with zero crashes
- [ ] 3 manual approvals executed successfully
- [ ] Performance metrics stable or improved
- [ ] Documentation complete
- [ ] Team trained on MOA system

---

## Timeline & Dependencies

### Gantt Chart (Text Format)

```
Week  Phase         Status      Deliverables
───────────────────────────────────────────────────────────────────
  0   Phase 0       ✅ DONE     Backtest foundation
 1-2  (continued)                VectorBT, validators
 3-4  Phase 1       ✅ DONE     Rejected items logging
 5-7  Phase 2       ✅ DONE     MOA analyzer + tracker

  8   Phase 2.5A    🔄 NEXT     15min/30min tracking     [1 hour]
  8   Phase 2.5B    🔄 NEXT     Historical scraper       [6-7 hours]
  8   (continued)                ├─ SEC feeds
  8   (continued)                ├─ Finviz data
  8   (continued)                └─ Outcome fetching

  9   Phase 2.6     ⏳ PENDING   Pattern classifier       [2-3 hours]
  9   (continued)                ├─ Flash/Sustained
  9   (continued)                ├─ PUMP detection
  9   (continued)                └─ Keyword patterns

10-11 Phase 3       ⏳ PENDING   Discord integration      [2 weeks]
  10  (Week 1)                   ├─ Embed builder
  10  (continued)                ├─ Button handlers
  11  (Week 2)                   ├─ Approval workflow
  11  (continued)                └─ Nightly scheduling

12-13 Phase 4       ⏳ PENDING   Learning loop            [2 weeks]
  12  (Week 1)                   ├─ Auto-approval
  12  (continued)                ├─ A/B testing
  13  (Week 2)                   ├─ Performance monitor
  13  (continued)                └─ Auto-rollback

14-15 Phase 5       ⏳ PENDING   Production deploy        [2 weeks]
  14  (Week 1)                   ├─ Shadow mode
  14  (continued)                ├─ Manual approval
  15  (Week 2)                   ├─ Auto-approval ON
  15  (continued)                └─ Full production
```

### Critical Path

```
Phase 0 ──> Phase 1 ──> Phase 2 ──> Phase 2.5A/B ──> Phase 2.6
                                           │
                                           ▼
                                      Phase 3 ──> Phase 4 ──> Phase 5
```

**Critical Dependencies:**
- Phase 2.5A/B must complete before Phase 2.6 (need data for patterns)
- Phase 2.6 must complete before Phase 3 (need patterns for Discord reports)
- Phase 3 must complete before Phase 4 (need approval UI for auto-approval)
- Phase 4 must complete before Phase 5 (need safety checks for production)

**Parallel Opportunities:**
- Phase 2.5A and 2.5B can run concurrently (live tracking + historical scraping)
- Phase 3 Discord work can start while Phase 2.6 runs (UI work is independent)

---

## Data Requirements

### Current Data State

```
data/
├── rejected_items.jsonl          [✅ Active, 2 items so far]
├── moa/
│   ├── outcomes.jsonl            [❌ Not created yet]
│   ├── recommendations.json       [❌ Not created yet]
│   └── bootstrap_checkpoint.json [❌ Not created yet]
├── analyzer/
│   └── keyword_stats.json        [✅ Exists, current weights]
└── feedback/
    └── alert_performance.db      [✅ Exists, Wave 1.2]
```

### After Phase 2.5B (Historical Scraper)

```
data/
├── rejected_items.jsonl          [~108,000 items, ~21 MB]
├── moa/
│   ├── outcomes.jsonl            [~648,000 outcomes, ~130 MB]
│   ├── recommendations.json       [Latest analysis]
│   ├── bootstrap_checkpoint.json [Resume point]
│   └── archives/
│       ├── recommendations_2025-01-14.json
│       ├── recommendations_2025-01-21.json
│       └── ...
└── analyzer/
    └── keyword_stats.json        [Enhanced with MOA learnings]
```

### Storage Projections

**6-Month Scrape:**
```
Rejected items:     54,000 items  ×  400 bytes  =   21.6 MB
Outcomes:          324,000 items  ×  400 bytes  =  129.6 MB
Recommendations:        Weekly    ×    5 KB    =    0.3 MB
──────────────────────────────────────────────────────────
Total:                                            ~151 MB
```

**12-Month Scrape:**
```
Rejected items:    108,000 items  ×  400 bytes  =   43.2 MB
Outcomes:          648,000 items  ×  400 bytes  =  259.2 MB
Recommendations:        Weekly    ×    5 KB    =    0.6 MB
──────────────────────────────────────────────────────────
Total:                                            ~303 MB
```

**Ongoing Growth (per month):**
```
New rejected items:  9,000 items  ×  400 bytes  =    3.6 MB
New outcomes:       54,000 items  ×  400 bytes  =   21.6 MB
──────────────────────────────────────────────────────────
Total:                                             ~25 MB/month
```

**Annual growth:** ~300 MB/year (very manageable)

---

## Success Metrics

### Phase Completion Criteria

**Phase 2.5A (15/30min tracking):**
```
✅ 15m/30m timeframes added to TIMEFRAMES dict
✅ fetch_intraday_price() implemented
✅ 2 test cases added and passing
✅ First rejected item has 15m/30m outcomes
✅ No errors in 24-hour monitoring
```

**Phase 2.5B (Historical scraper):**
```
✅ Can scrape 1 month of SEC data successfully
✅ Classification logic matches live system
✅ Outcomes fetched for all 6 timeframes
✅ 54,000+ rejected items backfilled (6 months)
✅ Data validation passes (reasonable returns, no anomalies)
✅ MOA analysis runs on historical data
✅ 15-20 keywords discovered with p<0.05
```

**Phase 2.6 (Pattern classifier):**
```
✅ Patterns classified: FLASH, SUSTAINED, DELAYED, PUMP
✅ Confidence scores calculated
✅ Keyword pattern analysis complete
✅ Enhanced recommendations include pattern data
✅ 3 test cases for each pattern type
```

**Phase 3 (Discord integration):**
```
✅ Rich embeds render correctly
✅ Interactive buttons functional
✅ Admin can approve/reject via Discord
✅ Nightly scheduling works reliably
✅ Error handling prevents crashes
```

**Phase 4 (Learning loop):**
```
✅ Auto-approval works for high-confidence (>90%)
✅ A/B testing framework functional
✅ Performance monitoring detects degradation
✅ Auto-rollback triggers when Sharpe drops >10%
✅ 7-day cooling period enforced
✅ Change audit trail complete
```

**Phase 5 (Production):**
```
✅ 7 days shadow mode with zero crashes
✅ 3+ manual approvals executed successfully
✅ Performance metrics stable or improved
✅ Auto-approval enabled and monitoring
✅ Documentation complete
✅ Team trained
```

### Overall Success Targets (6 Months)

**Quantitative:**
```
New keywords discovered:        20-30 (with p<0.05)
False negative reduction:       30-40%
Sharpe improvement:             +20-25%
F1 score:                       0.50-0.60
Walk-forward efficiency:        >0.60
Bootstrap confidence:           >70%
Validated trades:               385+ (95% confidence)
Manual tuning time:             <5 hrs/month (down from 10)
```

**Qualitative:**
```
✅ MOA runs reliably every night
✅ Admin reviews reports in <5 minutes
✅ System learns from mistakes automatically
✅ Keyword weights improve continuously
✅ No manual keyword hunting required
✅ Backtests validate all changes
✅ Rollback protection prevents disasters
```

---

## Next Actions

### Immediate (Today):
1. ✅ Create this roadmap document
2. 🔄 Implement Phase 2.5A (15/30min tracking) - **1 hour**
3. 🔄 Implement Phase 2.5B (Historical scraper) - **6-7 hours**

### This Week:
4. Run 6-month historical scrape
5. Validate scraped data quality
6. Generate first MOA recommendations from historical data
7. Implement Phase 2.6 (Pattern classifier)

### Next Week:
8. Begin Phase 3 (Discord integration)
9. Design embed layouts
10. Implement button handlers

---

## Risk Assessment

### High-Risk Items

**1. Historical Data Quality**
- **Risk:** SEC feeds may have gaps, yfinance may fail for some tickers
- **Mitigation:** Validate data at each step, log failures, accept 90%+ success rate

**2. Classification Drift**
- **Risk:** Current classification logic may not match historical behavior
- **Mitigation:** Use point-in-time parameter snapshots, document any config changes

**3. Timeframe Data Availability**
- **Risk:** 15/30min data only available for last 60 days
- **Mitigation:** Smart timeframe selection, skip intraday for old data

**4. Performance Degradation**
- **Risk:** Auto-approved changes could harm performance
- **Mitigation:** Auto-rollback, 7-day cooling period, manual review for medium confidence

### Medium-Risk Items

**1. Discord Rate Limits**
- **Risk:** Large reports may hit Discord message size limits
- **Mitigation:** Paginate long reports, use attachments for detailed data

**2. Database Growth**
- **Risk:** 300 MB/year could become unwieldy
- **Mitigation:** Archive old data, implement retention policies, compress JSONL

**3. A/B Testing Complexity**
- **Risk:** Running parallel weight schemes could confuse analysis
- **Mitigation:** Start simple (no A/B in Phase 4), add if needed later

---

## Appendix: File Structure

```
catalyst-bot/
├── src/catalyst_bot/
│   ├── rejected_items_logger.py         [✅ Phase 1]
│   ├── moa_analyzer.py                  [✅ Phase 2]
│   ├── moa_price_tracker.py             [✅ Phase 2]
│   ├── historical_bootstrapper.py       [🔄 Phase 2.5B - TO BUILD]
│   ├── moa_pattern_classifier.py        [⏳ Phase 2.6 - TO BUILD]
│   ├── moa_discord_reporter.py          [⏳ Phase 3 - TO BUILD]
│   └── moa_learning_loop.py             [⏳ Phase 4 - TO BUILD]
│
├── dataphase0/                          [✅ Phase 0]
│   ├── backtest_runner.py
│   ├── strategy_simulator.py
│   ├── validators.py
│   ├── metrics_calculator.py
│   └── database.py
│
├── tests/
│   ├── test_moa_analyzer.py             [✅ 20 tests]
│   ├── test_moa_price_tracker.py        [✅ 27 tests]
│   ├── test_historical_bootstrapper.py  [⏳ TO BUILD]
│   ├── test_moa_pattern_classifier.py   [⏳ TO BUILD]
│   └── test_moa_learning_loop.py        [⏳ TO BUILD]
│
├── data/
│   ├── rejected_items.jsonl             [✅ Active]
│   └── moa/
│       ├── outcomes.jsonl               [⏳ After 2.5B]
│       ├── recommendations.json         [⏳ After 2.5B]
│       └── bootstrap_checkpoint.json    [⏳ After 2.5B]
│
└── docs/
    ├── MOA_DESIGN_V2.md                 [✅ Exists]
    ├── MOA_EXECUTIVE_SUMMARY.md         [✅ Exists]
    ├── MOA_COMPLETION_SUMMARY.md        [✅ Exists]
    └── MOA_COMPLETE_ROADMAP.md          [✅ This file]
```

---

## Conclusion

**Current Status:** 3/8 phases complete (37.5%)

**Next Milestone:** Phase 2.5A+B (1 day, 8 hours work)

**Time to Production:** ~8-10 weeks (with full testing)

**Immediate Value:** Historical scraper will provide instant insights (no waiting weeks for data)

**Long-term Value:** Fully automated learning system that continuously improves keyword weights with statistical validation

**Key Insight from Our Discussion:** 15/30-minute tracking captures flash catalysts that fade quickly vs. sustained moves - critical for penny stock behavior patterns.

---

**Ready to proceed with Phase 2.5A (15/30min tracking)?**
