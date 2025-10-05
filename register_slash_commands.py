"""
Register Discord Slash Commands
=================================

This script registers slash commands with Discord's API.
Run this once to set up the commands, then they'll be available in your Discord server.

Usage:
    python register_slash_commands.py

Requirements:
    - DISCORD_BOT_TOKEN in .env
    - DISCORD_APPLICATION_ID in .env (or auto-detect from token)
    - Optional: DISCORD_GUILD_ID for guild-specific commands (faster update)
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Get credentials
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")  # Optional - for faster guild-specific commands

if not BOT_TOKEN:
    print("[ERROR] DISCORD_BOT_TOKEN not found in .env")
    sys.exit(1)

# Auto-detect application ID from token if not provided
if not APPLICATION_ID:
    import base64
    try:
        # Discord bot tokens are in format: base64(app_id).random.random
        APPLICATION_ID = BOT_TOKEN.split('.')[0]
        # Decode base64
        APPLICATION_ID = base64.b64decode(APPLICATION_ID + '==').decode('utf-8')
        print(f"[INFO] Auto-detected APPLICATION_ID: {APPLICATION_ID}")
    except Exception as e:
        print(f"[ERROR] Could not auto-detect APPLICATION_ID: {e}")
        print("[INFO] Please set DISCORD_APPLICATION_ID in .env")
        sys.exit(1)


# Define slash commands
COMMANDS = [
    {
        "name": "admin",
        "description": "Admin control commands for bot configuration",
        "options": [
            {
                "name": "report",
                "description": "Generate and post admin performance report",
                "type": 1,  # SUB_COMMAND
                "options": [
                    {
                        "name": "date",
                        "description": "Report date (YYYY-MM-DD, default: yesterday)",
                        "type": 3,  # STRING
                        "required": False,
                    }
                ],
            },
            {
                "name": "set",
                "description": "Update a bot parameter",
                "type": 1,  # SUB_COMMAND
                "options": [
                    {
                        "name": "parameter",
                        "description": "Parameter name (e.g., MIN_SCORE, PRICE_CEILING)",
                        "type": 3,  # STRING
                        "required": True,
                    },
                    {
                        "name": "value",
                        "description": "New parameter value",
                        "type": 3,  # STRING
                        "required": True,
                    },
                ],
            },
            {
                "name": "rollback",
                "description": "Rollback to previous configuration",
                "type": 1,  # SUB_COMMAND
            },
            {
                "name": "stats",
                "description": "Show current parameter values",
                "type": 1,  # SUB_COMMAND
            },
        ],
    }
]


def register_global_commands():
    """Register commands globally (takes ~1 hour to propagate)."""
    url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/commands"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    print("\n" + "="*60)
    print("Registering GLOBAL commands (takes ~1 hour to propagate)")
    print("="*60)

    for command in COMMANDS:
        print(f"\nRegistering: /{command['name']}")
        response = requests.post(url, json=command, headers=headers, timeout=10)

        if response.status_code in (200, 201):
            print(f"  [OK] Successfully registered /{command['name']}")
            print(f"  [INFO] Command ID: {response.json().get('id')}")
        else:
            print(f"  [FAIL] Failed to register /{command['name']}")
            print(f"  [ERROR] Status: {response.status_code}")
            print(f"  [ERROR] Response: {response.text[:200]}")


def register_guild_commands():
    """Register commands for specific guild (instant update)."""
    if not GUILD_ID:
        print("\n[WARN] DISCORD_GUILD_ID not set, skipping guild-specific registration")
        print("[INFO] Set DISCORD_GUILD_ID in .env for instant command updates")
        return

    url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/guilds/{GUILD_ID}/commands"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    print("\n" + "="*60)
    print(f"Registering GUILD commands for guild {GUILD_ID} (instant)")
    print("="*60)

    for command in COMMANDS:
        print(f"\nRegistering: /{command['name']}")
        response = requests.post(url, json=command, headers=headers, timeout=10)

        if response.status_code in (200, 201):
            print(f"  [OK] Successfully registered /{command['name']}")
            print(f"  [INFO] Command ID: {response.json().get('id')}")
        else:
            print(f"  [FAIL] Failed to register /{command['name']}")
            print(f"  [ERROR] Status: {response.status_code}")
            print(f"  [ERROR] Response: {response.text[:200]}")


def list_registered_commands():
    """List all currently registered commands."""
    print("\n" + "="*60)
    print("Currently Registered Commands")
    print("="*60)

    # Global commands
    url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/commands"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    response = requests.get(url, headers=headers, timeout=10)
    if response.ok:
        commands = response.json()
        print(f"\nGlobal commands ({len(commands)}):")
        for cmd in commands:
            print(f"  - /{cmd['name']} (ID: {cmd['id']})")
    else:
        print(f"\n[WARN] Could not fetch global commands: {response.status_code}")

    # Guild commands (if configured)
    if GUILD_ID:
        url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/guilds/{GUILD_ID}/commands"
        response = requests.get(url, headers=headers, timeout=10)
        if response.ok:
            commands = response.json()
            print(f"\nGuild commands ({len(commands)}):")
            for cmd in commands:
                print(f"  - /{cmd['name']} (ID: {cmd['id']})")
        else:
            print(f"\n[WARN] Could not fetch guild commands: {response.status_code}")


def main():
    """Main registration flow."""
    print("Discord Slash Command Registration")
    print("="*60)
    print(f"Application ID: {APPLICATION_ID}")
    print(f"Guild ID: {GUILD_ID or 'Not set (will register globally only)'}")
    print("="*60)

    # Show menu
    print("\nOptions:")
    print("  1. Register guild-specific commands (instant, recommended for testing)")
    print("  2. Register global commands (takes ~1 hour)")
    print("  3. Register both")
    print("  4. List registered commands")
    print("  5. Exit")

    try:
        choice = input("\nEnter choice (1-5): ").strip()

        if choice == "1":
            if GUILD_ID:
                register_guild_commands()
            else:
                print("\n[ERROR] DISCORD_GUILD_ID not set in .env")
                print("[INFO] Get your guild ID by enabling Developer Mode in Discord,")
                print("[INFO] right-clicking your server, and selecting 'Copy ID'")
        elif choice == "2":
            register_global_commands()
        elif choice == "3":
            if GUILD_ID:
                register_guild_commands()
            register_global_commands()
        elif choice == "4":
            list_registered_commands()
        elif choice == "5":
            print("\nExiting...")
            sys.exit(0)
        else:
            print("\n[ERROR] Invalid choice")
            sys.exit(1)

        # Show registered commands
        print("\n")
        list_registered_commands()

        print("\n" + "="*60)
        print("Registration Complete!")
        print("="*60)
        print("\nNext steps:")
        print("  1. If you registered guild commands, they're available now")
        print("  2. If you registered global commands, wait ~1 hour")
        print("  3. Make sure interaction server is running: python interaction_server.py")
        print("  4. Test commands in Discord: /admin stats")

    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
