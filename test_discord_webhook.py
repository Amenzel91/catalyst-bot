"""Test Discord webhook multipart upload to debug attachment display."""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()

webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

if not webhook_url:
    print("ERROR: DISCORD_WEBHOOK_URL not set in .env")
    sys.exit(1)

# Get the most recent chart and gauge
charts_dir = Path("out/charts")
gauges_dir = Path("out/gauges")

charts = sorted(charts_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
gauges = sorted(gauges_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)

if not charts:
    print("ERROR: No chart files found in out/charts")
    sys.exit(1)

chart_path = charts[0]
gauge_path = None  # DISABLE GAUGE to test if chart shows as image

print(f"Using chart: {chart_path.name}")
print("Gauge disabled for this test")

# Create test embed
embed = {
    "title": "Test: Discord Attachment Display",
    "description": "Testing if chart shows as main image and gauge as thumbnail",
    "color": 0x00FF00,
    "fields": [
        {"name": "Chart File", "value": chart_path.name, "inline": False},
        {"name": "Gauge File", "value": gauge_path.name if gauge_path else "None", "inline": False},
    ],
    # Set attachment references using FILENAMES (required for webhooks)
    "image": {"url": f"attachment://{chart_path.name}"},
    "thumbnail": {"url": f"attachment://{gauge_path.name}"} if gauge_path else {},
}

print("\n=== EMBED JSON ===")
print(json.dumps(embed, indent=2))

# Prepare multipart upload
files_dict = {}
open_files = []

try:
    # Upload chart as files[0] with filename reference
    f1 = open(chart_path, "rb")
    open_files.append(f1)
    files_dict["files[0]"] = (chart_path.name, f1, "image/png")

    # Upload gauge as files[1] with filename reference
    if gauge_path:
        f2 = open(gauge_path, "rb")
        open_files.append(f2)
        files_dict["files[1]"] = (gauge_path.name, f2, "image/png")

    print(f"\n=== FILES DICT KEYS ===")
    print(list(files_dict.keys()))

    # Send webhook request
    data = {"payload_json": json.dumps({"embeds": [embed]})}

    print("\n=== SENDING REQUEST ===")
    r = requests.post(webhook_url, data=data, files=files_dict, timeout=15)

    print(f"Status: {r.status_code}")
    if r.status_code >= 400:
        print(f"Error: {r.text}")
    else:
        print("Success! Check Discord to see if chart is embedded properly")

finally:
    for f in open_files:
        f.close()
