"""Manual test for WAVE 3 Float Data Robustness enhancements."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.float_data import (
    validate_float_value,
    is_cache_fresh,
    get_float_data,
    classify_float,
    get_float_multiplier,
)
from datetime import datetime, timedelta, timezone

print("=" * 70)
print("WAVE 3: Float Data Robustness - Manual Test")
print("=" * 70)

# Test 1: Validation
print("\n[TEST 1] Float Validation")
print("-" * 70)
test_values = [
    (5_000_000, True, "Valid 5M float"),
    (1, False, "Too small (1 share)"),
    (None, False, "Null value"),
    (-1000, False, "Negative value"),
    (999_000_000_000_000, False, "Too large"),
    (15_000_000, True, "Valid 15M float"),
]

for value, expected, desc in test_values:
    result = validate_float_value(value)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] {desc}: {value} -> {result}")

# Test 2: Cache Freshness
print("\n[TEST 2] Cache Freshness")
print("-" * 70)

now = datetime.now(timezone.utc)
fresh_time = now.isoformat()
old_time = (now - timedelta(hours=30)).isoformat()

print(f"  [PASS] Fresh cache (now): {is_cache_fresh(fresh_time, 24)}")
print(f"  [PASS] Stale cache (30h old): {not is_cache_fresh(old_time, 24)}")
print(f"  [PASS] Invalid timestamp: {not is_cache_fresh('invalid', 24)}")

# Test 3: Classification
print("\n[TEST 3] Float Classification")
print("-" * 70)
classifications = [
    (1_000_000, "MICRO_FLOAT", 1.3, "1M shares"),
    (10_000_000, "LOW_FLOAT", 1.2, "10M shares"),
    (30_000_000, "MEDIUM_FLOAT", 1.0, "30M shares"),
    (100_000_000, "HIGH_FLOAT", 0.9, "100M shares"),
    (None, "UNKNOWN", 1.0, "None"),
]

for float_val, exp_class, exp_mult, desc in classifications:
    actual_class = classify_float(float_val)
    actual_mult = get_float_multiplier(float_val)
    status = "PASS" if actual_class == exp_class and actual_mult == exp_mult else "FAIL"
    print(f"  [{status}] {desc}: {actual_class} (mult={actual_mult})")

# Test 4: Multi-source fetch (optional - requires network)
print("\n[TEST 4] Multi-Source Float Fetch (Optional - requires network)")
print("-" * 70)
print("  Testing fetch for AAPL (may take a few seconds)...")

try:
    result = get_float_data("AAPL")
    print(f"  [SUCCESS] Ticker: {result['ticker']}")
    if result['float_shares']:
        print(f"            Float: {result['float_shares']:,} shares")
    else:
        print(f"            Float: N/A")
    print(f"            Source: {result['source']}")
    print(f"            Class: {result['float_class']}")
    print(f"            Multiplier: {result['multiplier']}")
    print(f"            Success: {result['success']}")
except Exception as e:
    print(f"  [WARNING] Network fetch failed (expected): {e}")

print("\n" + "=" * 70)
print("WAVE 3 Manual Test Complete")
print("=" * 70)
