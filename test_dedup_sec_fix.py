#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify SEC deduplication fix.

This script tests that:
1. Same SEC filing from different URLs generates same signature
2. Different SEC filings generate different signatures
3. Non-SEC URLs still work correctly
4. Edge cases are handled (missing accession, malformed URLs)
"""

import sys
import io

# Set UTF-8 encoding for stdout to handle checkmarks
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.catalyst_bot.dedupe import signature_from, _extract_sec_accession_number


def test_accession_extraction():
    """Test accession number extraction from various URL formats."""
    print("\n=== Testing Accession Number Extraction ===")

    test_cases = [
        # Pattern 1: Query parameter
        (
            "https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-249922",
            "0001193125-24-249922",
            "Query parameter format"
        ),
        # Pattern 2: Path with dashes
        (
            "https://www.sec.gov/Archives/edgar/data/1234/0001193125-24-249922/d12345.htm",
            "0001193125-24-249922",
            "Path with dashes"
        ),
        # Pattern 3: Path without dashes (18 digits)
        (
            "https://www.sec.gov/Archives/edgar/data/1234/000119312524249922/d12345.htm",
            "0001193125-24-249922",
            "Path without dashes"
        ),
        # Pattern 4: Filename
        (
            "https://www.sec.gov/Archives/edgar/data/1234/0001193125-24-249922.txt",
            "0001193125-24-249922",
            "Filename format"
        ),
        # Non-SEC URL
        (
            "https://www.globenewswire.com/news/2024/10/24/TOVX-announces-earnings",
            None,
            "Non-SEC URL (should return None)"
        ),
        # Malformed URL
        (
            "",
            None,
            "Empty URL"
        ),
        # SEC URL without accession
        (
            "https://www.sec.gov/edgar/browse/",
            None,
            "SEC URL without accession number"
        ),
    ]

    all_passed = True
    for url, expected, description in test_cases:
        result = _extract_sec_accession_number(url)
        passed = result == expected
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} - {description}")
        if not passed:
            print(f"  Expected: {expected}")
            print(f"  Got: {result}")
            all_passed = False

    return all_passed


def test_duplicate_detection():
    """Test that same SEC filing from different URLs generates same signature."""
    print("\n=== Testing Duplicate Detection ===")

    # Same filing, different URLs (should generate SAME signature)
    url1 = "https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-249922"
    url2 = "https://www.sec.gov/Archives/edgar/data/6201/000119312524249922/tovx-8k.htm"
    url3 = "https://www.sec.gov/Archives/edgar/data/6201/0001193125-24-249922/tovx-8k.htm"

    title = "TOVX 8-K filing"
    ticker = "TOVX"

    sig1 = signature_from(title, url1, ticker)
    sig2 = signature_from(title, url2, ticker)
    sig3 = signature_from(title, url3, ticker)

    print(f"URL 1 signature: {sig1}")
    print(f"URL 2 signature: {sig2}")
    print(f"URL 3 signature: {sig3}")

    if sig1 == sig2 == sig3:
        print("✓ PASS - Same filing from different URLs generates same signature")
        return True
    else:
        print("✗ FAIL - Different signatures for same filing")
        return False


def test_different_filings():
    """Test that different SEC filings generate different signatures."""
    print("\n=== Testing Different Filings ===")

    # Different filings (should generate DIFFERENT signatures)
    url1 = "https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-249922"
    url2 = "https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-999999"

    title = "TOVX 8-K filing"
    ticker = "TOVX"

    sig1 = signature_from(title, url1, ticker)
    sig2 = signature_from(title, url2, ticker)

    print(f"Filing 1 signature: {sig1}")
    print(f"Filing 2 signature: {sig2}")

    if sig1 != sig2:
        print("✓ PASS - Different filings generate different signatures")
        return True
    else:
        print("✗ FAIL - Same signature for different filings")
        return False


def test_non_sec_urls():
    """Test that non-SEC URLs still work correctly."""
    print("\n=== Testing Non-SEC URLs ===")

    # Non-SEC URLs should use original logic (URL-based)
    url1 = "https://www.globenewswire.com/news/2024/10/24/TOVX-announces-earnings"
    url2 = "https://www.businesswire.com/news/2024/10/24/TOVX-announces-earnings"

    title = "TOVX announces earnings"
    ticker = "TOVX"

    sig1 = signature_from(title, url1, ticker)
    sig2 = signature_from(title, url2, ticker)

    print(f"GlobeNewswire signature: {sig1}")
    print(f"BusinessWire signature: {sig2}")

    if sig1 != sig2:
        print("✓ PASS - Different sources generate different signatures")
        return True
    else:
        print("✗ FAIL - Same signature for different sources")
        return False


def test_edge_cases():
    """Test edge cases: missing ticker, empty URLs, etc."""
    print("\n=== Testing Edge Cases ===")

    all_passed = True

    # Test 1: Missing ticker
    try:
        sig = signature_from(
            "Test title",
            "https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-249922",
            ""
        )
        print("✓ PASS - Missing ticker handled")
    except Exception as e:
        print(f"✗ FAIL - Missing ticker raised exception: {e}")
        all_passed = False

    # Test 2: Empty URL
    try:
        sig = signature_from("Test title", "", "TOVX")
        print("✓ PASS - Empty URL handled")
    except Exception as e:
        print(f"✗ FAIL - Empty URL raised exception: {e}")
        all_passed = False

    # Test 3: Malformed URL
    try:
        sig = signature_from("Test title", "not-a-valid-url", "TOVX")
        print("✓ PASS - Malformed URL handled")
    except Exception as e:
        print(f"✗ FAIL - Malformed URL raised exception: {e}")
        all_passed = False

    # Test 4: SEC URL without accession (should fall back to URL-based)
    try:
        sig1 = signature_from("Test", "https://www.sec.gov/edgar/browse/", "TOVX")
        sig2 = signature_from("Test", "https://www.sec.gov/edgar/search/", "TOVX")
        if sig1 != sig2:
            print("✓ PASS - SEC URLs without accession use URL-based dedup")
        else:
            print("✗ FAIL - SEC URLs without accession should generate different signatures")
            all_passed = False
    except Exception as e:
        print(f"✗ FAIL - SEC URL without accession raised exception: {e}")
        all_passed = False

    return all_passed


def main():
    print("=" * 60)
    print("SEC DEDUPLICATION FIX - TEST SUITE")
    print("=" * 60)

    results = []
    results.append(("Accession Extraction", test_accession_extraction()))
    results.append(("Duplicate Detection", test_duplicate_detection()))
    results.append(("Different Filings", test_different_filings()))
    results.append(("Non-SEC URLs", test_non_sec_urls()))
    results.append(("Edge Cases", test_edge_cases()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed! SEC deduplication fix is working correctly.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
