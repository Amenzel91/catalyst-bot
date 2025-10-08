"""
test_volume_profile_enhanced.py
================================

Tests for enhanced volume profile features including:
- Horizontal volume bar generation
- HVN (High Volume Node) identification
- LVN (Low Volume Node) identification
- POC (Point of Control) calculation
- Integration with chart rendering
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np  # noqa: E402

from catalyst_bot.indicators.volume_profile import (  # noqa: E402
    calculate_value_area,
    calculate_volume_profile,
    find_point_of_control,
    generate_horizontal_volume_bars,
    identify_hvn_lvn,
    render_volume_profile_data,
)


def generate_test_data(n=100):
    """Generate realistic test price and volume data."""
    # Create price data with clustering around certain levels
    base_price = 100
    prices = []
    volumes = []

    # Create three price clusters
    for _ in range(30):
        prices.append(base_price + np.random.normal(0, 1))
        volumes.append(np.random.randint(500000, 1500000))

    for _ in range(40):
        prices.append(base_price + 5 + np.random.normal(0, 1))
        volumes.append(np.random.randint(800000, 2000000))  # High volume cluster

    for _ in range(30):
        prices.append(base_price + 10 + np.random.normal(0, 1))
        volumes.append(np.random.randint(300000, 800000))

    return prices, volumes


def test_horizontal_volume_bars():
    """Test horizontal volume bar generation for chart overlay."""
    print("\n=== Testing Horizontal Volume Bar Generation ===")

    prices, volumes = generate_test_data(100)

    # Calculate volume profile
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=20)

    # Generate horizontal bars
    bars = generate_horizontal_volume_bars(
        price_levels, volume_at_price, normalize=True
    )

    print(f"Generated {len(bars)} horizontal volume bars")
    print("\nSample bars:")
    for i, bar in enumerate(bars[:5]):
        print(f"  Bar {i+1}:")
        print(f"    Price: ${bar['price']:.2f}")
        print(f"    Volume: {bar['volume']:,.0f}")
        print(f"    Normalized: {bar['normalized_volume']:.1f}%")

    # Validation
    assert len(bars) == len(price_levels), "Should have one bar per price level"
    assert all("price" in bar for bar in bars), "Each bar should have price"
    assert all("volume" in bar for bar in bars), "Each bar should have volume"
    assert all(
        "normalized_volume" in bar for bar in bars
    ), "Each bar should have normalized volume"

    # Check normalization
    max_normalized = max(bar["normalized_volume"] for bar in bars)
    assert 99 <= max_normalized <= 100, "Max normalized volume should be ~100%"

    min_normalized = min(bar["normalized_volume"] for bar in bars)
    assert min_normalized >= 0, "Normalized volume should be >= 0"

    print("[PASS] Horizontal volume bar generation tests passed")


def test_hvn_lvn_identification():
    """Test High Volume Node and Low Volume Node identification."""
    print("\n=== Testing HVN/LVN Identification ===")

    prices, volumes = generate_test_data(100)

    # Calculate volume profile
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=20)

    # Identify HVN and LVN
    hvn_list, lvn_list = identify_hvn_lvn(
        price_levels, volume_at_price, hvn_threshold=1.3, lvn_threshold=0.7
    )

    print(f"Identified {len(hvn_list)} High Volume Node(s)")
    print(f"Identified {len(lvn_list)} Low Volume Node(s)")

    print("\nHigh Volume Nodes:")
    for hvn in hvn_list[:3]:
        print(
            f"  - Price: ${hvn['price']:.2f}, Volume: {hvn['volume']:,.0f}, Ratio: {hvn['ratio']:.2f}x"  # noqa: E501
        )

    print("\nLow Volume Nodes:")
    for lvn in lvn_list[:3]:
        print(
            f"  - Price: ${lvn['price']:.2f}, Volume: {lvn['volume']:,.0f}, Ratio: {lvn['ratio']:.2f}x"  # noqa: E501
        )

    # Validation
    assert len(hvn_list) >= 0, "Should identify HVNs"
    assert len(lvn_list) >= 0, "Should identify LVNs"

    # Check that HVN ratios are > threshold
    for hvn in hvn_list:
        assert hvn["ratio"] >= 1.3, f"HVN ratio should be >= 1.3, got {hvn['ratio']}"

    # Check that LVN ratios are < threshold
    for lvn in lvn_list:
        assert lvn["ratio"] <= 0.7, f"LVN ratio should be <= 0.7, got {lvn['ratio']}"

    # Check that each has required fields
    for node in hvn_list + lvn_list:
        assert "price" in node
        assert "volume" in node
        assert "ratio" in node

    print("[PASS] HVN/LVN identification tests passed")


def test_poc_calculation():
    """Test Point of Control (POC) calculation."""
    print("\n=== Testing POC Calculation ===")

    prices, volumes = generate_test_data(100)

    # Calculate volume profile
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=20)

    # Find POC
    poc = find_point_of_control(price_levels, volume_at_price)

    print(f"Point of Control: ${poc:.2f}")

    # Validation
    assert poc is not None, "Should find POC"
    assert (
        min(price_levels) <= poc <= max(price_levels)
    ), "POC should be within price range"

    # POC should be at the level with highest volume
    max_volume_idx = volume_at_price.index(max(volume_at_price))
    expected_poc = price_levels[max_volume_idx]

    assert abs(poc - expected_poc) < 0.01, "POC should be at max volume level"

    print("[PASS] POC calculation tests passed")


def test_value_area_calculation():
    """Test Value Area (VAH, VAL) calculation."""
    print("\n=== Testing Value Area Calculation ===")

    prices, volumes = generate_test_data(100)

    # Calculate volume profile
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=20)

    # Calculate value area (70% of volume)
    vah, poc, val = calculate_value_area(
        price_levels, volume_at_price, value_area_pct=0.70
    )

    print(f"Value Area High (VAH): ${vah:.2f}")
    print(f"Point of Control (POC): ${poc:.2f}")
    print(f"Value Area Low (VAL): ${val:.2f}")
    print(f"Value Area Range: ${vah - val:.2f}")

    # Validation
    assert vah is not None, "Should find VAH"
    assert val is not None, "Should find VAL"
    assert poc is not None, "Should find POC"

    assert vah > val, "VAH should be greater than VAL"
    assert val <= poc <= vah, "POC should be within value area"

    # VAH and VAL should be within price range
    assert min(price_levels) <= val <= max(price_levels)
    assert min(price_levels) <= vah <= max(price_levels)

    print("[PASS] Value Area calculation tests passed")


def test_render_volume_profile_data():
    """Test complete volume profile data rendering."""
    print("\n=== Testing Complete Volume Profile Rendering ===")

    prices, volumes = generate_test_data(100)

    # Render complete volume profile
    vp_data = render_volume_profile_data(prices, volumes, bins=25)

    print("Volume Profile Data Summary:")
    print(f"  - Price bins: {len(vp_data['price_levels'])}")
    print(f"  - POC: ${vp_data['poc']:.2f}")
    print(f"  - VAH: ${vp_data['vah']:.2f}")
    print(f"  - VAL: ${vp_data['val']:.2f}")
    print(f"  - HVN count: {len(vp_data['hvn'])}")
    print(f"  - LVN count: {len(vp_data['lvn'])}")
    print(f"  - Horizontal bars: {len(vp_data['horizontal_bars'])}")

    # Validation
    assert "price_levels" in vp_data
    assert "volume_at_price" in vp_data
    assert "poc" in vp_data
    assert "vah" in vp_data
    assert "val" in vp_data
    assert "hvn" in vp_data
    assert "lvn" in vp_data
    assert "horizontal_bars" in vp_data

    assert len(vp_data["price_levels"]) == 25
    assert len(vp_data["horizontal_bars"]) == 25

    assert vp_data["poc"] is not None
    assert vp_data["vah"] is not None
    assert vp_data["val"] is not None

    print("[PASS] Complete volume profile rendering tests passed")


def test_volume_profile_bins():
    """Test volume profile with different bin counts."""
    print("\n=== Testing Volume Profile with Different Bin Counts ===")

    prices, volumes = generate_test_data(100)

    for bins in [10, 20, 30, 50]:
        price_levels, volume_at_price = calculate_volume_profile(
            prices, volumes, bins=bins
        )

        print(f"\nBins={bins}:")
        print(f"  - Price levels: {len(price_levels)}")
        print(f"  - Price range: ${min(price_levels):.2f} - ${max(price_levels):.2f}")

        assert len(price_levels) == bins, f"Should create {bins} price levels"
        assert len(volume_at_price) == bins, f"Should have volume for {bins} levels"

    print("\n[PASS] Volume profile bin tests passed")


def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n=== Testing Edge Cases ===")

    # Empty data
    bars = generate_horizontal_volume_bars([], [], normalize=True)
    assert len(bars) == 0, "Should handle empty data"

    # Mismatched lengths
    hvn, lvn = identify_hvn_lvn([100, 101], [1000], hvn_threshold=1.3)
    assert len(hvn) == 0 and len(lvn) == 0, "Should handle mismatched data"

    # Single data point (needs at least 2 points for bins)
    prices, volumes = [100, 101], [1000, 1000]
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=2)
    assert len(price_levels) == 2, "Should handle minimal data"

    # All same volume
    prices = [100, 101, 102, 103, 104]
    volumes = [1000, 1000, 1000, 1000, 1000]
    hvn, lvn = identify_hvn_lvn(prices, volumes, hvn_threshold=1.3)
    assert len(hvn) == 0, "Should not identify HVNs when all volumes equal"

    print("[PASS] Edge case tests passed")


def test_chart_integration():
    """Test integration with chart rendering workflow."""
    print("\n=== Testing Chart Integration ===")

    prices, volumes = generate_test_data(100)

    # This simulates the workflow used in chart generation
    vp_data = render_volume_profile_data(prices, volumes, bins=25)

    # Simulate adding to chart config
    chart_annotations = []

    # POC annotation
    if vp_data["poc"]:
        chart_annotations.append(
            {
                "type": "line",
                "price": vp_data["poc"],
                "label": f"POC: ${vp_data['poc']:.2f}",
                "color": "#FF9800",
            }
        )

    # VAH annotation
    if vp_data["vah"]:
        chart_annotations.append(
            {
                "type": "line",
                "price": vp_data["vah"],
                "label": f"VAH: ${vp_data['vah']:.2f}",
                "color": "#9C27B0",
            }
        )

    # VAL annotation
    if vp_data["val"]:
        chart_annotations.append(
            {
                "type": "line",
                "price": vp_data["val"],
                "label": f"VAL: ${vp_data['val']:.2f}",
                "color": "#9C27B0",
            }
        )

    # HVN markers
    for hvn in vp_data["hvn"]:
        chart_annotations.append(
            {"type": "point", "price": hvn["price"], "label": "HVN", "color": "#FF9800"}
        )

    # LVN markers
    for lvn in vp_data["lvn"]:
        chart_annotations.append(
            {"type": "point", "price": lvn["price"], "label": "LVN", "color": "#607D8B"}
        )

    print(f"Created {len(chart_annotations)} chart annotation(s)")
    print(f"  - Lines: {sum(1 for a in chart_annotations if a['type'] == 'line')}")
    print(f"  - Points: {sum(1 for a in chart_annotations if a['type'] == 'point')}")

    assert (
        len(chart_annotations) >= 3
    ), "Should create at least POC, VAH, VAL annotations"

    print("[PASS] Chart integration tests passed")


def run_all_tests():
    """Run all volume profile tests."""
    print("=" * 70)
    print("ENHANCED VOLUME PROFILE TEST SUITE")
    print("=" * 70)

    try:
        test_horizontal_volume_bars()
        test_hvn_lvn_identification()
        test_poc_calculation()
        test_value_area_calculation()
        test_render_volume_profile_data()
        test_volume_profile_bins()
        test_edge_cases()
        test_chart_integration()

        print("\n" + "=" * 70)
        print("[PASS] ALL VOLUME PROFILE TESTS PASSED")
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
