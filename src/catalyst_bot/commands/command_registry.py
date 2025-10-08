"""
Discord Slash Command Registry
===============================

Defines all public-facing slash commands for the Catalyst Bot.
These commands are registered with Discord's API via register_commands.py.

Command Types:
- 1: SUB_COMMAND
- 2: SUB_COMMAND_GROUP
- 3: STRING
- 4: INTEGER
- 5: BOOLEAN
- 6: USER
- 7: CHANNEL
- 8: ROLE
- 9: MENTIONABLE
- 10: NUMBER
"""

from typing import Any, Dict, List

# All user-facing slash commands
COMMANDS: List[Dict[str, Any]] = [
    {
        "name": "chart",
        "description": "Generate a price chart for any ticker",
        "options": [
            {
                "name": "ticker",
                "type": 3,  # STRING
                "description": "Stock ticker symbol (e.g., AAPL, TSLA)",
                "required": True,
            },
            {
                "name": "timeframe",
                "type": 3,  # STRING
                "description": "Chart timeframe (default: 1D)",
                "required": False,
                "choices": [
                    {"name": "1 Day", "value": "1D"},
                    {"name": "5 Days", "value": "5D"},
                    {"name": "1 Month", "value": "1M"},
                    {"name": "3 Months", "value": "3M"},
                    {"name": "1 Year", "value": "1Y"},
                ],
            },
        ],
    },
    {
        "name": "watchlist",
        "description": "Manage your personal watchlist",
        "options": [
            {
                "name": "action",
                "type": 3,  # STRING
                "description": "Action to perform",
                "required": True,
                "choices": [
                    {"name": "Add ticker", "value": "add"},
                    {"name": "Remove ticker", "value": "remove"},
                    {"name": "List all", "value": "list"},
                    {"name": "Clear all", "value": "clear"},
                ],
            },
            {
                "name": "ticker",
                "type": 3,  # STRING
                "description": "Ticker symbol (required for add/remove)",
                "required": False,
            },
        ],
    },
    {
        "name": "stats",
        "description": "Show bot performance statistics",
        "options": [
            {
                "name": "period",
                "type": 3,  # STRING
                "description": "Time period (default: This Week)",
                "required": False,
                "choices": [
                    {"name": "Today", "value": "1d"},
                    {"name": "This Week", "value": "7d"},
                    {"name": "This Month", "value": "30d"},
                    {"name": "All Time", "value": "all"},
                ],
            }
        ],
    },
    {
        "name": "backtest",
        "description": "Run a quick backtest on historical alerts",
        "options": [
            {
                "name": "ticker",
                "type": 3,  # STRING
                "description": "Stock ticker symbol",
                "required": True,
            },
            {
                "name": "days",
                "type": 4,  # INTEGER
                "description": "Number of days to backtest (default: 30)",
                "required": False,
            },
        ],
    },
    {
        "name": "sentiment",
        "description": "Get current sentiment score for a ticker",
        "options": [
            {
                "name": "ticker",
                "type": 3,  # STRING
                "description": "Stock ticker symbol",
                "required": True,
            }
        ],
    },
    {
        "name": "help",
        "description": "Show all available commands and usage examples",
    },
    {
        "name": "admin",
        "description": "[Admin Only] Admin control commands",
        "options": [
            {
                "name": "report",
                "type": 1,  # SUB_COMMAND
                "description": "Generate admin report on demand",
            },
            {
                "name": "set",
                "type": 1,  # SUB_COMMAND
                "description": "Manually set a parameter",
                "options": [
                    {
                        "name": "param",
                        "type": 3,  # STRING
                        "description": "Parameter name (e.g., MIN_SCORE)",
                        "required": True,
                    },
                    {
                        "name": "value",
                        "type": 3,  # STRING
                        "description": "New value",
                        "required": True,
                    },
                ],
            },
            {
                "name": "history",
                "type": 1,  # SUB_COMMAND
                "description": "Show recent parameter changes and their impact",
            },
            {
                "name": "rollback",
                "type": 1,  # SUB_COMMAND
                "description": "Rollback a parameter change",
                "options": [
                    {
                        "name": "change_id",
                        "type": 3,  # STRING
                        "description": "Change ID to rollback",
                        "required": True,
                    },
                ],
            },
        ],
    },
]


def get_command_names() -> List[str]:
    """
    Get list of all registered command names.

    Returns
    -------
    List[str]
        List of command names
    """
    return [cmd["name"] for cmd in COMMANDS]


def get_command_by_name(name: str) -> Dict[str, Any]:
    """
    Get command definition by name.

    Parameters
    ----------
    name : str
        Command name

    Returns
    -------
    Dict[str, Any]
        Command definition, or empty dict if not found
    """
    for cmd in COMMANDS:
        if cmd["name"] == name:
            return cmd
    return {}


def format_command_help() -> str:
    """
    Format all commands as a help string.

    Returns
    -------
    str
        Formatted help text
    """
    lines = ["**Available Commands:**\n"]

    for cmd in COMMANDS:
        name = cmd["name"]
        desc = cmd["description"]
        lines.append(f"**/{name}** - {desc}")

        # Add option details
        options = cmd.get("options", [])
        if options:
            for opt in options:
                opt_name = opt["name"]
                opt_desc = opt["description"]
                required = opt.get("required", False)
                req_str = "(required)" if required else "(optional)"
                lines.append(f"  - `{opt_name}` {req_str}: {opt_desc}")

        lines.append("")  # Empty line between commands

    return "\n".join(lines)
