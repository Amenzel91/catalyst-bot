#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test improved ticker extraction patterns."""

import re

# Current patterns from title_ticker.py
_EXCH_PREFIX_CORE = r"(?:NASDAQ|Nasdaq|NYSE(?:\s+American)?|AMEX|NYSE\s*Arca|CBOE|Cboe)"
_OTC_PREFIX = r"(?:OTC(?:MKTS)?|OTCQX|OTCQB|OTC\s*Markets?)"
_TICKER_CORE = r"([A-Z][A-Z0-9.\-]{0,5})"
_DOLLAR_PATTERN = rf"(?:(?<!\w)\${_TICKER_CORE}\b)"

# NEW PATTERNS
# Company + Ticker: Must have uppercase company name followed by ticker in parens
# Ticker must be 2-5 uppercase letters/numbers/dots (no lowercase, no long numbers)
_COMPANY_TICKER_PATTERN = r"[A-Z][A-Za-z0-9&\.\-]*(?:\s+(?:Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|L\.P\.))?\s*\(([A-Z]{2,5}(?:\.[A-Z])?)\)"

# Headline Start: 2-5 uppercase at start with colon (not "Price:", "Update:", etc.)
# Excluded common words that appear at headline start
_HEADLINE_EXCLUSIONS = {"PRICE", "UPDATE", "ALERT", "NEWS", "WATCH", "FLASH", "BRIEF"}
_HEADLINE_START_TICKER = r"^([A-Z]{2,5}):\s+"

# Standalone with context (not recommended for Phase 1)
_STANDALONE_CONTEXT_TICKER = (
    r"\b([A-Z]{2,5})\s+(?:stock|shares|share|equity|options?)\b"
)


def build_current_regex(allow_otc=False):
    """Build current regex (exchange + dollar tickers only)."""
    exch_prefix = _EXCH_PREFIX_CORE
    if allow_otc:
        exch_prefix = rf"(?:{_EXCH_PREFIX_CORE}|{_OTC_PREFIX})"

    exch_pattern = rf"\b{exch_prefix}\s*[:\-]\s*\$?{_TICKER_CORE}\b"
    combined = rf"{exch_pattern}|{_DOLLAR_PATTERN}"
    return re.compile(combined, re.IGNORECASE)


def build_improved_regex(allow_otc=False):
    """Build improved regex (adds company+ticker and headline patterns)."""
    exch_prefix = _EXCH_PREFIX_CORE
    if allow_otc:
        exch_prefix = rf"(?:{_EXCH_PREFIX_CORE}|{_OTC_PREFIX})"

    # Exchange pattern can be case-insensitive for exchange names
    exch_pattern = rf"\b{exch_prefix}\s*[:\-]\s*\$?{_TICKER_CORE}\b"

    # Company+ticker and headline patterns must be case-sensitive for tickers
    # So we compile exchange pattern with IGNORECASE, but new patterns without
    # Combine exchange (case-insensitive) with new patterns (case-sensitive)
    # Since we can't mix flags in one regex, we need all patterns to be case-sensitive
    # and manually handle case variations in exchange names

    # Make exchange pattern case-insensitive by including variations
    exch_casefold = r"(?:[Nn][Aa][Ss][Dd][Aa][Qq]|[Nn][Yy][Ss][Ee](?:\s+[Aa][Mm][Ee][Rr][Ii][Cc][Aa][Nn])?|[Aa][Mm][Ee][Xx]|[Nn][Yy][Ss][Ee]\s*[Aa][Rr][Cc][Aa]|[Cc][Bb][Oo][Ee])"
    exch_pattern_strict = rf"\b{exch_casefold}\s*[:\-]\s*\$?{_TICKER_CORE}\b"

    # Pattern priority: most specific first, all case-sensitive now
    combined = rf"{exch_pattern_strict}|{_COMPANY_TICKER_PATTERN}|{_HEADLINE_START_TICKER}|{_DOLLAR_PATTERN}"
    return re.compile(combined)


def extract_tickers(text, pattern):
    """Extract all unique tickers from text using pattern."""
    seen = set()
    out = []
    for m in pattern.finditer(text):
        raw = next((g for g in m.groups() if g), None)
        if not raw:
            continue
        t = raw.strip().upper()

        # Filter out headline exclusions (PRICE, UPDATE, etc.)
        if t in _HEADLINE_EXCLUSIONS:
            continue

        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def test_patterns():
    """Compare current vs improved patterns."""
    current = build_current_regex()
    improved = build_improved_regex()

    tests = [
        # ===== EXISTING PATTERNS (Should work with both) =====
        (
            "Exchange-Qualified",
            [
                ("Alpha (Nasdaq: ABCD) announces merger", ["ABCD"]),
                ("Tesla Stock (Nasdaq: TSLA) Jumps", ["TSLA"]),
                ("News (NYSE: XYZ) and more", ["XYZ"]),
                ("Breaking (NYSE American: ABC) news", ["ABC"]),
            ],
        ),
        (
            "Dollar Tickers",
            [
                ("$NVDA shares surge 15%", ["NVDA"]),
                ("$AAPL hits new high", ["AAPL"]),
                ("$TSLA deliveries beat", ["TSLA"]),
                ("Price: $GOOGL at $150", ["GOOGL"]),
            ],
        ),
        # ===== NEW PATTERNS (Should only work with improved) =====
        (
            "Company + Ticker",
            [
                ("Apple (AAPL) Reports Strong Quarter", ["AAPL"]),
                ("Tesla Inc. (TSLA) reports Q3 earnings", ["TSLA"]),
                ("Amazon.com Inc. (AMZN) Announces New Services", ["AMZN"]),
                ("Nvidia Corp. (NVDA) Beats Estimates", ["NVDA"]),
                ("Boeing Co. (BA) announces layoffs", ["BA"]),
                ("Meta Platforms Inc. (META) Q4 results", ["META"]),
                ("Alphabet Inc. (GOOGL) search revenue", ["GOOGL"]),
            ],
        ),
        (
            "Headline Start",
            [
                ("TSLA: Deliveries Beat Estimates", ["TSLA"]),
                ("AAPL: Reports Strong Q3", ["AAPL"]),
                ("NVDA: AI Revenue Soars 200%", ["NVDA"]),
                ("BA: Manufacturing Issues Continue", ["BA"]),
            ],
        ),
        # ===== FALSE POSITIVES (Should NOT match) =====
        (
            "No Ticker Present",
            [
                ("Apple reports strong quarter", []),
                ("Tesla announces new model", []),
                ("Stock market rallies today", []),
                ("Breaking news from CEO", []),
            ],
        ),
        (
            "Invalid Ticker Format",
            [
                ("Company (ABC123) announces", []),  # Too long
                ("Firm (ab) reports", []),  # Lowercase
                ("News (A) today", []),  # Too short (single char)
                ("Item (ABCDEFG) test", []),  # Way too long
            ],
        ),
        (
            "Common Acronyms",
            [
                ("CEO announces new strategy", []),
                ("USA stocks rally today", []),
                ("AI technology advances", []),
                ("FBI investigates company", []),
            ],
        ),
    ]

    print("=" * 100)
    print("TICKER EXTRACTION PATTERN COMPARISON")
    print("=" * 100)

    total_tests = 0
    improved_wins = 0
    current_correct = 0

    for category, cases in tests:
        print(f"\n{'=' * 100}")
        print(f"CATEGORY: {category}")
        print(f"{'=' * 100}")

        for headline, expected in cases:
            total_tests += 1
            current_result = extract_tickers(headline, current)
            improved_result = extract_tickers(headline, improved)

            current_match = current_result == expected
            improved_match = improved_result == expected

            if current_match:
                current_correct += 1

            if improved_match and not current_match:
                improved_wins += 1
                status = "NEW MATCH"
            elif improved_match and current_match:
                status = "BOTH OK"
            elif not improved_match and current_match:
                status = "REGRESSION"
            else:
                status = "BOTH FAIL"

            print(f"\n[{status}]")
            print(f"  Headline:  {headline!r}")
            print(f"  Expected:  {expected}")
            print(f"  Current:   {current_result} {'OK' if current_match else 'MISS'}")
            print(
                f"  Improved:  {improved_result} {'OK' if improved_match else 'MISS'}"
            )

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total test cases:        {total_tests}")
    print(
        f"Current correct:         {current_correct} ({current_correct/total_tests*100:.1f}%)"
    )
    print(f"New matches (improved):  {improved_wins}")
    print(f"Coverage improvement:    +{improved_wins/total_tests*100:.1f}%")


def test_exclusions():
    """Test that common non-ticker words are properly handled."""
    improved = build_improved_regex()

    # These should NOT extract tickers
    false_positives = [
        "CEO announces new strategy",
        "USA economy grows",
        "AI advances rapidly",
        "SEC files charges",
        "FDA approves drug",
        "IPO market heats up",
        "ETF flows continue",
    ]

    print("\n" + "=" * 100)
    print("FALSE POSITIVE PREVENTION TEST")
    print("=" * 100)

    all_pass = True
    for headline in false_positives:
        result = extract_tickers(headline, improved)
        status = "PASS" if not result else "FAIL"
        if result:
            all_pass = False
        print(f"\n[{status}] {headline!r}")
        print(f"  Extracted: {result}")
        print(f"  Expected:  []")

    if all_pass:
        print("\nAll false positive tests passed!")
    else:
        print("\nSome false positives detected - consider adding exclusion list")


def test_edge_cases():
    """Test edge cases and special scenarios."""
    improved = build_improved_regex()

    edge_cases = [
        # Multiple tickers in one headline
        ("Apple (AAPL) partners with Microsoft (MSFT)", ["AAPL", "MSFT"]),
        ("$TSLA and $NVDA lead tech rally", ["TSLA", "NVDA"]),
        ("NASDAQ: AAPL and NYSE: BA both up", ["AAPL", "BA"]),
        # Class shares (BRK.A, BF.B)
        ("Berkshire Hathaway (BRK.A) reports", ["BRK.A"]),
        ("Brown-Forman (BF.B) dividend", ["BF.B"]),
        # Mixed formats
        ("TSLA: Tesla Inc. (TSLA) stock jumps", ["TSLA"]),  # Should dedupe
        ("$AAPL (NASDAQ: AAPL) hits high", ["AAPL"]),  # Should dedupe
        # Company names with special chars
        ("Amazon.com Inc. (AMZN) earnings", ["AMZN"]),
        ("AT&T Inc. (T) merger news", ["T"]),
        ("L Brands Inc. (LB) reports", ["LB"]),
    ]

    print("\n" + "=" * 100)
    print("EDGE CASE TESTS")
    print("=" * 100)

    for headline, expected in edge_cases:
        result = extract_tickers(headline, improved)
        status = "PASS" if result == expected else "FAIL"
        print(f"\n[{status}] {headline!r}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")


if __name__ == "__main__":
    print("\n" + "=" * 100)
    print("IMPROVED TICKER EXTRACTION PATTERN TESTS")
    print("=" * 100)

    test_patterns()
    test_exclusions()
    test_edge_cases()

    print("\n" + "=" * 100)
    print("TEST SUITE COMPLETE")
    print("=" * 100)
