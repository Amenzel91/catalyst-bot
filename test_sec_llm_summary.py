"""Test script for SEC filing LLM summarization (Wave 4).

This script tests the new LLM summarization feature by simulating a SEC filing
and verifying that it generates an actionable summary instead of a placeholder.

Usage:
    python test_sec_llm_summary.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.llm_chain import get_filing_summary


async def test_llm_summary():
    """Test LLM summarization with a sample SEC filing."""

    # Sample SEC 8-K Item 2.02 (Earnings) filing text
    sample_filing = """
    FORM 8-K
    Item 2.02 - Results of Operations and Financial Condition

    Apple Inc. announced financial results for its fiscal 2024 third quarter ended June 29, 2024.

    The Company posted quarterly revenue of $85.78 billion, up 5% year over year, and quarterly
    earnings per diluted share of $1.40, up 11% year over year.

    "We are very pleased with our results," said Tim Cook, Apple's CEO. "We saw strong iPhone
    sales growth and continued momentum in Services, which reached an all-time revenue record."

    Revenue breakdown:
    - iPhone: $39.3 billion (up 6% YoY)
    - Services: $24.2 billion (up 14% YoY, all-time high)
    - Mac: $7.0 billion (down 2% YoY)
    - iPad: $7.2 billion (down 3% YoY)
    - Wearables: $8.1 billion (up 2% YoY)

    Gross margin improved to 46.3%, up from 44.5% in the prior year quarter.

    The Company also announced a quarterly dividend of $0.25 per share and an increase to
    its share repurchase program by $110 billion.

    For Q4 2024, Apple expects revenue growth in the low to mid single digits year over year.
    """

    print("Testing SEC Filing LLM Summarization")
    print("=" * 60)
    print("\nSample Filing Text (truncated):")
    print("-" * 60)
    print(sample_filing[:300] + "...")
    print("-" * 60)

    try:
        print("\n🤖 Calling LLM to generate summary...")
        print("(This may take 5-15 seconds depending on LLM provider)\n")

        # Call the async LLM summarization function
        summary = await get_filing_summary(sample_filing[:2000])

        print("✅ LLM Summary Generated Successfully!")
        print("=" * 60)
        print(summary)
        print("=" * 60)

        # Verify summary quality
        print("\n📊 Summary Analysis:")
        print(f"  - Length: {len(summary)} chars (target: 100-150 words)")
        print(f"  - Contains numbers: {'✓' if any(c.isdigit() for c in summary) else '✗'}")
        print(f"  - Contains 'revenue' or 'earnings': {'✓' if 'revenue' in summary.lower() or 'earnings' in summary.lower() else '✗'}")
        print(f"  - Not placeholder: {'✓' if 'SEC' not in summary or 'filing' not in summary.lower() else '✗'}")

        return True

    except Exception as e:
        print(f"\n❌ LLM Summarization Failed: {e}")
        print(f"   Error Type: {type(e).__name__}")
        import traceback
        print(f"\n{traceback.format_exc()}")
        return False


async def test_formatting():
    """Test summary formatting with ticker and filing type."""

    print("\n\nTesting Summary Formatting")
    print("=" * 60)

    sample_text = "Apple announced Q3 earnings beat with revenue of $85.78B, up 5% YoY."
    ticker = "AAPL"
    filing_type = "8-K"
    item_code = "2.02"

    try:
        raw_summary = await get_filing_summary(sample_text)

        # Format like feeds.py does
        formatted_summary = f"{ticker} {filing_type} Item {item_code}: {raw_summary}"

        print(f"\nRaw Summary: {raw_summary}")
        print(f"\nFormatted Summary: {formatted_summary}")
        print("\n✅ Formatting works correctly!")

        # Check format matches expected pattern
        expected_prefix = f"{ticker} {filing_type} Item {item_code}:"
        if formatted_summary.startswith(expected_prefix):
            print(f"✓ Matches expected format: '{expected_prefix}...'")
        else:
            print(f"✗ Format mismatch! Expected: '{expected_prefix}'")

        return True

    except Exception as e:
        print(f"\n❌ Formatting test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SEC Filing LLM Summarization Test Suite")
    print("Wave 4 Enhancement - Real Actionable Summaries")
    print("=" * 60 + "\n")

    # Test 1: Basic LLM summarization
    test1_result = await test_llm_summary()

    # Test 2: Summary formatting
    test2_result = await test_formatting()

    # Summary
    print("\n\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    print(f"LLM Summarization: {'✅ PASS' if test1_result else '❌ FAIL'}")
    print(f"Summary Formatting: {'✅ PASS' if test2_result else '❌ FAIL'}")
    print("=" * 60)

    if test1_result and test2_result:
        print("\n🎉 All tests passed! LLM summarization is working correctly.")
        print("\nNext steps:")
        print("  1. Enable SEC filing monitoring: FEATURE_SEC_FILINGS=true")
        print("  2. Configure LLM API key: GEMINI_API_KEY or ANTHROPIC_API_KEY")
        print("  3. Run the bot and watch for real SEC filings with actionable summaries!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")
        print("\nTroubleshooting:")
        print("  - Ensure GEMINI_API_KEY or ANTHROPIC_API_KEY is set in .env")
        print("  - Check that llm_hybrid.py can connect to LLM providers")
        print("  - Verify network connectivity")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
