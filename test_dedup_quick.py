"""Quick test of enhanced deduplication functions."""
from catalyst_bot.dedupe import signature_from, temporal_dedup_key
import time

print("=" * 60)
print("TESTING ENHANCED DEDUPLICATION")
print("=" * 60)

# Test 1: Ticker-aware signatures
print("\n1. Testing ticker-aware signatures:")
print("-" * 40)
title = "Company announces Q3 earnings beat"
url = "https://example.com/earnings"

sig_aapl = signature_from(title, url, ticker="AAPL")
sig_tsla = signature_from(title, url, ticker="TSLA")
sig_no_ticker = signature_from(title, url)

print(f"Title: {title}")
print(f"URL: {url}")
print(f"\nAPPL signature: {sig_aapl}")
print(f"TSLA signature: {sig_tsla}")
print(f"No ticker sig:  {sig_no_ticker}")
print(f"\nAPPL != TSLA: {sig_aapl != sig_tsla} (Expected: True)")
print(f"AAPL != No ticker: {sig_aapl != sig_no_ticker} (Expected: True)")

# Test 2: Backward compatibility
print("\n\n2. Testing backward compatibility:")
print("-" * 40)
title2 = "Breaking news alert"
url2 = "https://example.com/news"

sig_old1 = signature_from(title2, url2)
sig_old2 = signature_from(title2, url2)

print(f"Title: {title2}")
print(f"Signature 1: {sig_old1}")
print(f"Signature 2: {sig_old2}")
print(f"Same signature: {sig_old1 == sig_old2} (Expected: True)")
print(f"SHA1 length (40): {len(sig_old1) == 40} (Expected: True)")

# Test 3: Temporal dedup with 30-min buckets
print("\n\n3. Testing temporal deduplication:")
print("-" * 40)
ticker = "AAPL"
title3 = "Apple announces new product"

# Use timestamps that align to bucket boundaries
# Bucket 0: 0-1799, Bucket 1: 1800-3599, etc.
ts1 = 1800  # Start of bucket 1
ts2 = ts1 + (10 * 60)  # +10 minutes (1800 -> 2400, still in bucket 1)
ts3 = ts1 + (35 * 60)  # +35 minutes (1800 -> 3900, in bucket 2)

key1 = temporal_dedup_key(ticker, title3, ts1)
key2 = temporal_dedup_key(ticker, title3, ts2)
key3 = temporal_dedup_key(ticker, title3, ts3)

print(f"Ticker: {ticker}")
print(f"Title: {title3}")
print(f"\nTimestamp 1: {ts1}")
print(f"Timestamp 2: {ts2} (+10 min)")
print(f"Timestamp 3: {ts3} (+35 min)")
print(f"\nKey 1: {key1}")
print(f"Key 2: {key2}")
print(f"Key 3: {key3}")
print(f"\nSame bucket (ts1 == ts2): {key1 == key2} (Expected: True)")
print(f"Diff bucket (ts1 != ts3): {key1 != key3} (Expected: True)")

# Test 4: Temporal dedup with different tickers
print("\n\n4. Testing temporal dedup with different tickers:")
print("-" * 40)
title4 = "Earnings beat announced"
timestamp = int(time.time())

key_aapl = temporal_dedup_key("AAPL", title4, timestamp)
key_tsla = temporal_dedup_key("TSLA", title4, timestamp)

print(f"Title: {title4}")
print(f"Timestamp: {timestamp}")
print(f"\nAPPL key: {key_aapl}")
print(f"TSLA key: {key_tsla}")
print(f"Different tickers different keys: {key_aapl != key_tsla} (Expected: True)")

# Summary
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)

tests_passed = 0
tests_total = 5

if sig_aapl != sig_tsla:
    print("[PASS] Ticker-aware signatures work")
    tests_passed += 1
else:
    print("[FAIL] Ticker-aware signatures FAILED")

if sig_old1 == sig_old2 and len(sig_old1) == 40:
    print("[PASS] Backward compatibility maintained")
    tests_passed += 1
else:
    print("[FAIL] Backward compatibility FAILED")

if key1 == key2:
    print("[PASS] Same time bucket detection works")
    tests_passed += 1
else:
    print("[FAIL] Same time bucket detection FAILED")

if key1 != key3:
    print("[PASS] Different time bucket detection works")
    tests_passed += 1
else:
    print("[FAIL] Different time bucket detection FAILED")

if key_aapl != key_tsla:
    print("[PASS] Temporal dedup distinguishes tickers")
    tests_passed += 1
else:
    print("[FAIL] Temporal dedup ticker distinction FAILED")

print(f"\nPassed: {tests_passed}/{tests_total}")
if tests_passed == tests_total:
    print("\n*** ALL TESTS PASSED! ***")
else:
    print(f"\n*** {tests_total - tests_passed} TESTS FAILED ***")

print("=" * 60)
