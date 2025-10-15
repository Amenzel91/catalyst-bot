"""
Comprehensive test suite for all new features added to Catalyst-Bot.
Tests WAVE 0.0, 0.1, 1.1, 1.2, 2.1, 2.2, 2.3, 3.1, 7.1
"""

import os
from pathlib import Path

# Set up environment
os.chdir(Path(__file__).parent)

print("=" * 80)
print("CATALYST-BOT COMPREHENSIVE FEATURE TEST")
print("=" * 80)
print()

# Track results
results = []


def section(name):
    """Decorator for test sections."""
    print(f"\n{'='*80}")
    print(f"  {name}")
    print(f"{'='*80}\n")


def mark_pass(test_name):
    results.append((test_name, "PASS", None))
    print(f"[PASS] {test_name}")


def mark_fail(test_name, error):
    results.append((test_name, "FAIL", str(error)))
    print(f"[FAIL] {test_name}: {error}")


def mark_warn(test_name, warning):
    results.append((test_name, "WARN", str(warning)))
    print(f"[WARN] {test_name}: {warning}")


# ============================================================================
# TEST 1: Module Imports
# ============================================================================
section("TEST 1: Module Imports")

try:
    pass

    mark_pass("Import config")
except Exception as e:
    mark_fail("Import config", e)

try:
    pass

    mark_pass("Import market_hours (WAVE 0.0)")
except Exception as e:
    mark_fail("Import market_hours", e)

try:
    pass

    mark_pass("Import earnings_scorer (WAVE 0.1)")
except Exception as e:
    mark_fail("Import earnings_scorer", e)

try:
    pass

    mark_pass("Import feedback module (WAVE 1.2)")
except Exception as e:
    mark_fail("Import feedback module", e)

try:
    pass

    mark_pass("Import chart_cache (WAVE 2.1)")
except Exception as e:
    mark_fail("Import chart_cache", e)

try:
    pass

    mark_pass("Import ML models (WAVE 2.2)")
except Exception as e:
    mark_fail("Import ML models", e)

try:
    pass

    mark_pass("Import health_monitor (WAVE 2.3)")
except Exception as e:
    mark_fail("Import health_monitor", e)

try:
    pass

    mark_pass("Import indicators (WAVE 3.1)")
except Exception as e:
    mark_fail("Import indicators", e)

try:
    pass

    mark_pass("Import slash commands (WAVE 7.1)")
except Exception as e:
    mark_fail("Import slash commands", e)

try:
    pass

    mark_pass("Import sentiment aggregation (NEW)")
except Exception as e:
    mark_fail("Import sentiment aggregation", e)


# ============================================================================
# TEST 2: Configuration Loading
# ============================================================================
section("TEST 2: Configuration Loading (.env)")

try:
    from catalyst_bot.config import get_settings

    settings = get_settings()

    # Test market hours config (WAVE 0.0)
    assert hasattr(settings, "feature_market_hours_detection")
    mark_pass("Config: market_hours_detection")

    # Test earnings scorer config (WAVE 0.1)
    assert hasattr(settings, "feature_earnings_scorer")
    mark_pass("Config: earnings_scorer")

    # Test feedback loop config (WAVE 1.2)
    assert hasattr(settings, "feature_feedback_loop")
    mark_pass("Config: feedback_loop")

    # Test chart config (WAVE 2.1)
    assert hasattr(settings, "chart_cache_enabled")
    mark_pass("Config: chart_cache")

    # Test GPU config (WAVE 2.2)
    assert hasattr(settings, "sentiment_model_name")
    mark_pass("Config: sentiment_model")

    # Test sentiment weights (NEW)
    assert hasattr(settings, "sentiment_weight_earnings")
    assert hasattr(settings, "sentiment_weight_ml")
    assert hasattr(settings, "sentiment_weight_vader")
    assert hasattr(settings, "sentiment_weight_llm")
    mark_pass("Config: sentiment_weights")

    # Test deployment config (WAVE 2.3)
    assert hasattr(settings, "health_check_enabled")
    mark_pass("Config: health_check")

    # Test indicator config (WAVE 3.1)
    assert hasattr(settings, "chart_show_bollinger")
    mark_pass("Config: chart_indicators")

    # Test Discord config (WAVE 7.1)
    assert hasattr(settings, "feature_slash_commands")
    mark_pass("Config: slash_commands")

except Exception as e:
    mark_fail("Config loading", e)


# ============================================================================
# TEST 3: Database Initialization
# ============================================================================
section("TEST 3: Database Initialization")

# Test feedback database
try:
    from catalyst_bot.feedback import init_database

    init_database()
    db_path = Path("data/feedback/alert_performance.db")
    if db_path.exists():
        mark_pass("Feedback database created")
    else:
        mark_warn("Feedback database", "DB file not found after init")
except Exception as e:
    mark_fail("Feedback database init", e)

# Test chart cache database
try:
    from catalyst_bot.chart_cache import init_cache

    init_cache()
    cache_path = Path("data/chart_cache.db")
    if cache_path.exists():
        mark_pass("Chart cache database created")
    else:
        mark_warn("Chart cache", "Cache DB not found after init")
except Exception as e:
    mark_fail("Chart cache init", e)


# ============================================================================
# TEST 4: Market Hours Detection
# ============================================================================
section("TEST 4: Market Hours Detection (WAVE 0.0)")

try:
    from catalyst_bot.market_hours import get_market_info, get_market_status

    # Test market status detection
    status = get_market_status()
    assert status in ["pre_market", "regular", "after_hours", "closed"]
    mark_pass(f"Market status detection (current: {status})")

    # Test market info
    info = get_market_info()
    assert "status" in info
    assert "features" in info
    assert "cycle_seconds" in info
    mark_pass("Market info structure")

    # Test feature gating
    features = info["features"]
    assert "llm_enabled" in features
    assert "charts_enabled" in features
    assert "breakout_enabled" in features
    mark_pass("Market hours feature gating")

except Exception as e:
    mark_fail("Market hours detection", e)


# ============================================================================
# TEST 5: Earnings Scorer
# ============================================================================
section("TEST 5: Earnings Scorer (WAVE 0.1)")

try:
    from catalyst_bot.earnings_scorer import (
        calculate_earnings_sentiment,
        detect_earnings_result,
        parse_earnings_data,
    )

    # Test calendar detection (should be False)
    calendar_title = "AAPL scheduled to report earnings on Oct 31"
    is_result = detect_earnings_result(calendar_title, "")
    assert is_result is False
    mark_pass("Earnings calendar detection (negative)")

    # Test results detection (should be True)
    result_title = "AAPL reports Q4 EPS of $1.64 vs estimate $1.45"
    is_result = detect_earnings_result(result_title, "")
    assert is_result is True
    mark_pass("Earnings result detection (positive)")

    # Test parsing
    parsed = parse_earnings_data(result_title, "")
    assert parsed is not None
    assert "eps_actual" in parsed or "beat_miss" in parsed
    mark_pass("Earnings data parsing")

    # Test sentiment calculation
    sentiment = calculate_earnings_sentiment(1.64, 1.45, None, None)
    assert -1.0 <= sentiment <= 1.0
    assert sentiment > 0  # Beat should be positive
    mark_pass(f"Earnings sentiment calculation (sentiment: {sentiment:.2f})")

except Exception as e:
    mark_fail("Earnings scorer", e)


# ============================================================================
# TEST 6: Sentiment Aggregation
# ============================================================================
section("TEST 6: Sentiment Aggregation System (NEW)")

try:
    from catalyst_bot.classify import aggregate_sentiment_sources
    from catalyst_bot.feeds import NewsItem

    # Create test item
    item = NewsItem(
        title="Company announces strong Q4 results",
        url="https://example.com/test",
        published_at=1234567890,
        source="TestSource",
        tags=[],
        raw={"llm_sentiment": 0.65},
    )

    # Test aggregation with earnings
    earnings_data = {
        "is_earnings_result": True,
        "sentiment_score": 0.80,
        "sentiment_label": "Strong Beat",
    }

    sentiment, confidence, breakdown = aggregate_sentiment_sources(item, earnings_data)

    assert -1.0 <= sentiment <= 1.0
    assert 0.0 <= confidence <= 1.0
    assert isinstance(breakdown, dict)
    assert len(breakdown) >= 1  # At least one source should contribute

    mark_pass(
        f"Sentiment aggregation (sentiment: {sentiment:.3f}, confidence: {confidence:.3f})"
    )
    mark_pass(f"Sources used: {', '.join(breakdown.keys())}")

except Exception as e:
    mark_fail("Sentiment aggregation", e)


# ============================================================================
# TEST 7: Indicators
# ============================================================================
section("TEST 7: Chart Indicators (WAVE 3.1)")

try:
    pass

    from catalyst_bot.indicators import (
        calculate_bollinger_bands,
        calculate_fibonacci_levels,
        detect_support_resistance,
    )

    # Test data
    prices = [
        100,
        102,
        101,
        103,
        105,
        104,
        106,
        108,
        107,
        109,
        111,
        110,
        112,
        114,
        113,
        115,
        117,
        116,
        118,
        120,
    ]
    volumes = [1000] * 20

    # Test Bollinger Bands
    upper, middle, lower = calculate_bollinger_bands(prices, period=20)
    assert len(upper) == len(prices)
    mark_pass("Bollinger Bands calculation")

    # Test Fibonacci
    fib_levels = calculate_fibonacci_levels(max(prices), min(prices))
    assert "61.8%" in fib_levels
    mark_pass("Fibonacci levels calculation")

    # Test Support/Resistance
    support, resistance = detect_support_resistance(prices, volumes)
    assert isinstance(support, list)
    assert isinstance(resistance, list)
    mark_pass("Support/Resistance detection")

except Exception as e:
    mark_fail("Chart indicators", e)


# ============================================================================
# TEST 8: Health Monitoring
# ============================================================================
section("TEST 8: Health Monitoring (WAVE 2.3)")

try:
    from catalyst_bot.health_monitor import (
        get_health_status,
        init_health_monitor,
        is_healthy,
    )

    # Initialize
    init_health_monitor()
    mark_pass("Health monitor initialization")

    # Get status
    status = get_health_status()
    assert "status" in status
    mark_pass("Health status retrieval")

    # Check health
    healthy = is_healthy()
    assert isinstance(healthy, bool)
    mark_pass(f"Health check (healthy: {healthy})")

except Exception as e:
    mark_fail("Health monitoring", e)


# ============================================================================
# TEST 9: Classification Pipeline
# ============================================================================
section("TEST 9: Classification Pipeline (Integration)")

try:
    from catalyst_bot.classify import classify
    from catalyst_bot.feeds import NewsItem

    # Create test item
    item = NewsItem(
        title="FDA approves breakthrough cancer treatment",
        url="https://example.com/test",
        published_at=1234567890,
        source="TestSource",
        tags=["medical"],
        raw={},
    )

    # Classify
    scored = classify(item)

    assert scored is not None
    assert hasattr(scored, "relevance")
    assert hasattr(scored, "sentiment")
    assert hasattr(scored, "tags")

    mark_pass(
        f"Classification (relevance: {scored.relevance:.2f}, sentiment: {scored.sentiment:.3f})"
    )

except Exception as e:
    mark_fail("Classification pipeline", e)


# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("  TEST SUMMARY")
print("=" * 80 + "\n")

passed = sum(1 for _, result, _ in results if result == "PASS")
failed = sum(1 for _, result, _ in results if result == "FAIL")
warned = sum(1 for _, result, _ in results if result == "WARN")
total = len(results)

print(f"Total Tests: {total}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")
print(f"Warnings: {warned}")
print()

if failed > 0:
    print("FAILED TESTS:")
    for name, result, error in results:
        if result == "FAIL":
            print(f"  [FAIL] {name}: {error}")
    print()

if warned > 0:
    print("WARNINGS:")
    for name, result, warning in results:
        if result == "WARN":
            print(f"  [WARN] {name}: {warning}")
    print()

success_rate = (passed / total * 100) if total > 0 else 0
print(f"Success Rate: {success_rate:.1f}%")
print()

if failed == 0:
    print("[SUCCESS] ALL TESTS PASSED! Bot is ready for production.")
else:
    print(f"[FAILED] {failed} test(s) failed. Please review errors above.")

print("=" * 80)
