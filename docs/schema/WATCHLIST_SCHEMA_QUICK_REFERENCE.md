# Watchlist Performance Schema - Quick Reference

**For full documentation, see:** [WATCHLIST_PERFORMANCE_DESIGN.md](./WATCHLIST_PERFORMANCE_DESIGN.md)

---

## Schema Files

- **SQL Schema**: [watchlist_performance_schema.sql](./watchlist_performance_schema.sql)
- **Design Doc**: [WATCHLIST_PERFORMANCE_DESIGN.md](./WATCHLIST_PERFORMANCE_DESIGN.md)

---

## Tables

### watchlist_tickers (Main Table)
One row per ticker with state, trigger context, and latest performance.

**Key Columns:**
- `ticker` (PK): Uppercase ticker symbol
- `state`: HOT, WARM, or COOL
- `trigger_reason`, `catalyst_type`: Why ticker was added
- `trigger_price`, `latest_price`, `price_change_pct`: Performance tracking
- `next_check_at`: When to check next (INDEXED)
- `snapshot_count`: Number of performance snapshots

### performance_snapshots (Time-Series Table)
Many rows per ticker with historical performance data.

**Key Columns:**
- `snapshot_id` (PK): Auto-increment
- `ticker` (FK): Links to watchlist_tickers
- `snapshot_at`: Unix timestamp (INDEXED)
- `price`, `volume`, `rvol`, `vwap`: Core metrics
- `volume_surge`: Boolean flag

---

## Common Queries

### Get All HOT Tickers
```sql
SELECT * FROM v_hot_tickers;
```

### Get Tickers Needing Check
```sql
SELECT * FROM v_tickers_needing_check;
```

### Get Latest Snapshot for Ticker
```sql
SELECT * FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC
LIMIT 1;
```

### Get All Snapshots for Ticker
```sql
SELECT * FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC;
```

### Get Performance Summary
```sql
SELECT * FROM v_ticker_performance_summary
ORDER BY price_change_pct DESC;
```

### Count by State
```sql
SELECT state, COUNT(*) as count
FROM watchlist_tickers
WHERE removed_at IS NULL
GROUP BY state;
```

---

## Python Usage

### Initialize Database
```python
from catalyst_bot.watchlist.database import init_database

init_database()
```

### Add Ticker
```python
from catalyst_bot.watchlist.database import add_ticker

add_ticker(
    ticker="AAPL",
    trigger_reason="FDA approval for new device",
    trigger_price=150.25,
    trigger_volume=1500000,
    catalyst_type="fda_approval",
    trigger_score=0.85,
    trigger_sentiment=0.75,
    state="HOT",
)
```

### Record Performance Snapshot
```python
from catalyst_bot.watchlist.database import record_snapshot

record_snapshot(
    ticker="AAPL",
    price=152.50,
    volume=1800000,
    rvol=1.2,
    vwap=151.80,
    market_state="regular",
    price_change_pct=1.5,
    volume_surge=True,
)
```

### Get HOT Tickers
```python
from catalyst_bot.watchlist.database import get_hot_tickers

hot = get_hot_tickers()
for t in hot:
    print(f"{t['ticker']}: {t['price_change_pct']}% ({t['state']})")
```

### Get Tickers Needing Check
```python
from catalyst_bot.watchlist.database import get_tickers_needing_check

tickers = get_tickers_needing_check()
for t in tickers:
    print(f"Check {t['ticker']} (overdue by {t['seconds_overdue']}s)")
```

### Update Ticker State
```python
from catalyst_bot.watchlist.database import update_ticker_state

update_ticker_state("AAPL", "WARM")  # HOT -> WARM -> COOL
```

### Get Ticker Info
```python
from catalyst_bot.watchlist.database import get_ticker_info

info = get_ticker_info("AAPL")
print(f"State: {info['state']}")
print(f"Price change: {info['price_change_pct']}%")
print(f"Snapshots: {info['snapshot_count']}")
```

### Get Snapshots for Ticker
```python
from catalyst_bot.watchlist.database import get_ticker_snapshots

# Latest 100 snapshots
snapshots = get_ticker_snapshots("AAPL", limit=100)

# All snapshots since timestamp
snapshots = get_ticker_snapshots("AAPL", since=1700000000)
```

---

## Indexes (For Performance)

### watchlist_tickers Indexes
1. `idx_tickers_state_monitoring`: (state, monitoring_enabled)
2. `idx_tickers_next_check`: (next_check_at, monitoring_enabled)
3. `idx_tickers_catalyst_type`: (catalyst_type)
4. `idx_tickers_trigger_timestamp`: (trigger_timestamp DESC)
5. `idx_tickers_removed_at`: (removed_at) WHERE removed_at IS NULL

### performance_snapshots Indexes
1. `idx_snapshots_ticker_time`: (ticker, snapshot_at DESC)
2. `idx_snapshots_time`: (snapshot_at DESC)
3. `idx_snapshots_signals`: (buy_signal, sell_signal) WHERE signals = 1
4. `idx_snapshots_volume_surge`: (ticker, snapshot_at) WHERE volume_surge = 1

---

## Views (Convenience Queries)

- `v_hot_tickers`: All active HOT tickers
- `v_warm_tickers`: All active WARM tickers
- `v_cool_tickers`: All COOL tickers (candidates for removal)
- `v_tickers_needing_check`: Tickers that need check now
- `v_ticker_performance_summary`: Comprehensive performance summary
- `v_recent_snapshots`: Latest 100 snapshots across all tickers

---

## Triggers (Automatic Updates)

- `update_ticker_timestamp`: Auto-update `updated_at` on changes
- `track_state_transitions`: Track state changes and increment counter
- `track_promotions`: Increment `promoted_count` when returning to HOT
- `update_peak_tracking`: Update `max_price_seen` and `min_price_seen`

---

## State Lifecycle

```
HOT ──────> WARM ──────> COOL
 ↑                         │
 └─────────────────────────┘
      (Re-promotion on new catalyst)
```

**HOT**: Recent catalyst, check every 60s
**WARM**: Cooling down, check every 300s (5 min)
**COOL**: Inactive, check every 3600s (1 hour) or remove

---

## Reserved Columns (Future Phases)

### Phase 2: Technical Indicators
- RSI, MACD, Bollinger Bands
- Moving Averages (SMA, EMA)
- ATR, OBV

### Phase 3: Breakout Detection
- Breakout flags and types
- Resistance/support levels

### Phase 4-5: Risk Management
- Risk scores
- Position sizing
- Stop loss / take profit levels

---

## Performance Targets

**At 10K tickers, 1M snapshots:**
- Get HOT tickers: <5ms
- Get tickers needing check: <5ms
- Get latest snapshot: <10ms
- Get all snapshots for ticker: <50ms
- Performance summary: <100ms

---

## Storage Estimates

**watchlist_tickers**: ~1KB per row
- 1,000 tickers = 1MB
- 10,000 tickers = 10MB

**performance_snapshots**: ~200 bytes per row
- 100K snapshots = 20MB
- 1M snapshots = 200MB
- 10M snapshots = 2GB

---

## Maintenance Commands

### Optimize Database
```sql
ANALYZE;
```

### Compact After Deletes
```sql
VACUUM;
```

### Enable WAL Mode (Better Concurrency)
```sql
PRAGMA journal_mode=WAL;
```

### Check Index Usage
```sql
SELECT name, tbl_name, sql
FROM sqlite_master
WHERE type='index';
```

---

## Example Workflow

### 1. Initialize (Once)
```python
from catalyst_bot.watchlist.database import init_database
init_database()
```

### 2. Add Ticker to Watchlist (On Alert)
```python
add_ticker(
    ticker="AAPL",
    trigger_reason="FDA approval",
    trigger_price=150.00,
    catalyst_type="fda_approval",
    state="HOT",
)
```

### 3. Monitor Loop (Every 60s)
```python
# Get tickers needing check
tickers = get_tickers_needing_check()

for t in tickers:
    # Fetch current price/volume from market data API
    current_data = fetch_market_data(t['ticker'])

    # Record snapshot
    record_snapshot(
        ticker=t['ticker'],
        price=current_data['price'],
        volume=current_data['volume'],
        rvol=current_data.get('rvol'),
        vwap=current_data.get('vwap'),
        market_state=get_market_state(),
        price_change_pct=calculate_change(
            current_data['price'],
            t['trigger_price']
        ),
    )

    # Update next check time
    interval = get_check_interval(t['state'])
    update_next_check_time(
        ticker=t['ticker'],
        next_check_at=int(time.time()) + interval
    )
```

### 4. State Decay (Periodic)
```python
# Get tickers ready to transition
hot_tickers = get_tickers_by_state("HOT", min_age_days=2)
for t in hot_tickers:
    update_ticker_state(t['ticker'], "WARM")

warm_tickers = get_tickers_by_state("WARM", min_age_days=7)
for t in warm_tickers:
    update_ticker_state(t['ticker'], "COOL")
```

### 5. Analytics (Daily/Weekly)
```python
# Get performance summary
summary = get_performance_summary()

# Analyze by catalyst type
catalyst_performance = analyze_by_catalyst_type()

# Find top performers
top_10 = get_top_performers(limit=10)
```

---

## Migration Path

1. **Phase 1**: SQLite (current) - <1K tickers, <1M snapshots
2. **Phase 2**: SQLite + WAL - <10K tickers, <10M snapshots
3. **Phase 3**: PostgreSQL - >10K tickers, >10M snapshots
4. **Phase 4**: PostgreSQL + TimescaleDB - >100K tickers, >100M snapshots

---

## Testing Checklist

- [ ] Schema creates without errors
- [ ] Can add ticker with all fields
- [ ] Can record snapshot and update denormalized data
- [ ] State transitions work (HOT -> WARM -> COOL)
- [ ] Triggers fire correctly
- [ ] Views return expected data
- [ ] Indexes improve query performance
- [ ] Get hot tickers query < 5ms
- [ ] Get snapshots query < 50ms
- [ ] Soft delete (removed_at) works

---

## Troubleshooting

### Query Too Slow
```sql
-- Check if indexes are being used
EXPLAIN QUERY PLAN
SELECT * FROM watchlist_tickers WHERE state = 'HOT';

-- Rebuild statistics
ANALYZE;
```

### Database Growing Too Large
```sql
-- Check table sizes
SELECT
    name,
    SUM(pgsize) as size_bytes
FROM dbstat
GROUP BY name
ORDER BY size_bytes DESC;

-- Vacuum to reclaim space
VACUUM;
```

### Too Many Snapshots
```python
# Implement data retention policy
def cleanup_old_snapshots(days_to_keep=30):
    cutoff = int(time.time()) - (days_to_keep * 86400)
    conn.execute("""
        DELETE FROM performance_snapshots
        WHERE snapshot_at < ?
    """, (cutoff,))
```

---

**For full implementation details, see:** [WATCHLIST_PERFORMANCE_DESIGN.md](./WATCHLIST_PERFORMANCE_DESIGN.md)
