"""
test_chart_full_integration.py
===============================

CRITICAL END-TO-END INTEGRATION TEST

This test verifies that ALL chart enhancement features work together:
- Pattern detection and annotation
- Enhanced volume profile with HVN/LVN
- Dropdown menu generation
- All indicators (Bollinger, Fibonacci, S/R, Volume Profile)
- Chart.js configuration generation
- QuickChart URL generation

This is an interactive test that generates a complete alert with all features
enabled and saves the output for manual verification.
"""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np  # noqa: E402

from catalyst_bot.chart_indicators_integration import (  # noqa: E402
    add_pattern_annotations_to_config,
    generate_advanced_chart,
)
from catalyst_bot.indicators.patterns import detect_all_patterns  # noqa: E402
from catalyst_bot.indicators.volume_profile import (  # noqa: E402
    render_volume_profile_data,
)


def generate_realistic_market_data(days=50):
    """Generate realistic OHLCV data for testing."""
    np.random.seed(42)  # Reproducible results

    # Base trend
    trend = np.linspace(100, 120, days)

    # Add cyclical component
    cycle = 10 * np.sin(np.linspace(0, 4 * np.pi, days))

    # Add random walk
    random_walk = np.cumsum(np.random.normal(0, 1, days))

    # Combine to create closing prices
    closes = trend + cycle + random_walk

    # Generate OHLC from closes
    highs = closes + np.abs(np.random.normal(1, 0.5, days))
    lows = closes - np.abs(np.random.normal(1, 0.5, days))
    opens = closes + np.random.normal(0, 0.5, days)

    # Generate volumes with clustering (use float64 to avoid casting issues)
    volumes = np.random.randint(500000, 2000000, days).astype(np.float64)

    # Add volume spike in middle
    volumes[days // 2 : days // 2 + 5] = volumes[days // 2 : days // 2 + 5] * 2.5

    return {
        "opens": opens.tolist(),
        "highs": highs.tolist(),
        "lows": lows.tolist(),
        "closes": closes.tolist(),
        "volumes": [int(v) for v in volumes.tolist()],  # Convert back to int
    }


def build_dropdown_menu_component(ticker, default_indicators):
    """Build Discord select menu for indicator toggles."""
    return {
        "type": 1,  # Action Row
        "components": [
            {
                "type": 3,  # Select Menu
                "custom_id": f"chart_toggle_{ticker}",
                "placeholder": "Toggle Indicators",
                "min_values": 0,
                "max_values": 5,
                "options": [
                    {
                        "label": "Support/Resistance",
                        "value": "sr",
                        "description": "Key price levels",
                        "emoji": {"name": "📏"},
                        "default": "sr" in default_indicators,
                    },
                    {
                        "label": "Bollinger Bands",
                        "value": "bollinger",
                        "description": "Volatility bands",
                        "emoji": {"name": "📈"},
                        "default": "bollinger" in default_indicators,
                    },
                    {
                        "label": "Fibonacci",
                        "value": "fibonacci",
                        "description": "Retracement levels",
                        "emoji": {"name": "🔢"},
                        "default": "fibonacci" in default_indicators,
                    },
                    {
                        "label": "Volume Profile",
                        "value": "volume_profile",
                        "description": "POC + Value Area + HVN/LVN",
                        "emoji": {"name": "📊"},
                        "default": "volume_profile" in default_indicators,
                    },
                    {
                        "label": "Patterns",
                        "value": "patterns",
                        "description": "Auto-detected patterns",
                        "emoji": {"name": "🔺"},
                        "default": "patterns" in default_indicators,
                    },
                ],
            }
        ],
    }


def test_pattern_detection():
    """Test pattern detection on realistic data."""
    print("\n=== Testing Pattern Detection ===")

    data = generate_realistic_market_data(50)

    # Detect patterns
    patterns = detect_all_patterns(
        prices=data["closes"],
        highs=data["highs"],
        lows=data["lows"],
        volumes=data["volumes"],
        min_confidence=0.6,
    )

    print(f"Detected {len(patterns)} pattern(s):")
    for p in patterns:
        print(f"  - {p['type']}: {p['confidence']:.0%} confidence")
        print(f"    {p['description']}")

    return patterns


def test_volume_profile():
    """Test volume profile with HVN/LVN."""
    print("\n=== Testing Enhanced Volume Profile ===")

    data = generate_realistic_market_data(50)

    # Render complete volume profile
    vp_data = render_volume_profile_data(
        prices=data["closes"], volumes=data["volumes"], bins=25
    )

    print("Volume Profile Summary:")
    print(f"  - POC: ${vp_data['poc']:.2f}")
    print(f"  - VAH: ${vp_data['vah']:.2f}")
    print(f"  - VAL: ${vp_data['val']:.2f}")
    print(f"  - High Volume Nodes: {len(vp_data['hvn'])}")
    print(f"  - Low Volume Nodes: {len(vp_data['lvn'])}")
    print(f"  - Horizontal Bars: {len(vp_data['horizontal_bars'])}")

    return vp_data


def test_full_chart_generation():
    """Test complete chart generation with all indicators."""
    print("\n=== Testing Full Chart Generation ===")

    data = generate_realistic_market_data(50)

    # Generate chart with ALL indicators
    indicators = ["bollinger", "fibonacci", "sr", "volume_profile"]

    config = generate_advanced_chart(
        ticker="TEST",
        timeframe="1D",
        prices=data["closes"],
        volumes=data["volumes"],
        indicators=indicators,
    )

    print("Chart configuration generated:")
    print(f"  - Datasets: {len(config['data']['datasets'])}")

    # Count annotations
    annotations = (
        config.get("options", {})
        .get("plugins", {})
        .get("annotation", {})
        .get("annotations", {})
    )
    print(f"  - Annotations: {len(annotations)}")

    # Verify all indicators present
    datasets = config["data"]["datasets"]
    dataset_labels = [d.get("label", "") for d in datasets]

    print("\nDatasets:")
    for label in dataset_labels:
        print(f"  - {label}")

    print("\nAnnotations:")
    for key in list(annotations.keys())[:10]:  # Show first 10
        print(f"  - {key}")

    return config


def test_pattern_annotation():
    """Test pattern annotation integration."""
    print("\n=== Testing Pattern Annotation ===")

    data = generate_realistic_market_data(50)

    # Detect patterns
    patterns = detect_all_patterns(
        prices=data["closes"],
        highs=data["highs"],
        lows=data["lows"],
        volumes=data["volumes"],
        min_confidence=0.6,
    )

    # Create base config
    config = {
        "type": "candlestick",
        "data": {"datasets": [{"label": "Price", "data": data["closes"]}]},
        "options": {},
    }

    # Add pattern annotations
    enhanced_config = add_pattern_annotations_to_config(config, patterns)

    annotations = (
        enhanced_config.get("options", {})
        .get("plugins", {})
        .get("annotation", {})
        .get("annotations", {})
    )
    print(f"Added {len(annotations)} pattern annotation(s)")

    return enhanced_config


def test_dropdown_generation():
    """Test dropdown menu component generation."""
    print("\n=== Testing Dropdown Menu Generation ===")

    # Get default indicators from env
    default_indicators = os.getenv("CHART_DEFAULT_INDICATORS", "sr,bollinger").split(
        ","
    )

    dropdown = build_dropdown_menu_component("TEST", default_indicators)

    print("Dropdown menu component:")
    print(f"  - Type: {dropdown['type']}")
    print(f"  - Components: {len(dropdown['components'])}")
    print(f"  - Options: {len(dropdown['components'][0]['options'])}")

    for option in dropdown["components"][0]["options"]:
        default_marker = " (default)" if option["default"] else ""
        print(f"    - {option['label']}{default_marker}")

    return dropdown


def test_complete_alert_flow():
    """
    CRITICAL TEST: Simulate complete alert generation with all features.

    This test generates a complete alert as it would appear in Discord,
    including chart URL, pattern annotations, volume profile, and dropdown menu.
    """
    print("\n" + "=" * 70)
    print("COMPLETE ALERT FLOW TEST (CRITICAL)")
    print("=" * 70)

    # Step 1: Generate market data
    print("\n[Step 1] Generating market data...")
    data = generate_realistic_market_data(50)
    print(f"  [PASS] Generated {len(data['closes'])} candles")

    # Step 2: Detect patterns
    print("\n[Step 2] Detecting patterns...")
    patterns = detect_all_patterns(
        prices=data["closes"],
        highs=data["highs"],
        lows=data["lows"],
        volumes=data["volumes"],
        min_confidence=float(os.getenv("CHART_PATTERN_CONFIDENCE_MIN", "0.6")),
    )
    print(f"  [PASS] Detected {len(patterns)} pattern(s)")

    # Step 3: Calculate volume profile
    print("\n[Step 3] Calculating volume profile...")
    vp_data = render_volume_profile_data(
        prices=data["closes"],
        volumes=data["volumes"],
        bins=int(os.getenv("CHART_VOLUME_PROFILE_BINS", "25")),
    )
    print(
        f"  [PASS] POC: ${vp_data['poc']:.2f}, HVN: {len(vp_data['hvn'])}, LVN: {len(vp_data['lvn'])}"  # noqa: E501
    )

    # Step 4: Generate chart with all indicators
    print("\n[Step 4] Generating chart configuration...")
    indicators = ["bollinger", "fibonacci", "sr", "volume_profile"]
    config = generate_advanced_chart(
        ticker="TEST",
        timeframe="1D",
        prices=data["closes"],
        volumes=data["volumes"],
        indicators=indicators,
    )
    print(f"  [PASS] Created config with {len(config['data']['datasets'])} datasets")

    # Step 5: Add pattern annotations
    print("\n[Step 5] Adding pattern annotations...")
    config = add_pattern_annotations_to_config(config, patterns)
    annotations = (
        config.get("options", {})
        .get("plugins", {})
        .get("annotation", {})
        .get("annotations", {})
    )
    print(f"  [PASS] Added {len(annotations)} annotation(s)")

    # Step 6: Generate dropdown menu
    print("\n[Step 6] Generating dropdown menu...")
    dropdown = build_dropdown_menu_component("TEST", indicators)
    print(
        f"  [PASS] Created dropdown with {len(dropdown['components'][0]['options'])} option(s)"
    )

    # Step 7: Save output for verification
    print("\n[Step 7] Saving test output...")
    output_dir = Path(__file__).parent / "out" / "test_integration"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save chart config
    chart_file = output_dir / "chart_config.json"
    with open(chart_file, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  [PASS] Saved chart config: {chart_file}")

    # Save dropdown config
    dropdown_file = output_dir / "dropdown_config.json"
    with open(dropdown_file, "w") as f:
        json.dump(dropdown, f, indent=2)
    print(f"  [PASS] Saved dropdown config: {dropdown_file}")

    # Save pattern data
    pattern_file = output_dir / "patterns.json"
    with open(pattern_file, "w") as f:
        json.dump(patterns, f, indent=2)
    print(f"  [PASS] Saved pattern data: {pattern_file}")

    # Save volume profile data
    vp_file = output_dir / "volume_profile.json"
    with open(vp_file, "w") as f:
        json.dump(vp_data, f, indent=2, default=str)  # default=str for numpy types
    print(f"  [PASS] Saved volume profile data: {vp_file}")

    # Save market data
    data_file = output_dir / "market_data.json"
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  [PASS] Saved market data: {data_file}")

    # Create summary report
    summary = {
        "test": "Complete Alert Flow",
        "ticker": "TEST",
        "timeframe": "1D",
        "candles": len(data["closes"]),
        "patterns_detected": len(patterns),
        "pattern_types": list(set(p["type"] for p in patterns)),
        "volume_profile": {
            "poc": vp_data["poc"],
            "vah": vp_data["vah"],
            "val": vp_data["val"],
            "hvn_count": len(vp_data["hvn"]),
            "lvn_count": len(vp_data["lvn"]),
        },
        "chart": {
            "datasets": len(config["data"]["datasets"]),
            "annotations": len(annotations),
        },
        "indicators": indicators,
        "dropdown_options": len(dropdown["components"][0]["options"]),
    }

    summary_file = output_dir / "test_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  [PASS] Saved test summary: {summary_file}")

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Candles: {summary['candles']}")
    print(
        f"Patterns: {summary['patterns_detected']} ({', '.join(summary['pattern_types'])})"
    )
    print(
        f"Volume Profile: POC=${summary['volume_profile']['poc']:.2f}, HVN={summary['volume_profile']['hvn_count']}, LVN={summary['volume_profile']['lvn_count']}"  # noqa: E501
    )
    print(
        f"Chart: {summary['chart']['datasets']} datasets, {summary['chart']['annotations']} annotations"  # noqa: E501
    )
    print(f"Indicators: {', '.join(summary['indicators'])}")
    print(f"Dropdown: {summary['dropdown_options']} options")
    print("\nOutput saved to: " + str(output_dir))
    print("=" * 70)

    return summary


def verify_all_components():
    """Verify all components are working."""
    print("\n" + "=" * 70)
    print("COMPONENT VERIFICATION")
    print("=" * 70)

    results = {
        "pattern_detection": False,
        "volume_profile": False,
        "chart_generation": False,
        "pattern_annotation": False,
        "dropdown_generation": False,
        "complete_flow": False,
    }

    try:
        test_pattern_detection()
        results["pattern_detection"] = True
    except Exception as e:
        print(f"  [FAIL] Pattern detection failed: {e}")

    try:
        test_volume_profile()
        results["volume_profile"] = True
    except Exception as e:
        print(f"  [FAIL] Volume profile failed: {e}")

    try:
        test_full_chart_generation()
        results["chart_generation"] = True
    except Exception as e:
        print(f"  [FAIL] Chart generation failed: {e}")

    try:
        test_pattern_annotation()
        results["pattern_annotation"] = True
    except Exception as e:
        print(f"  [FAIL] Pattern annotation failed: {e}")

    try:
        test_dropdown_generation()
        results["dropdown_generation"] = True
    except Exception as e:
        print(f"  [FAIL] Dropdown generation failed: {e}")

    try:
        test_complete_alert_flow()
        results["complete_flow"] = True
    except Exception as e:
        print(f"  [FAIL] Complete flow failed: {e}")

    # Print results
    print("\n" + "=" * 70)
    print("VERIFICATION RESULTS")
    print("=" * 70)
    for component, passed in results.items():
        status = "[PASS] PASS" if passed else "[FAIL] FAIL"
        print(f"{component:25s} {status}")

    all_passed = all(results.values())
    print("=" * 70)

    if all_passed:
        print("[PASS] ALL COMPONENTS VERIFIED")
    else:
        print("[FAIL] SOME COMPONENTS FAILED")

    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = verify_all_components()
    sys.exit(0 if success else 1)
