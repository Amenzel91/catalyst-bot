# Catalyst-Bot - AI Development Context

## Mission Statement

**Generate high-quality, actionable catalyst alerts with minimal false positives in tickers under $10.**

This is the non-negotiable core goal. Every change, feature, and optimization must serve this mission.

---

## Current Priorities

1. **Streamlining Data** - Reduce redundancy, improve feed efficiency
2. **Reducing Scan Time** - Optimize the main loop cycle performance
3. **Enhancing Alerts** - Improve alert quality, formatting, and actionability
4. **Paper Trading** - Make TradingEngine fully functional and reliable
5. **LLM Efficiency** - Smart, cost-effective LLM usage with robust fallbacks

---

## Architecture Overview

```
Data Sources → Feed Aggregator → Classification Pipeline → Scoring → Alerts → Tracking
     ↓              ↓                    ↓                   ↓         ↓
  Finnhub      Deduplication      Keywords + VADER      Thresholds  Discord
  Tiingo       Ticker Extract     + LLM + Fundamentals  + Filters   Webhooks
  yfinance     Validation         + Sector Context
  RSS Feeds
```

**Key Entry Point**: `python -m catalyst_bot.runner --loop --sleep-secs 300`

**Database**: SQLite with WAL mode (`data/market.db`)

**Config**: Environment variables via `.env` file

---

## Protected Components - ASK BEFORE MODIFYING

These components require explicit user approval before changes:

### 1. Discord Alerts (`src/catalyst_bot/alerts.py`)
- Embed formatting and structure
- Webhook delivery logic
- Alert field definitions

### 2. LLM Services (`src/catalyst_bot/llm_hybrid.py`, `llm_cache.py`)
- Model routing logic (Local → Gemini Flash → Pro → Claude)
- Prompt templates
- Response parsing

### 3. Paper Trading (`src/catalyst_bot/trading/trading_engine.py`)
- Position management
- Order execution logic
- Risk calculations

**Before modifying these**: Explain the change, get approval, then proceed.

---

## Development Guidelines

### DO

- **Maintain definitions** - If you define a variable, constant, or interface, keep it consistent throughout the entire patch
- **Track progress** - Use TodoWrite extensively to track steps and prevent forgotten tasks after compacting
- **Test changes** - Run relevant tests before considering work complete
- **Be efficient** - Optimize for performance and API cost efficiency
- **Refactor when beneficial** - Don't be afraid of larger refactors if they improve the codebase
- **Add robust error handling** - Features should fail gracefully
- **Document non-obvious logic** - Add comments for complex algorithms

### DON'T

- **Don't change definitions mid-patch** - This breaks dependent code and causes cascading issues
- **Don't forget planned steps** - Always check the todo list before marking work complete
- **Don't modify protected components** without asking first
- **Don't add complexity without clear benefit** - Simple > clever
- **Don't break existing tests** - Target: 100% pass rate (currently 97.5%, 366 tests)

---

## Common Patterns

### Configuration
```python
from catalyst_bot.config import Settings
settings = Settings()
# Access via: settings.min_score, settings.price_ceiling, etc.
```

### Feature Flags
```python
# Enable/disable features via environment
FEATURE_LLM=1
FEATURE_TIINGO=1
FEATURE_FUNDAMENTAL_SCORING=1
```

### Caching Strategy (3-tier)
1. **Memory** - In-process dict (fastest, lost on restart)
2. **Disk** - Parquet files in `data/cache/` with TTL
3. **API** - Only on cache miss

### Error Handling
```python
# Use tenacity for retries with exponential backoff
from tenacity import retry, stop_after_attempt, wait_exponential
```

---

## API Integration Notes

| Service | Cost | Usage |
|---------|------|-------|
| Gemini Flash | ~$1.80/mo | Primary LLM |
| Finnhub | Free | News & sentiment |
| yfinance | Free | Price fallback |
| Tiingo | $30/mo | Premium OHLC |
| Alpha Vantage | Free tier | Fundamentals |

**Guidance**: Be efficient. Can add new free APIs or switch to similarly-priced alternatives when beneficial.

---

## Testing

Run tests before completing work:
```bash
pytest tests/ -v
```

**Target**: 100% pass rate (no exceptions)
**Current state**: 366 tests, 97.5% - needs improvement

---

## Key Files Reference

| Purpose | Location |
|---------|----------|
| Main runner | `src/catalyst_bot/runner.py` |
| Classification | `src/catalyst_bot/classify.py` |
| Feed aggregation | `src/catalyst_bot/feeds.py` |
| Alerts | `src/catalyst_bot/alerts.py` |
| LLM routing | `src/catalyst_bot/llm_hybrid.py` |
| Trading engine | `src/catalyst_bot/trading/trading_engine.py` |
| Configuration | `src/catalyst_bot/config.py` |
| Market data | `src/catalyst_bot/market.py` |

---

## Session Continuity Checklist

Before ending a session or after context compacting:

- [ ] Check TodoWrite list - are all planned steps complete?
- [ ] Were any definitions changed? Verify consistency across the codebase
- [ ] Run tests if code was modified
- [ ] Document any incomplete work clearly

---

## Target Stock Criteria

- **Price**: Under $10 (enforced via `PRICE_CEILING`)
- **Focus**: Small-cap momentum plays with material catalysts
- **Quality**: High signal-to-noise ratio, actionable information

---

*Last updated: 2025-12-06*
