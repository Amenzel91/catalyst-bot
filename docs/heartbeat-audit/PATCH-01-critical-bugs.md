# PATCH-01: Critical Bugs

> **Priority:** HIGH
> **Files Modified:** 3
> **Estimated Time:** 1 vibecoding session

## Overview

This patch fixes three critical bugs that cause heartbeat metrics to show incorrect/zero values:

1. `_score_of()` missing `source_weight` field
2. `TRADING_ACTIVITY_STATS` never incremented
3. LLM usage reading from wrong monitor

---

## Bug 1: MIN_SCORE Score Extraction

### Problem

The `_score_of()` function in `runner.py` is missing the `source_weight` field check, which is where `classify.py` stores the complete calculated score.

### Root Cause Analysis

There are 3 different implementations of score extraction:

| File | Line | Fields Checked |
|------|------|----------------|
| `classify.py` | 761 | total_score, score, **source_weight**, relevance |
| `classify.py` | 1558 | **source_weight**, total_score, score, relevance |
| `runner.py` | 1683 | total_score, score, relevance, value ❌ |

The `runner.py` version never checks `source_weight`, so it falls through to `relevance` (just keyword matching, excluding sentiment).

### File: `src/catalyst_bot/runner.py`

### Current Code (Lines 1683-1691)

```python
def _score_of(scored: Any) -> float:
    for name in ("total_score", "score", "relevance", "value"):
        v = _get(scored, name, None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0
```

### Modified Code

```python
def _score_of(scored: Any) -> float:
    """Extract numeric score from scored object or dict.

    Note: Checks source_weight because classify.py stores the complete
    calculated score (relevance + sentiment) in this field.
    """
    for name in ("total_score", "score", "source_weight", "relevance", "value"):
        v = _get(scored, name, None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0
```

### Change Summary

| Line | Change Type | Description |
|------|-------------|-------------|
| 1683 | MODIFY | Add docstring explaining source_weight |
| 1684 | MODIFY | Add `"source_weight"` to field list after `"score"` |

### Verification

After this fix, the MIN_SCORE comparison at line ~3035 will use the correct score value. Test by:

1. Processing an item with sentiment contribution
2. Check log output: `min_score_check score=X.XX threshold=Y.YY`
3. Verify "Above MIN_SCORE" in heartbeat matches actual passes

---

## Bug 2: Trading Activity Counters

### Problem

`TRADING_ACTIVITY_STATS` is initialized but never incremented when trades execute.

### Root Cause Analysis

The dict is defined at `runner.py:160-163`:
```python
TRADING_ACTIVITY_STATS: Dict[str, Any] = {
    "signals_generated": 0,
    "trades_executed": 0,
}
```

But the trading execution code in `alerts.py:1464-1474` doesn't update these counters.

### File: `src/catalyst_bot/alerts.py`

### Current Code (Lines 1452-1491)

```python
                    # Execute trade using TradingEngine (MIGRATED 2025-11-26)
                    if HAS_PAPER_TRADING and paper_trading_enabled():
                        try:
                            # Import extended hours detection
                            from decimal import Decimal

                            from .market_hours import is_extended_hours

                            # Get current settings
                            s = get_settings()

                            # Execute trade via TradingEngine adapter
                            success = execute_with_trading_engine(
                                item=scored,  # ScoredItem from classify()
                                ticker=ticker,
                                current_price=(
                                    Decimal(str(last_price)) if last_price else None
                                ),
                                extended_hours=is_extended_hours(),
                                settings=s,
                            )

                            if success:
                                log.info(
                                    "trading_engine_signal_executed ticker=%s extended_hours=%s",
                                    ticker,
                                    is_extended_hours(),
                                )
                            else:
                                log.debug(
                                    "trading_engine_signal_skipped ticker=%s reason=low_confidence_or_hold",
                                    ticker,
                                )
                        except Exception as trade_err:
                            log.error(
                                "trading_engine_execution_failed ticker=%s error=%s",
                                ticker,
                                str(trade_err),
                                exc_info=True,
                            )
```

### Modified Code

```python
                    # Execute trade using TradingEngine (MIGRATED 2025-11-26)
                    if HAS_PAPER_TRADING and paper_trading_enabled():
                        try:
                            # Import extended hours detection
                            from decimal import Decimal

                            from .market_hours import is_extended_hours
                            from .runner import TRADING_ACTIVITY_STATS

                            # Get current settings
                            s = get_settings()

                            # Track signal generation attempt
                            TRADING_ACTIVITY_STATS["signals_generated"] = (
                                TRADING_ACTIVITY_STATS.get("signals_generated", 0) + 1
                            )

                            # Execute trade via TradingEngine adapter
                            success = execute_with_trading_engine(
                                item=scored,  # ScoredItem from classify()
                                ticker=ticker,
                                current_price=(
                                    Decimal(str(last_price)) if last_price else None
                                ),
                                extended_hours=is_extended_hours(),
                                settings=s,
                            )

                            if success:
                                # Track successful trade execution
                                TRADING_ACTIVITY_STATS["trades_executed"] = (
                                    TRADING_ACTIVITY_STATS.get("trades_executed", 0) + 1
                                )
                                log.info(
                                    "trading_engine_signal_executed ticker=%s extended_hours=%s",
                                    ticker,
                                    is_extended_hours(),
                                )
                            else:
                                log.debug(
                                    "trading_engine_signal_skipped ticker=%s reason=low_confidence_or_hold",
                                    ticker,
                                )
                        except Exception as trade_err:
                            log.error(
                                "trading_engine_execution_failed ticker=%s error=%s",
                                ticker,
                                str(trade_err),
                                exc_info=True,
                            )
```

### Change Summary

| Line | Change Type | Description |
|------|-------------|-------------|
| 1457 | ADD | Import `TRADING_ACTIVITY_STATS` from runner |
| 1463-1465 | ADD | Increment `signals_generated` before execute |
| 1478-1480 | ADD | Increment `trades_executed` on success |

### Alternative: Import at Module Level

If circular import issues occur, add at the top of `alerts.py` (~line 50):

```python
# Late import to avoid circular dependency
def _get_trading_stats():
    """Get TRADING_ACTIVITY_STATS from runner module."""
    try:
        from .runner import TRADING_ACTIVITY_STATS
        return TRADING_ACTIVITY_STATS
    except ImportError:
        return {"signals_generated": 0, "trades_executed": 0}
```

Then use `_get_trading_stats()` instead of direct import.

### Verification

1. Enable paper trading: `FEATURE_PAPER_TRADING=1`
2. Generate an alert that triggers trade evaluation
3. Check heartbeat for non-zero "Signals Generated"
4. If trade executes, verify "Trades Executed" increments

---

## Bug 3: LLM Monitor Bridge

### Problem

The heartbeat reads LLM usage from `LLMUsageMonitor` (JSONL file), but the modern code path writes to `LLMMonitor` (in-memory).

### Root Cause Analysis

Two disconnected systems:

| System | File | Storage | Used By |
|--------|------|---------|---------|
| `LLMUsageMonitor` | `llm_usage_monitor.py` | JSONL file | `llm_hybrid.py`, heartbeat |
| `LLMMonitor` | `services/llm_monitor.py` | In-memory | `LLMService` |

The SEC processor uses `LLMService`, so its usage goes to `LLMMonitor` but heartbeat queries `LLMUsageMonitor`.

### Solution: Bridge the Monitors

Add a call to `LLMUsageMonitor.log_usage()` alongside `LLMMonitor.track_request()`.

### File: `src/catalyst_bot/services/llm_service.py`

### Current Code (Lines 373-385)

```python
            # 7. Track cost and performance
            if self.monitor:
                self.monitor.track_request(
                    feature=request.feature_name,
                    provider=provider_name,
                    model=model,
                    tokens_input=llm_response.tokens_input,
                    tokens_output=llm_response.tokens_output,
                    cost_usd=llm_response.cost_usd,
                    latency_ms=latency_ms,
                    cached=False,
                    error=None
                )
```

### Modified Code

```python
            # 7. Track cost and performance
            if self.monitor:
                self.monitor.track_request(
                    feature=request.feature_name,
                    provider=provider_name,
                    model=model,
                    tokens_input=llm_response.tokens_input,
                    tokens_output=llm_response.tokens_output,
                    cost_usd=llm_response.cost_usd,
                    latency_ms=latency_ms,
                    cached=False,
                    error=None
                )

            # 7b. Bridge to legacy monitor for heartbeat display
            # The heartbeat reads from LLMUsageMonitor (JSONL), so we need
            # to also log there for metrics to appear in admin alerts.
            try:
                from ..llm_usage_monitor import get_monitor as get_legacy_monitor
                legacy_monitor = get_legacy_monitor()
                if legacy_monitor:
                    legacy_monitor.log_usage(
                        provider=provider_name,
                        model=model,
                        operation=request.feature_name,
                        input_tokens=llm_response.tokens_input,
                        output_tokens=llm_response.tokens_output,
                        cost_estimate=llm_response.cost_usd,
                        latency_ms=latency_ms,
                    )
            except Exception:
                pass  # Non-critical - don't fail request if logging fails
```

### Change Summary

| Line | Change Type | Description |
|------|-------------|-------------|
| 385-400 | ADD | Bridge call to legacy LLMUsageMonitor |

### Also Update Error Tracking (Lines 411-423)

```python
            # Track error
            if self.monitor:
                self.monitor.track_request(
                    feature=request.feature_name,
                    provider="unknown",
                    model="unknown",
                    tokens_input=0,
                    tokens_output=0,
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    cached=False,
                    error=str(e)
                )

            # Bridge error to legacy monitor
            try:
                from ..llm_usage_monitor import get_monitor as get_legacy_monitor
                legacy_monitor = get_legacy_monitor()
                if legacy_monitor:
                    legacy_monitor.log_usage(
                        provider="unknown",
                        model="unknown",
                        operation=request.feature_name,
                        input_tokens=0,
                        output_tokens=0,
                        cost_estimate=0.0,
                        latency_ms=latency_ms,
                        error=str(e),
                    )
            except Exception:
                pass
```

### Alternative: Update Heartbeat to Read Modern Monitor

Instead of bridging, update `runner.py:_get_llm_usage_hourly()` to read from `LLMMonitor`:

### File: `src/catalyst_bot/runner.py`

### Current Code (Lines 477-522)

```python
def _get_llm_usage_hourly() -> Dict[str, Any]:
    """
    Get LLM usage statistics for the last hour and today.
    ...
    """
    try:
        from datetime import datetime, timedelta, timezone

        # Get hourly stats (last 60 minutes)
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        hourly_stats = get_monitor().get_stats(since=hour_ago, until=now)
        # ... rest of function
```

### Alternative Modified Code

```python
def _get_llm_usage_hourly() -> Dict[str, Any]:
    """
    Get LLM usage statistics for the last hour and today.

    Reads from both legacy (LLMUsageMonitor) and modern (LLMMonitor) systems,
    combining stats for comprehensive reporting.
    """
    try:
        from datetime import datetime, timedelta, timezone

        result = {
            "total_requests": 0,
            "gemini_count": 0,
            "claude_count": 0,
            "local_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "hourly_cost": 0.0,
            "daily_cost": 0.0,
        }

        # Try legacy monitor first (LLMUsageMonitor - JSONL based)
        try:
            now = datetime.now(timezone.utc)
            hour_ago = now - timedelta(hours=1)
            hourly_stats = get_monitor().get_stats(since=hour_ago, until=now)
            daily_stats = get_monitor().get_daily_stats()

            result["total_requests"] += hourly_stats.total_requests
            result["gemini_count"] += hourly_stats.gemini.total_requests
            result["claude_count"] += hourly_stats.anthropic.total_requests
            result["local_count"] += hourly_stats.local.total_requests
            result["input_tokens"] += (
                hourly_stats.gemini.total_input_tokens
                + hourly_stats.anthropic.total_input_tokens
            )
            result["output_tokens"] += (
                hourly_stats.gemini.total_output_tokens
                + hourly_stats.anthropic.total_output_tokens
            )
            result["hourly_cost"] += hourly_stats.total_cost
            result["daily_cost"] += daily_stats.total_cost
        except Exception:
            pass

        # Also try modern monitor (LLMMonitor - in-memory)
        try:
            from .services.llm_monitor import LLMMonitor
            modern_monitor = LLMMonitor.get_instance()
            if modern_monitor:
                modern_stats = modern_monitor.get_stats()
                result["total_requests"] += modern_stats.get("total_requests", 0)
                result["input_tokens"] += modern_stats.get("total_tokens_input", 0)
                result["output_tokens"] += modern_stats.get("total_tokens_output", 0)
                result["hourly_cost"] += modern_stats.get("total_cost_usd", 0.0)
                # Add provider counts from modern monitor
                for provider, count in modern_stats.get("requests_by_provider", {}).items():
                    if "gemini" in provider.lower():
                        result["gemini_count"] += count
                    elif "claude" in provider.lower() or "anthropic" in provider.lower():
                        result["claude_count"] += count
                    else:
                        result["local_count"] += count
        except Exception:
            pass

        return result
    except Exception:
        return {
            "total_requests": 0,
            "gemini_count": 0,
            "claude_count": 0,
            "local_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "hourly_cost": 0.0,
            "daily_cost": 0.0,
        }
```

### Recommendation

**Use the bridge approach (Option 1)** because:
- Single source of truth in JSONL file
- Persistent across restarts
- Less invasive change
- Already has time-based querying

### Verification

1. Trigger SEC filing processing (uses LLMService)
2. Wait for heartbeat interval
3. Check "LLM Usage" section shows non-zero values
4. Verify token counts and costs are reasonable

---

## Complete Change List

| File | Lines | Change |
|------|-------|--------|
| `runner.py` | 1683-1684 | Add `source_weight` to `_score_of()` |
| `alerts.py` | 1457 | Import `TRADING_ACTIVITY_STATS` |
| `alerts.py` | 1463-1465 | Increment `signals_generated` |
| `alerts.py` | 1478-1480 | Increment `trades_executed` |
| `llm_service.py` | 385-400 | Bridge to legacy LLM monitor |
| `llm_service.py` | 423-437 | Bridge errors to legacy monitor |

## Testing Checklist

- [ ] MIN_SCORE shows non-zero when alerts pass threshold
- [ ] Trading Activity shows signals when paper trading enabled
- [ ] LLM Usage shows requests when SEC filings processed
- [ ] No circular import errors on startup
- [ ] No performance regression in main loop
- [ ] Existing tests pass: `pytest test_enhanced_heartbeat.py -v`

## Commit Message Template

```
fix(heartbeat): wire up critical metrics for admin visibility

- Fix _score_of() to check source_weight field (classify.py parity)
- Wire TRADING_ACTIVITY_STATS counters in alerts.py
- Bridge LLMService to legacy LLMUsageMonitor for heartbeat display

Fixes: Above MIN_SCORE showing 0, Trading Activity showing 0,
       LLM Usage showing 0 in admin heartbeat alerts

Audit: docs/heartbeat-audit/PATCH-01-critical-bugs.md
```

---

*Proceed to [PATCH-02: Display Fixes](./PATCH-02-display-fixes.md) after completing this patch.*
