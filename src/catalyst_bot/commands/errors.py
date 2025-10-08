"""
Discord Command Error Handlers
===============================

Standardized error responses for slash commands.
"""

from typing import Any, Dict

# Response types
RESPONSE_TYPE_CHANNEL_MESSAGE = 4


def ticker_not_found_error(ticker: str) -> Dict[str, Any]:
    """
    Return error for invalid ticker.

    Parameters
    ----------
    ticker : str
        The ticker that was not found

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"Ticker `{ticker}` not found. Please check the symbol and try again.",
            "flags": 64,  # EPHEMERAL
        },
    }


def rate_limit_error(seconds_remaining: int) -> Dict[str, Any]:
    """
    Return error for rate limit exceeded.

    Parameters
    ----------
    seconds_remaining : int
        Seconds until rate limit resets

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"Rate limit exceeded. Please try again in {seconds_remaining} seconds.",
            "flags": 64,  # EPHEMERAL
        },
    }


def no_data_error(ticker: str, data_type: str = "data") -> Dict[str, Any]:
    """
    Return error for no data available.

    Parameters
    ----------
    ticker : str
        The ticker symbol
    data_type : str
        Type of data that's missing (e.g., "price data", "news", "alerts")

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"No {data_type} available for `{ticker}`. The ticker may be too new or illiquid.",  # noqa: E501
            "flags": 64,  # EPHEMERAL
        },
    }


def permission_denied_error(reason: str = "") -> Dict[str, Any]:
    """
    Return error for permission denied.

    Parameters
    ----------
    reason : str
        Optional reason for denial

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    message = "You don't have permission to use this command."
    if reason:
        message += f" {reason}"

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": message,
            "flags": 64,  # EPHEMERAL
        },
    }


def generic_error(error_message: str = "An error occurred") -> Dict[str, Any]:
    """
    Return generic error response.

    Parameters
    ----------
    error_message : str
        Error message to display

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"Error: {error_message}",
            "flags": 64,  # EPHEMERAL
        },
    }


def missing_parameter_error(parameter: str) -> Dict[str, Any]:
    """
    Return error for missing required parameter.

    Parameters
    ----------
    parameter : str
        Name of the missing parameter

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"Missing required parameter: `{parameter}`",
            "flags": 64,  # EPHEMERAL
        },
    }


def invalid_parameter_error(parameter: str, reason: str) -> Dict[str, Any]:
    """
    Return error for invalid parameter value.

    Parameters
    ----------
    parameter : str
        Name of the parameter
    reason : str
        Reason the value is invalid

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"Invalid value for `{parameter}`: {reason}",
            "flags": 64,  # EPHEMERAL
        },
    }


def feature_disabled_error(feature: str) -> Dict[str, Any]:
    """
    Return error for disabled feature.

    Parameters
    ----------
    feature : str
        Name of the disabled feature

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"The {feature} feature is currently disabled.",
            "flags": 64,  # EPHEMERAL
        },
    }


def watchlist_full_error(max_size: int) -> Dict[str, Any]:
    """
    Return error for watchlist at capacity.

    Parameters
    ----------
    max_size : int
        Maximum watchlist size

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"Your watchlist is full (max {max_size} tickers). Remove some tickers first.",  # noqa: E501
            "flags": 64,  # EPHEMERAL
        },
    }


def watchlist_empty_error() -> Dict[str, Any]:
    """
    Return error for empty watchlist.

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": "Your watchlist is empty. Use `/watchlist add` to add tickers.",
            "flags": 64,  # EPHEMERAL
        },
    }


def ticker_not_in_watchlist_error(ticker: str) -> Dict[str, Any]:
    """
    Return error for ticker not in watchlist.

    Parameters
    ----------
    ticker : str
        The ticker symbol

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"`{ticker}` is not in your watchlist.",
            "flags": 64,  # EPHEMERAL
        },
    }


def ticker_already_in_watchlist_error(ticker: str) -> Dict[str, Any]:
    """
    Return error for ticker already in watchlist.

    Parameters
    ----------
    ticker : str
        The ticker symbol

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "content": f"`{ticker}` is already in your watchlist.",
            "flags": 64,  # EPHEMERAL
        },
    }
