"""
Test script for volume-price divergence detection.

This script tests the divergence detection logic with various scenarios.
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.volume_price_divergence import detect_divergence


def test_divergence_patterns():
    """Test various divergence patterns."""

    print("=" * 80)
    print("VOLUME-PRICE DIVERGENCE DETECTION TEST")
    print("=" * 80)
    print()

    test_cases = [
        {
            "name": "WEAK RALLY - Price up 5%, Volume down 40%",
            "ticker": "AAPL",
            "price_change_pct": 0.05,
            "volume_change_pct": -0.40,
            "expected": "WEAK_RALLY",
        },
        {
            "name": "STRONG SELLOFF REVERSAL - Price down 4%, Volume down 35%",
            "ticker": "TSLA",
            "price_change_pct": -0.04,
            "volume_change_pct": -0.35,
            "expected": "STRONG_SELLOFF_REVERSAL",
        },
        {
            "name": "CONFIRMED RALLY - Price up 6%, Volume up 80%",
            "ticker": "NVDA",
            "price_change_pct": 0.06,
            "volume_change_pct": 0.80,
            "expected": "CONFIRMED_RALLY",
        },
        {
            "name": "CONFIRMED SELLOFF - Price down 5%, Volume up 70%",
            "ticker": "AMD",
            "price_change_pct": -0.05,
            "volume_change_pct": 0.70,
            "expected": "CONFIRMED_SELLOFF",
        },
        {
            "name": "NO SIGNAL - Small price move (1%)",
            "ticker": "MSFT",
            "price_change_pct": 0.01,
            "volume_change_pct": -0.40,
            "expected": None,
        },
        {
            "name": "NO SIGNAL - Small volume move (10%)",
            "ticker": "GOOGL",
            "price_change_pct": 0.05,
            "volume_change_pct": 0.10,
            "expected": None,
        },
    ]

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print(f"  Ticker: {test['ticker']}")
        print(f"  Price Change: {test['price_change_pct']*100:+.1f}%")
        print(f"  Volume Change: {test['volume_change_pct']*100:+.1f}%")

        result = detect_divergence(
            ticker=test["ticker"],
            price_change_pct=test["price_change_pct"],
            volume_change_pct=test["volume_change_pct"],
        )

        if result is None:
            divergence_type = None
            print("  Result: No divergence detected")
        else:
            divergence_type = result["divergence_type"]
            print(f"  Result: {divergence_type}")
            print(f"  Signal Strength: {result['signal_strength']}")
            print(f"  Sentiment Adjustment: {result['sentiment_adjustment']:+.3f}")
            print(f"  Interpretation: {result['interpretation']}")

        # Check if expected matches result
        if divergence_type == test["expected"]:
            print("  [PASS]")
            passed += 1
        else:
            print(f"  [FAIL] - Expected {test['expected']}, got {divergence_type}")
            failed += 1

        print()

    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_divergence_patterns()
    sys.exit(0 if success else 1)
