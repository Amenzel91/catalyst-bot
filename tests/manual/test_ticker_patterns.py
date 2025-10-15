#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test ticker extraction patterns on real-world headlines."""

from src.catalyst_bot.title_ticker import ticker_from_title, extract_tickers_from_title

def test_current_patterns():
    """Test current regex patterns to identify gaps."""
    tests = [
        # Works (exchange-qualified)
        ("Alpha (Nasdaq: ABCD) announces merger", {}, ["ABCD"]),
        ("Tesla Stock (Nasdaq: TSLA) Jumps", {}, ["TSLA"]),
        ("News (NYSE: XYZ) and more", {}, ["XYZ"]),
        ("OTC: GRLT updates", {"allow_otc": True}, ["GRLT"]),

        # Dollar tickers (should work by default)
        ("$NVDA shares surge 15%", {}, ["NVDA"]),
        ("$AAPL hits new high", {}, ["AAPL"]),
        ("$TSLA deliveries beat", {}, ["TSLA"]),

        # FAILS - Company name + ticker in parens (NO exchange)
        ("Apple (AAPL) Reports Strong Quarter", {}, []),
        ("Tesla Inc. (TSLA) reports Q3 earnings", {}, []),
        ("Amazon.com Inc. (AMZN) Announces...", {}, []),

        # FAILS - Standalone ticker (no qualifier)
        ("AAPL hits new high", {}, []),
        ("TSLA Shares Surge on Delivery Numbers", {}, []),
        ("NVDA Stock Jumps 20%", {}, []),
    ]

    print("=" * 80)
    print("CURRENT TICKER EXTRACTION PATTERNS")
    print("=" * 80)

    for headline, opts, expected in tests:
        result = extract_tickers_from_title(headline, **opts)
        status = "PASS" if result == expected else "FAIL"
        print(f"\n[{status}]")
        print(f"  Headline: {headline!r}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")

if __name__ == "__main__":
    test_current_patterns()
