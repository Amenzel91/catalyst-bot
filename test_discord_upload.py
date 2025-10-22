"""Test Discord upload directly."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from src.catalyst_bot.discord_upload import post_embed_with_attachment

# Get webhook URL
webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
if not webhook_url:
    print("ERROR: DISCORD_WEBHOOK_URL not set!")
    exit(1)

print(f"Webhook URL: ...{webhook_url[-20:]}")

# Find the most recent chart
charts_dir = Path("out/charts")
if not charts_dir.exists():
    print(f"ERROR: {charts_dir} doesn't exist!")
    exit(1)

chart_files = list(charts_dir.glob("AAPL_*.png"))
if not chart_files:
    print("ERROR: No AAPL charts found!")
    exit(1)

# Get the most recent chart
chart_path = max(chart_files, key=lambda p: p.stat().st_mtime)
print(f"Using chart: {chart_path}")
print(f"Chart exists: {chart_path.exists()}")
print(f"Chart size: {chart_path.stat().st_size} bytes")

# Create a simple embed
embed = {
    "title": "Test Chart Upload",
    "description": "Testing direct chart upload",
    "color": 0x2ECC71,
    "image": {"url": f"attachment://{chart_path.name}"}
}

print("\nPosting to Discord...")
success = post_embed_with_attachment(webhook_url, embed, chart_path)

print(f"\nResult: {'SUCCESS' if success else 'FAILED'}")
print("Check Discord to see if the chart appeared!")
