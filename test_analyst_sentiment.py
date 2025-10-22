"""Test script for analyst recommendations sentiment source.

Tests the newly implemented _fetch_analyst_recommendations function with real
ticker data from Finnhub API.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.sentiment_sources import _fetch_analyst_recommendations


def test_analyst_sentiment():
    """Test analyst recommendations for several well-known tickers."""

    # Get Finnhub API key from environment
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        print("ERROR: FINNHUB_API_KEY not set in environment")
        print("Please set FINNHUB_API_KEY in .env file or environment variables")
        return

    print("=" * 80)
    print("ANALYST RECOMMENDATIONS SENTIMENT TEST")
    print("=" * 80)
    print()

    # Test with several tickers
    test_tickers = [
        "AAPL",   # Apple - well-covered stock with many analysts
        "TSLA",   # Tesla - high-profile stock with diverse opinions
        "NVDA",   # NVIDIA - recent AI boom, likely strong buy ratings
        "AMD",    # AMD - semiconductor sector
        "MSFT",   # Microsoft - stable tech giant
    ]

    for ticker in test_tickers:
        print(f"\n{'=' * 80}")
        print(f"Testing: {ticker}")
        print('=' * 80)

        result = _fetch_analyst_recommendations(ticker, api_key)

        if result is None:
            print(f"  ❌ No analyst data returned for {ticker}")
            continue

        score, label, n_recommendations, details = result

        print(f"\n  Sentiment Score: {score:.3f}")
        print(f"  Sentiment Label: {label}")
        print(f"  Recommendations: {n_recommendations}")

        print(f"\n  Analyst Breakdown:")
        print(f"    Strong Buy:  {details.get('strong_buy', 0):3d}")
        print(f"    Buy:         {details.get('buy', 0):3d}")
        print(f"    Hold:        {details.get('hold', 0):3d}")
        print(f"    Sell:        {details.get('sell', 0):3d}")
        print(f"    Strong Sell: {details.get('strong_sell', 0):3d}")
        print(f"    -----------")
        print(f"    Total:       {details.get('total_analysts', 0):3d}")

        print(f"\n  Consensus: {details.get('consensus', 'N/A')}")

        print(f"\n  Recent Changes (last 7-30 days):")
        print(f"    Recent Upgrade:    {'✅ YES' if details.get('recent_upgrade') else '❌ No'}")
        print(f"    Recent Downgrade:  {'⚠️  YES' if details.get('recent_downgrade') else '✅ No'}")
        print(f"    Recent Initiation: {'🆕 YES' if details.get('recent_initiation') else '❌ No'}")

        print(f"\n  Sentiment Calculation:")
        print(f"    Base Score:          {details.get('base_score', 0):.3f}")
        print(f"    Sentiment Adjustment: {details.get('sentiment_adjustment', 0):.3f}")
        print(f"    Final Score:         {score:.3f}")

        # Interpret the result
        if score >= 0.5:
            interpretation = "STRONG BULLISH - Analysts favor buying"
        elif score >= 0.15:
            interpretation = "BULLISH - Positive analyst consensus"
        elif score >= -0.15:
            interpretation = "NEUTRAL - Mixed analyst opinions"
        elif score >= -0.5:
            interpretation = "BEARISH - Negative analyst consensus"
        else:
            interpretation = "STRONG BEARISH - Analysts favor selling"

        print(f"\n  💡 Interpretation: {interpretation}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nNOTE: Analyst sentiment is now integrated into the bot's sentiment pipeline.")
    print("To enable, set in .env:")
    print("  FEATURE_NEWS_SENTIMENT=1")
    print("  FEATURE_ANALYST_SENTIMENT=1")
    print("  SENTIMENT_WEIGHT_ANALYST=0.10")


if __name__ == "__main__":
    test_analyst_sentiment()
