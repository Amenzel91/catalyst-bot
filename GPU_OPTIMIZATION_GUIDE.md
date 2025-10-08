# GPU Optimization Guide - WAVE 2.2

**Implementation Date:** October 6, 2025
**Status:** Ready for Testing
**Estimated GPU Reduction:** 60-85%

---

## Overview

This guide provides instructions for implementing WAVE 2.2 GPU fine-tuning optimizations in Catalyst-Bot. The optimizations include model profiling, batch processing, lightweight model alternatives, and memory management.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Profiling Instructions](#profiling-instructions)
3. [Implementation Steps](#implementation-steps)
4. [Configuration Reference](#configuration-reference)
5. [Testing & Validation](#testing--validation)
6. [Expected Improvements](#expected-improvements)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Immediate Actions (30 minutes)

**Step 1: Enable GPU Memory Cleanup**
```ini
# In .env
GPU_MEMORY_CLEANUP=1
```

**Expected Impact:** 15-20% VRAM reduction through automatic cleanup

**Step 2: Increase Batch Size**
```ini
# In .env
SENTIMENT_BATCH_SIZE=20  # Increase from 10
```

**Expected Impact:** 30-40% faster sentiment scoring

**Step 3: Profile Current Performance**
```bash
python -m catalyst_bot.gpu_profiler --mode full --output-dir out/profiling
```

**Output:** Baseline GPU profiling report in `out/profiling/gpu_profile_YYYYMMDD_HHMMSS.json`

---

## Profiling Instructions

### 1. Sentiment Model Profiling

**Profile current FinBERT model:**
```bash
python -m catalyst_bot.gpu_profiler --mode sentiment --sentiment-model finbert
```

**Profile DistilBERT alternative:**
```bash
python -m catalyst_bot.gpu_profiler --mode sentiment --sentiment-model distilbert
```

**Profile VADER (CPU-only):**
```bash
python -m catalyst_bot.gpu_profiler --mode sentiment --sentiment-model vader
```

**Output:**
```
Sentiment Model: finbert
  Load time: 1243.56 ms
  Single item inference: 18.32 ms
  Throughput: 54.58 items/sec
  VRAM used: 847.23 MB
  Best speedup: 3.45x at batch_size=20
```

**Interpretation:**
- **Load time:** One-time cost (cached after first load)
- **Throughput:** Items scored per second
- **Speedup:** Improvement from batching vs single-item processing
- **VRAM used:** Memory consumed by model

---

### 2. LLM Profiling

**Profile Ollama/Mistral LLM:**
```bash
python -m catalyst_bot.gpu_profiler --mode llm
```

**Output:**
```
LLM Model: mistral
  Average inference: 1852.41 ms
  Throughput: 12.34 tokens/sec
  VRAM used: 4096.00 MB
```

**Interpretation:**
- High VRAM usage indicates LLM is the primary GPU consumer
- Low tokens/sec suggests opportunity for batching or parallel execution

---

### 3. Full System Profiling

**Profile all models:**
```bash
python -m catalyst_bot.gpu_profiler --mode full
```

**Output:** JSON report in `out/profiling/gpu_profile_YYYYMMDD_HHMMSS.json`

**Report includes:**
- System GPU stats (VRAM, temperature, utilization)
- Sentiment model metrics
- LLM metrics
- Batch speedup analysis
- Recommendations

**Example report structure:**
```json
{
  "generated_at": "2025-10-06T12:34:56",
  "system_info": {
    "used_mb": 1234.5,
    "total_mb": 12288.0,
    "utilization_pct": 10.05
  },
  "results": [
    {
      "model_name": "finbert",
      "model_type": "sentiment",
      "load_time_ms": 1243.56,
      "inference_time_ms": 18.32,
      "items_per_second": 54.58,
      "vram_used_mb": 847.23,
      "batch_results": [
        {"batch_size": 1, "avg_time_ms": 18.32, "items_per_second": 54.58, "speedup_vs_1": 1.0},
        {"batch_size": 5, "avg_time_ms": 62.15, "items_per_second": 80.45, "speedup_vs_1": 1.47},
        {"batch_size": 10, "avg_time_ms": 115.33, "items_per_second": 86.71, "speedup_vs_1": 1.59},
        {"batch_size": 20, "avg_time_ms": 231.67, "items_per_second": 86.34, "speedup_vs_1": 1.58}
      ],
      "notes": "Best speedup: 1.59x at batch_size=10"
    }
  ]
}
```

---

## Implementation Steps

### Phase 1: Baseline and Profiling (1 hour)

**1.1 Profile Current State**
```bash
# Profile sentiment model
python -m catalyst_bot.gpu_profiler --mode sentiment --sentiment-model finbert

# Profile LLM
python -m catalyst_bot.gpu_profiler --mode llm

# Save baseline report
python -m catalyst_bot.gpu_profiler --mode full --output-dir out/profiling/baseline
```

**1.2 Document Baseline Metrics**
- Record current VRAM usage
- Record cycle time
- Record GPU temperature
- Record items/sec throughput

**Example baseline:**
```
Baseline Metrics (before optimization):
- VRAM usage: 1200 MB average
- Cycle time: 45 seconds
- GPU temperature: 68°C
- Sentiment throughput: 55 items/sec
- LLM throughput: 12 tokens/sec
```

---

### Phase 2: Enable Basic Optimizations (30 minutes)

**2.1 Update .env Configuration**
```ini
# Enable GPU memory cleanup
GPU_MEMORY_CLEANUP=1

# Enable batch sentiment scoring
SENTIMENT_BATCH_SIZE=10

# Enable GPU monitoring
GPU_PROFILING_ENABLED=0  # Keep disabled in production
GPU_MAX_UTILIZATION_WARN=90
```

**2.2 Test Basic Optimizations**
```bash
# Run one cycle
python -m catalyst_bot.runner --once

# Check GPU usage
python -c "from catalyst_bot.gpu_monitor import log_gpu_stats; log_gpu_stats()"
```

**Expected improvements:**
- 15-20% VRAM reduction
- Slightly faster cycles

---

### Phase 3: Implement Batch Processing (1 hour)

**3.1 Integrate BatchSentimentScorer**

Edit your sentiment scoring code (likely in `src/catalyst_bot/classifier.py` or similar):

**Before (individual scoring):**
```python
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

for item in items:
    score = analyzer.polarity_scores(item['title'])
    item['sentiment'] = score['compound']
```

**After (batch scoring):**
```python
from catalyst_bot.ml.batch_sentiment import BatchSentimentManager
from catalyst_bot.ml.model_switcher import load_sentiment_model

# Load model once
model = load_sentiment_model()  # Uses SENTIMENT_MODEL_NAME from .env

# Create batch manager
batch_manager = BatchSentimentManager.from_env(model)

# Collect items
for item in items:
    batch_manager.score_or_queue(item['title'], item)

# Flush remaining items and apply scores
batch_manager.flush_and_apply(items)

# Now all items have sentiment scores
for item in items:
    sentiment = item.get('sentiment_score', 0.0)
```

**3.2 Test Batch Processing**
```bash
# Run with batch processing
python -m catalyst_bot.runner --once

# Profile improvement
python -m catalyst_bot.gpu_profiler --mode sentiment
```

**Expected improvements:**
- 30-50% faster sentiment scoring
- Better GPU utilization

---

### Phase 4: Switch to Lightweight Model (30 minutes)

**4.1 Test DistilBERT**
```bash
# Profile DistilBERT
python -m catalyst_bot.gpu_profiler --mode sentiment --sentiment-model distilbert

# Compare with FinBERT
python -c "
from catalyst_bot.ml.model_switcher import compare_models
results = compare_models(['finbert', 'distilbert', 'vader'])
import json
print(json.dumps(results, indent=2))
"
```

**4.2 Update Configuration**
```ini
# In .env
SENTIMENT_MODEL_NAME=distilbert
SENTIMENT_BATCH_SIZE=20  # DistilBERT handles larger batches
```

**4.3 Validate Accuracy**

Run bot for 1-2 hours and compare alert quality:
```bash
# Monitor alerts
tail -f data/logs/bot.jsonl | grep "alert_sent"

# Check for unexpected behavior
# - More false positives?
# - Missing important alerts?
# - Sentiment scores drastically different?
```

**Expected improvements:**
- 50% VRAM reduction (400 MB vs 800 MB)
- 2x faster sentiment scoring
- 5-7% accuracy reduction (acceptable)

---

### Phase 5: Adaptive Model Selection (1 hour)

**5.1 Implement Time-Based Switching**

Create `src/catalyst_bot/ml/adaptive_sentiment.py`:
```python
import os
from catalyst_bot.ml.model_switcher import load_sentiment_model

def get_adaptive_sentiment_model():
    """Get sentiment model based on market hours."""
    from catalyst_bot.config import get_market_status

    if not int(os.getenv("FEATURE_ADAPTIVE_SENTIMENT", "0")):
        # Adaptive mode disabled, use static model
        return load_sentiment_model()

    status = get_market_status()

    if status in ["open", "extended"]:
        model_name = os.getenv("SENTIMENT_MODEL_OPEN", "distilbert")
    else:  # closed
        model_name = os.getenv("SENTIMENT_MODEL_CLOSED", "vader")

    return load_sentiment_model(model_name)
```

**5.2 Update Configuration**
```ini
# In .env
FEATURE_ADAPTIVE_SENTIMENT=1
SENTIMENT_MODEL_OPEN=distilbert
SENTIMENT_MODEL_CLOSED=vader
```

**5.3 Test Adaptive Switching**
```bash
# Test during market hours
python -c "
from catalyst_bot.ml.adaptive_sentiment import get_adaptive_sentiment_model
model = get_adaptive_sentiment_model()
print(f'Model: {type(model).__name__}')
"
```

**Expected improvements:**
- 75% average GPU reduction across 24 hours
- Zero GPU usage during market closed hours
- Maintains accuracy during market hours

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTIMENT_MODEL_NAME` | `finbert` | Sentiment model: `vader`, `finbert`, `distilbert`, `roberta` |
| `SENTIMENT_BATCH_SIZE` | `10` | Batch size for sentiment scoring (higher = faster) |
| `GPU_MEMORY_CLEANUP` | `1` | Enable automatic GPU memory cleanup |
| `GPU_PROFILING_ENABLED` | `0` | Log GPU stats each cycle (debug only) |
| `GPU_MAX_UTILIZATION_WARN` | `90` | Warning threshold for GPU utilization (%) |
| `GPU_MAX_TEMPERATURE_C` | `85` | Warning threshold for GPU temperature (°C) |
| `GPU_MIN_FREE_VRAM_MB` | `500` | Warning threshold for free VRAM (MB) |
| `FEATURE_CUDA_STREAMS` | `0` | Enable parallel CUDA streams (advanced) |
| `FEATURE_ADAPTIVE_SENTIMENT` | `0` | Enable time-based model switching |
| `SENTIMENT_MODEL_OPEN` | `distilbert` | Model for market hours |
| `SENTIMENT_MODEL_CLOSED` | `vader` | Model for market closed |

---

## Testing & Validation

### Unit Tests

**Test batch processing:**
```bash
pytest tests/test_batch_sentiment.py -v
```

**Test model switcher:**
```bash
pytest tests/test_model_switcher.py -v
```

**Test GPU monitor:**
```bash
pytest tests/test_gpu_monitor.py -v
```

### Integration Tests

**Test full cycle with optimizations:**
```bash
# Run single cycle
python -m catalyst_bot.runner --once

# Check logs for GPU stats
grep "GPU" data/logs/bot.jsonl | tail -20
```

**Test adaptive switching:**
```bash
# Force closed market status
MARKET_STATUS_OVERRIDE=closed python -m catalyst_bot.runner --once

# Check which model was used
grep "sentiment_model" data/logs/bot.jsonl | tail -5
```

### Load Testing

**Simulate high load:**
```bash
# Create 100 dummy items
python -c "
from catalyst_bot.ml.batch_sentiment import batch_score_texts
from catalyst_bot.ml.model_switcher import load_sentiment_model

model = load_sentiment_model('distilbert')
texts = ['Test headline ' + str(i) for i in range(100)]

import time
start = time.time()
results = batch_score_texts(texts, model, batch_size=20)
elapsed = time.time() - start

print(f'Scored {len(results)} items in {elapsed:.2f}s')
print(f'Throughput: {len(results)/elapsed:.2f} items/sec')
"
```

---

## Expected Improvements

### Phase 1: Basic Optimizations

**Configuration:**
- `GPU_MEMORY_CLEANUP=1`
- `SENTIMENT_BATCH_SIZE=10`

**Expected Impact:**
- VRAM: 15-20% reduction
- Speed: 10-15% faster cycles
- No accuracy impact

**Actual Results (measure after implementation):**
- VRAM: _____ MB → _____ MB (___% reduction)
- Cycle time: _____ sec → _____ sec
- GPU temp: _____ °C → _____ °C

---

### Phase 2: Batch Processing

**Configuration:**
- Integrated `BatchSentimentScorer`
- `SENTIMENT_BATCH_SIZE=20`

**Expected Impact:**
- VRAM: 20-25% reduction (better utilization)
- Speed: 30-50% faster sentiment scoring
- No accuracy impact

**Actual Results:**
- Sentiment scoring: _____ items/sec → _____ items/sec
- Cycle time: _____ sec → _____ sec

---

### Phase 3: Lightweight Model (DistilBERT)

**Configuration:**
- `SENTIMENT_MODEL_NAME=distilbert`
- `SENTIMENT_BATCH_SIZE=20`

**Expected Impact:**
- VRAM: 50% reduction (400 MB vs 800 MB)
- Speed: 2x faster sentiment scoring
- Accuracy: 5-7% reduction (acceptable)

**Actual Results:**
- VRAM: _____ MB → _____ MB (___% reduction)
- Sentiment: _____ items/sec → _____ items/sec
- False positives: _____ % increase/decrease
- False negatives: _____ % increase/decrease

---

### Phase 4: Adaptive Switching

**Configuration:**
- `FEATURE_ADAPTIVE_SENTIMENT=1`
- `SENTIMENT_MODEL_OPEN=distilbert`
- `SENTIMENT_MODEL_CLOSED=vader`

**Expected Impact:**
- VRAM: 75% average reduction (24-hour weighted)
- Speed: Varies by market status
- Accuracy: High during market hours, lower overnight (acceptable)

**Actual Results:**
- Market hours VRAM: _____ MB
- Closed hours VRAM: _____ MB (should be ~0 MB)
- Overall GPU usage: _____ % of baseline

---

### Phase 5: Advanced (CUDA Streams)

**Configuration:**
- `FEATURE_CUDA_STREAMS=1`
- Requires parallel sentiment + LLM workload

**Expected Impact:**
- Speed: 20-40% faster when running sentiment + LLM together
- VRAM: No change
- Complexity: Higher (advanced optimization)

**Note:** Only enable after benchmarking confirms speedup

---

## Troubleshooting

### Issue: Model Loading Fails

**Symptom:**
```
Failed to load model distilbert: Connection error
```

**Solution:**
1. Check internet connection (first download)
2. Pre-download model:
   ```bash
   python -c "
   from transformers import pipeline
   pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')
   "
   ```
3. Fallback to VADER:
   ```ini
   SENTIMENT_MODEL_NAME=vader
   ```

---

### Issue: High GPU Memory Usage

**Symptom:**
```
GPU memory usage critically high: 95.2% (threshold: 90%)
```

**Solutions:**

**1. Enable cleanup:**
```ini
GPU_MEMORY_CLEANUP=1
```

**2. Reduce batch size:**
```ini
SENTIMENT_BATCH_SIZE=5  # Reduce from 10
```

**3. Switch to smaller model:**
```ini
SENTIMENT_MODEL_NAME=distilbert  # Or vader
```

**4. Clear cache manually:**
```python
from catalyst_bot.ml.gpu_memory import clear_model_cache
clear_model_cache()
```

---

### Issue: Slower Performance After Optimization

**Symptom:**
Cycles take longer than before optimizations

**Possible Causes:**

**1. Batch size too small:**
```ini
SENTIMENT_BATCH_SIZE=20  # Increase from 10
```

**2. CPU-bound model on GPU workload:**
```ini
# If using VADER during market hours, switch to GPU model
SENTIMENT_MODEL_NAME=distilbert
```

**3. Cleanup overhead:**
```ini
# Reduce cleanup frequency (edit gpu_memory.py _CLEANUP_INTERVAL_SEC)
# Or disable during market hours:
GPU_MEMORY_CLEANUP=0
```

---

### Issue: Accuracy Degradation

**Symptom:**
More false positives/negatives after switching to DistilBERT

**Solutions:**

**1. Test on sample data:**
```bash
python -c "
from catalyst_bot.ml.model_switcher import compare_models
results = compare_models(['finbert', 'distilbert'])
print(results)
"
```

**2. Use hybrid approach:**
```python
# High-priority sources: FinBERT
# Low-priority sources: DistilBERT
if item['source'] in ['businesswire', 'globenewswire']:
    model = load_sentiment_model('finbert')
else:
    model = load_sentiment_model('distilbert')
```

**3. Fine-tune DistilBERT on financial data:**
- Collect 10,000+ labeled financial headlines
- Fine-tune DistilBERT
- Achieve FinBERT accuracy with DistilBERT speed

---

### Issue: CUDA Streams No Speedup

**Symptom:**
Benchmark shows speedup < 1.1x

**Explanation:**
CUDA streams only help when:
1. Multiple models run simultaneously
2. Models have non-overlapping memory access
3. GPU has sufficient compute units

**Solution:**
```ini
# Disable CUDA streams
FEATURE_CUDA_STREAMS=0
```

Use batch processing instead for better gains.

---

## Performance Monitoring

### Real-time GPU Monitoring

**Watch GPU stats during operation:**
```bash
# Terminal 1: Run bot
python -m catalyst_bot.runner --loop

# Terminal 2: Monitor GPU
watch -n 2 "python -c 'from catalyst_bot.gpu_monitor import format_gpu_stats_text; print(format_gpu_stats_text())'"
```

**Output:**
```
GPU: NVIDIA GeForce RTX 3060
  Driver: 536.23
  Utilization: 45.2%
  VRAM: 1234/12288 MB (10.0%)
  Temperature: 62°C
  Power: 85/170 W
```

---

### Log-based Monitoring

**Enable GPU logging:**
```ini
GPU_PROFILING_ENABLED=1
```

**View GPU stats in logs:**
```bash
grep "GPU" data/logs/bot.jsonl | tail -20
```

**Disable after debugging:**
```ini
GPU_PROFILING_ENABLED=0  # Reduces overhead
```

---

### Health Check Integration

**Add GPU to health endpoint:**
```python
from catalyst_bot.gpu_monitor import add_gpu_to_health_check

health_response = {"status": "ok"}
health_response = add_gpu_to_health_check(health_response)

# Returns:
# {
#   "status": "ok",
#   "gpu": {
#     "healthy": true,
#     "gpu_available": true,
#     "utilization_pct": 45.2,
#     "vram_used_mb": 1234.5,
#     ...
#   }
# }
```

---

## Summary

### Implementation Checklist

- [ ] Run baseline profiling
- [ ] Enable GPU memory cleanup
- [ ] Increase batch size to 10-20
- [ ] Integrate batch sentiment scoring
- [ ] Profile DistilBERT vs FinBERT
- [ ] Switch to DistilBERT (if accuracy acceptable)
- [ ] Test for 24 hours
- [ ] Enable adaptive model switching
- [ ] Monitor GPU stats
- [ ] Document actual improvements

### Expected Total Impact

**Conservative estimate:**
- VRAM: 60% reduction
- Speed: 40% faster sentiment scoring
- GPU temp: 10-15°C cooler
- Accuracy: <5% reduction

**Aggressive estimate (with adaptive switching):**
- VRAM: 85% reduction (24-hour average)
- Speed: 2x faster during market hours
- GPU usage: Near-zero overnight
- Accuracy: High during market hours, acceptable overnight

---

**Generated:** October 6, 2025
**Author:** Catalyst-Bot WAVE 2.2 Implementation Team
**Status:** Ready for Production Testing
