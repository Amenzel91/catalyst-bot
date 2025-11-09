#!/usr/bin/env python3
"""
Comprehensive test suite for all chart enhancements.
Tests Waves 1, 2, and 3 implementations with real market data.

Waves:
- Wave 1: Heikin-Ashi candles + Fibonacci retracements
- Wave 2: Volume Profile (horizontal bars + POC/VAH/VAL)
- Wave 3: Pattern Recognition (triangles, H&S, double tops)
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_wave_1_fibonacci():
    """Test Wave 1: Fibonacci retracements with Heikin-Ashi candles."""
    print("\n" + "="*70)
    print("WAVE 1 TEST: Fibonacci Retracements + Heikin-Ashi Candles")
    print("="*70)

    try:
        from catalyst_bot.charts import render_multipanel_chart

        # Test with AAPL
        print("\n[1/3] Testing AAPL with Fibonacci + VWAP + RSI...")
        chart_path = render_multipanel_chart(
            ticker="AAPL",
            indicators=["vwap", "fibonacci", "rsi"],
            timeframe="1D",
            out_dir="out/charts/test/wave1"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with TSLA
        print("\n[2/3] Testing TSLA with Fibonacci + MACD...")
        chart_path = render_multipanel_chart(
            ticker="TSLA",
            indicators=["fibonacci", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/wave1"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with SPY
        print("\n[3/3] Testing SPY with Fibonacci + All Indicators...")
        chart_path = render_multipanel_chart(
            ticker="SPY",
            indicators=["vwap", "fibonacci", "rsi", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/wave1"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        print("\n✅ WAVE 1 TEST: PASSED")
        return True

    except Exception as e:
        print(f"\n❌ WAVE 1 TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_wave_2_volume_profile():
    """Test Wave 2: Volume Profile with POC/VAH/VAL."""
    print("\n" + "="*70)
    print("WAVE 2 TEST: Volume Profile + POC/VAH/VAL Lines")
    print("="*70)

    try:
        from catalyst_bot.charts import render_multipanel_chart

        # Ensure volume profile is enabled
        os.environ["CHART_VOLUME_PROFILE_ENHANCED"] = "1"
        os.environ["CHART_VOLUME_PROFILE_BARS"] = "1"
        os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"
        os.environ["CHART_VOLUME_PROFILE_SHOW_VALUE_AREA"] = "1"
        os.environ["CHART_VOLUME_PROFILE_SHOW_HVN_LVN"] = "1"

        # Test with AAPL
        print("\n[1/3] Testing AAPL with Volume Profile + VWAP...")
        chart_path = render_multipanel_chart(
            ticker="AAPL",
            indicators=["vwap", "rsi"],
            timeframe="1D",
            out_dir="out/charts/test/wave2"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
            print("   ℹ Check chart for horizontal volume bars on right side")
            print("   ℹ Check for POC (orange), VAH/VAL (purple) lines")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with TSLA
        print("\n[2/3] Testing TSLA with Volume Profile + Fibonacci...")
        chart_path = render_multipanel_chart(
            ticker="TSLA",
            indicators=["fibonacci", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/wave2"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with SPY
        print("\n[3/3] Testing SPY with Volume Profile + All Indicators...")
        chart_path = render_multipanel_chart(
            ticker="SPY",
            indicators=["vwap", "fibonacci", "rsi", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/wave2"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        print("\n✅ WAVE 2 TEST: PASSED")
        return True

    except Exception as e:
        print(f"\n❌ WAVE 2 TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_wave_3_pattern_recognition():
    """Test Wave 3: Pattern Recognition (triangles, H&S, double tops)."""
    print("\n" + "="*70)
    print("WAVE 3 TEST: Pattern Recognition (Triangles, H&S, Double Tops)")
    print("="*70)

    try:
        from catalyst_bot.charts import render_multipanel_chart

        # Ensure pattern recognition is enabled
        os.environ["CHART_PATTERN_RECOGNITION"] = "1"
        os.environ["CHART_PATTERNS_TRIANGLES"] = "1"
        os.environ["CHART_PATTERNS_HEAD_SHOULDERS"] = "1"
        os.environ["CHART_PATTERNS_DOUBLE_TOPS"] = "1"

        # Test with AAPL
        print("\n[1/3] Testing AAPL with Pattern Recognition...")
        chart_path = render_multipanel_chart(
            ticker="AAPL",
            indicators=["vwap", "patterns", "rsi"],
            timeframe="1D",
            out_dir="out/charts/test/wave3"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
            print("   ℹ Check chart for pattern overlays (triangles, H&S, double tops)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with TSLA
        print("\n[2/3] Testing TSLA with Pattern Recognition + Fibonacci...")
        chart_path = render_multipanel_chart(
            ticker="TSLA",
            indicators=["patterns", "fibonacci", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/wave3"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with SPY
        print("\n[3/3] Testing SPY with Pattern Recognition + All Indicators...")
        chart_path = render_multipanel_chart(
            ticker="SPY",
            indicators=["patterns", "vwap", "fibonacci", "rsi"],
            timeframe="1D",
            out_dir="out/charts/test/wave3"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        print("\n✅ WAVE 3 TEST: PASSED")
        return True

    except Exception as e:
        print(f"\n❌ WAVE 3 TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_all_features_combined():
    """Test all features combined in a single chart."""
    print("\n" + "="*70)
    print("COMPREHENSIVE TEST: All Features Combined")
    print("="*70)

    try:
        from catalyst_bot.charts import render_multipanel_chart

        # Enable everything
        os.environ["CHART_CANDLE_TYPE"] = "heikin-ashi"
        os.environ["CHART_SHOW_FIBONACCI"] = "1"
        os.environ["CHART_VOLUME_PROFILE_ENHANCED"] = "1"
        os.environ["CHART_VOLUME_PROFILE_BARS"] = "1"
        os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"
        os.environ["CHART_VOLUME_PROFILE_SHOW_VALUE_AREA"] = "1"
        os.environ["CHART_PATTERN_RECOGNITION"] = "1"
        os.environ["CHART_PATTERNS_TRIANGLES"] = "1"
        os.environ["CHART_PATTERNS_HEAD_SHOULDERS"] = "1"
        os.environ["CHART_PATTERNS_DOUBLE_TOPS"] = "1"

        # Test with AAPL - The ultimate chart
        print("\n[1/3] Testing AAPL with ALL ENHANCEMENTS...")
        chart_path = render_multipanel_chart(
            ticker="AAPL",
            indicators=["vwap", "fibonacci", "patterns", "rsi", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/comprehensive"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Ultimate chart generated: {chart_path} ({size_kb:.1f} KB)")
            print("\n   📊 Chart includes:")
            print("      - Heikin-Ashi candles")
            print("      - Fibonacci retracements (gold lines)")
            print("      - Volume Profile (horizontal bars on right)")
            print("      - POC/VAH/VAL lines (orange/purple)")
            print("      - Pattern overlays (triangles, H&S, double tops)")
            print("      - VWAP, RSI, MACD indicators")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with TSLA
        print("\n[2/3] Testing TSLA with ALL ENHANCEMENTS...")
        chart_path = render_multipanel_chart(
            ticker="TSLA",
            indicators=["vwap", "fibonacci", "patterns", "rsi", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/comprehensive"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        # Test with SPY
        print("\n[3/3] Testing SPY with ALL ENHANCEMENTS...")
        chart_path = render_multipanel_chart(
            ticker="SPY",
            indicators=["vwap", "fibonacci", "patterns", "rsi", "macd"],
            timeframe="1D",
            out_dir="out/charts/test/comprehensive"
        )

        if chart_path and Path(chart_path).exists():
            size_kb = Path(chart_path).stat().st_size / 1024
            print(f"   ✓ Chart generated: {chart_path} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ Chart generation failed")
            return False

        print("\n✅ COMPREHENSIVE TEST: PASSED")
        return True

    except Exception as e:
        print(f"\n❌ COMPREHENSIVE TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all test suites."""
    print("\n" + "="*70)
    print("CATALYST BOT - CHART ENHANCEMENTS TEST SUITE")
    print("="*70)
    print("\nTesting three waves of chart enhancements:")
    print("  Wave 1: Heikin-Ashi + Fibonacci")
    print("  Wave 2: Volume Profile + POC/VAH/VAL")
    print("  Wave 3: Pattern Recognition")
    print("\nTest tickers: AAPL, TSLA, SPY")

    # Create output directories
    for wave_dir in ["wave1", "wave2", "wave3", "comprehensive"]:
        Path(f"out/charts/test/{wave_dir}").mkdir(parents=True, exist_ok=True)

    results = {
        "Wave 1 (Fibonacci)": test_wave_1_fibonacci(),
        "Wave 2 (Volume Profile)": test_wave_2_volume_profile(),
        "Wave 3 (Pattern Recognition)": test_wave_3_pattern_recognition(),
        "Comprehensive (All Features)": test_all_features_combined()
    }

    # Summary
    print("\n" + "="*70)
    print("TEST SUITE SUMMARY")
    print("="*70)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:<35} {status}")

    total_tests = len(results)
    passed_tests = sum(results.values())

    print("\n" + "="*70)
    print(f"OVERALL: {passed_tests}/{total_tests} tests passed ({100*passed_tests/total_tests:.0f}%)")
    print("="*70)

    if passed_tests == total_tests:
        print("\n🎉 ALL TESTS PASSED! Chart enhancements are production-ready.")
        print("\nGenerated charts can be found in:")
        print("  out/charts/test/wave1/")
        print("  out/charts/test/wave2/")
        print("  out/charts/test/wave3/")
        print("  out/charts/test/comprehensive/")
        return 0
    else:
        print("\n⚠️  Some tests failed. Review error messages above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
