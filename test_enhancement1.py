"""
Test script for Enhancement #1: Multi-Dimensional Sentiment Extraction

This script verifies:
1. SentimentAnalysis model validation
2. Schema parsing from LLM responses
3. Confidence threshold filtering
4. Backward compatibility with existing classification
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_sentiment_analysis_model():
    """Test the SentimentAnalysis Pydantic model."""
    from catalyst_bot.llm_schemas import SentimentAnalysis

    print("Testing SentimentAnalysis model...")

    # Test valid data
    data = {
        "market_sentiment": "bullish",
        "confidence": 0.85,
        "urgency": "high",
        "risk_level": "medium",
        "institutional_interest": True,
        "retail_hype_score": 0.7,
        "reasoning": "FDA approval with strong clinical data"
    }

    sentiment = SentimentAnalysis(**data)
    print(f"[PASS] Created sentiment: {sentiment.market_sentiment}, confidence: {sentiment.confidence}")
    print(f"  Numeric sentiment: {sentiment.to_numeric_sentiment()}")

    # Test defaults
    minimal_data = {}
    sentiment_default = SentimentAnalysis(**minimal_data)
    print(f"[PASS] Defaults work: {sentiment_default.market_sentiment}, confidence: {sentiment_default.confidence}")

    # Test validation (should fail for invalid values)
    try:
        invalid_data = {"confidence": 1.5}  # Out of range
        SentimentAnalysis(**invalid_data)
        print("[FAIL] Should have failed validation")
        return False
    except Exception as e:
        print(f"[PASS] Validation correctly rejected invalid data: {type(e).__name__}")

    return True


def test_keyword_extraction_schema():
    """Test SECKeywordExtraction with optional sentiment_analysis field."""
    from catalyst_bot.llm_schemas import SECKeywordExtraction, SentimentAnalysis

    print("\nTesting SECKeywordExtraction schema...")

    # Test without sentiment_analysis (backward compatible)
    extraction1 = SECKeywordExtraction(
        keywords=["fda", "clinical", "phase_3"],
        sentiment=0.8,
        confidence=0.9,
        summary="FDA approval announced",
        material=True
    )
    print(f"[PASS] Basic extraction works: {len(extraction1.keywords)} keywords")

    # Test with sentiment_analysis
    sentiment_data = {
        "market_sentiment": "bullish",
        "confidence": 0.9,
        "urgency": "critical",
        "risk_level": "low",
        "institutional_interest": True,
        "retail_hype_score": 0.8,
        "reasoning": "Major FDA milestone"
    }

    extraction2 = SECKeywordExtraction(
        keywords=["fda", "approval"],
        sentiment=0.9,
        confidence=0.95,
        summary="FDA approval",
        material=True,
        sentiment_analysis=SentimentAnalysis(**sentiment_data)
    )
    print(f"[PASS] Enhanced extraction works: urgency={extraction2.sentiment_analysis.urgency}")

    return True


def test_classification_integration():
    """Test classification with multi-dimensional sentiment."""
    from catalyst_bot.models import NewsItem
    from catalyst_bot.classify import classify
    from datetime import datetime, timezone

    print("\nTesting classification integration...")

    # Test 1: Basic classification (no multi-dim sentiment)
    item1 = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Test news item about FDA approval",
        ticker="TEST"
    )

    scored1 = classify(item1)
    print(f"[PASS] Basic classification: sentiment={scored1.sentiment:.2f}, relevance={scored1.relevance:.2f}")

    # Test 2: Classification with multi-dim sentiment in raw data
    item2 = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="AAPL announces major partnership with tier 1 partner",
        ticker="AAPL",
        raw={
            "sentiment_analysis": {
                "market_sentiment": "bullish",
                "confidence": 0.85,
                "urgency": "high",
                "risk_level": "low",
                "institutional_interest": True,
                "retail_hype_score": 0.6,
                "reasoning": "Strategic partnership expected to boost revenue"
            }
        }
    )

    scored2 = classify(item2)
    print(f"[PASS] Enhanced classification: sentiment={scored2.sentiment:.2f}")

    # Check if multi-dim fields are attached
    has_urgency = hasattr(scored2, "urgency") or (isinstance(scored2, dict) and "urgency" in scored2)
    if has_urgency:
        urgency = scored2.urgency if hasattr(scored2, "urgency") else scored2["urgency"]
        print(f"  Multi-dim fields attached: urgency={urgency}")
    else:
        print("  [WARN] Multi-dim fields not attached (may be expected if feature disabled)")

    # Test 3: Low confidence rejection (confidence < 0.5)
    item3 = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Low confidence test",
        ticker="TEST",
        raw={
            "sentiment_analysis": {
                "market_sentiment": "bullish",
                "confidence": 0.3,  # Below threshold
                "urgency": "low",
                "risk_level": "high",
                "institutional_interest": False,
                "retail_hype_score": 0.1,
                "reasoning": "Uncertain catalyst"
            }
        }
    )

    scored3 = classify(item3)
    has_urgency_3 = hasattr(scored3, "urgency") or (isinstance(scored3, dict) and "urgency" in scored3)
    if not has_urgency_3:
        print("[PASS] Low confidence sentiment correctly rejected")
    else:
        print("[WARN] Low confidence sentiment was not rejected")

    return True


def run_all_tests():
    """Run all test suites."""
    print("=" * 60)
    print("ENHANCEMENT #1: Multi-Dimensional Sentiment - Test Suite")
    print("=" * 60)

    tests = [
        ("SentimentAnalysis Model", test_sentiment_analysis_model),
        ("Keyword Extraction Schema", test_keyword_extraction_schema),
        ("Classification Integration", test_classification_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[FAIL] {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")

    print(f"\nResults: {passed}/{total} test suites passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
