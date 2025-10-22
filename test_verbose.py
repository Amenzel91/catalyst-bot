"""Test with verbose logging to see what's happening."""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Set up verbose logging BEFORE importing
logging.basicConfig(
    level=logging.DEBUG,
    format='%(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timezone
from src.catalyst_bot.alerts import send_alert_safe

# Create test data
item = {
    "ticker": "AAPL",
    "title": "Test Alert - Catalyst Event Detected",
    "link": "https://example.com/news/aapl-test-alert",
    "pubDate": datetime.now(timezone.utc).isoformat(),
    "source": "Test Generator",
    "price": 175.50,
    "prev_close": 170.00,
    "change_pct": 3.24,
    "volume": 50000000,
    "avg_volume": 45000000,
    "rvol": 1.11,
    "sentiment": 0.75,
    "catalyst_type": "Product Launch",
    "reason": "Apple announces new product",
}

scored = {
    "score": 7.5,
    "reason": "Apple announces new product",
    "sentiment": 0.75,
    "rvol": 1.11,
    "current_volume": 50000000,
    "avg_volume_20d": 45000000,
    "rvol_class": "NORMAL_RVOL",
}

print("=" * 60)
print("SENDING ALERT WITH VERBOSE LOGGING")
print("=" * 60)

success = send_alert_safe(item, scored, 175.50, 3.24)

print("=" * 60)
print(f"Result: {'SUCCESS' if success else 'FAILED'}")
print("=" * 60)
