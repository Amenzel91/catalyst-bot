"""
Test Chart Alert Buttons
=========================

Generates a test stock alert with interactive chart timeframe buttons.

Usage:
    python test_chart_buttons.py           # Test with AAPL
    python test_chart_buttons.py TSLA      # Test with specific ticker
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load environment variables
from dotenv import load_dotenv
env_path = Path(__file__).parent / "env.env"
load_dotenv(env_path)

from catalyst_bot.alerts import send_alert_safe


def main():
    parser = argparse.ArgumentParser(description="Test chart alert buttons")
    parser.add_argument(
        "ticker",
        nargs="?",
        default="AAPL",
        help="Ticker symbol to test. Defaults to AAPL."
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()

    print(f"[*] Generating test alert for {ticker}...")
    print(f"[*] Using advanced charts: {os.getenv('FEATURE_ADVANCED_CHARTS', '0')}")
    print(f"[*] Bot token configured: {bool(os.getenv('DISCORD_BOT_TOKEN'))}")
    print(f"[*] Alert channel configured: {bool(os.getenv('DISCORD_ALERT_CHANNEL_ID'))}")
    print()

    # Create test event data
    test_event = {
        "ticker": ticker,
        "source": "test",
        "headline": f"Test Alert: {ticker} - Interactive Chart Buttons",
        "url": "https://example.com/test",
        "timestamp": "2025-10-02T14:00:00Z",
        "price": 150.00,
        "cls": {
            "score": 0.75,
            "category": "earnings",
            "sentiment": 0.6,
            "keywords": ["earnings", "revenue", "growth"]
        }
    }

    # Create scored event
    scored_event = {
        "item": test_event,
        "score": 0.75,
        "sentiment": 0.6,
        "category": "earnings"
    }

    # Get webhook URL from environment
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[ERROR] DISCORD_WEBHOOK_URL not set in env.env")
        return 1

    # Send alert
    print("[*] Posting test alert to Discord...")
    success = send_alert_safe(
        item_dict=test_event,
        scored=scored_event,
        last_price=152.50,
        last_change_pct=1.67,
        webhook_url=webhook_url
    )

    if success:
        print("[OK] Test alert posted successfully!")
        print()
        print("Check your Discord alerts channel:")
        print("  1. Verify the multi-panel chart is visible")
        print("  2. Verify timeframe buttons appear below the chart")
        print("  3. Click a button (e.g., '5D') to test timeframe switching")
        print("  4. Verify the chart updates and the clicked button becomes disabled")
        print()
        print("If buttons don't appear:")
        print("  - Check DISCORD_BOT_TOKEN is set in env.env")
        print("  - Check DISCORD_ALERT_CHANNEL_ID is set in env.env")
        print("  - Check interaction server is running")
        print("  - Check cloudflare tunnel is running")
    else:
        print("[ERROR] Failed to post test alert. Check logs.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
