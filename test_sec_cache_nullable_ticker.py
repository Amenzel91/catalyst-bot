#!/usr/bin/env python3
"""Test SEC LLM cache with nullable ticker field."""

from pathlib import Path

from src.catalyst_bot.sec_llm_cache import SECLLMCache

# Clean up test database
test_db = Path("data/sec_llm_cache_test.db")
if test_db.exists():
    test_db.unlink()
    print("Cleaned up old test database\n")

print("=" * 80)
print("TEST: SEC LLM Cache with ticker=None")
print("=" * 80)

# Create cache instance
cache = SECLLMCache(db_path=str(test_db), ttl_hours=72)

# Test 1: Cache filing with ticker
print("\n1. Caching filing WITH ticker...")
result1 = cache.cache_sec_analysis(
    filing_id="test_filing_1",
    ticker="AAPL",
    filing_type="8-K",
    analysis_result={
        "summary": "Apple files 8-K",
        "llm_sentiment": 0.5,
        "llm_confidence": 0.8,
    },
    document_hash="abc123",
)
print(f"   Cached: {result1}")
assert result1, "Should cache successfully with ticker"

# Retrieve it
cached1 = cache.get_cached_sec_analysis(
    filing_id="test_filing_1",
    ticker="AAPL",
    filing_type="8-K",
    document_hash="abc123",
)
print(f"   Retrieved: {cached1 is not None}")
assert cached1 is not None, "Should retrieve cached result"
assert cached1["summary"] == "Apple files 8-K", "Summary should match"
print("[PASS] Filing with ticker cached and retrieved successfully")

# Test 2: Cache filing with ticker=None
print("\n2. Caching filing WITHOUT ticker (ticker=None)...")
result2 = cache.cache_sec_analysis(
    filing_id="test_filing_2",
    ticker=None,  # This is the key test case
    filing_type="424B5",
    analysis_result={
        "summary": "No ticker filing",
        "llm_sentiment": -0.5,
        "llm_confidence": 0.7,
    },
    document_hash="def456",
)
print(f"   Cached: {result2}")
assert result2, "Should cache successfully with ticker=None"

# Retrieve it
cached2 = cache.get_cached_sec_analysis(
    filing_id="test_filing_2",
    ticker=None,  # Must match None
    filing_type="424B5",
    document_hash="def456",
)
print(f"   Retrieved: {cached2 is not None}")
assert cached2 is not None, "Should retrieve cached result with ticker=None"
assert cached2["summary"] == "No ticker filing", "Summary should match"
print("[PASS] Filing with ticker=None cached and retrieved successfully")

# Test 3: Verify cache miss for different ticker
print("\n3. Testing cache miss for different parameters...")
cached3 = cache.get_cached_sec_analysis(
    filing_id="test_filing_2",
    ticker="WRONG",  # Different ticker should miss
    filing_type="424B5",
    document_hash="def456",
)
print(f"   Cache miss: {cached3 is None}")
assert cached3 is None, "Should be cache miss for different ticker"
print("[PASS] Cache correctly misses for different parameters")

print("\n" + "=" * 80)
print("ALL TESTS PASSED")
print("=" * 80)
print("\nSEC LLM cache now supports ticker=None filings!")

# Clean up
test_db.unlink()
print("Test database cleaned up")
