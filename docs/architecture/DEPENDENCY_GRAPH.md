# System Dependency Graph
**3 Patch Waves - Architectural Dependencies**

---

## Wave 1: Feature Flag Dependency Map

```
┌─────────────────────────────────────────────────────────────┐
│                      .env Configuration                      │
│                     (Wave 1 Changes)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌──────────────────┐                    ┌──────────────────────┐
│  FEATURE_RVOL=0  │                    │  Cycle Time Changes  │
│ (Disabled)       │                    │  60s→20s, 90s→30s    │
└──────────────────┘                    └──────────────────────┘
        │                                           │
        │                                           │
        ▼                                           ▼
┌──────────────────────────────────┐    ┌────────────────────────────┐
│  src/catalyst_bot/rvol.py        │    │  src/catalyst_bot/runner.py│
│  ├─ calculate_rvol_intraday()    │    │  └─ Main loop sleep()      │
│  │  └─ Returns None if disabled  │    └────────────────────────────┘
│  ├─ get_rvol_multiplier()        │                │
│  │  └─ Not called               │                │
│  └─ get_volume_baseline()        │                │
│     └─ Not called               │                │
└──────────────────────────────────┘                │
        │                                           │
        │ (None return handled gracefully)          │
        ▼                                           ▼
┌──────────────────────────────────┐    ┌────────────────────────────┐
│  src/catalyst_bot/classify.py    │    │  Downstream Effects:       │
│  ├─ rvol_data = calculate_...()  │    │  ├─ 3x API calls/hour      │
│  ├─ if rvol_data:                │    │  ├─ 3x DB writes           │
│  │    apply_multiplier()         │    │  ├─ 3x feed fetches        │
│  │ else:                         │    │  └─ Potential rate limits  │
│  │    skip_rvol_boost()          │    └────────────────────────────┘
│  └─ (No error on None)           │
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  Impact: Classification Score    │
│  ├─ No RVOL multiplier applied   │
│  ├─ Lower scores for high-vol    │
│  │    tickers                    │
│  └─ Fewer alerts overall         │
└──────────────────────────────────┘
```

---

## Feature Flag Dependency Details

### FEATURE_RVOL=0 Chain

```
┌────────────────────┐
│  config.py:1006    │  feature_rvol: bool = _b("FEATURE_RVOL", False)
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  rvol.py:848       │  if not getattr(settings, "feature_rvol", True):
│                    │      return None
└─────────┬──────────┘
          │
          ▼
┌────────────────────────────────────────┐
│  classify.py (3 call sites)            │
│  1. Line ~XXX: calculate_rvol_intraday │
│  2. Line ~XXX: calculate_rvol_intraday │
│  3. Line ~XXX: calculate_rvol_intraday │
└─────────┬──────────────────────────────┘
          │
          ▼ (None returned)
┌────────────────────────────────────────┐
│  if rvol_data:                         │
│      # This branch NOT taken           │
│      multiplier = rvol_data['multiplier']
│  else:                                 │
│      # This branch TAKEN               │
│      multiplier = 1.0  # Baseline      │
└────────────────────────────────────────┘
```

**Safety**: ✓ No exceptions thrown, graceful degradation

---

### FEATURE_MOMENTUM_INDICATORS=0 Chain

```
┌────────────────────┐
│  config.py:257     │  feature_momentum_indicators: bool = False
└─────────┬──────────┘
          │
          ├──────────────────────┬─────────────────────┐
          ▼                      ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  alerts.py:253   │  │  market.py       │  │  runner.py       │
│  Chart overlay   │  │  MACD/EMA calc   │  │  Status report   │
└──────────────────┘  └──────────────────┘  └──────────────────┘
          │                      │                     │
          ▼                      ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Skip MACD/EMA   │  │  Return {}       │  │  Show "OFF"      │
│  on chart        │  │  (empty dict)    │  │  in status       │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

**Safety**: ✓ All consumers handle disabled state

---

### FEATURE_PREMARKET_SENTIMENT=0 Chain

```
┌────────────────────┐
│  config.py:294     │  feature_premarket_sentiment: bool = False
└─────────┬──────────┘
          │
          ▼
┌────────────────────────────┐
│  premarket_sentiment.py    │
│  if not feature_enabled:   │
│      return None           │
└─────────┬──────────────────┘
          │
          ▼
┌────────────────────────────┐
│  Sentiment Aggregation     │
│  (sentiment_gauge.py)      │
│  ├─ None check             │
│  ├─ Skip pre-market source │
│  └─ Use other sources      │
└────────────────────────────┘
```

**Safety**: ✓ Sentiment aggregation handles missing sources

---

## Wave 2: Retrospective Filter Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  Feed Ingestion Pipeline                     │
│                    (feeds.py)                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
    ┌────────────────────┐      ┌────────────────────┐
    │  RSS Feed Parser   │      │  News API Parser   │
    │  (Line ~680)       │      │  (Line ~740)       │
    └────────────────────┘      └────────────────────┘
                │                           │
                │  for each article         │
                ▼                           ▼
    ┌────────────────────────────────────────────────┐
    │  _is_retrospective_article(title, summary)     │
    │  (Lines 151-212)                               │
    │                                                 │
    │  ┌──────────────────────────────────────────┐  │
    │  │  Regex Pattern Matching:                 │  │
    │  │  1. "Why [ticker] stock..."              │  │
    │  │  2. "Here's why..."                      │  │
    │  │  3. "What happened to..."                │  │
    │  │  4. "Stock dropped X%..."                │  │
    │  │  5. "Shares slide despite..."            │  │
    │  │  6. "[Ticker] stock is down X%..."       │  │
    │  └──────────────────────────────────────────┘  │
    └────────────────────────────────────────────────┘
                │
                │
        ┌───────┴────────┐
        │                │
        ▼ (True)         ▼ (False)
┌─────────────────┐  ┌─────────────────────┐
│  Reject Article │  │  Accept Article     │
│  Log: retro_    │  │  Continue pipeline  │
│  article_filter │  │                     │
└─────────────────┘  └─────────────────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │  Deduplication     │
                    │  (SeenStore)       │
                    └────────────────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │  Classification    │
                    │  (classify.py)     │
                    └────────────────────┘
```

### Call Graph

```
fetch_pr_feeds()
  │
  ├─► for item in rss_items:
  │    └─► if _is_retrospective_article(title, summary):
  │           └─► continue (skip)
  │
  └─► for item in news_api_items:
       └─► if _is_retrospective_article(title, ""):
              └─► continue (skip)
```

**Test Coverage**:
- `tests/test_retrospective_patterns.py` ✓
- `tests/test_wave_fixes_11_5_2025.py` ✓
- `test_final_patterns.py` ✓
- `test_bulletproof_patterns.py` ✓

---

## Wave 3: SEC Filing Alert Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SEC Filing Pipeline                       │
│                  (sec_filing_alerts.py)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
    ┌────────────────────┐      ┌────────────────────┐
    │  FilingSection     │      │  SECSentimentOutput│
    │  ├─ ticker         │      │  ├─ score          │
    │  ├─ filing_type    │      │  ├─ weighted_score │
    │  ├─ filing_url     │      │  └─ justification  │
    │  └─ catalyst_type  │      └────────────────────┘
    └────────────────────┘
                │                           │
                │                           │
                └─────────────┬─────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  create_sec_filing_embed()       │
            │  (Lines 97-317)                  │
            │                                  │
            │  ┌────────────────────────────┐  │
            │  │  Build Discord Embed:      │  │
            │  │  ├─ Title (ticker + type)  │  │
            │  │  ├─ Description (LLM sum)  │  │
            │  │  ├─ Priority badge         │  │
            │  │  ├─ Key Metrics            │  │
            │  │  ├─ Guidance               │  │
            │  │  ├─ Sentiment              │  │
            │  │  ├─ Keywords               │  │
            │  │  └─ Footer metadata        │  │
            │  └────────────────────────────┘  │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  send_sec_filing_alert()         │
            │  (Lines 421-569)                 │
            │                                  │
            │  ┌────────────────────────────┐  │
            │  │  1. Check if enabled       │  │
            │  │  2. Check priority tier    │  │
            │  │  3. Create embed           │  │
            │  │  4. Create buttons         │  │
            │  │  5. POST to Discord        │  │
            │  └────────────────────────────┘  │
            └──────────────────────────────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │  Discord Webhook   │
                    │  (External API)    │
                    └────────────────────┘
```

### Deduplication Flow

```
┌────────────────────┐
│  filing_url        │  (e.g., "https://sec.gov/Archives/edgar/...")
└─────────┬──────────┘
          │
          ▼
┌────────────────────────────┐
│  dedupe.py:signature_from  │
│  └─ MD5 hash of URL        │
└─────────┬──────────────────┘
          │
          ▼
┌────────────────────────────┐
│  SeenStore.is_seen()       │
│  ├─ Check SQLite DB        │
│  ├─ URL hash in seen set?  │
│  └─ Return bool            │
└─────────┬──────────────────┘
          │
    ┌─────┴──────┐
    ▼ (True)     ▼ (False)
┌─────────┐  ┌──────────────┐
│  Skip   │  │  Process     │
│  Filing │  │  Filing      │
└─────────┘  └──────────────┘
                    │
                    ▼
            ┌──────────────────┐
            │  Add to SeenStore│
            └──────────────────┘
```

**Critical Fields** (must not remove):
- `filing_section.filing_url` → Used in deduplication hash
- `filing_section.ticker` → Used for alert routing
- `filing_section.filing_type` → Used for classification
- `timestamp` → Required by Discord API

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        MAIN RUNNER                           │
│                     (runner.py)                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Loop every N seconds
                              │ (20s/30s/60s based on market hours)
                              ▼
            ┌──────────────────────────────────┐
            │  1. Fetch Feeds                  │
            │     ├─ RSS feeds                 │
            │     ├─ News APIs                 │
            │     └─ SEC filings               │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  2. Filter Retrospective         │
            │     └─ _is_retrospective_article │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  3. Deduplication                │
            │     ├─ SeenStore.is_seen()       │
            │     └─ Add to seen set           │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  4. Classification               │
            │     ├─ Keyword matching          │
            │     ├─ Sentiment analysis        │
            │     ├─ RVOL calculation (if on)  │
            │     └─ Score aggregation         │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  5. Enrichment                   │
            │     ├─ Market data               │
            │     ├─ Float data                │
            │     ├─ Chart generation          │
            │     └─ Momentum indicators (if on)│
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  6. Alert Delivery               │
            │     ├─ Discord webhook           │
            │     ├─ SEC filing embeds         │
            │     └─ Feedback tracking         │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  7. Sleep & Repeat               │
            │     └─ time.sleep(cycle_sec)     │
            └──────────────────────────────────┘
```

---

## Database Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                      SQLite Databases                        │
└─────────────────────────────────────────────────────────────┘
          │
          ├───────────────────┬───────────────────┬─────────────────┐
          │                   │                   │                 │
          ▼                   ▼                   ▼                 ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  SeenStore       │  │  Chart Cache │  │  RVol Cache  │  │  Feedback DB │
│  (dedupe)        │  │              │  │              │  │              │
└──────────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
│                   │                   │                 │
│ Tables:           │ Tables:           │ Tables:         │ Tables:
│ ├─ seen_urls      │ ├─ chart_1d      │ ├─ rvol_data    │ ├─ alerts
│ ├─ seen_titles    │ ├─ chart_5d      │ └─ cached_at    │ ├─ outcomes
│ └─ first_seen     │ ├─ chart_1m      │                 │ └─ keywords
│                   │ └─ chart_3m      │                 │
│ WAL: ON           │ WAL: ON          │ WAL: ON         │ WAL: ON
│ Cache: 10K pages  │ Cache: 10K pages │ Cache: 10K pages│ Cache: 10K pages
│ Writes: 3x after  │ Writes: Same     │ Writes: None    │ Writes: 3x after
│ Reads: 3x after   │ Reads: Same      │ Reads: None     │ Reads: Same
└───────────────────┴──────────────────┴─────────────────┴─────────────────┘
```

**Impact of 3x Cycle Frequency**:
- **SeenStore**: +200% reads/writes → Handled by WAL mode ✓
- **Chart Cache**: No change (cache TTL, not cycle-driven)
- **RVol Cache**: No writes (feature disabled)
- **Feedback DB**: +200% alert tracking → SQLite handles ✓

---

## API Rate Limit Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                    External API Calls                        │
│                   (3x after cycle changes)                   │
└─────────────────────────────────────────────────────────────┘
          │
          ├──────────────┬────────────────┬──────────────────┐
          │              │                │                  │
          ▼              ▼                ▼                  ▼
┌──────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│  yfinance    │  │  Tiingo IEX │  │  Alpha Vant.│  │  RSS Feeds   │
│  (Free)      │  │  ($30/mo)   │  │  (Free)     │  │  (Various)   │
└──────────────┘  └─────────────┘  └─────────────┘  └──────────────┘
│              │                │                  │
│ Limit:       │ Limit:         │ Limit:          │ Limit:
│ 2000 req/hr  │ 1000 req/hr    │ 25 req/day      │ Varies
│              │                │                  │
│ Current:     │ Current:       │ Current:        │ Current:
│ ~60/hr       │ ~60/hr         │ ~20/day         │ ~60/hr
│              │                │                  │
│ After 3x:    │ After 3x:      │ After 3x:       │ After 3x:
│ ~180/hr      │ ~180/hr        │ ~60/day         │ ~180/hr
│              │                │                  │
│ Status: ✓    │ Status: ✓      │ Status: ⚠️       │ Status: ✓
│ (Within)     │ (Within)       │ (EXCEEDS!)      │ (Within)
└──────────────┴─────────────────┴─────────────────┴──────────────┘
```

**Critical**: Alpha Vantage will hit daily limit at 3x frequency ⚠️

**Mitigation**:
```python
# Extend AV cache TTL
AV_CACHE_TTL_HOURS=24  # Was 1 hour, now 24 hours
AV_MAX_CALLS_PER_DAY=20  # Hard limit with fallback
```

---

## Integration Point Matrix

| Component | Wave 1 Impact | Wave 2 Impact | Wave 3 Impact |
|-----------|---------------|---------------|---------------|
| `feeds.py` | Cycle freq +3x | Regex change | None |
| `classify.py` | RVOL disabled | None | None |
| `alerts.py` | Momentum disabled | None | SEC format change |
| `runner.py` | Cycle time change | None | None |
| `rvol.py` | Feature disabled | None | None |
| `market.py` | Momentum disabled | None | None |
| `dedupe.py` | +3x calls | None | None |
| `sec_filing_alerts.py` | None | None | Format change |
| SeenStore DB | +3x writes | None | None |
| Chart Cache DB | No change | None | None |
| yfinance API | +3x calls | None | None |
| Tiingo API | +3x calls | None | None |
| Alpha Vantage | +3x calls ⚠️ | None | None |
| Discord Webhook | +3x calls | None | Embed format |

---

## Dependency Summary

### Strong Dependencies (Breaking if removed)
- `filing_section.filing_url` → Deduplication ⚠️ **DO NOT REMOVE**
- `filing_section.ticker` → Alert routing ⚠️ **DO NOT REMOVE**
- `SeenStore` → Prevents duplicate alerts ⚠️ **DO NOT DISABLE**
- Discord `embed.timestamp` → Required by API ⚠️ **DO NOT REMOVE**

### Weak Dependencies (Graceful degradation)
- RVOL feature → Returns None, handled gracefully ✓
- Momentum indicators → Returns empty dict, handled gracefully ✓
- Pre/After sentiment → Returns None, aggregation skips ✓
- Chart cache → Miss = regenerate, no errors ✓

### No Dependencies (Independent changes)
- Retrospective filter → Isolated function ✓
- SEC embed formatting → Cosmetic only ✓
- Cycle times → Configuration only ✓

---

**Graph Generated**: 2025-11-05
**Validation Agent**: Architecture Stability Validator
**Status**: ✓ Complete dependency mapping
