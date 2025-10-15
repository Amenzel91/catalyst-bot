"""
Test Tiingo integration with a fresh ticker (not in cache)
Simulates the exact code path used during backtesting
"""
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Add src to path
sys.path.insert(0, 'src')

from catalyst_bot.historical_bootstrapper import HistoricalBootstrapper

print("=" * 70)
print("FRESH TICKER TEST - Tiingo Integration")
print("=" * 70)

# Create a minimal bootstrapper instance just to access the method
bootstrapper = HistoricalBootstrapper(
    start_date="2024-10-01",
    end_date="2024-10-03",
    sources=["sec_8k"],
    batch_size=10,
)

# Test parameters - using a ticker unlikely to be in cache
test_ticker = "TSLA"  # Popular ticker, good data
rejection_date = datetime(2024, 10, 1, 14, 30, 0, tzinfo=timezone.utc)
rejection_price = 250.00

print(f"\nTest Parameters:")
print(f"  Ticker: {test_ticker}")
print(f"  Rejection Date: {rejection_date}")
print(f"  Rejection Price: ${rejection_price}")
print(f"\nEnvironment:")
print(f"  FEATURE_TIINGO: {os.getenv('FEATURE_TIINGO')}")
print(f"  API Key Present: {bool(os.getenv('TIINGO_API_KEY'))}")
print("=" * 70)

print("\n[*] Calling _fetch_outcomes_batch...")
print("    This will show DEBUG output if Tiingo is used\n")

try:
    # Call the exact method used during backtesting
    outcomes = bootstrapper._fetch_outcomes_batch(
        test_ticker,
        rejection_date,
        rejection_price
    )

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    if outcomes:
        print(f"\n[SUCCESS] Retrieved {len(outcomes)} timeframe outcomes:")
        for timeframe, data in outcomes.items():
            print(f"\n  {timeframe}:")
            print(f"    Close: ${data.get('close', 'N/A')}")
            print(f"    Return: {data.get('return_pct', 'N/A')}%")
            if 'high' in data:
                print(f"    High: ${data['high']} (+{data.get('high_return_pct', 'N/A')}%)")
                print(f"    Low: ${data['low']} ({data.get('low_return_pct', 'N/A')}%)")
    else:
        print("\n[WARNING] No outcomes returned (empty dict)")
        print("  This could mean:")
        print("  - Ticker data unavailable for this date")
        print("  - API errors occurred")

    print("\n" + "=" * 70)
    print("Cache Statistics:")
    print(f"  Memory hits: {bootstrapper.stats['cache_hits']}")
    print(f"  Disk hits: {bootstrapper.stats['disk_cache_hits']}")
    print(f"  Misses: {bootstrapper.stats['cache_misses']}")
    print(f"  Bulk fetches: {bootstrapper.stats['bulk_fetches']}")
    print("=" * 70)

except Exception as e:
    print(f"\n[EXCEPTION] {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Look for DEBUG and TIINGO log messages above!")
print("=" * 70)
