"""
Register Discord Slash Commands
================================

Run this script once to register all slash commands with Discord.

Usage:
    python register_discord_commands.py

Requires:
    - DISCORD_BOT_TOKEN in .env
    - DISCORD_APP_ID in .env
"""

import os
import requests
from dotenv import load_dotenv

# Load environment
load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
APP_ID = os.getenv("DISCORD_APP_ID")

if not BOT_TOKEN or not APP_ID:
    print("❌ Error: DISCORD_BOT_TOKEN and DISCORD_APP_ID must be set in .env")
    exit(1)

# Command definitions
COMMANDS = [
    # Admin commands
    {
        "name": "admin",
        "description": "Admin controls for bot configuration",
        "options": [
            {
                "name": "report",
                "description": "Generate and post admin report",
                "type": 1,  # SUB_COMMAND
                "options": [
                    {
                        "name": "date",
                        "description": "Date in YYYY-MM-DD format (default: yesterday)",
                        "type": 3,  # STRING
                        "required": False,
                    }
                ],
            },
            {
                "name": "set",
                "description": "Update a bot parameter",
                "type": 1,
                "options": [
                    {
                        "name": "parameter",
                        "description": "Parameter name (e.g., MIN_SCORE)",
                        "type": 3,
                        "required": True,
                    },
                    {
                        "name": "value",
                        "description": "New value",
                        "type": 3,
                        "required": True,
                    },
                ],
            },
            {
                "name": "rollback",
                "description": "Rollback to previous configuration",
                "type": 1,
            },
            {
                "name": "stats",
                "description": "Show current parameter values",
                "type": 1,
            },
        ],
    },
    # Public commands
    {
        "name": "check",
        "description": "Quick ticker lookup with price and recent alerts",
        "options": [
            {
                "name": "ticker",
                "description": "Stock ticker symbol (e.g., AAPL)",
                "type": 3,
                "required": True,
            }
        ],
    },
    {
        "name": "research",
        "description": "LLM-powered deep dive analysis of a ticker",
        "options": [
            {
                "name": "ticker",
                "description": "Stock ticker symbol",
                "type": 3,
                "required": True,
            },
            {
                "name": "question",
                "description": "Specific question to ask about this ticker",
                "type": 3,
                "required": False,
            },
        ],
    },
    {
        "name": "ask",
        "description": "Ask the bot a natural language question",
        "options": [
            {
                "name": "question",
                "description": "Your question",
                "type": 3,
                "required": True,
            }
        ],
    },
    {
        "name": "compare",
        "description": "Compare two tickers side-by-side",
        "options": [
            {
                "name": "ticker1",
                "description": "First ticker",
                "type": 3,
                "required": True,
            },
            {
                "name": "ticker2",
                "description": "Second ticker",
                "type": 3,
                "required": True,
            },
        ],
    },
]

# Discord API endpoint
url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"
headers = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json",
}

print("=" * 60)
print("Registering Discord Slash Commands")
print("=" * 60)

# Register each command
for cmd in COMMANDS:
    print(f"\nRegistering: /{cmd['name']}")
    response = requests.post(url, json=cmd, headers=headers)

    if response.status_code in (200, 201):
        print(f"✅ Success: /{cmd['name']} registered")
    else:
        print(f"❌ Failed: /{cmd['name']}")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")

print("\n" + "=" * 60)
print("Command Registration Complete!")
print("=" * 60)
print("\nCommands should now appear in Discord.")
print("It may take a few minutes for them to propagate.")
print("\nAvailable commands:")
print("  • /admin report [date]")
print("  • /admin set <parameter> <value>")
print("  • /admin rollback")
print("  • /admin stats")
print("  • /check <ticker>")
print("  • /research <ticker> [question]")
print("  • /ask <question>")
print("  • /compare <ticker1> <ticker2>")
