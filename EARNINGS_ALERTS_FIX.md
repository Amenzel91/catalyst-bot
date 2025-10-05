# Earnings Alerts Fix - Patch Proposal

## Problem

Earnings **calendar** alerts are firing without sentiment, cluttering the alert channel:
- "AAPL Earnings BMO" - No actionable info
- "TSLA Earnings 10/20" - Future event, neutral sentiment
- These have 0.0 sentiment (neutral) and bypass filters because `MIN_SENT_ABS` is empty

## Root Cause

`fetch_finnhub_earnings_calendar()` creates alerts for **upcoming** earnings, not actual **results**:
- Title: "{TICKER} Earnings"
- Sentiment: ~0.0 (VADER sees "earnings" as neutral word)
- No indication if earnings will beat/miss/are positive catalyst

## Solution Options

### Option 1: Enable Sentiment Filter (Quick Fix)
**Pros**: Filters out all neutral alerts (earnings calendar + other noise)
**Cons**: Might filter valid neutral news

```ini
# .env
MIN_SENT_ABS=0.15  # Require absolute sentiment ≥ 0.15
```

**Result**: Earnings calendar alerts blocked (sentiment = 0.0)

---

### Option 2: Disable Earnings Calendar Entirely (Recommended)
**Pros**: Clean, direct, no false positives
**Cons**: No earnings calendar info

```ini
# .env
SKIP_SOURCES=Finnhub Earnings  # Block earnings calendar source
```

**Result**: No more "AAPL Earnings 10/20" spam

---

### Option 3: Smart Earnings Scoring (Best - Requires Code)
**Pros**: Only alert on significant earnings opportunities
**Cons**: Requires implementation

**Logic**:
1. **Detect actual earnings RESULTS** vs calendar:
   - Results have "beats", "misses", "EPS $0.50 vs $0.45 est" in title
   - Calendar just says "Earnings Date: 10/20"

2. **Score based on result quality**:
   ```python
   # Earnings beat
   if "beats" in title or actual_eps > estimate_eps * 1.05:
       sentiment = +0.7

   # Earnings miss
   elif "misses" in title or actual_eps < estimate_eps * 0.95:
       sentiment = -0.7

   # Calendar only (no results yet)
   else:
       sentiment = 0.0  # Will be filtered by MIN_SENT_ABS
   ```

3. **LLM enhancement** (optional):
   - Use LLM to predict earnings outcome based on:
     - Recent price action
     - Analyst sentiment
     - Historical beat rate
     - Sector performance

**Implementation**:
```python
# src/catalyst_bot/earnings_scorer.py

def score_earnings_event(event: Dict) -> float:
    """
    Score earnings events based on actual results.

    Returns:
        - +0.7 to +1.0: Strong beat
        - +0.3 to +0.7: Modest beat
        - -0.3 to -0.7: Miss
        - -0.7 to -1.0: Big miss
        - 0.0: Calendar only (no results)
    """
    title = event.get("title", "").lower()

    # Check if actual results available
    if "beats" in title or "tops" in title or "exceeds" in title:
        return 0.7

    if "misses" in title or "falls short" in title:
        return -0.7

    # Parse EPS actual vs estimate
    eps_actual = event.get("eps_actual")
    eps_estimate = event.get("eps_estimate")

    if eps_actual and eps_estimate:
        beat_pct = (eps_actual - eps_estimate) / abs(eps_estimate)

        if beat_pct > 0.10:  # Beat by >10%
            return min(1.0, 0.5 + beat_pct)
        elif beat_pct < -0.10:  # Miss by >10%
            return max(-1.0, -0.5 + beat_pct)
        else:
            return beat_pct * 3  # Scale modest beats/misses

    # No results yet - just calendar
    return 0.0
```

---

### Option 4: LLM Earnings Predictor (Advanced)
**Pros**: Actionable pre-earnings alerts
**Cons**: Requires Ollama + more prompt engineering

```python
def predict_earnings_sentiment(ticker: str, earnings_date: str) -> float:
    """Use LLM to predict earnings outcome."""

    # Gather context
    recent_news = fetch_finnhub_company_news(ticker, days=30)
    analyst_ratings = get_analyst_ratings(ticker)
    historical_beats = get_earnings_history(ticker, quarters=8)

    prompt = f"""
    Ticker: {ticker}
    Earnings Date: {earnings_date}

    Recent News (30 days):
    {recent_news[:5]}

    Analyst Ratings:
    {analyst_ratings}

    Historical Beat Rate: {historical_beats['beat_rate']:.0%} (last 8 quarters)

    Question: Will this company likely beat, meet, or miss earnings estimates?

    Respond with JSON:
    {{
      "prediction": "beat|meet|miss",
      "confidence": <0-1>,
      "sentiment": <-1 to +1>,
      "reason": "<brief explanation>"
    }}
    """

    response = query_llm(prompt, system="You are a financial analyst specializing in earnings predictions.")

    # Parse and return sentiment
    analysis = json.loads(response)
    return analysis['sentiment']  # e.g., +0.6 for likely beat
```

---

## Recommended Implementation

**Phase 1: Immediate Fix** (Today)
```ini
# .env - Add this line
MIN_SENT_ABS=0.15

# OR disable earnings calendar entirely
SKIP_SOURCES=Finnhub Earnings
```

**Phase 2: Smart Earnings Scoring** (This Week)
1. Create `src/catalyst_bot/earnings_scorer.py`
2. Modify `finnhub_feeds.py` to:
   - Detect actual results vs calendar
   - Apply `score_earnings_event()` to set sentiment
   - Skip calendar-only events (sentiment = 0.0)

**Phase 3: LLM Predictor** (Optional - Next Week)
1. Implement `predict_earnings_sentiment()`
2. Run for stocks with >$1B market cap
3. Only alert on high-confidence predictions (>0.7)

---

## Testing Plan

1. **Test sentiment filter**:
   ```bash
   # Set MIN_SENT_ABS=0.15, check logs
   grep "skipped_sent_gate" data/logs/bot.jsonl
   # Should see earnings calendar skipped
   ```

2. **Test earnings results detection**:
   ```python
   # Test with sample titles
   score_earnings_event({"title": "AAPL beats Q4 earnings"})  # → +0.7
   score_earnings_event({"title": "TSLA misses revenue"})     # → -0.7
   score_earnings_event({"title": "NVDA Earnings 10/20"})    # → 0.0 (filtered)
   ```

3. **Monitor for false negatives**:
   - Ensure actual earnings RESULTS still fire
   - Check if "XYZ beats earnings" gets positive sentiment
   - Verify LLM fallback activates if needed

---

## Success Metrics

- ✅ Zero earnings **calendar** alerts (future dates only)
- ✅ 100% of earnings **results** alerts (beats/misses)
- ✅ Positive sentiment for beats, negative for misses
- ✅ No valid catalysts filtered out

---

## Decision Matrix

| Situation | Option 1 | Option 2 | Option 3 | Option 4 |
|-----------|----------|----------|----------|----------|
| Want quick fix | ✅ | ✅ | ❌ | ❌ |
| Want earnings results only | ❌ | ✅ | ✅ | ✅ |
| Want pre-earnings predictions | ❌ | ❌ | ❌ | ✅ |
| Implementation time | 1 min | 1 min | 2-3 hrs | 5-6 hrs |
| Accuracy | Medium | High | High | Very High |

**My Recommendation**:
1. **Right now**: Option 2 (disable earnings calendar)
2. **This week**: Option 3 (smart earnings scoring)
3. **When LLM is stable**: Option 4 (predictions)

---

Would you like me to implement Option 2 (quick fix) or Option 3 (smart scoring)?
