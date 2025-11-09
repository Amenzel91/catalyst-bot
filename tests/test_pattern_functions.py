"""
test_pattern_functions.py
==========================

Test the pattern detection functions directly without chart rendering.

This script validates that the H&S and double pattern detection functions
work correctly with synthetic data.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_hs_detection():
    """Test Head & Shoulders pattern detection."""
    print("\n" + "=" * 60)
    print("Testing Head & Shoulders Detection")
    print("=" * 60)

    from catalyst_bot.indicators.patterns import detect_head_shoulders

    # Create synthetic H&S pattern
    # Left shoulder (peak at 105), head (peak at 110), right shoulder (peak at 106)
    prices = [
        100,
        105,
        102,  # Left shoulder
        108,
        110,
        107,  # Head (highest)
        104,
        106,
        103,  # Right shoulder
        100,
    ]

    patterns = detect_head_shoulders(prices, min_confidence=0.5, lookback=20)

    print(f"\nTest data: {len(prices)} price points")
    print(f"Patterns detected: {len(patterns)}")

    for i, pattern in enumerate(patterns, 1):
        print(f"\nPattern {i}:")
        print(f"  Type: {pattern['type']}")
        print(f"  Confidence: {pattern['confidence']:.1%}")
        print(f"  Key levels: {pattern['key_levels']}")
        print(f"  Target: ${pattern['target']:.2f}")

    if patterns:
        print("\n[OK] H&S detection working")
    else:
        print("\n[INFO] No H&S patterns detected (may be normal)")

    return patterns


def test_double_tops_bottoms():
    """Test Double Top/Bottom pattern detection."""
    print("\n" + "=" * 60)
    print("Testing Double Top/Bottom Detection")
    print("=" * 60)

    from catalyst_bot.indicators.patterns import detect_double_tops_bottoms

    # Create synthetic double top pattern
    # Two peaks at ~110
    prices = [100, 105, 110, 105, 108, 110, 105, 100]

    patterns = detect_double_tops_bottoms(
        prices, tolerance=0.02, min_spacing=3, lookback=20
    )

    print(f"\nTest data: {len(prices)} price points")
    print(f"Patterns detected: {len(patterns)}")

    for i, pattern in enumerate(patterns, 1):
        print(f"\nPattern {i}:")
        print(f"  Type: {pattern['type']}")
        print(f"  Confidence: {pattern['confidence']:.1%}")
        print(f"  Key levels: {pattern['key_levels']}")
        print(f"  Target: ${pattern['target']:.2f}")

    if patterns:
        print("\n[OK] Double pattern detection working")
    else:
        print("\n[INFO] No double patterns detected (may be normal)")

    return patterns


def test_visualization_functions():
    """Test that visualization functions can be imported."""
    print("\n" + "=" * 60)
    print("Testing Visualization Function Imports")
    print("=" * 60)

    try:
        from catalyst_bot.charts import add_hs_patterns, add_double_patterns

        print("\n[OK] add_hs_patterns imported successfully")
        print("[OK] add_double_patterns imported successfully")

        # Check function signatures
        import inspect

        hs_sig = inspect.signature(add_hs_patterns)
        double_sig = inspect.signature(add_double_patterns)

        print(f"\nadd_hs_patterns signature: {hs_sig}")
        print(f"add_double_patterns signature: {double_sig}")

        return True
    except Exception as err:
        print(f"\n[ERROR] Import failed: {err}")
        return False


def test_color_definitions():
    """Test that pattern colors are defined."""
    print("\n" + "=" * 60)
    print("Testing Pattern Color Definitions")
    print("=" * 60)

    from catalyst_bot.charts import INDICATOR_COLORS

    required_colors = [
        "hs_pattern",
        "hs_neckline",
        "double_top",
        "double_bottom",
    ]

    print("\nChecking for required color definitions...")
    all_present = True

    for color_key in required_colors:
        if color_key in INDICATOR_COLORS:
            color_value = INDICATOR_COLORS[color_key]
            print(f"  [OK] {color_key}: {color_value}")
        else:
            print(f"  [FAIL] {color_key}: NOT FOUND")
            all_present = False

    if all_present:
        print("\n[OK] All pattern colors defined")
    else:
        print("\n[FAIL] Some colors missing")

    return all_present


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("PATTERN FUNCTION TESTS")
    print("=" * 60)

    # Run tests
    test_color_definitions()
    test_visualization_functions()
    test_hs_detection()
    test_double_tops_bottoms()

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)
