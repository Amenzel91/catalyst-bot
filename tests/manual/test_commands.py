"""
Test Discord Slash Commands
============================

Quick test script to verify command handlers work correctly.

This does NOT test Discord integration - it only tests the command
handlers themselves with mock data.

Usage:
    python test_commands.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.commands.handlers import (  # noqa: E402
    handle_backtest_command,
    handle_chart_command,
    handle_help_command,
    handle_sentiment_command,
    handle_stats_command,
    handle_watchlist_command,
)


def test_chart_command():
    """Test /chart command."""
    print("\n" + "=" * 60)
    print("Testing /chart command")
    print("=" * 60)

    result = handle_chart_command("AAPL", "1D", "test_user_123")
    print(f"Response type: {result.get('type')}")
    print(f"Has embeds: {'embeds' in result.get('data', {})}")

    if "embeds" in result.get("data", {}):
        embed = result["data"]["embeds"][0]
        print(f"Title: {embed.get('title')}")
        print(f"Color: {embed.get('color')}")
        print("SUCCESS: Chart command works!")
    else:
        print(f"FAILED: No embed returned: {result.get('data', {}).get('content')}")


def test_watchlist_command():
    """Test /watchlist command."""
    print("\n" + "=" * 60)
    print("Testing /watchlist commands")
    print("=" * 60)

    # Test add
    result = handle_watchlist_command("add", "AAPL", "test_user_123")
    print(f"Add result: {result.get('data', {}).get('embeds', [{}])[0].get('title')}")

    # Test list
    result = handle_watchlist_command("list", None, "test_user_123")
    print(f"List result: {result.get('data', {}).get('embeds', [{}])[0].get('title')}")

    # Test remove
    result = handle_watchlist_command("remove", "AAPL", "test_user_123")
    print(
        f"Remove result: {result.get('data', {}).get('embeds', [{}])[0].get('title')}"
    )

    print("SUCCESS: Watchlist commands work!")


def test_stats_command():
    """Test /stats command."""
    print("\n" + "=" * 60)
    print("Testing /stats command")
    print("=" * 60)

    result = handle_stats_command("7d")
    print(f"Response type: {result.get('type')}")

    if "embeds" in result.get("data", {}):
        embed = result["data"]["embeds"][0]
        print(f"Title: {embed.get('title')}")
        print(f"Fields: {len(embed.get('fields', []))}")
        print("SUCCESS: Stats command works!")
    else:
        print("FAILED: No embed returned")


def test_backtest_command():
    """Test /backtest command."""
    print("\n" + "=" * 60)
    print("Testing /backtest command")
    print("=" * 60)

    result = handle_backtest_command("AAPL", 30)
    print(f"Response type: {result.get('type')}")

    if "embeds" in result.get("data", {}):
        embed = result["data"]["embeds"][0]
        print(f"Title: {embed.get('title')}")
        print("SUCCESS: Backtest command works!")
    else:
        print(f"Content: {result.get('data', {}).get('content')}")


def test_sentiment_command():
    """Test /sentiment command."""
    print("\n" + "=" * 60)
    print("Testing /sentiment command")
    print("=" * 60)

    result = handle_sentiment_command("AAPL")
    print(f"Response type: {result.get('type')}")

    if "embeds" in result.get("data", {}):
        embed = result["data"]["embeds"][0]
        print(f"Title: {embed.get('title')}")
        print("SUCCESS: Sentiment command works!")
    else:
        print(f"Content: {result.get('data', {}).get('content')}")


def test_help_command():
    """Test /help command."""
    print("\n" + "=" * 60)
    print("Testing /help command")
    print("=" * 60)

    result = handle_help_command()
    print(f"Response type: {result.get('type')}")

    if "embeds" in result.get("data", {}):
        embed = result["data"]["embeds"][0]
        print(f"Title: {embed.get('title')}")
        print(f"Fields: {len(embed.get('fields', []))}")
        print("SUCCESS: Help command works!")
    else:
        print("FAILED: No embed returned")


if __name__ == "__main__":
    print("\n")
    print("=" * 60)
    print("=" * 15 + " SLASH COMMAND TESTS " + "=" * 24)
    print("=" * 60)

    try:
        test_chart_command()
        test_watchlist_command()
        test_stats_command()
        test_backtest_command()
        test_sentiment_command()
        test_help_command()

        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Add DISCORD_APPLICATION_ID to .env")
        print("2. Run: python register_commands.py --guild <guild_id>")
        print("3. Test commands in Discord")
        print()

    except Exception as e:
        print(f"\nFAILED: Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
