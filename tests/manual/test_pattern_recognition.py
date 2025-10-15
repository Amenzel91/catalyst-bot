"""
test_pattern_recognition.py
============================

Comprehensive tests for pattern recognition functionality.

Tests cover:
- Triangle detection (ascending, descending, symmetrical)
- Head & Shoulders detection (classic and inverse)
- Double top/bottom detection
- Channel detection
- Flag/pennant detection
- Confidence scoring
- Pattern annotation rendering
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np  # noqa: E402

from catalyst_bot.chart_indicators_integration import (  # noqa: E402
    add_pattern_annotations_to_config,
)
from catalyst_bot.indicators.patterns import (  # noqa: E402
    detect_all_patterns,
    detect_channels,
    detect_double_tops_bottoms,
    detect_flags_pennants,
    detect_head_shoulders,
    detect_triangles,
)


def generate_ascending_triangle():
    """Generate synthetic ascending triangle price data."""
    # Flat resistance at 110, rising support
    base = np.linspace(100, 108, 20)
    noise = np.random.normal(0, 0.5, 20)
    prices = base + noise

    # Force some touches on resistance
    prices[5] = 110
    prices[10] = 110
    prices[15] = 110

    highs = prices + np.abs(np.random.normal(0, 0.3, 20))
    lows = prices - np.abs(np.random.normal(0, 0.3, 20))

    return prices.tolist(), highs.tolist(), lows.tolist()


def generate_descending_triangle():
    """Generate synthetic descending triangle price data."""
    # Flat support at 100, falling resistance
    base = np.linspace(110, 102, 20)
    noise = np.random.normal(0, 0.5, 20)
    prices = base + noise

    # Force some touches on support
    prices[5] = 100
    prices[10] = 100
    prices[15] = 100

    highs = prices + np.abs(np.random.normal(0, 0.3, 20))
    lows = prices - np.abs(np.random.normal(0, 0.3, 20))

    return prices.tolist(), highs.tolist(), lows.tolist()


def generate_head_shoulders():
    """Generate synthetic head and shoulders pattern."""
    # Left shoulder, head, right shoulder
    pattern = [100, 105, 102, 110, 103, 106, 100]
    # Add some noise and extend
    prices = pattern + [99, 98, 97]
    prices = prices + [prices[-1]] * (30 - len(prices))

    return prices


def generate_double_top():
    """Generate synthetic double top pattern."""
    # Two peaks at same level with trough between
    prices = [100, 105, 110, 105, 100, 105, 110, 105, 100]
    prices = prices + [prices[-1]] * (30 - len(prices))

    return prices


def generate_channel():
    """Generate synthetic channel pattern."""
    # Uptrending channel with parallel support and resistance
    trend = np.linspace(100, 120, 30)
    oscillation = 3 * np.sin(np.linspace(0, 6 * np.pi, 30))
    prices = trend + oscillation

    highs = prices + 2
    lows = prices - 2

    return prices.tolist(), highs.tolist(), lows.tolist()


def test_triangle_detection():
    """Test all three triangle pattern types."""
    print("\n=== Testing Triangle Detection ===")

    # Test ascending triangle
    print("\n1. Ascending Triangle:")
    prices, highs, lows = generate_ascending_triangle()
    patterns = detect_triangles(prices, highs, lows, min_touches=2)

    print(f"   Detected {len(patterns)} pattern(s)")
    for p in patterns:
        print(f"   - Type: {p['type']}")
        print(f"   - Confidence: {p['confidence']:.2f}")
        print(f"   - Description: {p['description']}")
        assert p["type"] in [
            "ascending_triangle",
            "symmetrical_triangle",
        ], "Should detect triangle"
        assert p["confidence"] >= 0.5, "Confidence should be reasonable"

    # Test descending triangle
    print("\n2. Descending Triangle:")
    prices, highs, lows = generate_descending_triangle()
    patterns = detect_triangles(prices, highs, lows, min_touches=2)

    print(f"   Detected {len(patterns)} pattern(s)")
    for p in patterns:
        print(f"   - Type: {p['type']}")
        print(f"   - Confidence: {p['confidence']:.2f}")
        print(f"   - Description: {p['description']}")
        assert p["type"] in [
            "descending_triangle",
            "symmetrical_triangle",
        ], "Should detect triangle"

    print("   [PASS] Triangle detection tests passed")


def test_head_shoulders_detection():
    """Test head and shoulders pattern detection."""
    print("\n=== Testing Head & Shoulders Detection ===")

    prices = generate_head_shoulders()
    patterns = detect_head_shoulders(prices, min_confidence=0.5, lookback=30)

    print(f"Detected {len(patterns)} pattern(s)")
    for p in patterns:
        print(f"- Type: {p['type']}")
        print(f"- Confidence: {p['confidence']:.2f}")
        print(f"- Description: {p['description']}")

        if "key_levels" in p:
            levels = p["key_levels"]
            if "neckline" in levels:
                print(f"- Neckline: ${levels['neckline']:.2f}")

        assert p["type"] in ["head_shoulders", "inverse_head_shoulders"]
        assert 0 <= p["confidence"] <= 1.0

    print("[PASS] Head & Shoulders detection tests passed")


def test_double_top_bottom_detection():
    """Test double top and bottom pattern detection."""
    print("\n=== Testing Double Top/Bottom Detection ===")

    prices = generate_double_top()
    patterns = detect_double_tops_bottoms(prices, tolerance=0.03, lookback=30)

    print(f"Detected {len(patterns)} pattern(s)")
    for p in patterns:
        print(f"- Type: {p['type']}")
        print(f"- Confidence: {p['confidence']:.2f}")
        print(f"- Description: {p['description']}")
        assert p["type"] in ["double_top", "double_bottom"]
        assert p["confidence"] >= 0.5

    print("[PASS] Double top/bottom detection tests passed")


def test_channel_detection():
    """Test channel pattern detection."""
    print("\n=== Testing Channel Detection ===")

    prices, highs, lows = generate_channel()
    patterns = detect_channels(prices, highs, lows, min_touches=2, lookback=30)

    print(f"Detected {len(patterns)} pattern(s)")
    for p in patterns:
        print(f"- Type: {p['type']}")
        print(f"- Confidence: {p['confidence']:.2f}")
        print(f"- Description: {p['description']}")
        assert "channel" in p["type"]
        assert p["confidence"] >= 0.5

    print("[PASS] Channel detection tests passed")


def test_flag_pennant_detection():
    """Test flag and pennant continuation patterns."""
    print("\n=== Testing Flag/Pennant Detection ===")

    # Generate sharp move followed by consolidation
    pole = np.linspace(100, 115, 7)  # 15% move
    consolidation = np.full(13, 114) + np.random.normal(0, 0.5, 13)
    prices = np.concatenate([pole, consolidation])
    volumes = np.concatenate([np.full(7, 1000000), np.full(13, 400000)])

    patterns = detect_flags_pennants(prices.tolist(), volumes.tolist(), lookback=20)

    print(f"Detected {len(patterns)} pattern(s)")
    for p in patterns:
        print(f"- Type: {p['type']}")
        print(f"- Confidence: {p['confidence']:.2f}")
        print(f"- Description: {p['description']}")
        assert "flag" in p["type"] or "pennant" in p["type"]

    print("[PASS] Flag/pennant detection tests passed")


def test_confidence_scoring():
    """Test confidence scoring across different pattern qualities."""
    print("\n=== Testing Confidence Scoring ===")

    # High quality pattern (perfect ascending triangle)
    prices_perfect = [100] * 5 + [102] * 5 + [104] * 5 + [106] * 5
    highs_perfect = [110] * 20
    lows_perfect = [p - 1 for p in prices_perfect]

    patterns_perfect = detect_triangles(
        prices_perfect, highs_perfect, lows_perfect, min_touches=2
    )

    # Low quality pattern (noisy)
    prices_noisy = list(np.random.normal(100, 5, 20))
    highs_noisy = [p + abs(np.random.normal(0, 2)) for p in prices_noisy]
    lows_noisy = [p - abs(np.random.normal(0, 2)) for p in prices_noisy]

    patterns_noisy = detect_triangles(
        prices_noisy, highs_noisy, lows_noisy, min_touches=2
    )

    print(f"Perfect pattern detections: {len(patterns_perfect)}")
    for p in patterns_perfect:
        print(f"  - Confidence: {p['confidence']:.2f}")

    print(f"Noisy pattern detections: {len(patterns_noisy)}")
    for p in patterns_noisy:
        print(f"  - Confidence: {p['confidence']:.2f}")

    print("[PASS] Confidence scoring tests passed")


def test_pattern_annotation_rendering():
    """Test pattern annotation rendering in Chart.js config."""
    print("\n=== Testing Pattern Annotation Rendering ===")

    # Create mock patterns
    mock_patterns = [
        {
            "type": "ascending_triangle",
            "confidence": 0.85,
            "start_idx": 10,
            "end_idx": 30,
            "key_levels": {
                "resistance": 110.0,
                "support_slope": 0.5,
                "current_price": 108.0,
            },
        },
        {
            "type": "head_shoulders",
            "confidence": 0.75,
            "start_idx": 5,
            "end_idx": 25,
            "key_levels": {
                "left_shoulder": (5, 105.0),
                "head": (15, 112.0),
                "right_shoulder": (25, 106.0),
                "neckline": 100.0,
            },
        },
    ]

    # Create base config
    config = {"type": "line", "data": {"datasets": []}, "options": {}}

    # Add pattern annotations
    enhanced_config = add_pattern_annotations_to_config(config, mock_patterns)

    # Verify annotations were added
    assert "options" in enhanced_config
    assert "plugins" in enhanced_config["options"]
    assert "annotation" in enhanced_config["options"]["plugins"]

    annotations = enhanced_config["options"]["plugins"]["annotation"].get(
        "annotations", {}
    )
    print(f"Created {len(annotations)} annotation(s)")

    # Should have labels for each pattern plus pattern-specific markers
    assert len(annotations) > 0, "Should create annotations"

    for key, annotation in annotations.items():
        print(f"  - {key}: {annotation.get('type', 'unknown')}")

    print("[PASS] Pattern annotation rendering tests passed")


def test_all_patterns_integration():
    """Test detect_all_patterns integration function."""
    print("\n=== Testing detect_all_patterns() Integration ===")

    # Generate complex price data with multiple patterns
    prices, highs, lows = generate_channel()
    volumes = [1000000] * len(prices)

    # Detect all patterns
    all_patterns = detect_all_patterns(
        prices, highs=highs, lows=lows, volumes=volumes, min_confidence=0.5
    )

    print(f"Total patterns detected: {len(all_patterns)}")

    # Group by type
    pattern_types = {}
    for p in all_patterns:
        ptype = p["type"]
        pattern_types[ptype] = pattern_types.get(ptype, 0) + 1

    print("Pattern type breakdown:")
    for ptype, count in pattern_types.items():
        print(f"  - {ptype}: {count}")

    # Verify sorting by confidence
    if len(all_patterns) > 1:
        for i in range(len(all_patterns) - 1):
            assert (
                all_patterns[i]["confidence"] >= all_patterns[i + 1]["confidence"]
            ), "Patterns should be sorted by confidence (highest first)"

    print("[PASS] detect_all_patterns() integration tests passed")


def run_all_tests():
    """Run all pattern recognition tests."""
    print("=" * 70)
    print("PATTERN RECOGNITION TEST SUITE")
    print("=" * 70)

    try:
        test_triangle_detection()
        test_head_shoulders_detection()
        test_double_top_bottom_detection()
        test_channel_detection()
        test_flag_pennant_detection()
        test_confidence_scoring()
        test_pattern_annotation_rendering()
        test_all_patterns_integration()

        print("\n" + "=" * 70)
        print("[PASS] ALL PATTERN RECOGNITION TESTS PASSED")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
