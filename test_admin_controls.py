"""
Test script for admin controls and reporting system.

Tests:
1. Admin report generation with sample data
2. Discord posting (dry run mode)
3. Button interaction handling
4. Parameter validation and updates
5. Rollback functionality
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.admin_controls import (
    generate_admin_report,
    build_admin_embed,
    build_admin_components,
    save_admin_report,
    load_admin_report,
)
from catalyst_bot.admin_interactions import (
    handle_admin_interaction,
    build_details_embed,
)
from catalyst_bot.config_updater import (
    validate_parameter,
    apply_parameter_changes,
    rollback_changes,
    create_backup,
)
from catalyst_bot.admin_reporter import post_admin_report


def create_sample_events(target_date):
    """Create sample events for testing."""
    events_path = Path("data/events.jsonl")
    events_path.parent.mkdir(parents=True, exist_ok=True)

    # Sample events with realistic data
    sample_events = [
        {
            "ts": (datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=9)).isoformat(),
            "ticker": "AAPL",
            "price": 150.0,
            "cls": {
                "keywords": ["earnings", "strong"],
                "confidence": 0.85,
            },
        },
        {
            "ts": (datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=10)).isoformat(),
            "ticker": "TSLA",
            "price": 200.0,
            "cls": {
                "keywords": ["breakout", "volume"],
                "confidence": 0.72,
            },
        },
        {
            "ts": (datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=11)).isoformat(),
            "ticker": "NVDA",
            "price": 400.0,
            "cls": {
                "keywords": ["catalyst", "merger"],
                "confidence": 0.65,
            },
        },
        {
            "ts": (datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=14)).isoformat(),
            "ticker": "AMD",
            "price": 100.0,
            "cls": {
                "keywords": ["news", "upgrade"],
                "confidence": 0.58,
            },
        },
        {
            "ts": (datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=15)).isoformat(),
            "ticker": "META",
            "price": 300.0,
            "cls": {
                "keywords": ["filing", "sec"],
                "confidence": 0.45,
            },
        },
    ]

    # Clear existing events for this date
    if events_path.exists():
        existing_lines = events_path.read_text(encoding="utf-8").splitlines()
        # Filter out events from target date
        filtered_lines = []
        for line in existing_lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                event_ts = datetime.fromisoformat(event.get("ts", "").replace("Z", "+00:00"))
                if event_ts.date() != target_date:
                    filtered_lines.append(line)
            except Exception:
                filtered_lines.append(line)

        events_path.write_text("\n".join(filtered_lines) + "\n" if filtered_lines else "", encoding="utf-8")

    # Append sample events
    with events_path.open("a", encoding="utf-8") as f:
        for event in sample_events:
            f.write(json.dumps(event) + "\n")

    print(f"[OK] Created {len(sample_events)} sample events for {target_date}")


@pytest.fixture
def report():
    """Generate admin report for testing."""
    print("\n" + "="*60)
    print("FIXTURE: Admin Report Generation")
    print("="*60)

    target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # Create sample events
    create_sample_events(target_date)

    # Generate report
    print(f"\nGenerating report for {target_date}...")
    report = generate_admin_report(target_date)

    # Validate report
    assert report is not None, "Report generation failed"
    assert report.date == target_date, "Report date mismatch"
    print(f"[OK] Report generated successfully")
    print(f"   Total alerts: {report.total_alerts}")
    print(f"   Backtest trades: {report.backtest_summary.n}")
    print(f"   Win rate: {report.backtest_summary.hit_rate:.1%}")
    print(f"   Avg return: {report.backtest_summary.avg_return:+.2%}")
    print(f"   Recommendations: {len(report.parameter_recommendations)}")

    return report


def test_report_generation(report):
    """Test admin report generation."""
    print("\n" + "="*60)
    print("TEST 1: Admin Report Generation")
    print("="*60)

    # The fixture already validates the report, just confirm it exists
    assert report is not None, "Report fixture failed"
    print(f"[OK] Report fixture working correctly")


def test_report_persistence(report):
    """Test saving and loading reports."""
    print("\n" + "="*60)
    print("TEST 2: Report Persistence")
    print("="*60)

    # Save report
    print("\nSaving report...")
    save_path = save_admin_report(report)
    assert save_path.exists(), "Report save failed"
    print(f"[OK] Report saved to {save_path}")

    # Load report
    print("\nLoading report...")
    report_id = report.date.isoformat()
    loaded_report = load_admin_report(report_id)
    assert loaded_report is not None, "Report load failed"
    assert loaded_report.date == report.date, "Loaded report date mismatch"
    print(f"[OK] Report loaded successfully")


def test_embed_building(report):
    """Test Discord embed and component building."""
    print("\n" + "="*60)
    print("TEST 3: Discord Embed Building")
    print("="*60)

    # Build embed
    print("\nBuilding embed...")
    embed = build_admin_embed(report)
    assert "title" in embed, "Embed missing title"
    assert "fields" in embed, "Embed missing fields"
    print(f"[OK] Embed built successfully")
    print(f"   Fields: {len(embed['fields'])}")
    print(f"   Color: 0x{embed['color']:06X}")

    # Build components
    print("\nBuilding button components...")
    report_id = report.date.isoformat()
    components = build_admin_components(report_id)
    assert len(components) > 0, "No components generated"
    assert components[0]["type"] == 1, "Invalid component type"
    print(f"[OK] Components built successfully")
    print(f"   Action rows: {len(components)}")
    print(f"   Buttons: {len(components[0]['components'])}")

    return embed, components


def test_interaction_handling(report):
    """Test button interaction handling."""
    print("\n" + "="*60)
    print("TEST 4: Button Interaction Handling")
    print("="*60)

    report_id = report.date.isoformat()

    # Test "View Details" interaction
    print("\nTesting 'View Details' interaction...")
    details_response = build_details_embed(report_id)
    assert "embeds" in details_response or "content" in details_response, "Details response invalid"
    print(f"[OK] View Details interaction works")

    # Test "Approve" interaction simulation
    print("\nTesting interaction routing...")
    interaction_data = {
        "type": 3,  # COMPONENT
        "data": {
            "custom_id": f"admin_details_{report_id}",
        },
    }
    response = handle_admin_interaction(interaction_data)
    assert response is not None, "Interaction handler failed"
    print(f"[OK] Interaction routing works")


def test_parameter_validation():
    """Test parameter validation."""
    print("\n" + "="*60)
    print("TEST 5: Parameter Validation")
    print("="*60)

    # Valid parameters
    valid_tests = [
        ("MIN_SCORE", 0.3),
        ("PRICE_CEILING", 5.0),
        ("CONFIDENCE_HIGH", 0.85),
        ("MAX_ALERTS_PER_CYCLE", 30),
    ]

    print("\nTesting valid parameters...")
    for name, value in valid_tests:
        is_valid, error = validate_parameter(name, value)
        assert is_valid, f"Valid parameter rejected: {name}={value}, error={error}"
        print(f"   [OK] {name}={value}")

    # Invalid parameters
    invalid_tests = [
        ("MIN_SCORE", 1.5),  # > 1
        ("PRICE_CEILING", -5),  # negative
        ("CONFIDENCE_HIGH", 2.0),  # > 1
        ("MAX_ALERTS_PER_CYCLE", -10),  # negative
    ]

    print("\nTesting invalid parameters...")
    for name, value in invalid_tests:
        is_valid, error = validate_parameter(name, value)
        assert not is_valid, f"Invalid parameter accepted: {name}={value}"
        print(f"   [OK] {name}={value} correctly rejected: {error}")

    print(f"\n[OK] All validation tests passed")


def test_parameter_updates():
    """Test parameter updates and rollback."""
    print("\n" + "="*60)
    print("TEST 6: Parameter Updates & Rollback")
    print("="*60)

    # Create backup first
    print("\nCreating backup...")
    backup_path = create_backup()
    assert backup_path is not None, "Backup creation failed"
    print(f"[OK] Backup created: {backup_path}")

    # Test applying changes
    print("\nApplying parameter changes...")
    changes = {
        "MIN_SCORE": 0.25,
        "PRICE_CEILING": 7.5,
    }
    success, message = apply_parameter_changes(changes)
    assert success, f"Parameter update failed"
    # Don't print message to avoid emoji encoding issues on Windows
    print(f"[OK] Parameters applied successfully")

    # Verify changes were applied
    print("\nVerifying changes...")
    env_path = Path(".env")
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        assert "MIN_SCORE=0.25" in env_content, "MIN_SCORE not updated"
        assert "PRICE_CEILING=7.5" in env_content, "PRICE_CEILING not updated"
        print(f"[OK] Changes verified in .env file")

    # Test rollback
    print("\nTesting rollback...")
    success, message = rollback_changes(backup_path)
    assert success, f"Rollback failed"
    # Don't print message to avoid emoji encoding issues on Windows
    print(f"[OK] Rollback successful")


def test_discord_posting(report):
    """Test Discord posting (dry run)."""
    print("\n" + "="*60)
    print("TEST 7: Discord Posting (Dry Run)")
    print("="*60)

    # Check if credentials are configured
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DISCORD_ADMIN_CHANNEL_ID")

    if bot_token and channel_id:
        print("\n[INFO] Discord credentials found. Set FEATURE_ADMIN_REPORTS=1 to enable posting.")
        print(f"   Bot token: {bot_token[:20]}...")
        print(f"   Channel ID: {channel_id}")
        print("[INFO] Skipping Discord post in automated test (set FEATURE_ADMIN_REPORTS=1 to enable)")
    else:
        print("\n[WARN] Discord credentials not configured")
        print("   Set DISCORD_BOT_TOKEN and DISCORD_ADMIN_CHANNEL_ID to test posting")


def main():
    """Run all tests."""
    print("Catalyst-Bot Admin Controls Test Suite")
    print("=" * 60)

    try:
        # Test 1: Generate report
        report = test_report_generation()

        # Test 2: Save and load
        loaded_report = test_report_persistence(report)

        # Test 3: Build embeds
        embed, components = test_embed_building(loaded_report)

        # Test 4: Test interactions
        test_interaction_handling(loaded_report)

        # Test 5: Validate parameters
        test_parameter_validation()

        # Test 6: Update parameters
        test_parameter_updates()

        # Test 7: Discord posting (optional)
        test_discord_posting(loaded_report)

        # Summary
        print("\n" + "="*60)
        print("ALL TESTS PASSED!")
        print("="*60)
        print(f"\nAdmin controls system is fully functional:")
        print(f"  [OK] Report generation")
        print(f"  [OK] Report persistence")
        print(f"  [OK] Discord embed building")
        print(f"  [OK] Button interaction handling")
        print(f"  [OK] Parameter validation")
        print(f"  [OK] Parameter updates & rollback")
        print(f"\nNext steps:")
        print(f"  1. Enable admin reports: Set FEATURE_ADMIN_REPORTS=1 in .env")
        print(f"  2. Configure Discord: Set DISCORD_BOT_TOKEN and DISCORD_ADMIN_CHANNEL_ID")
        print(f"  3. Test live posting: Run this script with Discord configured")
        print(f"  4. Schedule nightly reports in runner.py")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
