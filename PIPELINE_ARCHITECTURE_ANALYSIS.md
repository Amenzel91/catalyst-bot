# Catalyst-Bot News Alert Pipeline - Complete Architecture Analysis

## 1. ENTRY POINT & MAIN LOOP

### Main Entry Point: `/home/user/catalyst-bot/main.py`
- Entry point dispatcher that routes to:
  - `runner.main(once=once, loop=args.loop)` - Main bot runner
  - `analyzer.main(date=args.date)` - End-of-day analyzer

### Primary Bot Runner: `src/catalyst_bot/runner.py`
- **Function**: `runner_main(once=False, loop=True, sleep_s=None)`
- **Location**: Line 2952+
- **Configuration**:
  - Default polling interval: `LOOP_SECONDS` env var (default: **30 seconds**)
  - Can be overridden with market-aware cycle times
  - Graceful shutdown via SIGINT/SIGTERM signals

#### Main Loop Flow (Line 3088+):
```
while True:
  1. Check market status (if FEATURE_MARKET_HOURS_DETECTION enabled)
  2. Optional market-aware cycle adjustment:
     - MARKET_OPEN_CYCLE_SEC (during trading hours)
     - EXTENDED_HOURS_CYCLE_SEC (before/after market)
     - MARKET_CLOSED_CYCLE_SEC (market closed, 180s default)
  3. Execute _cycle() - the core processing loop
  4. Sleep until next cycle (with early exit on STOP signal)
  5. Optional heartbeat every HEARTBEAT_INTERVAL_MIN (default: 60 minutes)
```

---

## 2. CORE CYCLE PROCESSING - `_cycle()` Function

**Location**: `runner.py:985+`

### 2.1 News Fetching Stage (Ingest)

#### A. Async Concurrent Feed Fetching
- **Function**: `feeds.fetch_pr_feeds()` (Line 1099)
- **Architecture**: Async concurrent RSS/Atom feed fetching (10-20x faster than sequential)
- **Timeout**: 8 seconds per HTTP request (sentiment_sources.py)

**Feed Sources (with env overrides)**:
1. **Finnhub** (High-frequency news & catalysts)
   - `fetch_finnhub_news(max_items=30)` - Real-time news
   - `fetch_finnhub_earnings_calendar(days_ahead=7)` - Earnings
   - Condition: `FINNHUB_API_KEY` must be set

2. **Finviz Elite News** (Aggregated news)
   - Requires `FINVIZ_AUTH_TOKEN` or `FINVIZ_ELITE_AUTH`
   - Optional CSV export feed: `FINVIZ_NEWS_EXPORT_URL`
   - Feature flag: `FEATURE_FINVIZ_NEWS=1` (default enabled)

3. **RSS/Atom Feeds** (Multiple sources)
   - Parallel fetching via `_fetch_feeds_async_concurrent()` (Line 979)
   - Supports HTTP 304 Not Modified (bandwidth optimization)
   - Per-source error tracking and metrics

4. **SEC Filings** (Via SEC stream/monitor)
   - Automatic SEC document fetching when detected
   - Requires network connectivity to EDGAR

**Typical Latency**:
- Network fetch: 2-5 seconds (async concurrent, all sources in parallel)
- Feed parsing: <1 second
- Deduplication: 1-2 seconds
- **Total ingest time**: 3-8 seconds per cycle

---

### 2.2 Deduplication Stage

**Function**: `feeds.dedupe()` (Line 2608 in feeds.py)

**Algorithm**:
- Exact ID matching (source + GUID/link)
- Cross-source canonical link + normalized title matching
- Fuzzy matching via `rapidfuzz` (token_set_ratio, threshold: 0.8)
- SEC-specific: Accession number extraction for same-filing detection

**Signature Generation** (dedupe.py:271):
```
signature = SHA1(ticker | normalized_title | accession_number_or_url)
```

**Seen Store** (persistent cross-run dedup):
- SQLite-backed first-seen index
- Feature flag: `FEATURE_PERSIST_SEEN` (default: enabled)
- TTL configured via `SEEN_TTL_DAYS` (default: 7 days)
- Items marked seen AFTER successful alert (not before, to prevent race conditions)

**Skip Conditions**:
- Article already seen in this cycle (deduped)
- Article already seen in previous cycles (seen_store check)
- Stale articles: `MAX_ARTICLE_AGE_MINUTES` (default: 30 min for regular, 240 min for SEC)
- Finviz noise filtering (lawsuits, class action notices)

**Typical Latency**: <1 second for in-memory dedup

---

### 2.3 Watchlist Cascade & Special Event Scanners

#### Watchlist Cascade
- **Location**: runner.py:1055
- Decay HOT→WARM→COOL entries based on age
- Configurable age thresholds (default: 7/21/60 days)
- Optional state file: `WATCHLIST_STATE_FILE`

#### 52-Week Low Scanner
- **Condition**: `feature_52w_low_scanner` enabled
- **Scans**: Tickers trading near 52-week lows
- **Filters**: 
  - Min avg volume: `low_min_avg_vol` (default: 300,000)
  - Distance threshold: `low_distance_pct` (default: 5%)

**Latency**: 2-5 seconds (calls to yfinance/market data)

---

### 2.4 Ticker Enrichment

**Location**: runner.py:1116

**Operations**:
1. Extract missing tickers from titles
2. Validate ticker format (exchange-qualified, OTC filtering)
3. Cross-ticker deduplication prevention

**Filters**:
- `ALLOW_OTC_TICKERS` (default: 1)
- `FILTER_OTC_STOCKS` (default: 1) - Blocks illiquid OTC stocks
- `IGNORE_INSTRUMENT_TICKERS` (default: 1) - Blocks warrants/units/rights

**Latency**: <1 second

---

### 2.5 News Velocity Tracking

**Function**: `news_velocity.get_tracker().record_article()`

**Purpose**: Track article frequency per ticker for momentum detection

**Latency**: <1 second

---

### 2.6 Batch Price Fetching

**Location**: runner.py:1207-1227

**Optimization**: Batch-fetch all unique ticker prices in one call
- Uses: `market.batch_get_prices(all_tickers)`
- Condition: Only if `PRICE_CEILING` is set (no price fetching without it)
- **Cache TTL**: 60 seconds per price

**Typical Latency**: 3-10 seconds (depends on number of tickers)

---

### 2.7 SEC LLM Batch Processing

**Location**: runner.py:1265-1307

**Process**:
1. Collect all SEC filings from deduped items
2. Batch extract keywords in parallel (single `asyncio.run()` call for all)
3. Cache results for downstream classification

**Async Function**: `batch_extract_keywords_from_documents()`

**Typical Latency**: 5-15 seconds (depends on batch size and LLM provider)

---

### 2.8 Core Item Processing Loop

**Location**: runner.py:1309+

For each deduped item:

#### A. Seen Store Check
- Check if item seen in previous cycles
- Skip if seen (don't mark yet - mark only after successful alert)
- **Latency**: <1ms per item

#### B. Multi-Ticker Scoring
- **Condition**: `feature_multi_ticker_scoring` (default: True)
- Score ticker relevance instead of rejecting all multi-ticker articles
- **Scoring formula**:
  - Position in title: 0-50 points
  - First paragraph: 0-30 points
  - Frequency: 0-20 points
  - Total: 0-100 points
- **Thresholds**:
  - Min relevance: `MULTI_TICKER_MIN_RELEVANCE_SCORE` (default: 40)
  - Max primaries: `MULTI_TICKER_MAX_PRIMARY` (default: 2)
  - Score diff: `MULTI_TICKER_SCORE_DIFF_THRESHOLD` (default: 30)
- **Latency**: 1-2 seconds for multi-ticker analysis

#### C. Classification & Sentiment Analysis
- **Function**: `classify.classify()` or `classify.fast_classify()`
- **Bridge**: `classify_bridge.classify_text()`
- **Score Range**: 0.0-10.0
- **Dynamic Weights**: Load from `dynamic_keywords.json` (on-disk)
- **Sentiment Sources** (optional, parallel):
  1. FMP sentiment (RSS feed)
  2. External news sentiment (Alpha, Marketaux, StockNews, Finnhub)
  3. Local VADER sentiment (fallback)
  4. Premarket sentiment (price action 4:00-10:00 AM ET)
  5. Aftermarket sentiment (price action 4:00-8:00 PM ET)
  6. Analyst signals (Finnhub)
  7. Insider trading sentiment
  8. Google Trends sentiment
  9. Short interest sentiment

**ML Batch Scoring**:
- Batch sentiment scorer: `_ml_batch_scorer` (SENTIMENT_BATCH_SIZE: 10 items)
- GPU optimization: Reuse model across cycle
- Memory cleanup: `clear_ml_batch_scorer()` called at end of cycle
- **Latency**: 0.5-3 seconds per item (depends on sentiment sources enabled)

#### D. Filtering Gates

Multiple skip conditions applied in sequence:

1. **No ticker**: `skipped_no_ticker`
2. **Crypto**: Unless on watchlist, `skipped_crypto`
3. **Ticker relevance** (multi-ticker): `skipped_ticker_relevance`
4. **Price ceiling**: `PRICE_CEILING` check, `skipped_price_gate`
5. **Price floor**: `PRICE_FLOOR` check
6. **Instrument filter**: Warrants/units/rights, `skipped_instr`
7. **Source skip**: `SKIP_SOURCES` (CSV), `skipped_by_source`
8. **Score threshold**: `MIN_SCORE`, `skipped_low_score`
9. **Sentiment threshold**: `MIN_SENT_ABS`, `skipped_sent_gate`
10. **Category whitelist**: `CATEGORIES_ALLOW`, `skipped_cat_gate`
11. **OTC filter**: `FILTER_OTC_STOCKS`, `skipped_otc`
12. **Low volume**: Min avg volume check, `skipped_low_volume`
13. **Data presentation**: SEC filing filters, `skipped_data_presentation`

**Latency**: <1ms per filter check

#### E. Async Enrichment (Optional)

**Function**: `enqueue_for_enrichment(scored_item, news_item)` (Line 2190)

**Enrichment Worker** (`enrichment_worker.py`):
- Background thread: Parallel market data fetching
- Batch size: `ENRICHMENT_BATCH_SIZE` (default: 10)
- Batch timeout: `ENRICHMENT_BATCH_TIMEOUT` (default: 2.0 seconds)
- Max workers: `ENRICHMENT_WORKER_THREADS` (default: 5)
- Retrieval timeout: `5.0` seconds default

**Data enriched**:
- RVOL (Relative Volume)
- Float data
- VWAP (Volume Weighted Average Price)
- Volume/price divergence
- Support/resistance levels

**Latency**: 
- Enqueue: <1ms
- Enrichment: 2-5 seconds (parallel batch processing, non-blocking)
- Retrieval: 0-5 seconds (wait for enriched result)

---

### 2.9 Alert Generation & Discord Posting

**Location**: runner.py:2180+

#### A. Alert Formatting
- **Function**: `_format_discord_content()`
- Include: Price, change %, sentiment, score, source, link
- Optional embeds: Charts, indicators, trade plans

#### B. Rich Alert Features (Optional)
1. **Intraday candlestick charts**: `FEATURE_RICH_ALERTS=1`
   - Via `render_intraday_chart()` or QuickChart API
   - **Latency**: 1-3 seconds per chart
2. **Finviz daily charts**: `FEATURE_FINVIZ_CHART=1`
   - Static daily candle from charts2.finviz.com
   - **Latency**: <1 second
3. **QuickChart integration**: `FEATURE_QUICKCHART=1`
   - Hosted chart generation
   - **Latency**: 1-2 seconds
4. **Momentum indicators**: `FEATURE_MOMENTUM_INDICATORS=1`
   - MACD, EMA crossovers, VWAP deltas
   - **Latency**: 1-2 seconds
5. **Trade plans**: Entry/stop/target levels
   - **Latency**: <1 second
6. **Sentiment gauges**: Visual sentiment representation
   - **Latency**: <1 second

#### C. Rate Limiting
- Per-key rate limiting (optional): `ALERTS_KEY_RATE_LIMIT=1`
  - Key: (ticker, title, canonical_link)
  - Limiter: `limiter_allow(rl_key)`

#### D. Alert Flow Control
- Max alerts per cycle: `MAX_ALERTS_PER_CYCLE` (default: 40)
- Alert jitter: `ALERTS_JITTER_MS` (random delay to smooth bursts)
- **Jitter sleep**: `max(0, min(jitter_ms, 1000)) / 1000 * random.random()` (Line 2313)
- **Latency**: 0-1 second per jitter

#### E. Discord Posting

**Function**: `send_alert_safe()` (alerts.py:740) → `post_discord_json()` (alerts.py:695)

**Retries**:
- Max retries: 2 (default)
- Retry on: HTTP 429 (rate limit), 5xx (server error)
- Backoff: `min(0.5 * attempt, 3.0)` seconds exponential

**Webhook validation**:
- Cache validated webhooks to avoid repeated checks
- Fallback webhooks: DISCORD_WEBHOOK_URL → DISCORD_WEBHOOK → ALERT_WEBHOOK

**Latency**:
- Network POST: 1-3 seconds (includes retries)
- Discord processing: <1 second
- **Total alert latency**: 1-3 seconds per alert

**Typical Latency**: 2-5 seconds per item (classification + enrichment + alert)

---

### 2.10 Tracking & Metrics

**Statistics Tracked**:
```python
LAST_CYCLE_STATS = {
    "items": number_of_items_fetched,
    "deduped": number_deduped,
    "skipped": number_skipped_by_filters,
    "alerts": number_alerts_sent,
}

TOTAL_STATS = {
    "items": cumulative_items,
    "deduped": cumulative_deduped,
    "skipped": cumulative_skipped,
    "alerts": cumulative_alerts,
}
```

**Cycle logging**: Line 3210
- `log.info("CYCLE_DONE took=%.2fs", cycle_time)`

---

## 3. TIMING PARAMETERS & CONFIGURATION

### Environment Variables

#### Core Polling
| Parameter | Default | Description |
|-----------|---------|-------------|
| `LOOP_SECONDS` | 30 | Cycle interval when market hours detection disabled |
| `MARKET_OPEN_CYCLE_SEC` | 60 | Cycle during trading hours (when detection enabled) |
| `EXTENDED_HOURS_CYCLE_SEC` | 90 | Cycle during pre/after-market hours |
| `MARKET_CLOSED_CYCLE_SEC` | 180 | Cycle when market closed |
| `HEARTBEAT_INTERVAL_MIN` | 60 | Heartbeat message interval (minutes) |

#### Timing Thresholds
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_ARTICLE_AGE_MINUTES` | 30 | Max age for regular articles |
| `MAX_SEC_FILING_AGE_MINUTES` | 240 | Max age for SEC filings (4 hours) |
| `SEEN_TTL_DAYS` | 7 | Persistent seen store retention |
| `STREAM_SAMPLE_WINDOW_SEC` | 0 | Alpaca stream sampling duration |

#### Alert Flow Control
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_ALERTS_PER_CYCLE` | 40 | Hard cap on alerts per cycle |
| `ALERTS_JITTER_MS` | 0 | Random delay between alerts (ms) |
| `ALERTS_KEY_RATE_LIMIT` | 0 | Enable per-key rate limiting |
| `ALERT_CONSECUTIVE_EMPTY_CYCLES` | 5 | Threshold for feed outage detection |

#### Enrichment
| Parameter | Default | Description |
|-----------|---------|-------------|
| `ENRICHMENT_BATCH_SIZE` | 10 | Items per enrichment batch |
| `ENRICHMENT_BATCH_TIMEOUT` | 2.0 | Max wait for batch to fill (sec) |
| `ENRICHMENT_WORKER_THREADS` | 5 | Parallel enrichment threads |

#### Batch Processing
| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_BATCH_SIZE` | 5 | Items per LLM batch |
| `LLM_BATCH_DELAY_SEC` | 2.0 | Delay between batches |
| `LLM_BATCH_TIMEOUT` | 2.0 | Max wait for batch |
| `SENTIMENT_BATCH_SIZE` | 10 | ML sentiment batch size |

#### Market Data
| Parameter | Default | Description |
|-----------|---------|-------------|
| `PRICE_CEILING` | None (∞) | Max stock price for alerts |
| `PRICE_FLOOR` | 0.10 | Min stock price |
| `MIN_AVG_VOLUME` | None | Min average volume filter |
| `low_min_avg_vol` | 300,000 | Min volume for 52-week low scanner |
| `low_distance_pct` | 5.0 | Distance threshold for low scanner |

#### Classification & Sentiment
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MIN_SCORE` | 0 | Min classification score (0-10) |
| `MIN_SENT_ABS` | 0 | Min absolute sentiment (0-1) |
| `MULTI_TICKER_MIN_RELEVANCE_SCORE` | 40 | Min score for multi-ticker relevance |
| `MULTI_TICKER_MAX_PRIMARY` | 2 | Max primary tickers to alert |
| `MULTI_TICKER_SCORE_DIFF_THRESHOLD` | 30 | Score gap for single-ticker detection |

---

## 4. END-TO-END LATENCY ANALYSIS

### News Article Publish → Discord Alert Latency

```
Publication Time (t=0)
    ↓
[Feed Polling Interval] → Average latency: 15 seconds
    (Worst case: LOOP_SECONDS = 30s)
    ↓
News appears in feed at next cycle
    ↓
[Feed Fetch] → 2-5 seconds (async concurrent)
    ↓
[Deduplication] → <1 second
    ↓
[Ticker Enrichment] → <1 second
    ↓
[Classification] → 0.5-3 seconds (depends on sentiment sources)
    ↓
[Filtering] → <1 second (series of fast checks)
    ↓
[Chart Generation] (optional) → 1-3 seconds (if FEATURE_RICH_ALERTS=1)
    ↓
[Enrichment Wait] → 0-5 seconds (if async enrichment enabled)
    ↓
[Discord POST] → 1-3 seconds (with retries)
    ↓
Alert Visible in Discord (t=end)

Minimum Latency: ~20-25 seconds (fast path)
Typical Latency: ~45-60 seconds (with classification + charts)
Maximum Latency: ~90+ seconds (slow path with enrichment + retries)
```

### Cycle Timing Breakdown

**Typical 30-item cycle:**
```
Feed fetch & parse:        3-8 seconds
Deduplication:             <1 second
Ticker enrichment:         <1 second
Price batch fetch:         3-10 seconds (if price_ceiling set)
SEC LLM batch (if any):    5-15 seconds (if SEC items present)
Classification loop:       15-60 seconds (30 items × 0.5-2s each)
  - Per item:
    - Fast classify:       0.3-0.5 seconds
    - Sentiment sources:   0.5-2 seconds (parallel)
    - Filtering:           <1 second
    - Enrichment enqueue:  <1 second
Alert generation & POST:   10-20 seconds (40 alerts × 0.25-0.5s each)
Cleanup & logging:         <1 second
────────────────────────
Total cycle time:          40-120 seconds (typical: 60 seconds)
```

### Bottlenecks & Optimization Points

| Bottleneck | Current Approach | Latency | Mitigation |
|-----------|----------|---------|-----------|
| News publishing delay | Feed polling interval | 15s avg | Reduce LOOP_SECONDS, use real-time feeds |
| Feed fetching | Async concurrent aiohttp | 3-8s | Pre-connect, HTTP/2 |
| Classification | ML batch sentiment scorer | 0.5-2s/item | Disable unused sentiment sources |
| Price fetching | Batch fetch once per cycle | 3-10s | Cache longer, reduce frequency |
| SEC processing | Batch LLM calls | 5-15s | Use flash models, reduce batch |
| Chart generation | Sequential per alert | 1-3s/chart | Cache daily charts, use QuickChart API |
| Discord posting | Sequential with retries | 1-3s/alert | Batch webhook posts, adjust rate limit |
| Enrichment | Background async | 2-5s | Reduce batch timeout |

---

## 5. COMPONENT DEPENDENCY GRAPH

```
[Discord Webhook] ← [Alert Generation] ← [Discord Posting]
                           ↑
                    [Rich Features]
                      ↓
                [Sentiment Gauge, Trade Plan,
                 Charts, Indicators]
                      ↑
                    [Enrichment Worker]
                    (Async, Background)
                      ↑
           [Classification Result]
                      ↑
              [Fast Classify]
                      ↑
        [Dynamic Keyword Weights,
         ML Batch Scorer]
                      ↑
        [Sentiment Sources]
        (FMP, Alpha, Marketaux,
         Finnhub, VADER, Analyst,
         Insider, Google Trends)
                      ↑
              [Item Filtering]
              (Score, Price, OTC,
               Multi-ticker, etc.)
                      ↑
         [Ticker Enrichment,
          Seen Store Check]
                      ↑
          [Batch Price Fetch,
           SEC LLM Batch]
                      ↑
              [Deduplication]
              (Exact ID, Fuzzy,
               SEC Accession)
                      ↑
         [Async Concurrent Feed Fetch]
         (Finnhub, Finviz, RSS,
          SEC Monitor)
                      ↑
             [Main Cycle Loop]
      (Runs every LOOP_SECONDS)
```

---

## 6. FEATURE FLAGS & CONDITIONAL PATHS

### Performance Impact Features

| Feature | Flag | Default | Latency Impact |
|---------|------|---------|-----------------|
| Async enrichment | `FEATURE_ASYNC_ENRICHMENT` | - | +2-5s (async, non-blocking) |
| Rich alerts | `FEATURE_RICH_ALERTS` | False | +1-3s per alert |
| QuickChart | `FEATURE_QUICKCHART` | False | +1-2s per alert |
| Momentum indicators | `FEATURE_MOMENTUM_INDICATORS` | False | +1-2s per alert |
| Local sentiment | `FEATURE_LOCAL_SENTIMENT` | False | +0.5s per item |
| News sentiment | `FEATURE_NEWS_SENTIMENT` | False | +1-2s per item |
| Market hours detection | `FEATURE_MARKET_HOURS_DETECTION` | - | <1s check |
| SEC digester | `FEATURE_SEC_DIGESTER` | - | +5-15s for SEC items |
| LLM batch mode | `FEATURE_LLM_BATCH` | True | Reduces cost, similar latency |
| Watchlist cascade | `FEATURE_WATCHLIST_CASCADE` | - | <1s per cycle |
| 52w low scanner | `FEATURE_52W_LOW_SCANNER` | - | +2-5s per cycle |

---

## 7. POTENTIAL LATENCY OPTIMIZATIONS

### Quick Wins (1-5 second reduction)
1. Reduce `LOOP_SECONDS` from 30 to 15 seconds (+15s latency savings)
2. Disable unused sentiment sources (-0.5-1s per item)
3. Cache daily charts longer (-1-3s per alert)
4. Batch Discord webhooks (-1-2s per cycle)

### Medium-term (10-20 second reduction)
1. Implement real-time webhook feeds (replace polling)
2. Use flash LLM for SEC processing (-5-10s)
3. Parallel chart generation (-1-3s per alert)
4. HTTP/2 for feed fetching (-1-2s)

### Architectural (20+ second reduction)
1. Event-driven architecture (replace polling)
2. Cached ticker validation DB
3. Pre-computed sentiment baselines
4. Geographic CDN for Discord/API calls

---

## 8. DATABASE & PERSISTENT STATE

### SQLite Databases

**Seen Store** (`seen_store.db` or configured path):
- `first_seen_index` table: (signature, id, ts, source, link, weight)
- Purpose: Cross-run deduplication (7-day TTL default)
- Usage: Mark items seen after successful alert

**Feedback Database** (if `FEEDBACK_AVAILABLE`):
- Price tracking for outcomes
- Alert quality scoring
- Weight adjustment recommendations

**LLM Cache** (if SEC processing enabled):
- SEC filing keyword extraction cache
- Reduces redundant LLM calls

---

## 9. CONFIGURATION FILES

### Environment Files
- `.env` - Runtime config (loaded first)
- `.env.staging` - Staging variant (optional)
- `env.example.ini` - Documentation template

### YAML Configs
- `src/catalyst_bot/catalyst_bot.yaml` - Bot-specific defaults

### Data Files
- `data/watchlist.csv` - Watchlist tickers
- `data/finviz.csv` - Screener results
- `data/earnings_calendar.csv` - Earnings dates (job-updated)
- `data/filters/finviz_noise.txt` - Custom noise filter keywords

---

## 10. CRITICAL PATH ANALYSIS

**Critical path** (determines minimum cycle time):
```
Feed Fetch (3-8s) 
  → Dedup (1s) 
  → Price Batch (3-10s if active) 
  → Classify (0.5-2s per item × count)
  → Alert POST (1-3s per alert × count)
```

**Parallelizable**:
- Feed sources (async)
- Sentiment sources (often parallel)
- Enrichment (background async)
- Price batch (single call)

**Sequential**:
- Each item classification
- Each alert Discord POST (can batch with webhooks)

**Optimization Strategy**:
1. Minimize feed fetch time (polling interval + network)
2. Reduce classification time (disable sentiment sources, use fast classify)
3. Batch Discord posts or use background queue
4. Parallelize enrichment (already done)

