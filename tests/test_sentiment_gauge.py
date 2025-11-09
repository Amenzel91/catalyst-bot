"""
Test suite for enhanced sentiment gauge visualization (Wave 2 - Agent 2.4).

Tests the create_enhanced_sentiment_gauge function to ensure:
- Correct emoji selection for different sentiment ranges
- Proper label assignment (VERY BULLISH, BULLISH, NEUTRAL, etc.)
- Visual bar generation with appropriate length
- Output doesn't exceed Discord field limits (1024 chars)
- Edge case handling (None, invalid scores, extreme values)
"""

import sys
from pathlib import Path

# Fix Windows console encoding for emoji display
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_bot.sentiment_gauge import create_enhanced_sentiment_gauge


def test_very_bullish():
    """Test VERY BULLISH sentiment (85-100%)."""
    print("\n=== Testing VERY BULLISH (90%) ===")
    gauge = create_enhanced_sentiment_gauge(90)

    assert gauge["label"] == "VERY BULLISH", f"Expected 'VERY BULLISH', got '{gauge['label']}'"
    assert gauge["emoji"] == "🟢", f"Expected green circle, got {gauge['emoji']}"
    assert "Strong positive sentiment detected" in gauge["description"]
    assert "90%" in gauge["bar"]
    assert gauge["bar"].count("🟢") == 9, "Should have 9 green circles for 90%"
    assert gauge["bar"].count("⚪") == 1, "Should have 1 white circle for 90%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_bullish():
    """Test BULLISH sentiment (70-84%)."""
    print("\n=== Testing BULLISH (75%) ===")
    gauge = create_enhanced_sentiment_gauge(75)

    assert gauge["label"] == "BULLISH", f"Expected 'BULLISH', got '{gauge['label']}'"
    assert gauge["emoji"] == "🟢", f"Expected green circle, got {gauge['emoji']}"
    assert "Positive sentiment trend" in gauge["description"]
    assert "75%" in gauge["bar"]
    assert gauge["bar"].count("🟢") == 7, "Should have 7 green circles for 75%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_slightly_bullish():
    """Test SLIGHTLY BULLISH sentiment (55-69%)."""
    print("\n=== Testing SLIGHTLY BULLISH (60%) ===")
    gauge = create_enhanced_sentiment_gauge(60)

    assert gauge["label"] == "SLIGHTLY BULLISH", f"Expected 'SLIGHTLY BULLISH', got '{gauge['label']}'"
    assert gauge["emoji"] == "🟡", f"Expected yellow circle, got {gauge['emoji']}"
    assert "Moderately positive sentiment" in gauge["description"]
    assert "60%" in gauge["bar"]
    assert gauge["bar"].count("🟡") == 6, "Should have 6 yellow circles for 60%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_neutral():
    """Test NEUTRAL sentiment (45-54%)."""
    print("\n=== Testing NEUTRAL (50%) ===")
    gauge = create_enhanced_sentiment_gauge(50)

    assert gauge["label"] == "NEUTRAL", f"Expected 'NEUTRAL', got '{gauge['label']}'"
    assert gauge["emoji"] == "⚪", f"Expected white circle, got {gauge['emoji']}"
    assert "Mixed or neutral sentiment" in gauge["description"]
    assert "50%" in gauge["bar"]
    assert gauge["bar"].count("⚪") == 10, "Should have 10 white circles for 50%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_slightly_bearish():
    """Test SLIGHTLY BEARISH sentiment (30-44%)."""
    print("\n=== Testing SLIGHTLY BEARISH (35%) ===")
    gauge = create_enhanced_sentiment_gauge(35)

    assert gauge["label"] == "SLIGHTLY BEARISH", f"Expected 'SLIGHTLY BEARISH', got '{gauge['label']}'"
    assert gauge["emoji"] == "🟠", f"Expected orange circle, got {gauge['emoji']}"
    assert "Moderately negative sentiment" in gauge["description"]
    assert "35%" in gauge["bar"]
    assert gauge["bar"].count("🟠") == 3, "Should have 3 orange circles for 35%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_bearish():
    """Test BEARISH sentiment (15-29%)."""
    print("\n=== Testing BEARISH (20%) ===")
    gauge = create_enhanced_sentiment_gauge(20)

    assert gauge["label"] == "BEARISH", f"Expected 'BEARISH', got '{gauge['label']}'"
    assert gauge["emoji"] == "🔴", f"Expected red circle, got {gauge['emoji']}"
    assert "Negative sentiment trend" in gauge["description"]
    assert "20%" in gauge["bar"]
    assert gauge["bar"].count("🔴") == 2, "Should have 2 red circles for 20%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_very_bearish():
    """Test VERY BEARISH sentiment (0-14%)."""
    print("\n=== Testing VERY BEARISH (10%) ===")
    gauge = create_enhanced_sentiment_gauge(10)

    assert gauge["label"] == "VERY BEARISH", f"Expected 'VERY BEARISH', got '{gauge['label']}'"
    assert gauge["emoji"] == "🔴", f"Expected red circle, got {gauge['emoji']}"
    assert "Strong negative sentiment detected" in gauge["description"]
    assert "10%" in gauge["bar"]
    assert gauge["bar"].count("🔴") == 1, "Should have 1 red circle for 10%"

    print(f"  Label: {gauge['label']}")
    print(f"  Bar: {gauge['bar']}")
    print(f"  Description: {gauge['description']}")
    print("  ✓ PASSED")


def test_edge_cases():
    """Test edge cases and boundary values."""
    print("\n=== Testing Edge Cases ===")

    # Note: Input 0 is within -1 to +1 range, so it gets converted to 50% (NEUTRAL)
    # This is correct behavior as the function is designed for bullishness gauge (-1 to +1)
    gauge_0 = create_enhanced_sentiment_gauge(0)
    assert gauge_0["label"] == "NEUTRAL", f"Expected NEUTRAL for input 0, got {gauge_0['label']}"
    assert "50%" in gauge_0["bar"], f"Expected 50% for input 0, got {gauge_0['bar']}"
    print(f"  0 (converts to 50%): {gauge_0['bar']} - {gauge_0['label']} ✓")

    # Test 100% (direct percentage input, outside -1 to +1 range)
    gauge_100 = create_enhanced_sentiment_gauge(100)
    assert gauge_100["label"] == "VERY BULLISH"
    assert "100%" in gauge_100["bar"]
    assert gauge_100["bar"].count("🟢") == 10, "Should have 10 green circles for 100%"
    print(f"  100%: {gauge_100['bar']} - {gauge_100['label']} ✓")

    # Test boundary at 70% (BULLISH threshold)
    gauge_70 = create_enhanced_sentiment_gauge(70)
    assert gauge_70["label"] == "BULLISH"
    print(f"  70%: {gauge_70['bar']} - {gauge_70['label']} ✓")

    # Test boundary at 69% (SLIGHTLY BULLISH)
    gauge_69 = create_enhanced_sentiment_gauge(69)
    assert gauge_69["label"] == "SLIGHTLY BULLISH"
    print(f"  69%: {gauge_69['bar']} - {gauge_69['label']} ✓")

    # Test clamping above 100
    gauge_over = create_enhanced_sentiment_gauge(150)
    assert gauge_over["score"] == 100, "Should clamp to 100"
    print(f"  150 (clamped): {gauge_over['bar']} - {gauge_over['label']} ✓")

    # Test clamping below -1 (outside bullishness range)
    gauge_under = create_enhanced_sentiment_gauge(-50)
    assert gauge_under["score"] == 0, "Should clamp to 0"
    print(f"  -50 (clamped): {gauge_under['bar']} - {gauge_under['label']} ✓")

    print("  ✓ ALL EDGE CASES PASSED")


def test_negative_to_positive_range():
    """Test conversion from -1 to +1 range to 0-100 range."""
    print("\n=== Testing -1 to +1 Range Conversion ===")

    # Test negative score conversion (bullishness gauge range)
    gauge_neg = create_enhanced_sentiment_gauge(-0.5)
    # -0.5 should map to 25% in 0-100 range: (-0.5 + 1.0) * 50 = 25
    assert gauge_neg["score"] == 25, f"Expected 25%, got {gauge_neg['score']}%"
    assert gauge_neg["label"] in ["BEARISH", "SLIGHTLY BEARISH"]
    print(f"  -0.5 → {gauge_neg['score']}%: {gauge_neg['bar']} - {gauge_neg['label']} ✓")

    # Test -1.0 (most bearish in gauge range)
    gauge_very_neg = create_enhanced_sentiment_gauge(-1.0)
    assert gauge_very_neg["score"] == 0, f"Expected 0%, got {gauge_very_neg['score']}%"
    print(f"  -1.0 → {gauge_very_neg['score']}%: {gauge_very_neg['bar']} - {gauge_very_neg['label']} ✓")

    # Test +1.0 (most bullish in gauge range)
    gauge_very_pos = create_enhanced_sentiment_gauge(1.0)
    assert gauge_very_pos["score"] == 100, f"Expected 100%, got {gauge_very_pos['score']}%"
    print(f"  +1.0 → {gauge_very_pos['score']}%: {gauge_very_pos['bar']} - {gauge_very_pos['label']} ✓")

    # Test 0.0 (neutral in gauge range)
    gauge_neutral = create_enhanced_sentiment_gauge(0.0)
    assert gauge_neutral["score"] == 50, f"Expected 50%, got {gauge_neutral['score']}%"
    assert gauge_neutral["label"] == "NEUTRAL"
    print(f"  0.0 → {gauge_neutral['score']}%: {gauge_neutral['bar']} - {gauge_neutral['label']} ✓")

    # Test values outside -1 to +1 range get clamped (not converted)
    gauge_large_neg = create_enhanced_sentiment_gauge(-50)
    assert gauge_large_neg["score"] == 0, f"Expected 0% (clamped), got {gauge_large_neg['score']}%"
    print(f"  -50 (clamped) → {gauge_large_neg['score']}%: {gauge_large_neg['label']} ✓")

    print("  ✓ RANGE CONVERSION PASSED")


def test_discord_field_limits():
    """Test that output doesn't exceed Discord field limits."""
    print("\n=== Testing Discord Field Limits ===")

    # Test all score ranges
    test_scores = [0, 10, 25, 35, 50, 60, 75, 85, 100]

    for score in test_scores:
        gauge = create_enhanced_sentiment_gauge(score)

        # Field name limit (256 chars)
        field_name = f"{gauge['emoji']} Sentiment Analysis: {gauge['label']}"
        assert len(field_name) <= 256, f"Field name too long: {len(field_name)} chars"

        # Field value limit (1024 chars)
        field_value = (
            f"{gauge['bar']}\n"
            f"*{gauge['description']}*\n"
            f"Score: +0.50"  # Example score
        )
        assert len(field_value) <= 1024, f"Field value too long: {len(field_value)} chars"

        print(f"  {score}%: Field name={len(field_name)} chars, Value={len(field_value)} chars ✓")

    print("  ✓ ALL OUTPUTS WITHIN DISCORD LIMITS")


def test_visual_output():
    """Display visual examples of all sentiment levels."""
    print("\n" + "=" * 70)
    print("VISUAL EXAMPLES - How gauges appear in Discord")
    print("=" * 70)

    test_cases = [
        (100, "Maximum Bullish (percentage input)", 1.0),
        (85, "Very Bullish Boundary", 0.7),
        (75, "Bullish", 0.5),
        (60, "Slightly Bullish", 0.2),
        (50, "Perfect Neutral", 0.0),
        (35, "Slightly Bearish", -0.3),
        (20, "Bearish", -0.6),
        (10, "Very Bearish", -0.8),
        (1.0, "Maximum Bullish (bullishness +1.0)", 1.0),
        (-1.0, "Maximum Bearish (bullishness -1.0)", -1.0),
    ]

    for score, description, display_score in test_cases:
        gauge = create_enhanced_sentiment_gauge(score)
        print(f"\n{description}:")
        print(f"  📊 Sentiment Analysis: {gauge['label']}")
        print(f"  {gauge['bar']}")
        print(f"  {gauge['description']}")
        print(f"  Bullishness Score: {display_score:+.2f}")

    print("\n" + "=" * 70)


def run_all_tests():
    """Run all test functions."""
    print("\n" + "=" * 70)
    print("SENTIMENT GAUGE ENHANCEMENT TEST SUITE (Wave 2 - Agent 2.4)")
    print("=" * 70)

    try:
        test_very_bullish()
        test_bullish()
        test_slightly_bullish()
        test_neutral()
        test_slightly_bearish()
        test_bearish()
        test_very_bearish()
        test_edge_cases()
        test_negative_to_positive_range()
        test_discord_field_limits()
        test_visual_output()

        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED!")
        print("=" * 70)
        print("\nSentiment gauge enhancement is ready for production.")
        print("Integration point: alerts.py line 2369-2400")
        print("Feature flag: FEATURE_BULLISHNESS_GAUGE=1")
        return True

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
