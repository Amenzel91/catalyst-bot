"""
Quick test to verify Discord webhook is working.
"""
import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

if not webhook_url:
    print("[ERROR] DISCORD_WEBHOOK_URL not set in .env!")
    exit(1)

print(f"Testing webhook: {webhook_url[:50]}...")

# Create a simple test embed
embed = {
    "title": "[TEST] Catalyst Bot - Alert System Test",
    "description": "This is a test alert to verify the Discord webhook is functioning correctly.",
    "color": 0x00FF00,  # Green
    "fields": [
        {
            "name": "Status",
            "value": "[OK] All systems configured",
            "inline": True
        },
        {
            "name": "Keywords",
            "value": "128 total (59 new added today)",
            "inline": True
        },
        {
            "name": "Features",
            "value": "[OK] Closed-loop learning\n[OK] Sector multipliers\n[OK] Negative alerts\n[OK] MOA nightly",
            "inline": False
        }
    ],
    "footer": {
        "text": "Production readiness check"
    }
}

payload = {
    "embeds": [embed]
}

try:
    response = requests.post(webhook_url, json=payload, timeout=10)

    if response.status_code == 204:
        print("\n[SUCCESS] Alert posted to Discord!")
        print("   Check your Discord channel to verify the test alert appeared.")
    elif response.status_code == 429:
        print(f"\n[WARN] Rate limited by Discord (429)")
        print(f"   Retry after: {response.headers.get('Retry-After', 'unknown')} seconds")
    else:
        print(f"\n[FAIL] HTTP {response.status_code}")
        print(f"   Response: {response.text}")
        exit(1)

except Exception as e:
    print(f"\n[FAIL] Exception: {e}")
    exit(1)

print("\n" + "=" * 60)
print("If you see the test alert in Discord, the system is ready!")
print("=" * 60)
