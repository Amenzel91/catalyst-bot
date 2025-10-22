"""
Quick .env verification for production launch.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(".env")
if not env_path.exists():
    print("[ERROR] .env file not found!")
    exit(1)

load_dotenv()

# Critical settings for production
checks = {
    "Core Features": {
        "FEATURE_RECORD_ONLY": ("0", "Must be 0 for production (live alerts)"),
        "FEATURE_ALERTS": ("1", "Must be 1 to send alerts"),
        "DISCORD_WEBHOOK_URL": ("https://", "Must start with https://"),
    },
    "Scoring & Filtering": {
        "MIN_SCORE": (None, "Minimum relevance score threshold"),
        "PRICE_CEILING": (None, "Maximum stock price for alerts"),
    },
    "API Keys": {
        "TIINGO_API_KEY": (None, "Required for intraday data"),
        "GEMINI_API_KEY": (None, "Required for LLM classification"),
        "ALPHAVANTAGE_API_KEY": (None, "Backup price provider"),
        "FINNHUB_API_KEY": (None, "Sentiment provider"),
    },
    "Features Enabled": {
        "FEATURE_TIINGO": ("1", "Enable Tiingo price provider"),
        "FEATURE_LLM_HYBRID": ("1", "Enable LLM hybrid router"),
        "FEATURE_PROMPT_COMPRESSION": ("1", "Enable prompt compression"),
        "FEATURE_SECTOR_MULTIPLIERS": ("1", "Enable MOA sector boosts"),
        "FEATURE_NEGATIVE_ALERTS": ("1", "Enable negative catalyst alerts"),
        "MOA_NIGHTLY_ENABLED": ("1", "Enable nightly MOA analysis"),
    }
}

print("=" * 70)
print(" PRODUCTION ENVIRONMENT VERIFICATION")
print("=" * 70)

all_passed = True
warnings = []

for category, settings in checks.items():
    print(f"\n[{category}]")
    for key, (expected, desc) in settings.items():
        value = os.getenv(key, "")

        if expected is None:
            # Just check if set
            if value:
                print(f"  [OK] {key} = {value[:20]}{'...' if len(value) > 20 else ''}")
            else:
                print(f"  [WARN] {key} = (not set) - {desc}")
                warnings.append(f"{key}: {desc}")
                all_passed = False
        else:
            # Check expected value
            if expected == "https://":
                # Check if starts with
                if value.startswith(expected):
                    print(f"  [OK] {key} = {value[:40]}...")
                else:
                    print(f"  [FAIL] {key} = '{value}' - {desc}")
                    all_passed = False
            else:
                # Exact match
                if value == expected:
                    print(f"  [OK] {key} = {value}")
                else:
                    actual = value if value else "(not set)"
                    print(f"  [FAIL] {key} = '{actual}' - Expected '{expected}' - {desc}")
                    all_passed = False

print("\n" + "=" * 70)
if all_passed:
    print(" [SUCCESS] All checks passed - Ready for production!")
else:
    print(f" [WARN] {len([w for w in warnings if w])} warnings found")
    if warnings:
        print("\n Warnings:")
        for w in warnings:
            print(f"   - {w}")
print("=" * 70)
