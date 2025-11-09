#!/usr/bin/env python
"""Simple test to verify catalyst badge extraction works."""

from catalyst_bot.catalyst_badges import extract_catalyst_badges

# Test 1: Earnings detection
badges1 = extract_catalyst_badges(None, "AAPL beats Q4 earnings")
assert "EARNINGS" in str(badges1), f"Failed: {badges1}"
print("[OK] Test 1 passed: Earnings detection")

# Test 2: FDA detection
badges2 = extract_catalyst_badges(None, "FDA approves new drug")
assert "FDA" in str(badges2), f"Failed: {badges2}"
print("[OK] Test 2 passed: FDA detection")

# Test 3: Multiple badges with priority
badges3 = extract_catalyst_badges(None, "FDA approval boosts earnings outlook")
assert len(badges3) >= 2, f"Failed: {badges3}"
assert "FDA" in str(badges3[0]), f"Failed priority: {badges3}"
print("[OK] Test 3 passed: Multiple badges with priority")

# Test 4: Classification tags
classification = {"tags": ["merger", "acquisition"]}
badges4 = extract_catalyst_badges(classification, "Deal announced")
assert "M&A" in str(badges4) or "MERGER" in str(badges4), f"Failed: {badges4}"
print("[OK] Test 4 passed: Classification tags")

# Test 5: No matches returns NEWS
badges5 = extract_catalyst_badges(None, "Random update")
assert "NEWS" in str(badges5), f"Failed: {badges5}"
print("[OK] Test 5 passed: Fallback to NEWS badge")

# Test 6: Max badges limit
badges6 = extract_catalyst_badges(
    None,
    "FDA approves drug, earnings beat, merger announced, guidance raised",
    max_badges=2
)
assert len(badges6) == 2, f"Failed: {len(badges6)} badges instead of 2"
print("[OK] Test 6 passed: Max badges limit")

print("\n" + "=" * 40)
print("ALL TESTS PASSED!")
print("=" * 40)
print(f"\nBadge system is working correctly.")
print(f"Example output: {len(badges1)} badge(s) detected for earnings alert")
