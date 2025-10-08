"""QuickChart Chart.js v3 configuration generator for financial charts.

This module generates Chart.js v3 configurations for candlestick charts with
technical indicators (VWAP, RSI, MACD, Volume, Bollinger Bands) optimized for
QuickChart rendering. Supports URL-encoded GET requests and POST endpoints for
URL shortening when configs exceed threshold.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("charts_quickchart")


log = get_logger("charts_quickchart")


def generate_chart_config(
    ticker: str,
    timeframe: str,
    ohlcv_data: List[Dict[str, Any]],
    indicators: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate Chart.js v3 configuration JSON for QuickChart.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe label (e.g., "1D", "5D", "1M")
    ohlcv_data : List[Dict[str, Any]]
        List of OHLC data points with keys: x (timestamp), o, h, l, c
    indicators : Optional[Dict[str, Any]]
        Dictionary of indicator data (vwap, rsi, macd, volume, bollinger)

    Returns
    -------
    Dict[str, Any]
        Chart.js v3 configuration object ready for QuickChart
    """
    indicators = indicators or {}

    # WeBull color scheme (default)
    use_webull = os.getenv("CHART_THEME", "dark").lower() == "dark"
    candle_up = "#3dc985" if use_webull else "#26A69A"
    candle_down = "#ef4f60" if use_webull else "#EF5350"

    # Base candlestick dataset
    datasets = [
        {
            "label": ticker,
            "type": "candlestick",
            "data": ohlcv_data,
            "color": {
                "up": candle_up,
                "down": candle_down,
                "unchanged": "#999999",
            },
            "borderColor": {
                "up": candle_up,
                "down": candle_down,
                "unchanged": "#999999",
            },
        }
    ]

    # VWAP indicator (orange line)
    vwap_data = indicators.get("vwap")
    if vwap_data:
        datasets.append(
            {
                "label": "VWAP",
                "type": "line",
                "data": vwap_data,
                "borderColor": "#FF9800",
                "backgroundColor": "rgba(255, 152, 0, 0.1)",
                "borderWidth": 2,
                "pointRadius": 0,
                "fill": False,
            }
        )

    # Bollinger Bands (upper/lower/middle)
    bollinger = indicators.get("bollinger", {})
    if bollinger.get("upper") and bollinger.get("lower"):
        datasets.append(
            {
                "label": "BB Upper",
                "type": "line",
                "data": bollinger["upper"],
                "borderColor": "#9C27B0",
                "backgroundColor": "rgba(156, 39, 176, 0.05)",
                "borderWidth": 1,
                "pointRadius": 0,
                "borderDash": [5, 5],
                "fill": False,
            }
        )
        datasets.append(
            {
                "label": "BB Lower",
                "type": "line",
                "data": bollinger["lower"],
                "borderColor": "#9C27B0",
                "backgroundColor": "rgba(156, 39, 176, 0.05)",
                "borderWidth": 1,
                "pointRadius": 0,
                "borderDash": [5, 5],
                "fill": False,
            }
        )
        if bollinger.get("middle"):
            datasets.append(
                {
                    "label": "BB Middle",
                    "type": "line",
                    "data": bollinger["middle"],
                    "borderColor": "#9C27B0",
                    "backgroundColor": "rgba(156, 39, 176, 0.05)",
                    "borderWidth": 1,
                    "pointRadius": 0,
                    "fill": False,
                }
            )

    # Volume bars (on separate y-axis)
    volume_data = indicators.get("volume")
    if volume_data:
        datasets.append(
            {
                "label": "Volume",
                "type": "bar",
                "data": volume_data,
                "backgroundColor": "#546E7A",
                "borderColor": "#546E7A",
                "yAxisID": "volume",
                "barThickness": "flex",
                "maxBarThickness": 8,
            }
        )

    # Annotation lines for RSI and MACD (using plugins.annotation)
    annotations = []

    # RSI reference lines at 30 and 70
    rsi_data = indicators.get("rsi")
    if rsi_data:
        annotations.append(
            {
                "type": "line",
                "yMin": 30,
                "yMax": 30,
                "borderColor": "#00BCD4",
                "borderWidth": 1,
                "borderDash": [5, 5],
                "label": {
                    "display": True,
                    "content": "RSI 30",
                    "position": "end",
                },
            }
        )
        annotations.append(
            {
                "type": "line",
                "yMin": 70,
                "yMax": 70,
                "borderColor": "#00BCD4",
                "borderWidth": 1,
                "borderDash": [5, 5],
                "label": {
                    "display": True,
                    "content": "RSI 70",
                    "position": "end",
                },
            }
        )

    # MACD zero line
    macd_data = indicators.get("macd", {})
    if macd_data.get("line"):
        annotations.append(
            {
                "type": "line",
                "yMin": 0,
                "yMax": 0,
                "borderColor": "#888888",
                "borderWidth": 1,
                "label": {
                    "display": True,
                    "content": "MACD Zero",
                    "position": "start",
                },
            }
        )

    # WeBull dark theme colors
    bg_color = "#1b1f24" if use_webull else "#000000"
    grid_color = "#2c2e31" if use_webull else "#2A2A2A"
    text_color = "#cccccc"
    title_color = "#ffffff"

    # Chart.js v3 configuration with WeBull dark theme
    config = {
        "type": "candlestick",
        "data": {"datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "backgroundColor": bg_color,
            "scales": {
                "x": {
                    "type": "timeseries",
                    "time": {
                        "unit": "hour" if timeframe in ["1D", "5D"] else "day",
                        "displayFormats": {
                            "hour": "HH:mm",
                            "day": "MMM DD",
                        },
                    },
                    "grid": {
                        "display": True,
                        "color": grid_color,
                        "lineWidth": 0.5,
                    },
                    "ticks": {
                        "color": text_color,
                        "font": {
                            "size": int(os.getenv("CHART_AXIS_LABEL_SIZE", "12")),
                        },
                    },
                },
                "y": {
                    "type": "linear",
                    "position": "right",
                    "grid": {
                        "display": True,
                        "color": grid_color,
                        "lineWidth": 0.5,
                    },
                    "ticks": {
                        "color": text_color,
                        "font": {
                            "size": int(os.getenv("CHART_AXIS_LABEL_SIZE", "12")),
                        },
                    },
                },
            },
            "plugins": {
                "legend": {
                    "display": True,
                    "position": "top",
                    "labels": {
                        "color": text_color,
                        "filter": lambda item: item.text != ticker,  # Hide ticker label
                    },
                },
                "title": {
                    "display": True,
                    "text": f"{ticker} - {timeframe}",
                    "color": title_color,
                    "font": {
                        "size": int(os.getenv("CHART_TITLE_SIZE", "16")),
                        "weight": "bold",
                    },
                },
                "tooltip": {
                    "enabled": True,
                    "mode": "index",
                    "intersect": False,
                    "backgroundColor": bg_color,
                    "titleColor": title_color,
                    "bodyColor": text_color,
                    "borderColor": grid_color,
                    "borderWidth": 1,
                },
            },
            "layout": {
                "padding": {
                    "left": 10,
                    "right": 10,
                    "top": 10,
                    "bottom": 10,
                },
            },
        },
    }

    # Add volume y-axis if volume data present
    if volume_data:
        config["options"]["scales"]["volume"] = {
            "type": "linear",
            "position": "left",
            "grid": {
                "display": False,
            },
            "ticks": {
                "display": False,
            },
        }

    # Add annotation plugin config if annotations exist
    if annotations:
        config["options"]["plugins"]["annotation"] = {
            "annotations": annotations,
        }

    return config


def get_quickchart_url(
    ticker: str,
    timeframe: str,
    ohlcv_data: List[Dict[str, Any]],
    indicators: Optional[Dict[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    use_post: bool = True,
) -> Optional[str]:
    """Generate QuickChart URL for the given chart configuration.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe label (e.g., "1D", "5D", "1M")
    ohlcv_data : List[Dict[str, Any]]
        List of OHLC data points
    indicators : Optional[Dict[str, Any]]
        Dictionary of indicator data
    base_url : Optional[str]
        QuickChart base URL (defaults to QUICKCHART_URL env var or localhost:3400)
    use_post : bool
        Use POST /chart/create endpoint for URL shortening (default: True)

    Returns
    -------
    Optional[str]
        QuickChart image URL or None on failure
    """
    if not ohlcv_data:
        log.warning("quickchart_url_no_data ticker=%s", ticker)
        return None

    # Generate Chart.js config
    config = generate_chart_config(ticker, timeframe, ohlcv_data, indicators)

    # Resolve base URL
    base_url = (
        base_url
        or os.getenv("QUICKCHART_URL")
        or os.getenv("QUICKCHART_BASE_URL")
        or "http://localhost:3400"
    )
    base_url = base_url.rstrip("/")

    # Serialize config to JSON
    config_json = json.dumps(config, separators=(",", ":"))

    # URL-encode for GET request
    encoded_config = urllib.parse.quote(config_json, safe="")
    get_url = f"{base_url}/chart?c={encoded_config}"

    # Determine if we should use POST shortening
    shorten_threshold = int(os.getenv("QUICKCHART_SHORTEN_THRESHOLD", "3500"))

    if use_post and len(get_url) > shorten_threshold:
        # Use POST /chart/create endpoint for URL shortening
        try:
            short_url = _shorten_quickchart_url(
                config, base_url=base_url, ticker=ticker, timeframe=timeframe
            )
            if short_url:
                log.info(
                    "quickchart_url_shortened ticker=%s tf=%s url_len=%d",
                    ticker,
                    timeframe,
                    len(short_url),
                )
                return short_url
        except Exception as e:
            log.warning("quickchart_shorten_failed ticker=%s err=%s", ticker, str(e))

    # Return GET URL (either because use_post=False or POST failed)
    log.info(
        "quickchart_url_get ticker=%s tf=%s url_len=%d",
        ticker,
        timeframe,
        len(get_url),
    )
    return get_url


def _shorten_quickchart_url(
    config: Dict[str, Any],
    *,
    base_url: str,
    ticker: str,
    timeframe: str,
) -> Optional[str]:
    """Shorten QuickChart URL using POST /chart/create endpoint.

    Parameters
    ----------
    config : Dict[str, Any]
        Chart.js configuration object
    base_url : str
        QuickChart base URL
    ticker : str
        Stock ticker symbol (for logging)
    timeframe : str
        Timeframe label (for logging)

    Returns
    -------
    Optional[str]
        Shortened QuickChart URL or None on failure
    """
    # Try multiple create endpoints
    create_endpoints = [
        f"{base_url}/chart/create",
        f"{base_url}/create",
    ]

    # Build payload
    payload = {"chart": config}

    # Include API key if provided
    api_key = os.getenv("QUICKCHART_API_KEY")
    if api_key:
        payload["key"] = api_key

    # Try each endpoint
    for endpoint in create_endpoints:
        try:
            log.debug(
                "quickchart_create_request ticker=%s tf=%s endpoint=%s",
                ticker,
                timeframe,
                endpoint,
            )
            resp = requests.post(endpoint, json=payload, timeout=10)

            if resp.ok:
                try:
                    data = resp.json()
                except Exception:
                    data = {}

                # Extract URL from response
                url = data.get("url") or data.get("shortUrl") or None
                if isinstance(url, str) and url.startswith("http"):
                    log.info(
                        "quickchart_create_success ticker=%s tf=%s url=%s",
                        ticker,
                        timeframe,
                        url,
                    )
                    return url

        except Exception as e:
            log.debug(
                "quickchart_create_attempt_failed endpoint=%s err=%s",
                endpoint,
                str(e),
            )
            continue

    log.warning(
        "quickchart_create_all_failed ticker=%s tf=%s",
        ticker,
        timeframe,
    )
    return None
