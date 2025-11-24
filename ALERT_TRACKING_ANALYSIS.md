# Alert Tracking & Storage Mechanisms - Comprehensive Analysis

## Executive Summary

The catalyst-bot uses a **dual-database approach** for alert tracking:
1. **alert_outcomes** table in `data/market.db` - Tracks alert performance/breakout outcomes
2. **alert_performance** table in `data/feedback/alert_performance.db` - Tracks alert feedback and historical performance

Currently, **Discord message IDs are NOT stored** in either database, but the infrastructure exists to add them.

---

## 1. Database Schemas for Alerts

### Database 1: Alert Outcomes (Breakout Feedback)
**Location:** `data/market.db` (via `breakout_feedback.py`)

```sql
CREATE TABLE IF NOT EXISTS alert_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL UNIQUE,          -- Unique alert identifier
    ticker TEXT NOT NULL,                    -- Stock ticker (e.g., "AAPL")
    entry_price REAL NOT NULL,               -- Price at alert time
    entry_volume REAL,                       -- Volume at alert time
    timestamp INTEGER NOT NULL,              -- Alert timestamp (Unix epoch)
    keywords TEXT,                           -- JSON array of keywords/catalysts
    confidence REAL,                         -- Model confidence score (0-1)
    outcome_15m TEXT,                        -- JSON: {price, price_change_pct, volume, volume_change_pct, timestamp, breakout_confirmed}
    outcome_1h TEXT,                         -- JSON outcome at 1 hour
    outcome_4h TEXT,                         -- JSON outcome at 4 hours
    outcome_1d TEXT,                         -- JSON outcome at 1 day
    tracked_at INTEGER,                      -- Last update timestamp
    UNIQUE(alert_id) ON CONFLICT REPLACE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON alert_outcomes(ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp ON alert_outcomes(timestamp);
CREATE INDEX IF NOT EXISTS idx_outcomes_tracked_at ON alert_outcomes(tracked_at);
```

### Database 2: Alert Performance (Feedback Loop)
**Location:** `data/feedback/alert_performance.db` (via `feedback/database.py`)

```sql
CREATE TABLE IF NOT EXISTS alert_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT UNIQUE NOT NULL,          -- Unique alert identifier
    ticker TEXT NOT NULL,                    -- Stock ticker
    source TEXT NOT NULL,                    -- Alert source (e.g., "finviz", "businesswire")
    catalyst_type TEXT NOT NULL,             -- Catalyst type (e.g., "fda_approval", "partnership")
    keywords TEXT,                           -- JSON array of keywords
    posted_at INTEGER NOT NULL,              -- When alert was posted (Unix epoch)
    posted_price REAL,                       -- Price at time of posting
    
    -- Performance metrics at different timeframes
    price_15m REAL,
    price_1h REAL,
    price_4h REAL,
    price_1d REAL,
    
    price_change_15m REAL,
    price_change_1h REAL,
    price_change_4h REAL,
    price_change_1d REAL,
    
    volume_15m REAL,
    volume_1h REAL,
    volume_4h REAL,
    volume_1d REAL,
    
    volume_change_15m REAL,
    volume_change_1h REAL,
    volume_change_4h REAL,
    volume_change_1d REAL,
    
    breakout_confirmed BOOLEAN,             -- True if price_change > 3% and volume sustained
    max_gain REAL,
    max_loss REAL,
    
    -- Evaluation
    outcome TEXT,                            -- Classification: 'win', 'loss', 'neutral'
    outcome_score REAL,                      -- Score: -1.0 to +1.0
    
    updated_at INTEGER NOT NULL
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_ticker ON alert_performance(ticker);
CREATE INDEX IF NOT EXISTS idx_posted_at ON alert_performance(posted_at);
CREATE INDEX IF NOT EXISTS idx_catalyst_type ON alert_performance(catalyst_type);
CREATE INDEX IF NOT EXISTS idx_outcome ON alert_performance(outcome);
```

---

## 2. Unique Identifier for Alerts

### How alert_id is Generated

Alerts use a **two-part identification system**:

#### Part 1: Explicit ID (in payload)
From `src/catalyst_bot/alert_guard.py`:
```python
def build_alert_id(payload: Dict[str, Any]) -> Optional[str]:
    """
    Precedence:
      1) payload.get('id') if it's a non-empty str
      2) hash(canonical_url + "||" + normalized_title)
      3) None if insufficient fields
    """
    # Preferred: explicit 'id' in payload
    if payload.get('id'):
        return payload['id']
    
    # Fallback: hash canonical URL + normalized title
    url = canonicalize_url(payload.get('url') or payload.get('link'))
    title = normalize_title(payload.get('title'))
    
    if url and title:
        raw = f"{url}||{title}"
        h = hashlib.sha1(raw.encode('utf-8')).hexdigest()
        return f"aid:{h}"  # Prefixed with "aid:"
    
    return None
```

#### Part 2: Generated ID (in runner.py)
When alert is registered for tracking (line 2445 in `runner.py`):
```python
register_alert_for_tracking(
    ticker=ticker,
    entry_price=last_px,
    entry_volume=None,
    timestamp=datetime.now(timezone.utc),
    keywords=keywords,
    confidence=confidence,
    # alert_id is auto-generated if not provided:
    # "{ticker}_{int(timestamp.timestamp())}"
)
```

**Result:** Each alert has a stable, unique identifier:
- **Sources:** URL + title hash, or explicit ID from payload, or ticker + timestamp
- **Usage:** Prevents duplicate alerts (via SeenStore), tracks outcomes, links to feedback

---

## 3. Alert-to-Ticker & Timestamp Linkage

### Alert Payload Structure (runner.py, line 2306-2321)

```python
alert_payload = {
    "item": it,                              -- Original feed item
    "item_dict": it,                         -- Duplicate reference
    "scored": scored,                        -- Classification with confidence/keywords
    "last_price": last_px,                   -- Current price
    "last_change_pct": last_chg,            -- Percent change
    "record_only": False,                    -- Whether to skip Discord posting
    "webhook_url": webhook_url,              -- Discord webhook
    "market_info": market_info,              -- Market hours info
}
```

### Feed Item Structure (it = item from feed)

```python
{
    "id": str,                    -- Unique item ID from feed
    "ticker": str,                -- Stock ticker (e.g., "AAPL")
    "title": str,                 -- News headline
    "source": str,                -- Feed source (finviz, businesswire, etc.)
    "link": str,                  -- Article URL
    "ts": ISO datetime,           -- Timestamp when published
    "price": float,               -- Stock price at time of feed
    # ... other fields
}
```

### How They're Linked in Databases

**In alert_outcomes table:**
- `alert_id` ← Built from URL + title hash or explicit ID
- `ticker` ← Extracted from item_dict["ticker"]
- `timestamp` ← Item's published timestamp (Unix epoch)
- `keywords` ← Classification keywords (JSON array)

**In alert_performance table:**
- `alert_id` ← Same ID as alert_outcomes
- `ticker` ← Same ticker
- `posted_at` ← When alert was sent to Discord
- `catalyst_type` ← Type of catalyst detected

---

## 4. Feedback/Tracking Tables & Outcomes

### Alert Outcomes Tracking Workflow

**Step 1: Alert Registration** (runner.py, line 2445)
```python
# Called after send_alert_safe succeeds
register_alert_for_tracking(
    ticker=ticker,
    entry_price=last_px,
    timestamp=datetime.now(timezone.utc),
    keywords=keywords,  -- From classification
    confidence=confidence,
    # Generates alert_id automatically
)
```
⟹ Creates entry in `alert_outcomes` table

**Step 2: Performance Tracking** (breakout_feedback.py)
Updates happen periodically via `track_pending_outcomes()`:

```python
# For each alert, fetch current price and update:
update_alert_outcome(
    alert_id=alert_id,
    interval="15m",      -- Can be: "15m", "1h", "4h", "1d"
    current_price=price,
    current_volume=volume,
)
```

This calculates:
- `price_change_pct = ((current_price - entry_price) / entry_price) * 100`
- `volume_change_pct = ((current_volume - entry_volume) / entry_volume) * 100`
- `breakout_confirmed = price_change_pct > 3.0 and volume_change_pct > -20`

**Step 3: Outcome Scoring** (feedback/outcome_scorer.py)
```python
# Called periodically to score outcomes
update_outcome(
    alert_id=alert_id,
    outcome="win",        -- "win", "loss", or "neutral"
    score=0.85,          -- -1.0 to +1.0
)
```

### Keyword Weight Adjustment

From `breakout_feedback.get_keyword_performance_stats()`:
- Aggregates outcomes by keyword
- Calculates: success_rate = successes / total
- Suggests weight adjustments:
  - **INCREASE:** keywords with ≥70% success rate (≥10 samples)
  - **DECREASE:** keywords with <40% success rate (≥10 samples)

---

## 5. Data Flow: Alert Detection → Discord Posting

### Complete Flow Diagram

```
1. FEED INGEST (feeds.py, runner.py)
   ↓
   News item arrives from Finviz, BusinessWire, etc.
   Contains: [ticker, title, link, source, price, timestamp]
   
2. DEDUPLICATION (seen_store.py)
   ↓
   Check if item ID already seen
   If YES → Skip
   If NO → Continue
   
3. CLASSIFICATION (classify.py)
   ↓
   Run ML model to classify alert
   Output: {keywords, confidence, sentiment, alert_type}
   
4. FILTERING (runner.py, lines 2100-2284)
   ↓
   Apply gates:
   - Ticker validation (real stock?)
   - Crypto filter (exclude)
   - Price ceiling (too expensive?)
   - Volume gate (high enough?)
   - Score threshold (good enough?)
   - Time gate (not too old?)
   - Sentiment gate (positive enough?)
   - Category gate (appropriate type?)
   
5. BUILD ALERT PAYLOAD (runner.py, line 2306)
   ↓
   alert_payload = {
       "item": it,
       "scored": scored,
       "last_price": last_px,
       "last_change_pct": last_chg,
       "webhook_url": webhook_url,
       "market_info": market_info,
   }
   
6. SEND DISCORD ALERT (alerts.py, send_alert_safe)
   ↓
   Format Discord message:
   - Content (text summary)
   - Embed (rich formatting)
   - Images (chart, sentiment gauge)
   - Components (interactive buttons)
   
7. POST TO DISCORD (alerts.py, post_discord_json)
   ↓
   HTTP POST to Discord webhook
   Rate limit aware (respect X-RateLimit headers)
   Retry on 429/5xx with exponential backoff
   Response: 200-299 = success
   
8. MARK SEEN (runner.py, line 2392)
   ↓
   Only if send_alert_safe returned True
   Item marked in SeenStore (prevents re-alert)
   
9. LOG ACCEPTED ITEM (runner.py, line 2401)
   ↓
   Store in accepted_items.jsonl for analysis
   Contains: item, price, score, sentiment, keywords
   
10. REGISTER FOR TRACKING (runner.py, line 2445)
    ↓
    register_alert_for_tracking(
        ticker=ticker,
        entry_price=last_px,
        timestamp=datetime.now(timezone.utc),
        keywords=keywords,
        confidence=confidence,
    )
    Creates entry in alert_outcomes table
    
11. ASYNC ENRICHMENT (runner.py, line 2291)
    ↓
    Optional: Queue for background enrichment
    Fetches: RVOL, float, VWAP, divergence patterns
    
12. PERIODIC OUTCOME TRACKING (scheduled job)
    ↓
    Every 5-10 minutes, track_pending_outcomes() runs
    Updates: outcome_15m, outcome_1h, outcome_4h, outcome_1d
    
13. FEEDBACK LOOP (weekly job)
    ↓
    Analyze keyword performance
    Suggest weight adjustments
    Retrain classification model
```

---

## 6. Current Discord Integration

### What's Currently Captured

**From Discord Webhook Response (alerts.py, line 354-360):**
```python
resp = requests.post(url, json=payload, timeout=10)
if 200 <= resp.status_code < 300:
    return True, resp.status_code, None  # ✓ Success
```

**Status Code Only:** The current implementation only checks HTTP status (200-299 = success).

**Message ID Available (But Not Captured):**
Discord webhook POST response includes JSON:
```json
{
  "id": "123456789",           // ← Message ID (not captured!)
  "channel_id": "987654321",   // ← Channel ID (not captured!)
  "guild_id": "...",
  "author": {...},
  "content": "...",
  "timestamp": "2025-01-01T..."
}
```

### Async Alert Posting with Message ID (alerts.py, lines 1420-1440)

There's a newer async implementation that DOES capture message IDs:

```python
async def _send_progressive_alert(webhook_url, alert_data, embed):
    """Send alert and capture message ID for LLM enrichment."""
    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(webhook_url, session=session)
            message = await webhook.send(embed=embed, wait=True)  # ← Captures message!
        
        # Queue for LLM processing with message ID
        asyncio.create_task(
            _enrich_alert_with_llm(
                message_id=message.id,          # ← Message ID extracted!
                webhook_url=webhook_url,
                alert_data=alert_data,
                initial_embed=embed,
            )
        )
        return {"id": message.id, "channel_id": message.channel_id}
    except Exception as e:
        log.error("progressive_alert_send_failed err=%s", str(e))
        return None
```

---

## 7. Adding Discord Message IDs to Database

### Recommended Schema Modifications

#### Option A: Add to alert_outcomes table

```sql
ALTER TABLE alert_outcomes ADD COLUMN discord_message_id TEXT;
ALTER TABLE alert_outcomes ADD COLUMN discord_channel_id TEXT;
ALTER TABLE alert_outcomes ADD COLUMN discord_posted_at INTEGER;

CREATE INDEX IF NOT EXISTS idx_outcomes_discord_msg ON alert_outcomes(discord_message_id);
```

#### Option B: Add to alert_performance table

```sql
ALTER TABLE alert_performance ADD COLUMN discord_message_id TEXT;
ALTER TABLE alert_performance ADD COLUMN discord_channel_id TEXT;
ALTER TABLE alert_performance ADD COLUMN posted_at_timestamp INTEGER;

CREATE INDEX IF NOT EXISTS idx_perf_discord_msg ON alert_performance(discord_message_id);
```

#### Option C: Create separate discord_audit table (recommended for compliance)

```sql
CREATE TABLE IF NOT EXISTS discord_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    discord_message_id TEXT UNIQUE NOT NULL,
    discord_channel_id TEXT NOT NULL,
    discord_guild_id TEXT,
    webhook_url_hash TEXT,                  -- SHA256 of webhook URL for security
    posted_at INTEGER NOT NULL,
    edited_at INTEGER,
    reaction_count INTEGER DEFAULT 0,
    
    -- Linkage
    FOREIGN KEY (alert_id) REFERENCES alert_outcomes(alert_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_alert_id ON discord_audit(alert_id);
CREATE INDEX IF NOT EXISTS idx_audit_message_id ON discord_audit(discord_message_id);
CREATE INDEX IF NOT EXISTS idx_audit_ticker ON discord_audit(ticker);
```

---

## 8. Implementation Path: Capture Message IDs

### Step 1: Modify post_discord_json to Return Message ID

```python
-- Current (alerts.py, line 695)
def post_discord_json(payload: dict, webhook_url: str | None = None, *, max_retries: int = 2) -> bool:
    """Returns True/False only"""

-- Recommended
def post_discord_json(payload: dict, webhook_url: str | None = None, *, max_retries: int = 2) -> dict | bool:
    """Returns (success: bool, message_id: str | None, status_code: int)"""
    
    # In _post_discord_with_backoff, capture response JSON
    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
            message_id = data.get('id')
            return True, message_id, resp.status_code
        except Exception:
            return True, None, resp.status_code
```

### Step 2: Update send_alert_safe to Handle Response

```python
-- Current: returns bool
ok = send_alert_safe(alert_payload)

-- Proposed: returns dict with metadata
result = send_alert_safe(alert_payload)
if result['success']:
    discord_message_id = result['discord_message_id']
    # Store in database
```

### Step 3: Store Message ID After Successful Post

```python
# In runner.py, after send_alert_safe returns
if ok:
    # Get message ID from response
    message_id = result.get('discord_message_id')
    
    # Store in database
    if message_id and alert_id:
        store_discord_message_id(
            alert_id=alert_id,
            discord_message_id=message_id,
            discord_channel_id=result.get('discord_channel_id'),
        )
```

---

## 9. Query Examples

### Get recent alerts for a ticker

```sql
SELECT 
    alert_id, ticker, posted_at, keywords, outcome
FROM alert_performance
WHERE ticker = 'AAPL'
ORDER BY posted_at DESC
LIMIT 20;
```

### Get alert outcomes at different timeframes

```sql
SELECT 
    alert_id, ticker, entry_price,
    json_extract(outcome_15m, '$.price_change_pct') as change_15m,
    json_extract(outcome_1h, '$.price_change_pct') as change_1h,
    json_extract(outcome_1d, '$.price_change_pct') as change_1d
FROM alert_outcomes
WHERE ticker = 'TSLA'
ORDER BY timestamp DESC
LIMIT 10;
```

### Get keyword performance

```sql
SELECT 
    keyword,
    COUNT(*) as total_alerts,
    COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins,
    ROUND(100.0 * COUNT(CASE WHEN outcome = 'win' THEN 1 END) / COUNT(*), 1) as win_rate_pct,
    ROUND(AVG(outcome_score), 2) as avg_score
FROM (
    SELECT 
        json_each.value as keyword,
        outcome,
        outcome_score
    FROM alert_performance, 
    json_each(alert_performance.keywords)
)
WHERE posted_at > datetime('now', '-7 days')
GROUP BY keyword
ORDER BY win_rate_pct DESC;
```

### Link alerts to Discord messages (if implemented)

```sql
SELECT 
    a.alert_id,
    a.ticker,
    a.posted_at,
    d.discord_message_id,
    d.discord_channel_id
FROM alert_performance a
LEFT JOIN discord_audit d ON a.alert_id = d.alert_id
WHERE a.posted_at > datetime('now', '-24 hours')
ORDER BY a.posted_at DESC;
```

---

## 10. Key Files Reference

| File | Purpose |
|------|---------|
| `src/catalyst_bot/alerts.py` | Alert posting, Discord integration |
| `src/catalyst_bot/breakout_feedback.py` | Alert outcome tracking (alert_outcomes table) |
| `src/catalyst_bot/feedback/database.py` | Alert performance tracking (alert_performance table) |
| `src/catalyst_bot/alert_guard.py` | Alert ID generation via URL + title hash |
| `src/catalyst_bot/runner.py` | Main alert workflow, lines 2305-2456 |
| `src/catalyst_bot/seen_store.py` | Deduplication (prevents duplicate alerts) |
| `src/catalyst_bot/discord_transport.py` | Low-level Discord HTTP transport with rate limiting |
| `data/market.db` | Contains alert_outcomes table |
| `data/feedback/alert_performance.db` | Contains alert_performance table |

---

## Summary

1. **Unique Identifier:** Each alert has a stable `alert_id` built from URL+title hash or explicit ID
2. **Ticker Linkage:** Stored in both `alert_outcomes` and `alert_performance` tables
3. **Timestamps:** Multiple timestamps track: published_at, posted_at, tracked_at
4. **Feedback:** Two tables track outcomes at 15m, 1h, 4h, 1d intervals with price/volume changes
5. **Discord IDs:** Currently NOT captured in persistent storage, but infrastructure exists
6. **Flow:** Feed → Classify → Filter → Build Payload → Post Discord → Register Tracking → Periodic Updates
7. **Rate Limiting:** Discord rate limits respected via headers (X-RateLimit-*)
8. **Deduplication:** SeenStore prevents alert re-posting within configured window

The system is well-architected for tracking alert quality and adjusting classification weights based on outcomes.
