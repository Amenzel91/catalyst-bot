#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test script for market hours detection.

This script demonstrates the market hours detection system by checking
the current market status and simulating different times of day.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.catalyst_bot.market_hours import (
    get_cycle_seconds,
    get_feature_config,
    get_market_info,
)

ET = ZoneInfo("America/New_York")


def test_current_status():
    """Test current market status."""
    print("=" * 70)
    print("CURRENT MARKET STATUS")
    print("=" * 70)

    now = datetime.now(timezone.utc)
    info = get_market_info(now)

    print(f"\nCurrent Time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Current Time (ET):  {now.astimezone(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"\nMarket Status:      {info['status']}")
    print(f"Cycle Time:         {info['cycle_seconds']} seconds")
    print(f"Is Warmup:          {info['is_warmup']}")
    print(f"Is Weekend:         {info['is_weekend']}")
    print(f"Is Holiday:         {info['is_holiday']}")

    print("\nFeatures Enabled:")
    for feature, enabled in info["features"].items():
        status = "[X] ENABLED" if enabled else "[ ] DISABLED"
        print(f"  {feature:20s} {status}")


def test_time_scenarios():
    """Test various time scenarios."""
    print("\n" + "=" * 70)
    print("TIME SCENARIO TESTS")
    print("=" * 70)

    # Create a reference date (a weekday, not a holiday)
    # Using January 2, 2025 (Thursday)
    base_date = datetime(2025, 1, 2, tzinfo=ET)

    scenarios = [
        ("Pre-market (7:00 AM ET)", base_date.replace(hour=7, minute=0)),
        ("Market Open (9:30 AM ET)", base_date.replace(hour=9, minute=30)),
        ("Mid-day (12:00 PM ET)", base_date.replace(hour=12, minute=0)),
        ("Market Close (4:00 PM ET)", base_date.replace(hour=16, minute=0)),
        ("After-hours (5:00 PM ET)", base_date.replace(hour=17, minute=0)),
        ("Evening Closed (9:00 PM ET)", base_date.replace(hour=21, minute=0)),
        ("Early Morning (3:00 AM ET)", base_date.replace(hour=3, minute=0)),
    ]

    for label, dt in scenarios:
        info = get_market_info(dt.astimezone(timezone.utc))
        features = info["features"]
        enabled_count = sum(1 for v in features.values() if v)

        print(f"\n{label}")
        print(
            f"  Status: {info['status']:15s} Cycle: {info['cycle_seconds']:3d}s  Features: {enabled_count}/3 enabled"  # noqa: E501
        )


def test_weekend_and_holiday():
    """Test weekend and holiday detection."""
    print("\n" + "=" * 70)
    print("WEEKEND & HOLIDAY TESTS")
    print("=" * 70)

    # Saturday
    saturday = datetime(2025, 1, 4, 12, 0, tzinfo=ET)  # January 4, 2025 is Saturday
    info = get_market_info(saturday.astimezone(timezone.utc))
    print("\nSaturday (Jan 4, 2025 12:00 PM ET)")
    print(
        f"  Status: {info['status']:15s} Weekend: {info['is_weekend']}  Holiday: {info['is_holiday']}"  # noqa: E501
    )

    # New Year's Day
    new_years = datetime(2025, 1, 1, 12, 0, tzinfo=ET)
    info = get_market_info(new_years.astimezone(timezone.utc))
    print("\nNew Year's Day (Jan 1, 2025 12:00 PM ET)")
    print(
        f"  Status: {info['status']:15s} Weekend: {info['is_weekend']}  Holiday: {info['is_holiday']}"  # noqa: E501
    )

    # Independence Day
    july_4 = datetime(2025, 7, 4, 12, 0, tzinfo=ET)
    info = get_market_info(july_4.astimezone(timezone.utc))
    print("\nIndependence Day (Jul 4, 2025 12:00 PM ET)")
    print(
        f"  Status: {info['status']:15s} Weekend: {info['is_weekend']}  Holiday: {info['is_holiday']}"  # noqa: E501
    )


def test_feature_gating():
    """Test feature gating based on market status."""
    print("\n" + "=" * 70)
    print("FEATURE GATING BY MARKET STATUS")
    print("=" * 70)

    statuses = ["regular", "pre_market", "after_hours", "closed"]

    for status in statuses:
        config = get_feature_config(status)
        cycle = get_cycle_seconds(status)

        print(f"\n{status.upper():15s} (Cycle: {cycle}s)")
        for feature, enabled in config.items():
            status_icon = "[X]" if enabled else "[ ]"
            print(f"  {status_icon} {feature}")


def main():
    """Run all tests."""
    print("\n")
    print("+" + "=" * 68 + "+")
    print("|" + " " * 68 + "|")
    print(
        "|" + "  WAVE 0.0 Phase 2: Market Hours Detection Test Suite".center(68) + "|"
    )
    print("|" + " " * 68 + "|")
    print("+" + "=" * 68 + "+")

    test_current_status()
    test_time_scenarios()
    test_weekend_and_holiday()
    test_feature_gating()

    print("\n" + "=" * 70)
    print("Example Log Output (when bot is running):")
    print("=" * 70)
    print(
        """
INFO market_status status=regular cycle=60s features=llm_enabled,charts_enabled,breakout_enabled warmup=False weekend=False holiday=False  # noqa: E501
INFO CYCLE_DONE took=2.34s

INFO market_status status=after_hours cycle=90s features=llm_enabled,breakout_enabled warmup=False weekend=False holiday=False  # noqa: E501
INFO CYCLE_DONE took=1.87s

INFO market_status status=closed cycle=180s features= warmup=False weekend=False holiday=False
DEBUG breakout_scanner_skipped reason=market_closed
INFO CYCLE_DONE took=0.92s
    """.strip()
    )

    print("\n" + "=" * 70)
    print("[X] All tests completed successfully!")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
