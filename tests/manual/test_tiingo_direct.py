"""
Direct Tiingo API test - bypasses all caching
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Import Tiingo function
from src.catalyst_bot.market import _tiingo_intraday_series

# Test parameters
ticker = "AAPL"
start_date = "2024-11-01"
end_date = "2024-11-02"
api_key = os.getenv("TIINGO_API_KEY", "").strip()
feature_enabled = os.getenv("FEATURE_TIINGO", "0").strip().lower() in {"1", "true", "yes", "on"}

print("=" * 70)
print("TIINGO DIRECT API TEST")
print("=" * 70)
print(f"Ticker: {ticker}")
print(f"Date range: {start_date} to {end_date}")
print(f"FEATURE_TIINGO: {feature_enabled}")
print(f"API Key present: {bool(api_key)}")
print(f"API Key (first 10 chars): {api_key[:10]}..." if api_key else "API Key: (empty)")
print("=" * 70)

if not feature_enabled:
    print("\n[ERROR] FEATURE_TIINGO is disabled!")
    print("   Set FEATURE_TIINGO=1 in .env")
    sys.exit(1)

if not api_key:
    print("\n[ERROR] TIINGO_API_KEY is missing!")
    sys.exit(1)

print("\n[*] Calling _tiingo_intraday_series...")
try:
    data = _tiingo_intraday_series(
        ticker,
        api_key,
        start_date=start_date,
        end_date=end_date,
        resample_freq="15min",
        after_hours=True,
        timeout=30,
    )

    if data is not None and not data.empty:
        print(f"\n[SUCCESS] Retrieved {len(data)} rows of 15min data")
        print(f"\nFirst 5 rows:")
        print(data.head())
        print(f"\nLast 5 rows:")
        print(data.tail())
        print(f"\nColumns: {list(data.columns)}")
        print(f"\nDate range in data: {data.index[0]} to {data.index[-1]}")
    else:
        print(f"\n[FAILED] Got empty DataFrame or None")
        print(f"   Data: {data}")

except Exception as e:
    print(f"\n[EXCEPTION] {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
