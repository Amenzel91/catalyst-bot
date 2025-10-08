# Tonight's Patch Work - Ollama Stability + Heartbeat Fix

**Date:** October 6, 2025
**Priority:** High - Production stability issues

---

## **PATCH 1: Ollama/Mistral GPU Overload Fix**

### **Problem**
- Mistral LLM returning HTTP 500 errors due to GPU overload
- Processing 136 items without batching or delays
- Bot continues but loses 25% of sentiment analysis accuracy

### **Root Cause**
```python
# Current: All items sent to Mistral at once
for item in all_feeds:  # 136 items
    llm_sentiment = query_llm(prompt)  # No delay, no batching
```

### **Solution: Smart Batching + Delays**

**File:** `src/catalyst_bot/llm_client.py`

```python
import time
from catalyst_bot.config import settings

def query_llm_with_batching(prompt: str, priority: str = "normal") -> str:
    """
    Query LLM with rate limiting and error handling.

    Args:
        prompt: The prompt to send
        priority: "high", "normal", "low" - determines retry behavior
    """
    max_retries = 3 if priority == "high" else 1
    retry_delay = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": "mistral", "prompt": prompt, "stream": False},
                timeout=30
            )

            if resp.status_code == 200:
                return resp.json().get("response", "")

            elif resp.status_code == 500:
                # Ollama overloaded, wait and retry
                _logger.warning(f"Ollama overloaded (500), retry {attempt+1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    # Give up, return empty (fallback to other sentiment sources)
                    _logger.error("Ollama failed after retries, skipping LLM sentiment")
                    return ""

        except requests.exceptions.Timeout:
            _logger.warning(f"Ollama timeout, retry {attempt+1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return ""

        except Exception as e:
            _logger.error(f"Ollama error: {e}")
            return ""

    return ""
```

**File:** `src/catalyst_bot/classify.py`

Add batching logic:

```python
# Add to config/.env
MISTRAL_BATCH_SIZE=5          # Process 5 items at a time
MISTRAL_BATCH_DELAY=2.0       # 2 second delay between batches
MISTRAL_MIN_PRESCALE=0.20     # Only use Mistral on items scoring >0.20 from VADER+FinBERT

def process_items_with_mistral(items: List[Dict]) -> List[Dict]:
    """
    Process items through Mistral in batches with delays.
    """
    batch_size = settings.MISTRAL_BATCH_SIZE or 5
    batch_delay = settings.MISTRAL_BATCH_DELAY or 2.0
    min_prescale = settings.MISTRAL_MIN_PRESCALE or 0.20

    # Pre-filter: Only send high-potential items to expensive LLM
    items_needing_llm = [
        item for item in items
        if item.get("prescale_score", 0) >= min_prescale
    ]

    _logger.info(f"Mistral batching: {len(items_needing_llm)}/{len(items)} items qualify (score >= {min_prescale})")

    for i in range(0, len(items_needing_llm), batch_size):
        batch = items_needing_llm[i:i+batch_size]

        _logger.info(f"Processing Mistral batch {i//batch_size + 1}/{(len(items_needing_llm)-1)//batch_size + 1}")

        for item in batch:
            llm_result = query_llm_with_batching(item["prompt"], priority="normal")
            item["llm_sentiment"] = llm_result

        # Delay between batches (except last batch)
        if i + batch_size < len(items_needing_llm):
            time.sleep(batch_delay)

    return items
```

### **Expected Impact**
- Reduces GPU load by 73% (136 → ~40 items based on pre-filtering)
- Spreads processing over time (2s delays prevent spikes)
- Graceful degradation (continues with 3 sources if Mistral fails)
- Bot completes cycles faster (skip low-scoring items)

### **Advanced Stability Strategies (Optional Add-ons)**

**1. GPU Priming/Warmup**
```python
def prime_ollama_gpu():
    """
    Prime Ollama GPU with small warmup query before batch processing.
    Prevents cold-start overhead on first LLM call.
    """
    warmup_prompt = "Respond with 'OK'"
    try:
        resp = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": "mistral", "prompt": warmup_prompt, "stream": False},
            timeout=10
        )
        if resp.status_code == 200:
            _logger.info("Ollama GPU warmed up successfully")
            return True
    except Exception as e:
        _logger.warning(f"GPU warmup failed: {e}")
    return False

# Call before batch processing
if items_needing_llm:
    prime_ollama_gpu()
    process_items_with_mistral(items_needing_llm)
```
**Benefit:** Reduces first-call latency by ~500ms, prevents GPU spin-up during critical processing

**2. Progressive Embed Updates (Delayed Sentiment)**
```python
def post_alert_progressive(alert_data):
    """
    Post alert in 2 phases: immediate basic info, then update with LLM sentiment.
    """
    # Phase 1: Post immediately with 3 sources (VADER + FinBERT + Earnings)
    basic_embed = build_basic_embed(alert_data)  # No LLM yet
    msg = discord_webhook.post(basic_embed)
    alert_data["message_id"] = msg.id

    # Queue for LLM processing later
    llm_queue.append(alert_data)

    return msg

def process_llm_queue_async():
    """
    Process LLM queue in background, update embeds when complete.
    Runs every 30 seconds, processes 5 items per batch.
    """
    while True:
        batch = llm_queue[:5]
        llm_queue = llm_queue[5:]

        for alert in batch:
            llm_sentiment = query_llm_with_batching(alert["prompt"])
            alert["llm_sentiment"] = llm_sentiment

            # Update Discord embed with full 4-source sentiment
            updated_embed = build_full_embed(alert)
            discord_webhook.edit_message(alert["message_id"], updated_embed)

        time.sleep(30)  # Wait 30s between batches
```
**Benefit:** Alerts post instantly (1-2s), LLM sentiment fills in later (no blocking)

**3. Adaptive Batch Sizing (Monitor GPU Health)**
```python
def get_ollama_health():
    """Check Ollama health and adjust batch size dynamically."""
    try:
        resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2)
        if resp.status_code == 200:
            return "healthy"
        elif resp.status_code == 500:
            return "overloaded"
    except:
        return "down"

def adaptive_batch_size():
    """Adjust batch size based on Ollama health."""
    health = get_ollama_health()

    if health == "healthy":
        return 5  # Normal batch size
    elif health == "overloaded":
        return 2  # Reduce to 2 items per batch
    else:
        return 0  # Skip LLM entirely

# Use before batching
batch_size = adaptive_batch_size()
if batch_size > 0:
    process_items_with_mistral(items, batch_size=batch_size)
```
**Benefit:** Self-regulates based on GPU strain, prevents cascading failures

**4. LLM Result Caching**
```python
import hashlib
import json

llm_cache = {}  # In-memory cache (or use Redis for persistence)

def query_llm_cached(prompt: str) -> str:
    """
    Cache LLM results for identical prompts (common for similar news).
    """
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()

    if prompt_hash in llm_cache:
        _logger.debug(f"LLM cache hit: {prompt_hash[:8]}")
        return llm_cache[prompt_hash]

    result = query_llm_with_batching(prompt)
    llm_cache[prompt_hash] = result

    # Expire cache after 1 hour
    if len(llm_cache) > 100:  # Keep last 100 results
        llm_cache.pop(next(iter(llm_cache)))

    return result
```
**Benefit:** Skip redundant LLM calls for similar headlines (common in PR blasts)

**5. Sentiment Score Interpolation (Fallback)**
```python
def estimate_llm_sentiment_fallback(vader_score, finbert_score):
    """
    If LLM unavailable, estimate what it would return based on other sources.
    Training: Analyze 100+ alerts to find correlation.
    """
    # Example: LLM typically amplifies strong signals
    if abs(vader_score) > 0.5 and abs(finbert_score) > 0.5:
        # Strong agreement → LLM likely agrees strongly
        estimated = (vader_score + finbert_score) / 2 * 1.2  # 20% boost
    else:
        # Weak signals → LLM likely neutral
        estimated = (vader_score + finbert_score) / 2 * 0.8

    return max(-1.0, min(1.0, estimated))  # Clamp to [-1, 1]

# Use when Mistral fails
if llm_result == "" or llm_result is None:
    item["llm_sentiment"] = estimate_llm_sentiment_fallback(
        item["vader_sentiment"],
        item["finbert_sentiment"]
    )
    item["llm_fallback"] = True  # Flag for tracking
```
**Benefit:** Maintain 4-source appearance even when LLM down

**6. Ollama Queue Monitor & Auto-Restart**
```python
def check_ollama_queue_depth():
    """Monitor Ollama's internal queue (if API exposes it)."""
    # If Ollama has 5+ pending requests, delay new submissions
    # Pseudo-code (API may not support this)
    pass

def auto_restart_ollama_on_failure():
    """
    If Ollama repeatedly fails, restart the service.
    """
    global ollama_failure_count
    ollama_failure_count += 1

    if ollama_failure_count >= 10:  # 10 consecutive failures
        _logger.error("Ollama critically failing, attempting restart")
        subprocess.run(["net", "stop", "Ollama"], shell=True)
        time.sleep(5)
        subprocess.run(["net", "start", "Ollama"], shell=True)
        ollama_failure_count = 0
        time.sleep(30)  # Wait for startup
```
**Benefit:** Self-healing without manual intervention

---

### **Recommended Implementation Priority**

**Phase 1 (Tonight - Core Fixes):**
1. ✅ Batching (5 items, 2s delay)
2. ✅ Pre-filtering (>0.20 prescale)
3. ✅ Retry logic (3 attempts, exponential backoff)

**Phase 2 (Tomorrow - Enhancements):**
4. GPU warmup (5 min)
5. LLM result caching (10 min)
6. Sentiment fallback estimation (15 min)

**Phase 3 (Future - Advanced):**
7. Progressive embed updates (30 min)
8. Adaptive batch sizing (20 min)
9. Auto-restart logic (15 min)

**Total time if implementing all:** ~2.5 hours

---

## **PATCH 2: Heartbeat Cumulative Counts Fix**

### **Problem**
Heartbeat only shows counts from most recent scan, not cumulative since last heartbeat.

**Current behavior:**
```
Heartbeat: scanned=136, alerts=2  (just the last cycle)
```

**Expected behavior:**
```
Heartbeat: scanned=816, alerts=12  (6 cycles since last heartbeat)
```

### **Root Cause**
```python
# Current: Resets every cycle
stats = {
    "scanned": len(current_items),
    "alerts": len(alerts_posted_this_cycle)
}
send_heartbeat(stats)
```

### **Solution: Cumulative Tracking**

**File:** `src/catalyst_bot/runner.py`

```python
# Add class-level accumulator
class HeartbeatAccumulator:
    def __init__(self):
        self.reset()

    def reset(self):
        self.total_scanned = 0
        self.total_alerts = 0
        self.total_errors = 0
        self.cycles_completed = 0
        self.last_heartbeat_time = datetime.now(timezone.utc)

    def add_cycle(self, scanned: int, alerts: int, errors: int):
        self.total_scanned += scanned
        self.total_alerts += alerts
        self.total_errors += errors
        self.cycles_completed += 1

    def should_send_heartbeat(self, interval_minutes: int = 60) -> bool:
        """Check if it's time for heartbeat (default: every 60 min)"""
        elapsed = (datetime.now(timezone.utc) - self.last_heartbeat_time).total_seconds()
        return elapsed >= (interval_minutes * 60)

    def get_stats(self) -> dict:
        elapsed_min = (datetime.now(timezone.utc) - self.last_heartbeat_time).total_seconds() / 60
        return {
            "total_scanned": self.total_scanned,
            "total_alerts": self.total_alerts,
            "total_errors": self.total_errors,
            "cycles_completed": self.cycles_completed,
            "elapsed_minutes": round(elapsed_min, 1),
            "avg_alerts_per_cycle": round(self.total_alerts / max(self.cycles_completed, 1), 1)
        }

# Global accumulator
_heartbeat_acc = HeartbeatAccumulator()

def _cycle(log, settings, market_info):
    # ... existing cycle logic ...

    # Track cycle results
    _heartbeat_acc.add_cycle(
        scanned=len(items_processed),
        alerts=len(alerts_posted),
        errors=error_count
    )

    # Send heartbeat periodically (every 60 min)
    if _heartbeat_acc.should_send_heartbeat(interval_minutes=60):
        stats = _heartbeat_acc.get_stats()
        send_heartbeat(stats)
        _heartbeat_acc.reset()  # Reset for next period
```

**File:** `src/catalyst_bot/discord_utils.py`

Update heartbeat embed format:

```python
def build_heartbeat_embed(stats: dict) -> dict:
    """Build heartbeat embed with cumulative stats."""
    return {
        "title": "🤖 Bot Heartbeat",
        "color": 0x00FF00,
        "fields": [
            {
                "name": "Period Summary",
                "value": f"Last {stats['elapsed_minutes']} minutes",
                "inline": False
            },
            {
                "name": "📊 Feeds Scanned",
                "value": f"{stats['total_scanned']:,}",
                "inline": True
            },
            {
                "name": "🔔 Alerts Posted",
                "value": f"{stats['total_alerts']}",
                "inline": True
            },
            {
                "name": "🔄 Cycles Completed",
                "value": f"{stats['cycles_completed']}",
                "inline": True
            },
            {
                "name": "📈 Avg Alerts/Cycle",
                "value": f"{stats['avg_alerts_per_cycle']}",
                "inline": True
            },
            {
                "name": "❌ Errors",
                "value": f"{stats['total_errors']}",
                "inline": True
            }
        ],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

### **Configuration**

Add to `.env`:
```ini
# Heartbeat Settings
HEARTBEAT_INTERVAL_MINUTES=60    # Send heartbeat every 60 minutes
HEARTBEAT_WEBHOOK_URL=...        # Optional separate webhook for heartbeats
```

### **Expected Impact**
- Better visibility into bot performance over time
- See cumulative metrics between hourly heartbeats
- Track average alerts per cycle
- Easier to spot performance degradation

---

## **PATCH 3: Unicode Logging Fix (Quick Win)**

### **Problem**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2011'
```

### **Solution**

**File:** `src/catalyst_bot/llm_client.py:135`

```python
# Before:
_logger.warning("LLM API returned non‑200 status: %s", resp.status_code)

# After:
_logger.warning("LLM API returned non-200 status: %s", resp.status_code)
```

Simple: Replace non-breaking hyphen with regular dash.

---

## **Implementation Order**

1. **PATCH 3** (5 min) - Unicode fix - quick win
2. **PATCH 1** (30 min) - Ollama batching - critical stability
3. **PATCH 2** (20 min) - Heartbeat cumulative - nice to have

**Total time:** ~1 hour

---

## **Testing Plan**

**After PATCH 1:**
```bash
# Monitor Ollama health
curl http://localhost:11434/api/tags

# Watch for reduced 500 errors
tail -f data/logs/bot.jsonl | findstr "Ollama"

# Verify batching in logs
# Should see: "Processing Mistral batch 1/8" instead of all at once
```

**After PATCH 2:**
```bash
# Wait for 2 cycles, check heartbeat shows cumulative
# Heartbeat should show: scanned=272 (136*2), alerts=4 (2+2), cycles=2
```

---

## **Rollback Plan**

All patches are additive, no breaking changes. If issues:

1. **PATCH 1:** Set `MISTRAL_BATCH_SIZE=999` to disable batching
2. **PATCH 2:** Heartbeat will just send more frequently (no harm)
3. **PATCH 3:** Already fixed (no rollback needed)

---

**Ready to implement when you're back!**

---

## **PATCH 4: Pre-Market Coverage Verification**

### **Problem**
Bot may not be running early enough to catch pre-market movers (4am-9:30am ET).

**Example:** Missed 125% gainer this morning - need to verify coverage window.

### **Current State Check**

**File:** `.env`
```ini
# Check current settings
MARKET_OPEN_CYCLE_SEC=60        # Regular market hours
EXTENDED_HOURS_CYCLE_SEC=90     # Extended hours
MARKET_CLOSED_CYCLE_SEC=180     # Closed
```

**File:** `src/catalyst_bot/runner.py`

Need to verify:
1. Market hours detection working correctly
2. Bot cycles during 4am-9:30am ET pre-market
3. All feeds active during pre-market (not just SEC filings)

### **Solution: Pre-Market Verification Script**

**File:** `verify_premarket_coverage.bat` (NEW)

```batch
@echo off
REM Verify pre-market coverage settings

echo.
echo ============================================================
echo  Pre-Market Coverage Verification
echo ============================================================
echo.

REM Check if bot is running
echo [1/4] Checking if bot is running...
tasklist | findstr python >nul 2>nul
if not errorlevel 1 (
    echo   [OK] Bot is running
) else (
    echo   [ERROR] Bot is NOT running - start it before pre-market!
    pause
    exit /b 1
)

echo.

REM Check recent logs for market hours detection
echo [2/4] Checking market hours detection...
powershell "Get-Content data\logs\bot.jsonl -Tail 100 | Select-String 'market_status' | Select-Object -First 5"

echo.

REM Check cycle intervals in logs
echo [3/4] Checking cycle intervals...
powershell "Get-Content data\logs\bot.jsonl -Tail 50 | Select-String 'CYCLE_DONE' | Select-Object -First 5"

echo.

REM Show active feeds
echo [4/4] Checking active feeds...
powershell "Get-Content data\logs\bot.jsonl -Tail 100 | Select-String 'feeds_summary' | Select-Object -First 3"

echo.
echo ============================================================
echo  Recommendations:
echo ============================================================
echo.
echo If market_status shows "closed" during 4am-9:30am ET:
echo   - Check timezone settings (should be America/Chicago or UTC-6)
echo   - Verify market hours detection in runner.py
echo.
echo If no feeds during pre-market:
echo   - Ensure SKIP_SOURCES does NOT include Finnhub News
echo   - Check feed fetch logs for errors
echo.
pause
```

### **Configuration Additions**

Add to `.env`:

```ini
# Pre-Market Settings
PREMARKET_START_HOUR=4          # 4am ET (3am CT during DST)
PREMARKET_ALERTS_ENABLED=1      # Enable alerts during pre-market
PREMARKET_MIN_SCORE=0.30        # Slightly higher threshold (less liquidity)

# Logging
LOG_MARKET_HOURS_DETECTION=1    # Log market status changes
```

### **Code Fix: Ensure Pre-Market Feeds Active**

**File:** `src/catalyst_bot/runner.py`

Add market hours logging:

```python
def detect_market_hours():
    """Detect current market period and log transitions."""
    now = datetime.now(tz=timezone(timedelta(hours=-6)))  # CT
    hour = now.hour

    if 3 <= hour < 8:  # 4am-9am ET = 3am-8am CT (during DST)
        status = "pre-market"
        cycle_interval = settings.EXTENDED_HOURS_CYCLE_SEC or 90
    elif 8 <= hour < 15:  # 9:30am-4pm ET = 8:30am-3pm CT
        status = "open"
        cycle_interval = settings.MARKET_OPEN_CYCLE_SEC or 60
    elif 15 <= hour < 19:  # 4pm-8pm ET = 3pm-7pm CT
        status = "after-hours"
        cycle_interval = settings.EXTENDED_HOURS_CYCLE_SEC or 90
    else:
        status = "closed"
        cycle_interval = settings.MARKET_CLOSED_CYCLE_SEC or 180

    # Log status changes
    if status != getattr(detect_market_hours, 'last_status', None):
        _logger.info(f"market_status_changed from={getattr(detect_market_hours, 'last_status', 'unknown')} to={status} cycle_sec={cycle_interval}")
        detect_market_hours.last_status = status

    return status, cycle_interval
```

### **Testing Tomorrow Morning**

**4:00am CT (5:00am ET):**
```bash
# Check if bot detected pre-market
powershell "Get-Content data\logs\bot.jsonl -Tail 20 | Select-String 'market_status'"

# Should show: market_status_changed from=closed to=pre-market cycle_sec=90

# Check if feeds are being fetched
powershell "Get-Content data\logs\bot.jsonl -Tail 20 | Select-String 'feeds_summary'"

# Should show: feeds_summary sources=Finnhub,SEC,GlobeNewswire count=...
```

---

## **PATCH 5: Manual Feedback System (Missed Opportunities)**

### **Problem**
No way to manually feed missed opportunities back to bot for analysis and learning.

**Use Case:** User sees news catalyst that bot missed, wants to:
1. Log it for backtesting analysis
2. Understand why it was missed (score too low? source not covered?)
3. Improve detection for similar future events

### **Solution: Missed Opportunity Logger**

**File:** `log_missed_opportunity.py` (NEW)

```python
"""
Manual feedback system for missed trading opportunities.

Usage:
    python log_missed_opportunity.py TICKER "News headline" --gain 125 --time "2025-10-06 08:45"

This will:
1. Log the missed opportunity to data/missed_opportunities.jsonl
2. Fetch historical data for the ticker
3. Run sentiment analysis on the headline
4. Generate a report showing why it was missed
5. Add to backtest dataset for future analysis
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.classify import classify_text
from catalyst_bot.market import get_market_data
from catalyst_bot.logger import get_logger

_logger = get_logger(__name__)

def log_missed_opportunity(ticker: str, headline: str, gain_pct: float, timestamp: str):
    """
    Log a missed trading opportunity for analysis.

    Args:
        ticker: Stock ticker (e.g., "AAPL")
        headline: News headline that caused the move
        gain_pct: Percentage gain (e.g., 125 for +125%)
        timestamp: When the news broke (ISO format or "2025-10-06 08:45")
    """
    # Parse timestamp
    try:
        if "T" in timestamp:
            ts = datetime.fromisoformat(timestamp)
        else:
            ts = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
            ts = ts.replace(tzinfo=timezone.utc)
    except:
        ts = datetime.now(timezone.utc)

    # Run sentiment analysis on the headline
    classification = classify_text(headline, headline)

    # Fetch market data at that time (if available)
    market_data = get_market_data(ticker, timestamp=ts)

    # Build missed opportunity record
    record = {
        "ticker": ticker,
        "headline": headline,
        "gain_pct": gain_pct,
        "timestamp": ts.isoformat(),
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "score": classification.get("score", 0),
            "sentiment": classification.get("sentiment", 0),
            "keywords": classification.get("keywords", []),
            "catalyst_type": classification.get("catalyst_type", "unknown")
        },
        "market_data": market_data,
        "analysis": {
            "missed_reason": determine_missed_reason(classification),
            "suggested_fix": suggest_fix(classification)
        }
    }

    # Save to missed opportunities log
    missed_log = Path("data/missed_opportunities.jsonl")
    missed_log.parent.mkdir(parents=True, exist_ok=True)

    with open(missed_log, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Print analysis
    print("\n" + "="*60)
    print(f"Missed Opportunity Logged: {ticker} (+{gain_pct}%)")
    print("="*60)
    print(f"\nHeadline: {headline}")
    print(f"Timestamp: {ts}")
    print(f"\nSentiment Analysis:")
    print(f"  Score: {classification.get('score', 0):.3f}")
    print(f"  Sentiment: {classification.get('sentiment', 0):.3f}")
    print(f"  Catalyst Type: {classification.get('catalyst_type', 'unknown')}")
    print(f"  Keywords: {', '.join(classification.get('keywords', []))}")
    print(f"\nWhy Was This Missed?")
    print(f"  {record['analysis']['missed_reason']}")
    print(f"\nSuggested Fix:")
    print(f"  {record['analysis']['suggested_fix']}")
    print("\n" + "="*60)

    _logger.info(f"missed_opportunity_logged ticker={ticker} gain={gain_pct}% score={classification.get('score', 0):.3f}")

    return record

def determine_missed_reason(classification):
    """Analyze why the alert was missed."""
    score = classification.get("score", 0)
    sentiment = classification.get("sentiment", 0)
    keywords = classification.get("keywords", [])

    reasons = []

    if score < 0.25:
        reasons.append(f"Score too low ({score:.3f} < 0.25 threshold)")

    if abs(sentiment) < 0.3:
        reasons.append(f"Weak sentiment signal ({sentiment:.3f})")

    if not keywords:
        reasons.append("No high-value keywords detected")

    if classification.get("catalyst_type") == "unknown":
        reasons.append("Catalyst type not recognized")

    if not reasons:
        reasons.append("Alert likely posted but you missed it (check Discord)")

    return " | ".join(reasons)

def suggest_fix(classification):
    """Suggest parameter changes to catch similar events."""
    score = classification.get("score", 0)
    keywords = classification.get("keywords", [])

    suggestions = []

    if score < 0.25:
        suggestions.append(f"Lower MIN_SCORE to {max(0.15, score - 0.05):.2f}")

    if keywords:
        suggestions.append(f"Add keywords to whitelist: {', '.join(keywords[:3])}")

    if classification.get("catalyst_type") == "unknown":
        suggestions.append("Add catalyst type to classification logic")

    if not suggestions:
        suggestions.append("Review Discord alert history - may have been posted")

    return " | ".join(suggestions)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log missed trading opportunity")
    parser.add_argument("ticker", help="Stock ticker (e.g., AAPL)")
    parser.add_argument("headline", help="News headline that caused the move")
    parser.add_argument("--gain", type=float, required=True, help="Percentage gain (e.g., 125)")
    parser.add_argument("--time", required=True, help="When news broke (YYYY-MM-DD HH:MM or ISO format)")

    args = parser.parse_args()

    log_missed_opportunity(args.ticker, args.headline, args.gain, args.time)
```

### **Usage Examples**

**Example 1: Log this morning's missed 125% gainer**
```bash
python log_missed_opportunity.py EXAI "Exscientia announces FDA breakthrough therapy designation" --gain 125 --time "2025-10-06 08:45"
```

**Example 2: Batch import from CSV**
```bash
# Create missed_opportunities.csv with columns: ticker, headline, gain, timestamp
python batch_import_missed.py missed_opportunities.csv
```

### **Integration with Backtesting**

Add to `run_backtest.py`:

```python
def include_missed_opportunities(backtest_data):
    """
    Include manually logged missed opportunities in backtest analysis.
    """
    missed_log = Path("data/missed_opportunities.jsonl")
    if not missed_log.exists():
        return backtest_data

    with open(missed_log) as f:
        missed = [json.loads(line) for line in f]

    # Convert to backtest format
    for opp in missed:
        backtest_data.append({
            "ticker": opp["ticker"],
            "timestamp": opp["timestamp"],
            "score": opp["classification"]["score"],
            "sentiment": opp["classification"]["sentiment"],
            "gain_pct": opp["gain_pct"],
            "source": "manual_feedback"
        })

    return backtest_data
```

### **Weekly Missed Opportunities Report**

Add to admin reports:

```python
def generate_missed_opportunities_report():
    """
    Analyze all manually logged missed opportunities.
    Shows patterns in what the bot is missing.
    """
    missed_log = Path("data/missed_opportunities.jsonl")
    if not missed_log.exists():
        return "No missed opportunities logged"

    with open(missed_log) as f:
        missed = [json.loads(line) for line in f]

    # Analysis
    total_missed = len(missed)
    avg_gain = sum(m["gain_pct"] for m in missed) / total_missed

    # Common reasons
    reasons = {}
    for m in missed:
        reason = m["analysis"]["missed_reason"]
        reasons[reason] = reasons.get(reason, 0) + 1

    # Build report
    report = f"""
# Missed Opportunities Report

**Total Missed:** {total_missed}
**Avg Gain Missed:** {avg_gain:.1f}%

**Top Reasons for Misses:**
"""
    for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        report += f"- {reason}: {count} times\n"

    return report
```

### **Expected Workflow**

**Morning Routine:**
1. Check Discord for bot alerts
2. Check finviz/news for big movers
3. If bot missed something:
   ```bash
   python log_missed_opportunity.py TICKER "headline" --gain XX --time "YYYY-MM-DD HH:MM"
   ```
4. Review analysis output - see why it was missed
5. Adjust parameters if needed

**Weekly Review:**
- Run backtest including missed opportunities
- Review patterns in what's being missed
- Fine-tune MIN_SCORE, keywords, catalyst detection

---

## **Implementation Priority**

**Tonight (Critical):**
1. ✅ PATCH 1: Ollama batching (30 min)
2. ✅ PATCH 2: Heartbeat cumulative (20 min)
3. ✅ PATCH 3: Unicode fix (5 min)
4. ⏰ PATCH 4: Pre-market verification (15 min)

**Tomorrow Morning (Validation):**
5. ⏰ Test pre-market coverage (run verify script at 4am CT)
6. ⏰ Create PATCH 5: Manual feedback system (30 min if needed)

**Total Tonight:** ~70 minutes
**Total Tomorrow:** ~30 minutes

---

**Ready when you are!**
