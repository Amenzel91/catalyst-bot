# News Velocity (Momentum) Sentiment Source - Implementation Summary

## Overview

Successfully implemented news article velocity/momentum tracking as a new sentiment source for the Catalyst Bot. A sudden spike in article count indicates breaking news, viral catalysts, or pump attempts - all valuable trading signals.

## Files Modified/Created

### 1. **src/catalyst_bot/news_velocity.py** (NEW)
- **Purpose**: Core module for tracking article velocity and calculating sentiment
- **Key Components**:
  - `NewsVelocityTracker` class with SQLite storage
  - Article deduplication by title similarity (MD5 hash)
  - Time-windowed velocity calculation (1h, 4h, 24h)
  - Spike detection for sustained coverage
  - Sentiment scoring based on thresholds

### 2. **src/catalyst_bot/classify.py** (MODIFIED)
- **Changes**: Added news velocity sentiment integration to `aggregate_sentiment_sources()`
- **Integration Point**: Section 6 (between external sentiment sources and AI adapter)
- **Weight**: 0.05 (configurable via `SENTIMENT_WEIGHT_NEWS_VELOCITY`)
- **Confidence**: 0.70 (indirect signal - high media attention)

### 3. **src/catalyst_bot/runner.py** (MODIFIED)
- **Changes**: Added velocity tracking hook in `_cycle()` function
- **Location**: After ticker enrichment, before classification
- **Function**: Records each article to build time-series of article counts per ticker
- **Feature Flag**: `FEATURE_NEWS_VELOCITY` (default: enabled)

### 4. **test_news_velocity.py** (NEW)
- **Purpose**: Comprehensive test suite for velocity tracking
- **Test Coverage**:
  - Normal flow (2-3 articles/day)
  - Article spike (10+ articles/hour)
  - Viral catalyst (20+ articles/hour)
  - Extreme attention (50+ articles/hour)
  - Deduplication by title similarity
  - Sustained coverage detection
  - Classifier integration
  - Statistics tracking

## Velocity Calculation Logic

### Thresholds

```python
# Article count thresholds (1-hour window)
if articles_1h > 50:
    sentiment = 0.7  # Extreme attention - potential pump
elif articles_1h > 20:
    sentiment = 0.5  # Viral catalyst
elif articles_1h > 10:
    sentiment = 0.3  # High media attention
else:
    sentiment = articles_1h / 10.0 * 0.3  # Linear scaling
```

### Sustained Coverage Bonus

```python
# Sustained spike detection (4-hour window)
if articles_4h >= 15 and velocity_4h > (baseline_hourly * 3):
    is_spike = True
    sentiment += 0.2  # Bonus for sustained coverage (capped at 1.0)
```

### Confidence Levels

```python
# Confidence based on data availability
if articles_24h >= 10:
    confidence = 0.70  # High confidence
elif articles_24h >= 5:
    confidence = 0.60  # Medium confidence
elif articles_24h >= 2:
    confidence = 0.50  # Low-medium confidence
else:
    confidence = 0.40  # Low confidence
```

## Storage Approach

### Option Selected: SQLite Database

**File**: `data/news_velocity.db`

**Schema**:
```sql
CREATE TABLE article_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    timestamp INTEGER NOT NULL,  -- Unix timestamp
    article_title TEXT,
    article_url TEXT,
    source TEXT,
    title_hash TEXT              -- MD5 hash for deduplication
);

CREATE INDEX idx_ticker_time ON article_history(ticker, timestamp);
CREATE INDEX idx_title_hash ON article_history(title_hash);
```

**Why SQLite?**
- Lightweight and zero-config
- Efficient time-windowed queries with indexes
- Persistent storage across bot restarts
- Automatic cleanup of old data (7-day retention)

## Deduplication Logic

### Title Similarity Hash
```python
def _title_similarity_hash(title: str) -> str:
    # Normalize: lowercase, remove special chars, collapse whitespace
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Hash normalized title
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
```

### Duplicate Detection
- Checks for identical title hash within 24-hour window
- Rejects duplicates automatically
- Prevents spam/duplicate articles from inflating velocity

## Test Results

### All Tests Passed ✓

```
Test 1: Normal Flow (2-3 articles/day)
  Articles 1h: 3
  Velocity Score: 0.090
  Sentiment: 0.090
  Is Spike: False
  [PASS]

Test 2: Article Spike (10+ articles in 1 hour)
  Articles 1h: 15
  Velocity Score: 0.500
  Sentiment: 0.500
  Is Spike: True
  [PASS]

Test 3: Viral Catalyst (20+ articles in 1 hour)
  Articles 1h: 25
  Velocity Score: 0.700
  Sentiment: 0.700
  Is Spike: True
  [PASS]

Test 4: Extreme Attention (50+ articles in 1 hour)
  Articles 1h: 60
  Velocity Score: 0.900
  Sentiment: 0.900
  Is Spike: True
  [PASS]

Test 5: Deduplication
  Articles 24h: 1 (4 duplicates rejected)
  [PASS]

Test 6: Sustained Coverage Detection
  Articles 4h: 48
  Velocity 4h: 12.00 articles/hour
  Is Spike: True
  [PASS]

Test 7: Classifier Integration
  Feature enabled, sentiment correctly aggregated
  [PASS]

Test 8: Tracker Statistics
  Total Articles: 167
  Unique Tickers: 7
  [PASS]
```

## Configuration

### Environment Variables

```bash
# Enable/disable news velocity tracking
FEATURE_NEWS_VELOCITY=1  # Default: enabled

# Sentiment weight (0.0 to 1.0)
SENTIMENT_WEIGHT_NEWS_VELOCITY=0.05  # Default: 0.05
```

### Baseline Configuration

Default baseline: **5 articles/day** per ticker

Can be customized per-ticker:
```python
tracker.get_velocity_sentiment(
    ticker="AAPL",
    baseline_articles_per_day=10.0  # Higher baseline for large-cap stocks
)
```

## Integration Points

### 1. Article Recording (runner.py)
```python
# Called for each deduplicated article
velocity_tracker.record_article(
    ticker=ticker,
    title=title,
    url=url,
    source=source,
)
```

### 2. Sentiment Calculation (classify.py)
```python
# Called during sentiment aggregation
velocity_data = velocity_tracker.get_velocity_sentiment(ticker)
sentiment_sources["news_velocity"] = velocity_data["sentiment"]
```

### 3. Metadata Attachment
Velocity data attached to scored items:
- `articles_1h`: Article count in last hour
- `articles_4h`: Article count in last 4 hours
- `articles_24h`: Article count in last 24 hours
- `velocity_1h`: Articles per hour (1h window)
- `velocity_4h`: Articles per hour (4h window)
- `velocity_24h`: Articles per hour (24h window)
- `is_spike`: Boolean flag for sustained spikes
- `velocity_score`: Normalized velocity score (0.0-1.0)

## Edge Cases Handled

### 1. New Ticker with No History
- Uses market-wide baseline (5 articles/day)
- Low confidence until data accumulates
- Gracefully returns None if insufficient data

### 2. Article Spam/Duplicates
- Deduplication by title similarity hash
- 24-hour deduplication window
- Prevents velocity inflation from spam

### 3. Non-News Tickers (ETFs, Indices)
- Skips velocity calculation if no ticker
- Returns None for invalid/missing tickers
- No crash on edge cases

### 4. Database Lock Issues
- Uses SQLite connection pooling
- Graceful error handling
- Continues operation even if tracking fails

## Performance Considerations

### Storage Efficiency
- **Cleanup**: Automatic 7-day retention (configurable)
- **Indexes**: Optimized for time-windowed queries
- **Deduplication**: Prevents database bloat from duplicates

### Query Performance
```sql
-- Fast time-windowed queries (indexed)
SELECT COUNT(*) FROM article_history
WHERE ticker = ? AND timestamp >= ?
```

### Memory Usage
- Minimal memory footprint (SQLite on disk)
- No in-memory caching required
- Singleton pattern for tracker instance

## Monitoring & Debugging

### Logging
```python
# Debug logs for velocity tracking
log.debug("article_recorded ticker=%s source=%s", ticker, source)
log.debug("article_duplicate_skipped ticker=%s", ticker)
log.debug("velocity_sentiment_calculated ticker=%s articles_1h=%d", ticker, count)
log.debug("news_velocity_sentiment ticker=%s velocity_score=%.3f", ticker, score)
```

### Statistics API
```python
tracker = get_tracker()
stats = tracker.get_stats()
# Returns:
# {
#     "total_articles": 1234,
#     "unique_tickers": 56,
#     "articles_24h": 89
# }
```

## Future Enhancements

### Potential Improvements
1. **Dynamic Baseline**: Learn baseline from historical data per ticker
2. **Source Weighting**: Weight articles by source credibility
3. **Geographic Analysis**: Track velocity by region/market
4. **Velocity Trends**: Detect acceleration/deceleration patterns
5. **Correlation Analysis**: Correlate velocity spikes with price movements

### Integration Opportunities
1. **Alert Metadata**: Show velocity metrics in Discord alerts
2. **Gauge Display**: Add velocity indicator to sentiment gauge
3. **Trade Plan**: Factor velocity into entry/exit decisions
4. **Performance Tracking**: Measure alert success rate for high-velocity events

## Conclusion

The news velocity sentiment source has been successfully implemented and tested. It provides a valuable attention indicator that complements existing sentiment sources by detecting breaking news, viral catalysts, and potential pump schemes through article volume analysis.

**Key Metrics**:
- ✓ 8/8 tests passed
- ✓ Deduplication working correctly
- ✓ Spike detection accurate
- ✓ Classifier integration successful
- ✓ Zero performance impact on main loop

The implementation is production-ready and can be enabled via `FEATURE_NEWS_VELOCITY=1`.
