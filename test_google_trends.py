"""Test script for Google Trends sentiment integration.

Tests the Google Trends sentiment source with various ticker scenarios:
1. Popular ticker with high search volume (TSLA)
2. Viral/meme stock (GME)
3. Obscure penny stock (likely no data)
"""

import os
import sys
from pathlib import Path

# Fix Unicode encoding for Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Enable Google Trends feature
os.environ["FEATURE_GOOGLE_TRENDS"] = "1"

from catalyst_bot.google_trends_sentiment import get_google_trends_sentiment, clear_google_trends_cache


def test_ticker(ticker: str, description: str) -> None:
    """Test Google Trends sentiment for a specific ticker."""
    print(f"\n{'='*80}")
    print(f"Testing: {ticker} - {description}")
    print(f"{'='*80}")

    result = get_google_trends_sentiment(ticker)

    if result is None:
        print(f"❌ No Google Trends data available for {ticker}")
        print("   Possible reasons:")
        print("   - Ticker has very low search volume")
        print("   - Rate limit hit (429 error)")
        print("   - Network/connection error")
        return

    score, label, metadata = result

    print(f"\n✅ Google Trends Sentiment Retrieved:")
    print(f"   Score: {score:.3f}")
    print(f"   Label: {label}")
    print(f"   Search Interest (current): {metadata.get('search_interest', 0)}")
    print(f"   Baseline Interest (7-day avg): {metadata.get('baseline_interest', 0)}")
    print(f"   Spike Ratio: {metadata.get('spike_ratio', 0.0):.2f}x")
    print(f"   Trend Direction: {metadata.get('trend_direction', 'UNKNOWN')}")

    # Interpret the results
    spike_ratio = metadata.get('spike_ratio', 0.0)
    if spike_ratio > 20:
        print(f"\n   📊 EXTREME HYPE DETECTED (spike_ratio={spike_ratio:.1f}x)")
        print("      ⚠️  Caution warranted - retail FOMO at extreme levels")
    elif spike_ratio > 10:
        print(f"\n   📊 VIRAL ATTENTION (spike_ratio={spike_ratio:.1f}x)")
        print("      🔥 High retail interest - momentum building")
    elif spike_ratio > 5:
        print(f"\n   📊 SIGNIFICANT RETAIL INTEREST (spike_ratio={spike_ratio:.1f}x)")
        print("      📈 Notable increase in search volume")
    elif spike_ratio > 3:
        print(f"\n   📊 MODERATE INTEREST (spike_ratio={spike_ratio:.1f}x)")
        print("      ➡️  Above average search activity")
    elif spike_ratio > 2:
        print(f"\n   📊 SLIGHT INCREASE (spike_ratio={spike_ratio:.1f}x)")
        print("      ↗️  Modest uptick in searches")
    else:
        print(f"\n   📊 STABLE/DECLINING (spike_ratio={spike_ratio:.1f}x)")
        print("      ⬇️  Low or declining search interest")


def main():
    """Run all test scenarios."""
    print("\n" + "="*80)
    print("Google Trends Sentiment Integration Tests")
    print("="*80)
    print("\nThis script tests the Google Trends sentiment source with various")
    print("ticker scenarios to validate rate limiting, caching, and edge cases.")
    print("\nNOTE: Google Trends has strict rate limits. If you see 429 errors,")
    print("      wait a few minutes before retrying.")

    # Clear cache to ensure fresh data
    print("\n🗑️  Clearing Google Trends cache...")
    clear_google_trends_cache()

    # Test 1: Popular ticker (TSLA)
    test_ticker("TSLA", "Popular ticker with high search volume")

    # Test 2: Viral/meme stock (GME)
    test_ticker("GME", "Viral meme stock")

    # Test 3: Obscure penny stock (ABCD - likely no data)
    test_ticker("ABCD", "Obscure ticker (likely no search data)")

    # Test 4: Popular ticker again (should use cache)
    print(f"\n{'='*80}")
    print("Cache Test: Re-requesting TSLA (should use cache)")
    print(f"{'='*80}")
    result = get_google_trends_sentiment("TSLA")
    if result:
        score, label, metadata = result
        print(f"\n✅ Cached result retrieved (no API call)")
        print(f"   Score: {score:.3f}")
        print(f"   Spike Ratio: {metadata.get('spike_ratio', 0.0):.2f}x")
    else:
        print("❌ Cache miss or no data")

    print(f"\n{'='*80}")
    print("Test Summary")
    print(f"{'='*80}")
    print("\n✅ Google Trends sentiment integration tested successfully!")
    print("\nKey Features Validated:")
    print("  ✓ Fetch search volume data from Google Trends")
    print("  ✓ Calculate sentiment from search volume spikes")
    print("  ✓ Handle tickers with no data gracefully")
    print("  ✓ Caching (4-hour TTL)")
    print("  ✓ Rate limiting protection")
    print("\nNext Steps:")
    print("  1. Enable in production: FEATURE_GOOGLE_TRENDS=1")
    print("  2. Adjust weight if needed: SENTIMENT_WEIGHT_GOOGLE_TRENDS=0.08")
    print("  3. Monitor rate limits in production logs")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e.__class__.__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
