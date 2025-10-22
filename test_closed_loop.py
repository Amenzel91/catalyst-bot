"""
Test the closed-loop keyword weight update system.

Verifies:
1. keyword_stats.json schema is correct
2. update_keyword_stats_file() function works
3. classify.py can load updated weights
4. Integration in runner.py is correct
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.moa_historical_analyzer import update_keyword_stats_file


def test_schema_format():
    """Test 1: Verify keyword_stats.json has correct schema."""
    print("\n" + "=" * 60)
    print("TEST 1: Verify keyword_stats.json Schema")
    print("=" * 60)

    stats_path = Path("data/analyzer/keyword_stats.json")
    if not stats_path.exists():
        print("[FAIL] FAIL: keyword_stats.json not found")
        return False

    with open(stats_path, 'r') as f:
        data = json.load(f)

    # Check for required top-level keys
    required_keys = ["weights", "last_updated", "source"]
    missing_keys = [k for k in required_keys if k not in data]

    if missing_keys:
        print(f"[FAIL] Missing keys: {missing_keys}")
        print(f"   Current schema: {list(data.keys())}")
        return False

    # Check that weights is a dict
    if not isinstance(data["weights"], dict):
        print(f"[FAIL] 'weights' should be a dict, got {type(data['weights'])}")
        return False

    print("[PASS] Schema is correct")
    print(f"   - weights: {len(data['weights'])} keywords")
    print(f"   - last_updated: {data['last_updated']}")
    print(f"   - source: {data['source']}")

    # Show sample weights
    print("\n   Sample weights:")
    for keyword, weight in list(data["weights"].items())[:5]:
        print(f"     - {keyword}: {weight}")

    return True


def test_update_function():
    """Test 2: Test update_keyword_stats_file() function."""
    print("\n" + "=" * 60)
    print("TEST 2: Test update_keyword_stats_file() Function")
    print("=" * 60)

    # Create test recommendations
    test_recommendations = [
        {
            "keyword": "test_keyword_1",
            "recommended_weight": 1.5,
            "confidence": 0.8,
            "reason": "High hit rate (75%)"
        },
        {
            "keyword": "test_keyword_2",
            "recommended_weight": 0.5,
            "confidence": 0.9,
            "reason": "Low hit rate (25%)"
        },
        {
            "keyword": "test_keyword_low_confidence",
            "recommended_weight": 2.0,
            "confidence": 0.4,  # Below threshold
            "reason": "Should be skipped"
        }
    ]

    try:
        # Apply recommendations with min_confidence=0.6
        stats_path = update_keyword_stats_file(
            test_recommendations, min_confidence=0.6
        )

        print(f"[OK] Function executed successfully")
        print(f"   - Updated file: {stats_path}")

        # Verify the updates
        with open(stats_path, 'r') as f:
            data = json.load(f)

        # Check that high-confidence recommendations were applied
        if "test_keyword_1" in data["weights"] and data["weights"]["test_keyword_1"] == 1.5:
            print(f"   - test_keyword_1: [OK] Applied (confidence 0.8 >= 0.6)")
        else:
            print(f"   - test_keyword_1: [FAIL] Not applied correctly")
            return False

        if "test_keyword_2" in data["weights"] and data["weights"]["test_keyword_2"] == 0.5:
            print(f"   - test_keyword_2: [OK] Applied (confidence 0.9 >= 0.6)")
        else:
            print(f"   - test_keyword_2: [FAIL] Not applied correctly")
            return False

        # Check that low-confidence recommendation was skipped
        if "test_keyword_low_confidence" not in data["weights"]:
            print(f"   - test_keyword_low_confidence: [OK] Skipped (confidence 0.4 < 0.6)")
        else:
            print(f"   - test_keyword_low_confidence: [FAIL] Should have been skipped")
            return False

        # Check metadata
        if data.get("updates_applied") == 2:
            print(f"   - updates_applied: [OK] {data['updates_applied']} (expected 2)")
        else:
            print(f"   - updates_applied: [FAIL] {data.get('updates_applied')} (expected 2)")
            return False

        print("[PASS] update_keyword_stats_file() works correctly")
        return True

    except Exception as e:
        print(f"[FAIL] FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_classify_integration():
    """Test 3: Verify classify.py can load the updated weights."""
    print("\n" + "=" * 60)
    print("TEST 3: Verify classify.py Integration")
    print("=" * 60)

    try:
        from catalyst_bot.classify import load_dynamic_keyword_weights

        weights = load_dynamic_keyword_weights()

        if not weights:
            print("[FAIL] FAIL: load_dynamic_keyword_weights() returned empty dict")
            return False

        # Check that our test keywords are present
        if "test_keyword_1" in weights and weights["test_keyword_1"] == 1.5:
            print(f"   - test_keyword_1: [OK] Loaded correctly (1.5)")
        else:
            print(f"   - test_keyword_1: [FAIL] Not loaded correctly")
            return False

        if "test_keyword_2" in weights and weights["test_keyword_2"] == 0.5:
            print(f"   - test_keyword_2: [OK] Loaded correctly (0.5)")
        else:
            print(f"   - test_keyword_2: [FAIL] Not loaded correctly")
            return False

        print(f"[OK] PASS: classify.py can load updated weights")
        print(f"   - Total keywords loaded: {len(weights)}")

        return True

    except Exception as e:
        print(f"[FAIL] FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_runner_integration():
    """Test 4: Verify runner.py has correct integration."""
    print("\n" + "=" * 60)
    print("TEST 4: Verify runner.py Integration")
    print("=" * 60)

    runner_path = Path("src/catalyst_bot/runner.py")
    with open(runner_path, 'r', encoding='utf-8') as f:
        runner_content = f.read()

    # Check for key integration points
    checks = [
        ("update_keyword_stats_file import", "from .moa_historical_analyzer import update_keyword_stats_file"),
        ("Load analysis report", "report_path = Path(\"data/moa/analysis_report.json\")"),
        ("Apply recommendations", "update_keyword_stats_file("),
        ("Min confidence threshold", "min_confidence=0.6"),
        ("Log success", "moa_keyword_weights_applied"),
    ]

    all_passed = True
    for check_name, check_string in checks:
        if check_string in runner_content:
            print(f"   - {check_name}: [OK]")
        else:
            print(f"   - {check_name}: [FAIL] Not found")
            all_passed = False

    if all_passed:
        print("[OK] PASS: runner.py integration is correct")
    else:
        print("[FAIL] FAIL: Some integration points missing")

    return all_passed


def cleanup_test_keywords():
    """Remove test keywords from keyword_stats.json."""
    print("\n" + "=" * 60)
    print("CLEANUP: Removing Test Keywords")
    print("=" * 60)

    stats_path = Path("data/analyzer/keyword_stats.json")
    with open(stats_path, 'r') as f:
        data = json.load(f)

    # Remove test keywords
    test_keywords = ["test_keyword_1", "test_keyword_2", "test_keyword_low_confidence"]
    removed = []
    for keyword in test_keywords:
        if keyword in data["weights"]:
            del data["weights"][keyword]
            removed.append(keyword)

    # Update metadata
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    data["source"] = "test_cleanup"

    # Save
    with open(stats_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"[OK] Removed {len(removed)} test keywords: {removed}")


def main():
    print("\n" + "=" * 70)
    print(" CLOSED-LOOP KEYWORD SYSTEM TEST SUITE")
    print("=" * 70)

    results = {
        "Schema Format": test_schema_format(),
        "Update Function": test_update_function(),
        "Classify Integration": test_classify_integration(),
        "Runner Integration": test_runner_integration(),
    }

    # Cleanup
    cleanup_test_keywords()

    # Summary
    print("\n" + "=" * 70)
    print(" TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"{status}: {test_name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED - Closed-loop system is ready for production!")
        return 0
    else:
        print("\n[WARN]  SOME TESTS FAILED - Review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())

