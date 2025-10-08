"""
Catalyst Bot Discord Commands
==============================

User-facing slash commands and interactions.
"""

from .command_registry import COMMANDS, get_command_names
from .embeds import (
    create_backtest_embed,
    create_chart_embed,
    create_help_embed,
    create_sentiment_embed,
    create_stats_embed,
    create_watchlist_embed,
)
from .errors import (
    feature_disabled_error,
    generic_error,
    no_data_error,
    rate_limit_error,
    ticker_not_found_error,
)
from .handlers import (
    handle_backtest_command,
    handle_chart_command,
    handle_help_command,
    handle_sentiment_command,
    handle_stats_command,
    handle_watchlist_command,
)

__all__ = [
    "COMMANDS",
    "get_command_names",
    "create_backtest_embed",
    "create_chart_embed",
    "create_help_embed",
    "create_sentiment_embed",
    "create_stats_embed",
    "create_watchlist_embed",
    "feature_disabled_error",
    "generic_error",
    "no_data_error",
    "rate_limit_error",
    "ticker_not_found_error",
    "handle_backtest_command",
    "handle_chart_command",
    "handle_help_command",
    "handle_sentiment_command",
    "handle_stats_command",
    "handle_watchlist_command",
]
