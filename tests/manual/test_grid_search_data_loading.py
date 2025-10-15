#!/usr/bin/env python3
"""
Test script for grid search data loading with Tiingo API integration.

This script validates that the _load_data_for_grid_search() function:
1. Successfully loads events from events.jsonl
2. Fetches price data from Tiingo API
3. Creates aligned price and signal DataFrames
4. Handles missing data gracefully
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta, timezone
from catalyst_bot.backtesting.validator import _load_data_for_grid_search
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_grid_search")

def test_data_loading():
    """Test the data loading function with real Tiingo API calls."""

    print("\n" + "="*80)
    print("GRID SEARCH DATA LOADING TEST")
    print("="*80)

    # Use date range that matches events.jsonl data (August-October 2025)
    # Most recent events are around Oct 7, 2025
    end_date = datetime(2025, 10, 8, tzinfo=timezone.utc)
    start_date = datetime(2025, 10, 1, tzinfo=timezone.utc)  # Last week of data

    print(f"\nTest Parameters:")
    print(f"  Start Date: {start_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  End Date:   {end_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    print("\n" + "-"*80)
    print("STEP 1: Loading data from events.jsonl and Tiingo API")
    print("-"*80)

    price_data, signal_data = _load_data_for_grid_search(start_date, end_date)

    print("\n" + "-"*80)
    print("STEP 2: Validating results")
    print("-"*80)

    if price_data is None or signal_data is None:
        print("\n[FAILED] No data loaded")
        print("\nPossible causes:")
        print("  1. No events with tickers in events.jsonl for the date range")
        print("  2. Tiingo API key not configured (check .env file)")
        print("  3. Network issues or API rate limits")
        print("  4. All tickers failed to fetch price data")
        return False

    print(f"\n[SUCCESS] Data loaded successfully!")

    print(f"\nPrice Data:")
    print(f"  Shape:      {price_data.shape}")
    print(f"  Tickers:    {list(price_data.columns)}")
    print(f"  Date Range: {price_data.index[0]} to {price_data.index[-1]}")
    print(f"  Total Rows: {len(price_data)}")

    print(f"\nSignal Data:")
    print(f"  Shape:         {signal_data.shape}")
    print(f"  Non-zero:      {(signal_data > 0).sum().sum()}")
    print(f"  Max Signal:    {signal_data.max().max():.4f}")
    print(f"  Signals/Ticker:")
    for ticker in signal_data.columns:
        count = (signal_data[ticker] > 0).sum()
        if count > 0:
            max_score = signal_data[ticker].max()
            print(f"    {ticker}: {count} signals (max={max_score:.4f})")

    print("\n" + "-"*80)
    print("STEP 3: Data Quality Checks")
    print("-"*80)

    # Check 1: Shape alignment
    if price_data.shape == signal_data.shape:
        print("[PASS] Shape alignment")
    else:
        print(f"[FAIL] Shape alignment (price={price_data.shape}, signal={signal_data.shape})")
        return False

    # Check 2: No NaN values in price data
    nan_count = price_data.isna().sum().sum()
    if nan_count == 0:
        print("[PASS] No NaN values")
    else:
        print(f"[WARN] NaN values found: {nan_count} (may be acceptable)")

    # Check 3: Signal data has non-zero values
    signal_count = (signal_data > 0).sum().sum()
    if signal_count > 0:
        print(f"[PASS] Signal data ({signal_count} non-zero signals)")
    else:
        print("[WARN] No signals found (events may have score=0)")

    # Check 4: Price data has valid values
    if (price_data > 0).all().all():
        print("[PASS] Price data validity (all positive)")
    else:
        print("[WARN] Some non-positive prices found")

    print("\n" + "-"*80)
    print("STEP 4: Sample Data Preview")
    print("-"*80)

    print("\nPrice Data (first 5 rows):")
    print(price_data.head())

    print("\nSignal Data (rows with signals):")
    signal_rows = signal_data[(signal_data > 0).any(axis=1)]
    if len(signal_rows) > 0:
        print(signal_rows.head(10))
    else:
        print("  (No signal rows found)")

    print("\n" + "="*80)
    print("TEST COMPLETED SUCCESSFULLY")
    print("="*80)
    print("\n[SUCCESS] The grid search data loading function is working correctly!")
    print("   - Events loaded from events.jsonl")
    print("   - Price data fetched from Tiingo API")
    print("   - DataFrames aligned and validated")
    print("   - Ready for vectorized backtesting")

    return True


if __name__ == "__main__":
    try:
        success = test_data_loading()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
