# BacktestEngine Configurable Data Source - Implementation Summary

## Overview
Successfully implemented configurable data source functionality for `BacktestEngine` to allow loading historical alerts from custom files and applying custom filters.

## Changes Made

### 1. Modified File: `src/catalyst_bot/backtesting/engine.py`

#### Added Import
- Added `Callable` to type imports to support the data_filter parameter

#### Updated `__init__` Method
Added two new optional parameters:
- `data_source: str = "data/events.jsonl"` - Path to historical events data file
- `data_filter: Optional[Callable] = None` - Optional filter function for alerts

```python
def __init__(
    self,
    start_date: str,
    end_date: str,
    initial_capital: float = 10000.0,
    strategy_params: Optional[Dict] = None,
    data_source: str = "data/events.jsonl",  # NEW
    data_filter: Optional[Callable] = None,  # NEW
):
```

#### Updated `load_historical_alerts()` Method
- Changed from hardcoded `Path("data/events.jsonl")` to `Path(self.data_source)`
- Added logic to apply `data_filter` if provided
- Added logging for filter application showing original and filtered counts

```python
# Apply custom data filter if provided
if self.data_filter is not None:
    original_count = len(alerts)
    alerts = [alert for alert in alerts if self.data_filter(alert)]
    log.info(
        "data_filter_applied original=%d filtered=%d",
        original_count,
        len(alerts),
    )
```

#### Updated Documentation
- Enhanced docstring to document both new parameters
- Updated `load_historical_alerts()` docstring to reflect configurable data source

### 2. Created Test File: `tests/test_backtest_configurable_data_source.py`

Comprehensive test suite with 9 tests covering:
- Default data source behavior
- Custom data source loading
- Ticker filtering
- Score filtering
- Keyword filtering
- Combined filters
- No filter behavior
- Nonexistent file handling
- Backward compatibility

**All tests pass ✓**

### 3. Created Example File: `examples/backtest_custom_data_source_example.py`

8 practical examples demonstrating:
1. Custom data source usage
2. Ticker-specific filtering
3. High-score filtering
4. FDA catalyst filtering
5. Combined multi-condition filters
6. Sector-based filtering
7. Time-based filtering
8. Strategy comparison

## Backward Compatibility

**100% Backward Compatible** - All existing code continues to work without modification:
- Default `data_source` is `"data/events.jsonl"` (same as before)
- Default `data_filter` is `None` (no filtering)
- All existing tests pass (23 tests in test_backtesting.py)
- No breaking changes to API

## Test Results

```
tests/test_backtesting.py - 23 tests PASSED ✓
tests/test_backtest_configurable_data_source.py - 9 tests PASSED ✓
Total: 32 tests PASSED ✓
```

## Usage Examples

### Example 1: Custom Data Source
```python
engine = BacktestEngine(
    start_date="2025-01-01",
    end_date="2025-01-31",
    initial_capital=10000.0,
    data_source="data/custom_events.jsonl",  # Custom file
)
```

### Example 2: Filter by Ticker
```python
def ticker_filter(alert):
    return alert.get("ticker") in ["AAPL", "TSLA"]

engine = BacktestEngine(
    start_date="2025-01-01",
    end_date="2025-01-31",
    data_filter=ticker_filter,
)
```

### Example 3: Filter by Score
```python
def high_score_filter(alert):
    score = alert.get("cls", {}).get("score", 0.0)
    return score >= 0.7

engine = BacktestEngine(
    start_date="2025-01-01",
    end_date="2025-01-31",
    data_filter=high_score_filter,
)
```

### Example 4: Combined Filters
```python
def combined_filter(alert):
    score = alert.get("cls", {}).get("score", 0.0)
    sentiment = alert.get("cls", {}).get("sentiment", 0.0)
    return score >= 0.6 and sentiment >= 0.5

engine = BacktestEngine(
    start_date="2025-01-01",
    end_date="2025-01-31",
    data_source="data/custom_events.jsonl",
    data_filter=combined_filter,
)
```

## Benefits

1. **Flexibility** - Load data from any source file
2. **Testability** - Easy to test with custom datasets
3. **Experimentation** - Quickly test different filtering strategies
4. **Performance** - Filter data before processing (more efficient)
5. **Reusability** - Filter functions can be reused across backtests
6. **Backward Compatible** - No impact on existing code

## Files Modified
- `src/catalyst_bot/backtesting/engine.py` (updated)

## Files Created
- `tests/test_backtest_configurable_data_source.py` (new)
- `examples/backtest_custom_data_source_example.py` (new)
- `BACKTEST_ENGINE_CONFIGURABLE_DATA_SOURCE.md` (this file)

## Next Steps (Optional Enhancements)

1. **Database Support** - Add support for loading from database instead of files
2. **Filter Composition** - Create helper functions for combining filters
3. **Performance Metrics** - Track filter performance/selectivity
4. **Validation** - Add validation for data_source path format
5. **Documentation** - Add to main README if needed

## Conclusion

The BacktestEngine now supports configurable data sources and custom filtering, making it more flexible and powerful for backtesting strategies. All changes maintain full backward compatibility with existing code.

**Status: ✓ Complete - All tests pass**
