# CRITICAL ISSUE: Seen Store Race Condition

**Severity:** CRITICAL
**Status:** NOT FIXED
**File:** `src/catalyst_bot/runner.py`
**Lines:** 1405-1418, 2187-2500
**Discovered:** 2025-01-25 (Research Agent Audit)

---

## Problem Description

The SEC filing deduplication logic has a **race condition** that can cause permanent data loss:

1. **Filing is marked as "seen" IMMEDIATELY after LLM processing** (line ~1405)
2. **Alert generation happens LATER** in the pipeline (line ~2187+)
3. **If alert generation fails**, the filing is already marked as "seen" and will never be retried

### Current Code Flow

```python
# Line 1405-1418: Mark ALL SEC filings as seen immediately after processing
if seen_store:
    for filing in sec_filings_to_process:
        seen_store.mark_seen(filing_id)  # ← Marked HERE (TOO EARLY!)

# ... many lines of processing ...

# Line 2187+: Later, keyword extraction and alert logic
if _is_sec_source(source):
    llm_result = sec_llm_cache.get(item_id, {})
    # ← If this fails, filing is permanently lost!
    # ← Already marked as "seen" so won't be retried
```

### Why This Is Critical

- **Permanent data loss**: Failed alerts are never retried
- **Silent failures**: No warning to user that filing was lost
- **Affects all SEC filings**: Any transient error (network, Discord API, etc.) causes data loss
- **Cannot be recovered**: Once marked "seen", filing is skipped forever

---

## Impact Assessment

### Scenarios Where Data Loss Occurs

1. **Discord API timeout** during alert send → Filing lost
2. **Network error** during keyword extraction → Filing lost
3. **Database lock** during position update → Filing lost
4. **Memory pressure** causing crash before alert → Filing lost
5. **Rate limiting** from Discord → Filing lost

### Real-World Example

```
[2025-01-25 18:30:15] INFO: sec_filing_processed ticker=FBLG events=2 metrics=3
[2025-01-25 18:30:15] INFO: marked_as_seen filing_id=0001234567-25-000123
[2025-01-25 18:30:16] ERROR: discord_api_timeout channel=alerts timeout=10s
[2025-01-25 18:30:16] WARNING: alert_send_failed ticker=FBLG
[2025-01-25 18:30:17] INFO: cycle_complete filings_skipped_seen=121
```

**Result:** FBLG filing with 2 material events is permanently lost. Will never be retried.

---

## Solution Options

### **Solution 1: Move seen-store marking to END of pipeline** (RECOMMENDED)

**Approach:** Only mark filing as "seen" AFTER successful alert delivery.

**Implementation:**

```python
# Line 1405-1418: REMOVE early seen-store marking
# DELETE THIS BLOCK:
# if seen_store:
#     for filing in sec_filings_to_process:
#         seen_store.mark_seen(filing_id)

# Line 2500+ (after successful alert send): ADD seen-store marking here
async def send_sec_alert(ticker, filing_data, llm_result):
    try:
        # ... send alert to Discord ...
        await channel.send(embed=alert_embed)

        # SUCCESS: Now mark as seen to prevent reprocessing
        if seen_store:
            filing_id = filing_data.get("item_id")
            seen_store.mark_seen(filing_id)
            log.info("filing_marked_seen_after_success ticker=%s filing_id=%s", ticker, filing_id)
    except Exception as e:
        log.error("alert_send_failed ticker=%s err=%s WILL_RETRY_NEXT_CYCLE", ticker, str(e))
        # DO NOT mark as seen - allow retry on next cycle
        raise
```

**Pros:**
- Simple and clean
- Guarantees no data loss
- Failed alerts automatically retry next cycle
- No architectural changes needed

**Cons:**
- May reprocess same filing multiple times if alerts keep failing
- Requires moving seen-store logic to multiple locations (one per alert type)

**Risk:** LOW - Straightforward change with clear semantics

---

### **Solution 2: Two-phase commit with "pending" state**

**Approach:** Add intermediate "pending" state between "unseen" and "seen".

**Implementation:**

```python
# Add new seen store states
class SeenStore:
    def mark_pending(self, item_id: str):
        """Mark filing as pending (processed but not yet alerted)."""
        self.db.execute(
            "INSERT OR REPLACE INTO seen_items VALUES (?, ?, 'pending')",
            (item_id, int(time.time()))
        )

    def mark_seen(self, item_id: str):
        """Mark filing as fully processed (alert sent)."""
        self.db.execute(
            "UPDATE seen_items SET status='seen' WHERE item_id=?",
            (item_id,)
        )

    def is_seen(self, item_id: str) -> bool:
        """Check if filing is fully processed."""
        status = self.db.execute(
            "SELECT status FROM seen_items WHERE item_id=?",
            (item_id,)
        ).fetchone()
        return status and status[0] == 'seen'

    def cleanup_stale_pending(self, max_age_hours=4):
        """Clean up pending items older than X hours (failed alerts)."""
        cutoff = int(time.time()) - (max_age_hours * 3600)
        self.db.execute(
            "DELETE FROM seen_items WHERE status='pending' AND timestamp < ?",
            (cutoff,)
        )

# Usage:
# Line 1405: Mark as pending after LLM processing
seen_store.mark_pending(filing_id)

# Line 2500: Mark as seen after successful alert
seen_store.mark_seen(filing_id)

# Startup: Clean up stale pending items (retry them)
seen_store.cleanup_stale_pending(max_age_hours=4)
```

**Pros:**
- Explicit state machine (unseen → pending → seen)
- Can track and report on stuck filings
- Automatic cleanup of failed alerts
- Better observability

**Cons:**
- More complex implementation
- Requires database schema change
- Need to handle migration of existing seen items

**Risk:** MEDIUM - More complex but better long-term solution

---

### **Solution 3: Transactional alert queue with retry**

**Approach:** Queue alerts with guaranteed delivery semantics.

**Implementation:**

```python
class AlertQueue:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS alert_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                alert_data TEXT NOT NULL,  -- JSON
                created_at INTEGER NOT NULL,
                retry_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',  -- pending, sent, failed
                last_error TEXT
            )
        """)

    def enqueue(self, filing_id: str, ticker: str, alert_data: dict):
        """Add alert to queue for guaranteed delivery."""
        self.db.execute(
            "INSERT INTO alert_queue (filing_id, ticker, alert_data, created_at) VALUES (?, ?, ?, ?)",
            (filing_id, ticker, json.dumps(alert_data), int(time.time()))
        )

    async def process_queue(self, max_retries=3):
        """Process all pending alerts with retry logic."""
        pending = self.db.execute(
            "SELECT * FROM alert_queue WHERE status='pending' AND retry_count < ?",
            (max_retries,)
        ).fetchall()

        for alert in pending:
            try:
                await send_alert_to_discord(alert)
                self.db.execute(
                    "UPDATE alert_queue SET status='sent' WHERE id=?",
                    (alert['id'],)
                )
                # Mark filing as seen ONLY after successful send
                seen_store.mark_seen(alert['filing_id'])
            except Exception as e:
                self.db.execute(
                    "UPDATE alert_queue SET retry_count=retry_count+1, last_error=? WHERE id=?",
                    (str(e), alert['id'])
                )

# Usage in runner.py:
# After LLM processing, enqueue alert instead of sending directly
alert_queue.enqueue(filing_id, ticker, llm_result)

# In main loop, process alert queue every cycle
await alert_queue.process_queue()
```

**Pros:**
- Guaranteed delivery (with bounded retries)
- Persistent queue survives bot restarts
- Can batch alerts for rate limiting
- Built-in retry logic
- Can monitor queue depth for health

**Cons:**
- Most complex solution
- Requires new database table
- More moving parts (queue processing logic)
- Need to handle queue cleanup

**Risk:** HIGH - Most complex but production-grade solution

---

## Recommendation

**Use Solution 1** (Move seen-store marking to end of pipeline) for immediate fix because:

1. **Lowest risk** - Simple, clear change
2. **Quick to implement** - No schema changes
3. **Easy to test** - Straightforward logic
4. **No regression risk** - Worst case is duplicate alerts (better than data loss)

**Future Enhancement:** Consider Solution 2 or 3 for production hardening:
- Solution 2 provides better observability
- Solution 3 provides enterprise-grade reliability

---

## Testing Plan

### Test Cases for Solution 1

1. **Happy path**: Filing → LLM → Alert → Marked seen ✓
2. **Discord timeout**: Filing → LLM → Alert FAILS → NOT marked seen → Retries next cycle ✓
3. **Duplicate prevention**: Same filing processes twice → Second time skips (already seen) ✓
4. **Network failure**: Filing → LLM → Network error → NOT marked seen → Retries ✓
5. **Bot restart**: Filing pending alert → Bot restarts → Alert sent on next cycle ✓

### Validation Commands

```bash
# Monitor seen store size (should grow slower with fix)
sqlite3 data/seen_store.db "SELECT COUNT(*) FROM seen_items"

# Check for duplicate alerts (acceptable with fix)
grep "alert_sent ticker=FBLG" logs/*.log | wc -l

# Monitor retry rate
grep "WILL_RETRY_NEXT_CYCLE" logs/*.log | wc -l
```

---

## Implementation Priority

**Priority:** P0 (CRITICAL)
**Estimated Effort:** 2-4 hours (Solution 1)
**Dependencies:** None
**Blocking:** No (current system works but loses data on errors)

**Next Steps:**
1. Implement Solution 1 (move seen-store marking)
2. Add comprehensive logging for retry tracking
3. Monitor for 24 hours to ensure no regressions
4. Plan Solution 2/3 for future production hardening

---

## Related Issues

- **Deduplication window**: Currently infinite (seen forever). Consider 7-day TTL.
- **LLM retry logic**: Already implemented (Fix #6) - complements this fix
- **Alert rate limiting**: May need backoff if retries cause spam

---

**Document Version:** 1.0
**Last Updated:** 2025-01-25
**Author:** SEC LLM Audit (Research Agent Report)
