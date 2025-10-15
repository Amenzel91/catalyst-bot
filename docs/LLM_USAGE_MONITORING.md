# LLM Usage Monitoring System

Comprehensive real-time tracking of LLM API usage, costs, and rate limits to prevent bill shock and ensure you stay within budget.

## Features

- ✅ **Automatic Token Counting** - Tracks input/output tokens for all LLM calls
- ✅ **Real-Time Cost Calculation** - Accurate pricing based on latest API rates
- ✅ **Multi-Provider Support** - Gemini, Anthropic, and local Mistral tracking
- ✅ **Budget Alerts** - Configurable daily/monthly cost thresholds
- ✅ **Detailed Reports** - Per-provider, per-operation cost breakdowns
- ✅ **Cost Projections** - Estimates monthly spend based on current usage
- ✅ **Persistent Logging** - All API calls logged to JSONL for analysis

## Quick Start

### 1. Automatic Monitoring (Already Integrated!)

The monitor is **automatically integrated** into your LLM hybrid router. All Gemini and Anthropic API calls are logged automatically with no code changes needed.

Usage data is logged to: `data/logs/llm_usage.jsonl`

### 2. View Today's Usage

```bash
python scripts/llm_usage_report.py
```

### 3. View Monthly Usage

```bash
python scripts/llm_usage_report.py --monthly
```

### 4. Custom Date Range

```bash
python scripts/llm_usage_report.py --since "2025-01-01" --until "2025-01-31"
```

## Usage Examples

### Example Output

```
======================================================================
LLM USAGE SUMMARY
======================================================================
Period: 2025-01-15T00:00:00+00:00 to 2025-01-15T23:59:59+00:00
Total Requests: 256
Total Tokens: 1,250,000
Total Cost: $2.35

----------------------------------------------------------------------
COST BY PROVIDER:
----------------------------------------------------------------------
Gemini          $  1.85  (200 requests, 950,000 tokens)
Anthropic       $  0.50  (10 requests, 125,000 tokens)

----------------------------------------------------------------------
COST BY OPERATION:
----------------------------------------------------------------------
sec_keyword_extraction         $  2.10
sentiment_analysis             $  0.15
llm_query                      $  0.10

----------------------------------------------------------------------
PROVIDER DETAILS:
----------------------------------------------------------------------

GEMINI (gemini-2.5-flash):
  Requests: 200 (OK:198 FAIL:2)
  Tokens:   950,000 (in: 800,000, out: 150,000)
  Cost:     $1.8500 (in: $1.2000, out: $0.6500)

======================================================================
COST PROJECTIONS
======================================================================
Cost per hour:   $0.0979
Daily projection: $2.35
Monthly projection: $70.50

[WARNING] Projected monthly cost ($70.50) exceeds budget ($50.00)
======================================================================
```

## Configuration

### Environment Variables

```bash
# Cost alert thresholds
LLM_COST_ALERT_DAILY=5.00      # Daily budget ($5/day default)
LLM_COST_ALERT_MONTHLY=50.00   # Monthly budget ($50/month default)

# Custom log path (optional)
LLM_USAGE_LOG_PATH=data/logs/llm_usage.jsonl
```

### Current Pricing (as of January 2025)

The monitor uses these rates for cost calculation:

**Gemini 2.5 Flash:**
- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens

**Anthropic Claude 3 Haiku:**
- Input: $0.25 per 1M tokens
- Output: $1.25 per 1M tokens

**Local Mistral (via Ollama):**
- Input: $0.00 (FREE)
- Output: $0.00 (FREE)

## Integration Details

### How It Works

1. **Automatic Logging** - Every Gemini/Anthropic API call is intercepted by the monitor
2. **Token Estimation** - Input/output tokens estimated using ~4 chars/token
3. **Cost Calculation** - Costs computed using current pricing tables
4. **JSONL Storage** - Each call appended to log file with full metadata
5. **Realtime Alerts** - Budget warnings logged when thresholds exceeded

### Integration Points

The monitor is integrated at these locations:

**`src/catalyst_bot/llm_hybrid.py`**
- Lines 214-274: `_call_gemini()` - Wraps Gemini API calls
- Lines 276-350: `_call_anthropic()` - Wraps Anthropic API calls

Both functions automatically call `monitor.log_usage()` after every API request.

### Manual Integration (for Custom LLM Calls)

If you're making LLM calls outside the hybrid router:

```python
from catalyst_bot.llm_usage_monitor import get_monitor, estimate_tokens

monitor = get_monitor()

# Your LLM call
prompt = "Analyze this SEC filing..."
response = your_llm_call(prompt)

# Log usage
input_tokens = estimate_tokens(prompt)
output_tokens = estimate_tokens(response)

monitor.log_usage(
    provider="gemini",  # or "anthropic", "local"
    model="gemini-2.5-flash",
    operation="custom_analysis",
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    success=True,
    ticker="AAPL",  # optional
    article_length=len(prompt),  # optional
)
```

## Cost Analysis

### Understanding Your Costs

**Per-Call Costs (based on test data):**
- Gemini SEC filing keyword extraction: ~$0.001 per call
- Anthropic SEC filing analysis: ~$0.003 per call
- Local Mistral sentiment: $0.00 (FREE)

**Typical Usage Patterns:**
- 100 SEC filings/day with Gemini: $0.10/day = $3.00/month
- 1000 SEC filings/day with Gemini: $1.00/day = $30.00/month
- 10,000 SEC filings/day with Gemini: $10.00/day = $300.00/month

### Cost Optimization Strategies

1. **Maximize Local Mistral Usage** - Free for short articles (<1000 chars)
2. **Prefer Gemini over Anthropic** - Gemini is ~3x cheaper per call
3. **Use Prompt Compression** - Reduces input tokens by 30-50%
4. **Batch Processing** - Process filings in batches to reduce overhead
5. **Smart Pre-filtering** - Only send high-quality candidates to LLM

## Monitoring Best Practices

### Daily Check-In

```bash
# View today's usage each morning
python scripts/llm_usage_report.py

# Look for:
# - Unexpected cost spikes
# - High failure rates
# - Provider imbalances
```

### Weekly Analysis

```bash
# Review last 7 days
python scripts/llm_usage_report.py --since "2025-01-08"

# Check:
# - Cost trends
# - Provider performance
# - Operation efficiency
```

### Monthly Review

```bash
# Full month analysis
python scripts/llm_usage_report.py --monthly

# Analyze:
# - Total monthly spend
# - Cost projections
# - Budget adherence
```

## Troubleshooting

### High Costs?

1. Check operation breakdown - which operations cost most?
2. Review provider distribution - are you hitting expensive fallbacks?
3. Analyze failure rate - failed calls still cost money
4. Consider prompt compression - reduce token usage

### Missing Data?

1. Verify log file exists: `data/logs/llm_usage.jsonl`
2. Check file permissions
3. Ensure hybrid router is being used (not direct API calls)
4. Look for import errors in application logs

### Incorrect Costs?

1. Verify pricing table in `src/catalyst_bot/llm_usage_monitor.py` (lines 110-134)
2. Check model names match exactly (case-sensitive)
3. Anthropic provides exact token counts - Gemini uses estimates

## Advanced Features

### Custom Log Path

```python
from pathlib import Path
from catalyst_bot.llm_usage_monitor import LLMUsageMonitor

monitor = LLMUsageMonitor(log_path=Path("custom/path/usage.jsonl"))
```

### Programmatic Access

```python
from catalyst_bot.llm_usage_monitor import get_monitor
from datetime import datetime, timezone, timedelta

monitor = get_monitor()

# Get last 24 hours
since = datetime.now(timezone.utc) - timedelta(days=1)
summary = monitor.get_stats(since=since)

print(f"Total cost: ${summary.total_cost:.2f}")
print(f"Total requests: {summary.total_requests}")
print(f"Gemini cost: ${summary.gemini.total_cost:.2f}")
```

### Cost Alerts in Code

The monitor automatically logs warnings when budgets are exceeded:

```
WARNING:llm_usage_monitor:llm_daily_cost_alert cost=$6.50 threshold=$5.00 providers={'gemini': '$5.20', 'anthropic': '$1.30'}
```

These appear in your application logs and can trigger monitoring alerts.

## Testing

### Run Test Suite

```bash
python test_llm_usage_monitor.py
```

This simulates 28 API calls (Gemini, Anthropic, Local) and generates a full usage report.

### Test Output

The test demonstrates:
- Logging API calls with different providers
- Cost calculation accuracy
- Report generation
- Cost savings from local Mistral
- Failure handling

## Files and Locations

**Core Module:**
- `src/catalyst_bot/llm_usage_monitor.py` - Main monitoring system

**Integration:**
- `src/catalyst_bot/llm_hybrid.py` - LLM router with automatic logging

**Tools:**
- `scripts/llm_usage_report.py` - CLI report generator
- `test_llm_usage_monitor.py` - Test suite

**Data:**
- `data/logs/llm_usage.jsonl` - Usage log (JSONL format)
- `data/logs/llm_usage_test.jsonl` - Test data

## Future Enhancements

Potential improvements:
- Real-time dashboard web UI
- Slack/email cost alerts
- Provider health monitoring
- Rate limit tracking
- Cost forecasting ML model
- Integration with cloud billing APIs

## Support

If you encounter issues:

1. Check the test suite runs successfully
2. Verify log file is being created
3. Review application logs for errors
4. Check environment variable configuration

For questions or bug reports, file an issue with:
- Example usage report output
- Log file snippet (first 10 lines)
- Environment configuration
