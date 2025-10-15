"""
Discord Command Registration Script
====================================

Registers slash commands with Discord's API.

This script should be run manually or as part of deployment to register
all user-facing commands with Discord.

Usage:
    python register_commands.py

Environment Variables Required:
    DISCORD_BOT_TOKEN - Your Discord bot token
    DISCORD_APPLICATION_ID - Your Discord application ID
    DISCORD_GUILD_ID - (Optional) Guild ID for guild-specific commands

Commands can be registered globally or for a specific guild:
- Global commands: Available in all servers, take up to 1 hour to propagate
- Guild commands: Available instantly in one server, useful for testing
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv  # noqa: E402

# Load environment variables
load_dotenv()

import requests  # noqa: E402

from catalyst_bot.commands.command_registry import COMMANDS  # noqa: E402

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")  # Optional for guild commands


def register_global_commands() -> None:
    """
    Register commands globally (available in all servers).

    Global commands take up to 1 hour to propagate across Discord.
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_APPLICATION_ID:
        print("ERROR: Missing DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID in .env")
        sys.exit(1)

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/commands"

    print("=" * 60)
    print("Registering Global Commands")
    print("=" * 60)
    print(f"Application ID: {DISCORD_APPLICATION_ID}")
    print(f"Commands to register: {len(COMMANDS)}")
    print()

    for command in COMMANDS:
        command_name = command["name"]
        print(f"Registering /{command_name}...", end=" ")

        try:
            response = requests.post(url, headers=headers, json=command, timeout=10)

            if response.status_code in (200, 201):
                print("OK")
            else:
                print(f"FAILED ({response.status_code})")
                print(f"  Response: {response.text}")

        except Exception as e:
            print(f"ERROR: {e}")

    print()
    print("Global command registration complete!")
    print("Note: Global commands may take up to 1 hour to appear in all servers.")
    print()


def register_guild_commands(guild_id: str) -> None:
    """
    Register commands for a specific guild (instant propagation).

    Parameters
    ----------
    guild_id : str
        Discord guild (server) ID
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_APPLICATION_ID:
        print("ERROR: Missing DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID in .env")
        sys.exit(1)

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/guilds/{guild_id}/commands"  # noqa: E501

    print("=" * 60)
    print("Registering Guild Commands")
    print("=" * 60)
    print(f"Application ID: {DISCORD_APPLICATION_ID}")
    print(f"Guild ID: {guild_id}")
    print(f"Commands to register: {len(COMMANDS)}")
    print()

    for command in COMMANDS:
        command_name = command["name"]
        print(f"Registering /{command_name}...", end=" ")

        try:
            response = requests.post(url, headers=headers, json=command, timeout=10)

            if response.status_code in (200, 201):
                print("OK")
            else:
                print(f"FAILED ({response.status_code})")
                print(f"  Response: {response.text}")

        except Exception as e:
            print(f"ERROR: {e}")

    print()
    print("Guild command registration complete!")
    print("Commands should be available immediately in your server.")
    print()


def delete_all_commands(guild_id: Optional[str] = None) -> None:
    """
    Delete all registered commands (useful for cleanup).

    Parameters
    ----------
    guild_id : Optional[str]
        Guild ID for guild-specific deletion, None for global
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_APPLICATION_ID:
        print("ERROR: Missing DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID in .env")
        sys.exit(1)

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    if guild_id:
        url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/guilds/{guild_id}/commands"  # noqa: E501
        scope = f"guild {guild_id}"
    else:
        url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/commands"
        scope = "global"

    print(f"Fetching {scope} commands...")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch commands: {response.status_code}")
            return

        commands = response.json()
        print(f"Found {len(commands)} command(s) to delete")

        for cmd in commands:
            cmd_id = cmd["id"]
            cmd_name = cmd["name"]
            print(f"Deleting /{cmd_name}...", end=" ")

            delete_url = f"{url}/{cmd_id}"
            delete_response = requests.delete(delete_url, headers=headers, timeout=10)

            if delete_response.status_code == 204:
                print("OK")
            else:
                print(f"FAILED ({delete_response.status_code})")

        print("Deletion complete!")

    except Exception as e:
        print(f"ERROR: {e}")


def list_commands(guild_id: Optional[str] = None) -> None:
    """
    List all registered commands.

    Parameters
    ----------
    guild_id : Optional[str]
        Guild ID for guild-specific listing, None for global
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_APPLICATION_ID:
        print("ERROR: Missing DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID in .env")
        sys.exit(1)

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    if guild_id:
        url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/guilds/{guild_id}/commands"  # noqa: E501
        scope = f"guild {guild_id}"
    else:
        url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/commands"
        scope = "global"

    print(f"Fetching {scope} commands...")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch commands: {response.status_code}")
            return

        commands = response.json()
        print(f"Found {len(commands)} command(s):\n")

        for cmd in commands:
            print(f"  /{cmd['name']} - {cmd.get('description', 'No description')}")

        print()

    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Register Discord slash commands")
    parser.add_argument(
        "--global",
        dest="use_global",
        action="store_true",
        help="Register commands globally (takes up to 1 hour)",
    )
    parser.add_argument(
        "--guild",
        type=str,
        help="Register commands for a specific guild ID (instant)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete all commands instead of registering",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all registered commands",
    )

    args = parser.parse_args()

    # Default to guild commands if DISCORD_GUILD_ID is set
    if not args.use_global and not args.guild and DISCORD_GUILD_ID:
        args.guild = DISCORD_GUILD_ID

    if args.list:
        list_commands(args.guild)
    elif args.delete:
        if args.guild:
            delete_all_commands(args.guild)
        else:
            delete_all_commands()
    elif args.use_global:
        register_global_commands()
    elif args.guild:
        register_guild_commands(args.guild)
    else:
        print("ERROR: Please specify --global or --guild <guild_id>")
        print("Example: python register_commands.py --guild 1234567890")
        print("Or set DISCORD_GUILD_ID in .env and run: python register_commands.py")
        sys.exit(1)
