# LLM Stability & Optimization Roadmap
**Date:** October 6, 2025
**Focus:** Make local Ollama/Mistral bulletproof for production

---

## 🎯 **KEY INSIGHT: LLM as Final Approval, Not First Filter**

**Current Problem:**
- Sending all 136 items → Mistral (GPU overload)
- LLM processing low-quality noise
- Wasting compute on items that won't alert anyway

**New Architecture:**
```
136 items → Price filter → Keyword filter → VADER+FinBERT → Score >= 0.20?
                                                                    ↓
                                                    YES → Send to Mistral (final approval)
                                                    NO  → Skip LLM (save GPU)
```

**Impact:**
- 136 items → ~15-25 LLM calls (70-85% reduction)
- Only high-quality candidates get expensive LLM analysis
- LLM becomes "confirmation" step, not discovery step
- Faster cycles, lower GPU load, same or better accuracy

---

## 📊 **Brainstorming: All Stability Features**

### **Category 1: Smart Pre-Filtering**
1. ✅ **Score-based gating**: Only send items with prescale >= 0.20
2. ✅ **Watchlist priority**: Always send watchlist tickers to LLM
3. ✅ **SEC filing priority**: Always send SEC filings (high-value analysis)
4. ⚡ **Market hours logic**: Skip LLM during closed market (lower urgency)
5. ⚡ **Top-N selection**: Only send top 20 items per cycle
6. ⚡ **Duplicate detection**: Skip LLM if similar headline processed recently

### **Category 2: Retry & Error Handling**
7. ✅ **Exponential backoff**: Retry with 2s, 4s, 6s delays on 500 errors
8. ✅ **Max retry count**: 3 attempts before giving up
9. ✅ **Timeout handling**: Graceful timeout, retry once
10. ⚡ **Connection pooling**: Reuse HTTP connections
11. ⚡ **Circuit breaker**: Auto-disable LLM after 10 consecutive failures
12. ⚡ **Graceful degradation**: Continue with 3 sources when LLM fails

### **Category 3: Batching & Rate Limiting**
13. ✅ **Batch processing**: Process 5 items at a time
14. ✅ **Inter-batch delay**: 2 second pause between batches
15. ⚡ **Adaptive batch size**: Reduce to 2 items if Ollama struggling
16. ⚡ **Queue depth monitoring**: Pause if Ollama queue > 5 requests
17. ⚡ **Max LLM calls per cycle**: Hard cap at 30 calls/cycle

### **Category 4: Caching**
18. ✅ **Hash-based caching**: Cache identical prompts (PR blasts)
19. ✅ **TTL expiration**: 1 hour cache lifetime
20. ⚡ **Persistent cache**: Survive bot restarts (Redis/SQLite)
21. ⚡ **Cache size limits**: Max 1000 entries, LRU eviction
22. ⚡ **Cache hit metrics**: Track cache effectiveness

### **Category 5: Health Monitoring**
23. ✅ **Pre-flight check**: Ping Ollama before processing
24. ✅ **GPU warmup**: Send "OK" prompt on bot startup
25. ⚡ **Health endpoint polling**: Check `/api/tags` every 5 min
26. ⚡ **Response time tracking**: Alert if avg > 10 seconds
27. ⚡ **Success rate monitoring**: Alert if success < 80%
28. ⚡ **Auto-disable on failure**: Disable LLM if health check fails 3x

### **Category 6: GPU Optimization**
29. ⚡ **Model quantization**: Use smaller Mistral (7B → 4B quantized)
30. ⚡ **Context window tuning**: Reduce to 2048 tokens (faster inference)
31. ⚡ **Temperature setting**: Lock to 0.3 for consistent sentiment
32. ⚡ **Parallel requests**: Set `num_parallel=2` in Ollama
33. ⚡ **GPU memory limit**: Reserve 6GB for Mistral, rest for system

### **Category 7: Progressive/Async Processing**
34. ⚡ **Post alerts immediately**: Send Discord alert with 3 sources first
35. ⚡ **Update with LLM later**: Edit embed with 4th source after LLM
36. ⚡ **Background queue**: Process LLM in separate thread
37. ⚡ **Non-blocking calls**: Don't wait for LLM during cycle

### **Category 8: Auto-Recovery**
38. ⚡ **Ollama crash detection**: Check if service died
39. ⚡ **Auto-restart service**: `net start Ollama` on Windows
40. ⚡ **Startup health check**: Verify Ollama running before cycle
41. ⚡ **Fallback mode logging**: Track when running without LLM

### **Category 9: Observability**
42. ⚡ **LLM call metrics**: Count calls, successes, failures per cycle
43. ⚡ **Response time percentiles**: p50, p95, p99 latencies
44. ⚡ **Cache hit rate**: % of requests served from cache
45. ⚡ **GPU utilization**: Log GPU memory/compute usage
46. ⚡ **Admin summary**: LLM stats in heartbeat embed

### **Category 10: Multi-LLM Router (Future)**
47. 🔮 **Anthropic fallback**: Use Claude Haiku when Ollama fails
48. 🔮 **Gemini fallback**: Use Gemini Flash as third tier
49. 🔮 **Cost tracking**: Monitor API spend
50. 🔮 **Provider selection**: Route based on task priority

---

## 🌊 **PATCH WAVES - Organized by Priority**

### **🔴 WAVE 1: Critical Stability (RECOMMEND TONIGHT)**
**Goal:** Make Ollama work reliably without crashes
**Time:** 45-60 minutes
**Impact:** Eliminates 500 errors, reduces load by 75%

#### Patches:
1. **PATCH 1.1: Pre-Filtering (Smart Selection)**
   - Only send items with `prescale_score >= 0.20` to LLM
   - Always send watchlist tickers
   - Always send SEC filings
   - Log: "LLM pre-filter: 15/136 items qualified"

2. **PATCH 1.2: Retry Logic**
   - Add exponential backoff (2s, 4s, 6s)
   - Max 3 retries
   - Timeout handling
   - Fix Unicode bug (line 135)

3. **PATCH 1.3: Basic Batching**
   - Process 5 items at a time
   - 2 second delay between batches
   - Log batch progress

4. **PATCH 1.4: Health Check**
   - Ping Ollama before processing
   - GPU warmup on bot startup
   - Skip LLM if health check fails

**Files Changed:**
- `src/catalyst_bot/llm_client.py` (retry logic)
- `src/catalyst_bot/classify.py` or wherever LLM is called (pre-filtering)
- `src/catalyst_bot/runner.py` (health check on startup)
- `.env` (config)

**Config (.env):**
```ini
# Wave 1: Critical Stability
LLM_MAX_RETRIES=3
LLM_RETRY_DELAY=2.0
LLM_PRESCALE_MIN=0.20         # Only send items scoring >= 0.20
LLM_BATCH_SIZE=5
LLM_BATCH_DELAY=2.0
LLM_WARMUP_ENABLED=1
LLM_HEALTH_CHECK_ENABLED=1
```

---

### **🟡 WAVE 2: Performance & Caching (OPTIONAL TONIGHT)**
**Goal:** Speed up LLM, reduce duplicate calls
**Time:** 30-40 minutes
**Impact:** 30-50% faster cycles, cache hits on PR blasts

#### Patches:
5. **PATCH 2.1: Result Caching**
   - Hash prompt → cache response
   - 1 hour TTL
   - Max 1000 entries
   - LRU eviction

6. **PATCH 2.2: Adaptive Batch Sizing**
   - Check Ollama health before batch
   - Healthy = 5 items/batch
   - Struggling = 2 items/batch
   - Down = 0 (skip LLM)

7. **PATCH 2.3: Connection Pooling**
   - Reuse HTTP sessions
   - Keep-alive connections
   - Reduce overhead

**Files Changed:**
- `src/catalyst_bot/llm_client.py` (caching, adaptive batching)

**Config (.env):**
```ini
# Wave 2: Performance & Caching
LLM_CACHE_ENABLED=1
LLM_CACHE_TTL=3600            # 1 hour
LLM_CACHE_MAX_SIZE=1000
LLM_ADAPTIVE_BATCH=1          # Auto-adjust batch size
```

---

### **🟢 WAVE 3: Advanced Resilience (TOMORROW/OPTIONAL)**
**Goal:** Zero downtime, progressive alerts
**Time:** 60-90 minutes
**Impact:** Alerts post instantly, LLM fills in later

#### Patches:
8. **PATCH 3.1: Progressive Alerts**
   - Post Discord alert with 3 sources immediately
   - Queue item for LLM processing
   - Edit embed with 4th source when LLM completes
   - Non-blocking, faster alerts

9. **PATCH 3.2: Circuit Breaker**
   - Track consecutive LLM failures
   - Auto-disable after 10 failures
   - Re-enable after 10 minutes
   - Log degraded mode

10. **PATCH 3.3: Auto-Recovery**
    - Detect Ollama crash (connection refused)
    - Attempt restart via `net start Ollama` (Windows)
    - Wait 30s, retry health check
    - Log recovery attempts

11. **PATCH 3.4: Persistent Cache**
    - Store cache in SQLite (`data/llm_cache.db`)
    - Survive bot restarts
    - Share cache across runs
    - Expire old entries on startup

**Files Changed:**
- `src/catalyst_bot/alerts.py` (progressive posting)
- `src/catalyst_bot/llm_client.py` (circuit breaker, auto-recovery, persistent cache)

**Config (.env):**
```ini
# Wave 3: Advanced Resilience
LLM_PROGRESSIVE_ALERTS=1      # Post alerts immediately, LLM later
LLM_CIRCUIT_BREAKER=1
LLM_AUTO_RECOVERY=1
LLM_CACHE_PERSISTENT=1
LLM_CACHE_DB=data/llm_cache.db
```

---

### **🔵 WAVE 4: Multi-LLM Router (FUTURE)**
**Goal:** Fallback to cloud LLMs when Ollama fails
**Time:** 60 minutes
**Impact:** 99.9% uptime, zero single point of failure

#### Patches:
12. **PATCH 4.1: LLM Router**
    - Tier 1: Ollama (free)
    - Tier 2: Anthropic Haiku (fast, cheap)
    - Tier 3: Gemini Flash (backup)
    - Automatic fallback on failure

13. **PATCH 4.2: Provider-Specific Logic**
    - SEC filings → always Anthropic Sonnet (best quality)
    - High priority → Anthropic Haiku
    - Normal → Ollama → fallback

14. **PATCH 4.3: Cost Tracking**
    - Log API calls per provider
    - Track spend (tokens × price)
    - Alert if exceeding budget

**Files Changed:**
- `src/catalyst_bot/llm_router.py` (NEW)
- `src/catalyst_bot/classify.py` (use router instead of client)

**Config (.env):**
```ini
# Wave 4: Multi-LLM Router
LLM_ROUTER_ENABLED=1
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
LLM_FALLBACK_PROVIDER=anthropic
LLM_SEC_PROVIDER=anthropic   # Always use Sonnet for SEC
LLM_BUDGET_DAILY=5.00        # Max $5/day
```

---

### **🟣 WAVE 5: Observability (FUTURE)**
**Goal:** Monitor, measure, optimize
**Time:** 45 minutes
**Impact:** Data-driven decisions, catch issues early

#### Patches:
15. **PATCH 5.1: LLM Metrics**
    - Track calls, successes, failures per cycle
    - Response time p50/p95/p99
    - Cache hit rate
    - Log to `data/llm_metrics.jsonl`

16. **PATCH 5.2: Admin Dashboard**
    - Add LLM stats to heartbeat embed
    - Show cache efficiency
    - Alert on degraded mode
    - Include in `/admin stats` command

17. **PATCH 5.3: Performance Alerts**
    - Alert admin if LLM success rate < 80%
    - Alert if avg response time > 10s
    - Alert if GPU overload detected

**Files Changed:**
- `src/catalyst_bot/llm_metrics.py` (NEW)
- `src/catalyst_bot/alerts.py` (admin alerts)
- `src/catalyst_bot/runner.py` (metrics logging)

**Config (.env):**
```ini
# Wave 5: Observability
LLM_METRICS_ENABLED=1
LLM_METRICS_LOG=data/llm_metrics.jsonl
LLM_ALERT_THRESHOLD_SUCCESS=0.80   # Alert if < 80% success
LLM_ALERT_THRESHOLD_LATENCY=10.0   # Alert if > 10s avg
```

---

## 🎯 **RECOMMENDED IMPLEMENTATION PLAN**

### **Tonight (1.5-2 hours):**
✅ **WAVE 1** (Critical Stability) - 60 min
✅ **WAVE 2** (Performance & Caching) - 30 min

**Why:**
- Wave 1 fixes the immediate problem (GPU overload, 500 errors)
- Wave 2 optimizes what you just fixed (faster, smarter)
- Both are low-risk, high-impact
- You can test together tomorrow morning

**Implementation Order:**
1. PATCH 1.1: Pre-filtering (20 min) - **BIGGEST IMPACT**
2. PATCH 1.2: Retry logic (15 min)
3. PATCH 1.3: Basic batching (15 min)
4. PATCH 1.4: Health check (10 min)
5. PATCH 2.1: Caching (20 min)
6. PATCH 2.2: Adaptive batching (10 min)

**Testing Tomorrow:**
- Run full cycle, monitor logs
- Check cache hit rate
- Verify GPU not overloading
- Confirm 70-85% fewer LLM calls

### **Tomorrow Evening (Optional):**
⚡ **WAVE 3** (Advanced Resilience) - 90 min

**Only if needed:**
- If you see Ollama still struggling
- If you want progressive alerts (faster to Discord)

### **Next Week (Optional):**
🔮 **WAVE 4** (Multi-LLM Router) - 60 min
🔮 **WAVE 5** (Observability) - 45 min

---

## 📝 **Pre-Filtering Logic Deep Dive**

This is the **most important** change - here's exactly how it should work:

### **Current Flow (BAD):**
```python
# classify.py or wherever
for item in all_items:  # 136 items
    vader_score = get_vader(item)
    finbert_score = get_finbert(item)
    llm_score = query_llm(item)  # ❌ LLM called 136 times!

    final_score = combine(vader_score, finbert_score, llm_score)

    if final_score >= 0.25:
        post_alert(item)
```

### **New Flow (GOOD):**
```python
# classify.py or wherever
for item in all_items:  # 136 items
    vader_score = get_vader(item)
    finbert_score = get_finbert(item)

    # Prescale = VADER + FinBERT only (cheap, fast)
    prescale_score = combine(vader_score, finbert_score)
    item["prescale_score"] = prescale_score

    # Pre-filter: Only high-scoring items get LLM
    if prescale_score >= 0.20:  # ✅ ~15-25 items qualify
        llm_score = query_llm(item)
        final_score = combine(vader_score, finbert_score, llm_score)
    else:
        llm_score = None  # Skip expensive LLM
        final_score = prescale_score

    if final_score >= 0.25:
        post_alert(item)
```

### **Special Cases:**
```python
# Always send these to LLM regardless of prescale:
if item.get("ticker") in watchlist_tickers:
    llm_score = query_llm(item)  # Watchlist = always analyze

if item.get("source") in ["SEC-8K", "SEC-424B5", "SEC-FWP"]:
    llm_score = query_llm(item)  # SEC filings = always analyze

# Market hours logic (optional):
if market_status == "closed" and prescale_score < 0.30:
    llm_score = None  # Skip marginal items during off-hours
```

### **Logging:**
```python
_logger.info(
    f"llm_prefilter total={len(all_items)} "
    f"qualified={len(items_for_llm)} "
    f"watchlist={watchlist_count} "
    f"sec_filings={sec_count} "
    f"reduction={100*(1-len(items_for_llm)/len(all_items)):.1f}%"
)

# Example output:
# llm_prefilter total=136 qualified=18 watchlist=3 sec_filings=2 reduction=86.8%
```

---

## 🧪 **Testing Strategy**

After implementing Wave 1 + 2 tonight:

### **Test 1: Pre-Filtering Works**
```bash
python -m catalyst_bot.runner --once
```

Check logs:
```bash
powershell "Get-Content data/logs/bot.jsonl -Tail 100 | Select-String 'llm_prefilter'"
```

Should see:
```
llm_prefilter total=136 qualified=15 reduction=89.0%
```

### **Test 2: Retry Logic Works**
Stop Ollama mid-cycle, should see:
```
Ollama overloaded (500), attempt 1/3
Ollama overloaded (500), attempt 2/3
Ollama overloaded (500), attempt 3/3
Ollama failed after retries, returning None
```

Then bot continues with 3 sources instead of crashing.

### **Test 3: Cache Works**
Run 2 cycles back-to-back:
```bash
python -m catalyst_bot.runner --once
python -m catalyst_bot.runner --once
```

Second run should show cache hits:
```
llm_cache_hit prompt=abc123... count=5
```

### **Test 4: Batching Works**
Check logs for batch progress:
```
Processing LLM batch 1/3 (5 items)
Processing LLM batch 2/3 (5 items)
Processing LLM batch 3/3 (5 items)
```

### **Test 5: Health Check Works**
Stop Ollama before running bot:
```
llm_health_check status=failed error=ConnectionError
llm_disabled_for_cycle reason=health_check_failed
CYCLE_DONE llm_calls=0
```

Bot completes successfully without LLM.

---

## 💾 **Configuration Summary**

Add to `.env` (Wave 1 + 2):

```ini
# ============================================================
# LLM Stability & Performance (Wave 1 + 2)
# ============================================================

# Feature Flags
FEATURE_LLM_CLASSIFIER=1
FEATURE_LLM_FALLBACK=1
FEATURE_LLM_SEC_ANALYSIS=1

# Pre-Filtering (Wave 1.1)
LLM_PRESCALE_MIN=0.20         # Only send items scoring >= 0.20
LLM_WATCHLIST_ALWAYS=1        # Always analyze watchlist tickers
LLM_SEC_ALWAYS=1              # Always analyze SEC filings

# Retry Logic (Wave 1.2)
LLM_MAX_RETRIES=3             # Retry 3 times on failure
LLM_RETRY_DELAY=2.0           # Base delay: 2s, 4s, 6s (exponential)
LLM_TIMEOUT_SECS=20           # Request timeout

# Batching (Wave 1.3)
LLM_BATCH_SIZE=5              # Process 5 items at a time
LLM_BATCH_DELAY=2.0           # 2 second pause between batches

# Health Checks (Wave 1.4)
LLM_WARMUP_ENABLED=1          # Send warmup query on startup
LLM_HEALTH_CHECK_ENABLED=1    # Ping Ollama before processing

# Caching (Wave 2.1)
LLM_CACHE_ENABLED=1           # Enable result caching
LLM_CACHE_TTL=3600            # Cache lifetime: 1 hour
LLM_CACHE_MAX_SIZE=1000       # Max cached entries

# Adaptive Batching (Wave 2.2)
LLM_ADAPTIVE_BATCH=1          # Auto-adjust batch size based on health
LLM_BATCH_SIZE_MIN=2          # Reduce to 2 when struggling
LLM_BATCH_SIZE_MAX=5          # Max 5 when healthy

# Existing (keep these)
LLM_ENDPOINT_URL=http://127.0.0.1:11434/api/generate
LLM_MODEL_NAME=mistral
LLM_CONFIDENCE_THRESHOLD=0.6
```

---

## 🚀 **Quick Start: Implement Wave 1 + 2 Tonight**

Ready to implement? Here's the game plan:

1. **PATCH 1.1: Pre-filtering** (20 min)
   - Find where you call `query_llm()` in classification code
   - Add prescale calculation before LLM call
   - Only call LLM if prescale >= 0.20 OR watchlist OR SEC

2. **PATCH 1.2: Retry logic** (15 min)
   - Edit `llm_client.py:129-165`
   - Add retry loop with exponential backoff
   - Handle 500 errors, timeouts

3. **PATCH 1.3: Batching** (15 min)
   - Wrap LLM calls in batching logic
   - Process 5 at a time, 2s delay

4. **PATCH 1.4: Health check** (10 min)
   - Add warmup function to `runner.py`
   - Call on bot startup
   - Skip LLM if health check fails

5. **PATCH 2.1: Caching** (20 min)
   - Add cache dict to `llm_client.py`
   - Hash prompt → lookup cache
   - Store results with timestamp

6. **PATCH 2.2: Adaptive batching** (10 min)
   - Check Ollama health before batch
   - Adjust batch size dynamically

**Total: 90 minutes, rock-solid LLM**

---

**Want me to implement Wave 1 + 2 right now?** Or just Wave 1 (critical stability only)?
