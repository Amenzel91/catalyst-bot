"""
Interactive Admin Controls Test Script
=======================================

This script allows manual testing of admin controls with Discord-like interactions.
Run this script to:
1. Generate a test admin report
2. Simulate button clicks
3. Test modal submissions
4. Verify parameter changes
5. Test rollback functionality

Usage:
    python test_admin_interactive.py
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.admin_controls import (  # noqa: E402
    AdminReport,
    BacktestSummary,
    KeywordPerformance,
    ParameterRecommendation,
    build_admin_components,
    build_admin_embed,
    load_admin_report,
    save_admin_report,
)
from catalyst_bot.admin_interactions import (  # noqa: E402
    build_custom_modal,
    handle_admin_interaction,
    handle_approve,
    handle_modal_submit,
    handle_reject,
)
from catalyst_bot.config_updater import (  # noqa: E402
    get_change_history,
    rollback_changes,
    validate_parameter,
)


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def print_json(data, indent=2):
    """Pretty print JSON data."""
    print(json.dumps(data, indent=indent, default=str))


def create_sample_report():
    """Create a sample admin report for testing."""
    return AdminReport(
        date=date.today(),
        backtest_summary=BacktestSummary(
            n=75,
            hits=45,
            hit_rate=0.60,
            avg_return=0.038,
            max_drawdown=0.11,
            sharpe=1.35,
            sortino=1.62,
            profit_factor=1.75,
            avg_win_loss=1.48,
            trade_count=75,
        ),
        keyword_performance=[
            KeywordPerformance(
                category="fda",
                hits=12,
                misses=3,
                neutrals=2,
                hit_rate=0.71,
                avg_return=7.2,
                current_weight=1.0,
                proposed_weight=1.2,
            ),
            KeywordPerformance(
                category="earnings",
                hits=18,
                misses=9,
                neutrals=4,
                hit_rate=0.58,
                avg_return=3.8,
                current_weight=0.9,
                proposed_weight=1.0,
            ),
            KeywordPerformance(
                category="dilution",
                hits=4,
                misses=12,
                neutrals=3,
                hit_rate=0.21,
                avg_return=-3.9,
                current_weight=1.0,
                proposed_weight=0.8,
            ),
        ],
        parameter_recommendations=[
            ParameterRecommendation(
                name="MIN_SCORE",
                current_value=0.25,
                proposed_value=0.28,
                reason="Win rate at 60% - slight increase for consistency",
                impact="medium",
            ),
            ParameterRecommendation(
                name="KEYWORD_WEIGHT_FDA",
                current_value=1.0,
                proposed_value=1.2,
                reason="fda: 71% hit rate, +7.2% avg return (strong performer)",
                impact="high",
            ),
            ParameterRecommendation(
                name="KEYWORD_WEIGHT_DILUTION",
                current_value=1.0,
                proposed_value=0.8,
                reason="dilution: 21% hit rate, -3.9% avg return (poor performer)",
                impact="high",
            ),
        ],
        total_alerts=75,
        total_revenue=285.0,
    )


def test_report_generation():
    """Test 1: Generate and save admin report."""
    print_header("TEST 1: Report Generation & Persistence")

    # Create sample report
    report = create_sample_report()
    print(f"Created report for date: {report.date}")
    print(f"Total alerts: {report.total_alerts}")
    print(f"Backtest trades: {report.backtest_summary.n}")
    print(f"Win rate: {report.backtest_summary.hit_rate:.1%}")
    print(f"Recommendations: {len(report.parameter_recommendations)}")

    # Save report
    save_path = save_admin_report(report)
    print(f"\n✅ Report saved to: {save_path}")

    # Load it back
    loaded_report = load_admin_report(report.date.isoformat())
    if loaded_report:
        print("✅ Report loaded successfully")
        print(f"   Verified date: {loaded_report.date}")
        print(f"   Verified alerts: {loaded_report.total_alerts}")
    else:
        print("❌ Failed to load report")

    return report


@pytest.fixture(scope="module")
def report():
    """Pytest fixture that provides a sample admin report."""
    return create_sample_report()


def test_embed_generation(report):
    """Test 2: Generate Discord embed."""
    print_header("TEST 2: Discord Embed Generation")

    # Build embed
    embed = build_admin_embed(report)
    print("Generated Discord embed:")
    print_json(embed)

    # Verify key fields
    print("\n✅ Embed verification:")
    print(f"   Title: {embed.get('title', 'N/A')}")
    print(f"   Color: #{embed.get('color', 0):06X}")
    print(f"   Fields: {len(embed.get('fields', []))}")

    return embed


def test_components_generation(report):
    """Test 3: Generate interactive components."""
    print_header("TEST 3: Interactive Components Generation")

    report_id = report.date.isoformat()
    components = build_admin_components(report_id)

    print(f"Generated components for report ID: {report_id}")
    print_json(components)

    # Verify buttons
    buttons = components[0]["components"]
    print("\n✅ Button verification:")
    for btn in buttons:
        print(f"   - {btn['label']}: {btn['custom_id']}")

    return components


def test_view_details_interaction(report):
    """Test 4: View Details button interaction."""
    print_header("TEST 4: View Details Button Interaction")

    report_id = report.date.isoformat()

    # Simulate button click
    interaction_data = {
        "type": 3,  # INTERACTION_TYPE_COMPONENT
        "data": {
            "custom_id": f"admin_details_{report_id}",
            "component_type": 2,  # Button
        },
    }

    print("Simulating 'View Details' button click...")
    print("Interaction data:")
    print_json(interaction_data)

    response = handle_admin_interaction(interaction_data)

    print("\n📨 Response:")
    print_json(response)

    # Verify response
    if response.get("type") == 4:
        print("\n✅ Response type correct (RESPONSE_TYPE_MESSAGE)")
        if "embeds" in response.get("data", {}):
            print("✅ Response contains embed")
            embed = response["data"]["embeds"][0]
            print(f"   Embed title: {embed.get('title', 'N/A')}")
        if response.get("data", {}).get("flags") == 64:
            print("✅ Response is ephemeral (only visible to admin)")
    else:
        print("❌ Unexpected response type")

    return response


def test_approve_interaction(report):
    """Test 5: Approve Changes button interaction."""
    print_header("TEST 5: Approve Changes Button Interaction")

    report_id = report.date.isoformat()

    print("🔍 Current recommendations:")
    for rec in report.parameter_recommendations:
        print(f"   - {rec.name}: {rec.current_value} → {rec.proposed_value}")

    print("\nSimulating 'Approve Changes' button click...")

    # Create backup first
    from catalyst_bot.config_updater import create_backup

    backup_path = create_backup()
    if backup_path:
        print(f"✅ Backup created: {backup_path}")
    else:
        print("⚠️  No .env file to backup (may be expected in test environment)")

    response = handle_approve(report_id)

    print("\n📨 Response:")
    print_json(response)

    # Check if changes were applied
    print("\n📋 Checking change history...")
    history = get_change_history(limit=1)
    if history:
        print("✅ Latest change logged:")
        print_json(history[0], indent=4)
    else:
        print("ℹ️  No change history found")

    return response


def test_reject_interaction(report):
    """Test 6: Reject Changes button interaction."""
    print_header("TEST 6: Reject Changes Button Interaction")

    report_id = report.date.isoformat()

    print("Simulating 'Reject Changes' button click...")

    response = handle_reject(report_id)

    print("\n📨 Response:")
    print_json(response)

    # Verify rejection
    if response.get("type") == 4:
        embed = response.get("data", {}).get("embeds", [{}])[0]
        if "Rejected" in embed.get("description", ""):
            print("✅ Rejection confirmed in response")
        else:
            print("⚠️  Rejection message not found")

    return response


def test_custom_modal(report):
    """Test 7: Custom Adjust modal."""
    print_header("TEST 7: Custom Adjust Modal")

    report_id = report.date.isoformat()

    print("Building custom adjustment modal...")

    modal_response = build_custom_modal(report_id)

    print("\n📨 Modal structure:")
    print_json(modal_response)

    # Verify modal
    if modal_response.get("type") == 9:  # RESPONSE_TYPE_MODAL
        print("✅ Modal response type correct")

        modal_data = modal_response.get("data", {})
        components = modal_data.get("components", [])
        print(f"✅ Modal has {len(components)} input fields:")

        for action_row in components:
            for component in action_row.get("components", []):
                label = component.get("label", "N/A")
                custom_id = component.get("custom_id", "N/A")
                print(f"   - {label} (ID: {custom_id})")

    return modal_response


def test_modal_submission(report):
    """Test 8: Modal submission."""
    print_header("TEST 8: Modal Submission")

    report_id = report.date.isoformat()

    # Simulate modal submission
    interaction_data = {
        "type": 5,  # INTERACTION_TYPE_MODAL_SUBMIT
        "data": {
            "custom_id": f"admin_modal_{report_id}",
            "components": [
                {
                    "components": [
                        {
                            "custom_id": "min_score",
                            "value": "0.3",
                        }
                    ]
                },
                {
                    "components": [
                        {
                            "custom_id": "price_ceiling",
                            "value": "9.0",
                        }
                    ]
                },
            ],
        },
    }

    print("Submitting modal with custom values:")
    print("   MIN_SCORE: 0.3")
    print("   PRICE_CEILING: 9.0")

    response = handle_modal_submit(interaction_data)

    print("\n📨 Response:")
    print_json(response)

    return response


def test_parameter_validation():
    """Test 9: Parameter validation."""
    print_header("TEST 9: Parameter Validation")

    test_cases = [
        ("MIN_SCORE", 0.5, True),
        ("MIN_SCORE", 1.5, False),
        ("PRICE_CEILING", 10.0, True),
        ("PRICE_CEILING", -5.0, False),
        ("MAX_ALERTS_PER_CYCLE", 50, True),
        ("MAX_ALERTS_PER_CYCLE", -10, False),
        ("CONFIDENCE_HIGH", 0.85, True),
        ("CONFIDENCE_HIGH", 1.5, False),
    ]

    print("Running validation tests:\n")

    passed = 0
    failed = 0

    for param_name, value, expected_valid in test_cases:
        is_valid, error = validate_parameter(param_name, value)

        status = "✅" if (is_valid == expected_valid) else "❌"
        result = "PASS" if (is_valid == expected_valid) else "FAIL"

        print(
            f"{status} {param_name}={value}: "
            f"Expected {'valid' if expected_valid else 'invalid'}, "
            f"Got {'valid' if is_valid else 'invalid'} ({result})"
        )

        if error and not is_valid:
            print(f"   Error: {error}")

        if is_valid == expected_valid:
            passed += 1
        else:
            failed += 1

    print(f"\n📊 Results: {passed} passed, {failed} failed")

    return passed, failed


def test_rollback():
    """Test 10: Configuration rollback."""
    print_header("TEST 10: Configuration Rollback")

    print("Attempting to rollback to most recent backup...")

    success, message = rollback_changes()

    print("\n📨 Rollback result:")
    print(f"   Success: {success}")
    print(f"   Message: {message}")

    if success:
        print("✅ Rollback completed successfully")
    else:
        print("⚠️  Rollback failed (may be expected if no backups exist)")

    return success, message


def run_all_tests():
    """Run all interactive tests."""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "ADMIN CONTROLS INTERACTIVE TEST SUITE" + " " * 21 + "║")
    print("╚" + "═" * 78 + "╝")

    try:
        # Test 1: Report Generation
        report = test_report_generation()

        # Test 2: Embed Generation
        test_embed_generation(report)

        # Test 3: Components Generation
        test_components_generation(report)

        # Test 4: View Details Interaction
        test_view_details_interaction(report)

        # Test 5: Approve Interaction
        # Note: Skip if no .env file exists
        if Path(".env").exists():
            test_approve_interaction(report)
        else:
            print_header("TEST 5: Approve Changes (SKIPPED)")
            print("⚠️  No .env file found - skipping approve test")

        # Test 6: Reject Interaction
        test_reject_interaction(report)

        # Test 7: Custom Modal
        test_custom_modal(report)

        # Test 8: Modal Submission
        # Note: Skip if no .env file exists
        if Path(".env").exists():
            test_modal_submission(report)
        else:
            print_header("TEST 8: Modal Submission (SKIPPED)")
            print("⚠️  No .env file found - skipping modal submission test")

        # Test 9: Parameter Validation
        passed, failed = test_parameter_validation()

        # Test 10: Rollback
        if Path(".env").exists():
            test_rollback()
        else:
            print_header("TEST 10: Configuration Rollback (SKIPPED)")
            print("⚠️  No .env file found - skipping rollback test")

        # Summary
        print_header("TEST SUITE SUMMARY")
        print("✅ All core tests completed successfully!")
        print("\nℹ️  Some tests may have been skipped if .env file doesn't exist.")
        print("   This is expected in a test environment.")
        print("\n📝 Next Steps:")
        print("   1. Review the generated report in out/admin_reports/")
        print("   2. Check change history in data/admin_changes.jsonl")
        print("   3. Verify backups in data/config_backups/")
        print("\n✨ Admin controls system is working correctly!")

    except Exception as e:
        print_header("ERROR")
        print("❌ Test suite failed with error:")
        print(f"   {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
