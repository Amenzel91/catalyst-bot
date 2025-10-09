# Performance Optimization Guide

Complete guide to profiling and optimizing Catalyst-Bot performance.

---

## Quick Start: Profile Your Bot

```powershell
# Full profiling report (recommended first run)
python profile_performance.py --full

# Profile a single cycle
python profile_performance.py --cycle

# Monitor GPU continuously (run alongside bot)
python profile_performance.py --gpu
```

---

## Understanding the Results

### GPU Utilization

**Expected values**:
- **Without LLM**: 0-5% (VADER + matplotlib are CPU-only)
- **With LLM enabled**: 30-60% during inference
- **High utilization (>80%)**: LLM is bottleneck - enable batching

**What to do**:
```ini
# If GPU underutilized (<20%)
FEATURE_LLM_CLASSIFIER=1
FEATURE_LLM_FALLBACK=1
FEATURE_LLM_SEC_ANALYSIS=1

# If GPU overutilized (>80%)
LLM_BATCH_WORKERS=3  # Increase from default
LLM_CACHE_TTL=7200  # Cache longer (2 hours)
```

### Cycle Time

**Target**: <5 seconds per cycle
**Typical breakdown**:
- Feed fetching: 1-2s
- Classification: 0.5-1s
- Chart generation: 1-3s (biggest bottleneck)
- LLM calls: 2-5s each (if enabled)

**Optimizations**:
```ini
# If cycle time >10s
CHART_QUEUE_WORKERS=4  # Parallel chart generation
MAX_ALERTS_PER_CYCLE=5  # Reduce volume

# If network I/O is slow
SLEEP_SECONDS=90  # Increase cycle interval
```

### Memory Usage

**Expected**:
- Baseline: 200-400 MB
- With LLM (Mistral 7B): +4-6 GB GPU memory
- Peak during charts: +500 MB

**Red flags**:
- Memory leak (usage grows over time) → Check chart cleanup
- OOM errors → Reduce MAX_ALERTS_PER_CYCLE or CHART_QUEUE_WORKERS

---

## Optimization Strategies

### 1. LLM Batching

**When to use**: GPU utilization >60%, multiple LLM calls per cycle

**Enable**:
```ini
# .env
LLM_BATCH_WORKERS=3  # Number of concurrent LLM workers
LLM_CACHE_TTL=3600  # Cache responses for 1 hour
```

**Usage**:
```python
# OLD (blocking, sequential)
from catalyst_bot.llm_client import query_llm
response = query_llm(prompt)  # Blocks for 2-5s

# NEW (async, batched)
from catalyst_bot.llm_batch import submit_llm_request

def handle_response(response):
    if response:
        print(f"LLM response: {response}")

submit_llm_request(
    prompt="Analyze this filing...",
    priority=1,  # High priority
    callback=handle_response
)
# Returns immediately, callback invoked when ready
```

**Benefits**:
- Doesn't block main loop
- Automatic caching (avoid duplicate queries)
- Priority queuing (urgent requests first)

---

### 2. Chart Generation Queue

**When to use**: Chart generation >2s, multiple charts per cycle

**Enable**:
```ini
# .env
CHART_QUEUE_WORKERS=4  # Parallel chart workers
CHART_CACHE_TTL=300  # Cache for 5 minutes
```

**Usage**:
```python
# OLD (blocking, sequential)
from catalyst_bot.charts_advanced import generate_advanced_chart
chart_path = generate_advanced_chart("AAPL", "1D")  # Blocks for 2-3s

# NEW (async, queued)
from catalyst_bot.chart_queue import submit_chart_request

def handle_chart(chart_path):
    if chart_path:
        print(f"Chart ready: {chart_path}")

submit_chart_request(
    ticker="AAPL",
    timeframe="1D",
    priority=1,
    callback=handle_chart
)
# Returns immediately, callback invoked when ready
```

**Benefits**:
- Up to 4x faster with parallel workers
- Cache prevents redundant generation
- Main loop never blocks on charts

---

### 3. Sentiment Gauge Optimization

**Current**: Matplotlib generates gauge synchronously (500ms-1s)

**Optimization**: Pre-generate common sentiments, use lookup table

```python
# Pre-generate gauges for common values
sentiments = [-1.0, -0.5, 0.0, 0.5, 1.0]
for sentiment in sentiments:
    generate_sentiment_gauge(sentiment)  # Cache at startup

# Runtime: instant lookup instead of generation
```

**Implementation**: Add to `sentiment_gauge.py`:
```python
_GAUGE_CACHE = {}

def get_or_generate_gauge(sentiment: float) -> str:
    """Get cached gauge or generate new one."""
    # Round to nearest 0.1 for caching
    rounded = round(sentiment, 1)

    if rounded in _GAUGE_CACHE:
        return _GAUGE_CACHE[rounded]

    path = generate_sentiment_gauge(sentiment)
    _GAUGE_CACHE[rounded] = path
    return path
```

---

### 4. Feed Fetching Optimization

**Current**: Fetches all feeds sequentially

**Optimization**: Parallel fetching with timeout

```python
import concurrent.futures

def fetch_feeds_parallel():
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_finnhub_news): "finnhub",
            executor.submit(fetch_sec_8k): "sec_8k",
            executor.submit(fetch_globenewswire): "globenewswire",
        }

        results = []
        for future in concurrent.futures.as_completed(futures, timeout=10):
            try:
                items = future.result()
                results.extend(items)
            except Exception as e:
                log.warning(f"feed_fetch_failed source={futures[future]} err={e}")

        return results
```

**Benefits**: 3-5x faster feed fetching (2s → 0.5s)

---

## Configuration Reference

### Performance-Related Environment Variables

```ini
# LLM Batching
LLM_BATCH_WORKERS=3  # Number of concurrent LLM workers (default: 3)
LLM_CACHE_TTL=3600  # Cache TTL in seconds (default: 3600 = 1 hour)
LLM_TIMEOUT_SECS=20  # Individual request timeout (default: 20)

# Chart Generation
CHART_QUEUE_WORKERS=4  # Parallel chart workers (default: 4)
CHART_CACHE_TTL=300  # Chart cache TTL in seconds (default: 300 = 5 min)

# Alert Volume
MAX_ALERTS_PER_CYCLE=10  # Max alerts per cycle (default: 10)
SLEEP_SECONDS=60  # Cycle interval (default: 60)

# Network
FEEDS_TIMEOUT=15  # Feed fetch timeout (default: 15)
FEEDS_PARALLEL=1  # Enable parallel fetching (default: 0)
```

---

## Monitoring & Benchmarks

### Baseline Performance (No LLM)

**Hardware**: RTX 3060, 16GB RAM, SSD
```
Cycle time: 4.2s
├─ Feed fetching: 1.8s
├─ Classification: 0.6s
├─ Chart generation: 1.5s
└─ Alert posting: 0.3s

GPU utilization: 2%
Memory: 350 MB
```

### With LLM Enabled

```
Cycle time: 8.5s
├─ Feed fetching: 1.8s
├─ Classification: 0.6s
├─ LLM calls: 4.2s ⚠️ BOTTLENECK
├─ Chart generation: 1.6s
└─ Alert posting: 0.3s

GPU utilization: 45%
Memory: 5.2 GB (GPU), 450 MB (RAM)
```

### With Batching Enabled

```
Cycle time: 5.1s
├─ Feed fetching: 1.8s
├─ Classification: 0.6s
├─ LLM queued: <0.1s ✅ (async)
├─ Chart queued: <0.1s ✅ (async)
└─ Alert posting: 2.5s (includes waiting for charts)

GPU utilization: 55% (sustained)
Memory: 5.4 GB (GPU), 480 MB (RAM)

LLM queue stats:
├─ Requests: 12
├─ Cache hits: 8 (67%)
├─ Avg processing: 2.3s
└─ Workers busy: 3/3

Chart queue stats:
├─ Requests: 5
├─ Cache hits: 2 (40%)
├─ Avg generation: 1.4s
└─ Workers busy: 4/4
```

---

## Troubleshooting

### Problem: High GPU usage but slow LLM

**Cause**: Model is large or GPU is shared
**Solution**:
```ini
LLM_MODEL_NAME=llama3.2:1b  # Use smaller model
# Or reduce concurrent workers
LLM_BATCH_WORKERS=2
```

### Problem: Charts generation slow

**Cause**: Disk I/O or matplotlib overhead
**Solution**:
```ini
CHART_QUEUE_WORKERS=6  # More workers
QUICKCHART_IMAGE_DIR=/tmp/charts  # Use faster disk (SSD/RAM disk)
```

### Problem: Memory leak

**Cause**: Chart files not cleaned up
**Solution**: Add cleanup job
```python
# In runner.py, after each cycle
from pathlib import Path
import time

chart_dir = Path("out/charts")
cutoff = time.time() - 3600  # 1 hour ago

for chart_file in chart_dir.glob("*.png"):
    if chart_file.stat().st_mtime < cutoff:
        chart_file.unlink()  # Delete old charts
```

### Problem: GPU not detected

**Cause**: Driver issue or wrong Ollama config
**Solution**:
```bash
# Check GPU
nvidia-smi

# Restart Ollama with GPU
ollama serve

# Test GPU inference
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "test"
}'
```

---

## Advanced: Custom Profiling

### Profile Specific Function

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here
from catalyst_bot.charts_advanced import generate_advanced_chart
generate_advanced_chart("AAPL", "1D")

profiler.disable()

stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

### Memory Profiling

```python
from memory_profiler import profile

@profile
def my_function():
    # Your code here
    pass
```

### GPU Profiling (Advanced)

```bash
# Nsight Systems (Nvidia's profiler)
nsys profile python -m catalyst_bot.runner --once

# Output: report.qdrep (open in Nsight Systems GUI)
```

---

## Optimization Checklist

- [ ] Run `python profile_performance.py --full`
- [ ] Check GPU utilization (<20% = underused, >80% = saturated)
- [ ] Measure cycle time (target: <5s)
- [ ] Enable LLM batching if LLM calls >2s per cycle
- [ ] Enable chart queue if chart gen >2s per cycle
- [ ] Set `MAX_ALERTS_PER_CYCLE` based on throughput needs
- [ ] Monitor memory usage over 24 hours (check for leaks)
- [ ] Benchmark before/after optimizations

---

## Next Steps

1. **Profile your bot**: `python profile_performance.py --full`
2. **Identify bottleneck**: Charts? LLM? Network?
3. **Enable batching**: Add config to `.env`
4. **Re-profile**: Measure improvement
5. **Iterate**: Tune worker counts, cache TTLs

Target: <5s cycle time, <60% GPU utilization, 0 memory leaks

---

**Questions?** Check logs for `llm_batch` and `chart_queue` entries to see batching in action.