"""Analyst signals and price target helper for Catalyst‑Bot.

This module provides functions to fetch consensus analyst price targets and
derive an implied return versus the current price.  The results are used to
augment news events with an analyst‐based sentiment label (Bullish, Neutral,
Bearish) based on a configurable return threshold.  The primary consumer is
``feeds.py``, which attaches the computed metrics to each event when
``FEATURE_ANALYST_SIGNALS`` is enabled.

The design aims for resilience: API errors are swallowed and return values
default to ``None``.  Providers are pluggable via the ``ANALYST_PROVIDER``
environment variable.  Currently supported providers include:

    * **fmp** – Uses Financial Modeling Prep’s Price Target API.  Requires
      either ``ANALYST_API_KEY`` or ``FMP_API_KEY`` in the environment.
    * **yahoo** – Uses yfinance to pull consensus targets from Yahoo Finance.

Functions exported by this module do not raise exceptions; they log
failures internally and return ``None`` when data cannot be fetched.

Example usage::

    from catalyst_bot.analyst_signals import get_analyst_signal
    res = get_analyst_signal("AAPL")
    if res:
        print(res["target_mean"], res["implied_return"], res["analyst_label"])

"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import requests

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

# Optional import: only loaded when computing implied returns
try:
    from .market import get_last_price_snapshot  # type: ignore
except Exception:
    get_last_price_snapshot = None  # type: ignore

from .config import get_settings
from .logging_utils import get_logger

log = get_logger("analyst_signals")


def _safe_float(val: Any) -> Optional[float]:
    """Return ``float(val)`` when possible, else ``None``."""
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except Exception:
        return None


def _fetch_fmp_target(
    ticker: str, api_key: str, *, timeout: int = 8
) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
    """Return (mean, high, low, n_analysts) from FMP price target API.

    The Financial Modeling Prep API returns a list of objects with keys such as
    ``targetMean``, ``targetHigh``, ``targetLow`` and ``numberAnalysts``.  On
    any error, (None, None, None, 0) is returned.  The function does not
    raise.
    """
    try:
        sym = ticker.strip().upper()
        if not sym:
            return (None, None, None, 0)
        # Use the v3 endpoint; FMP also has /stable/price-target-consensus.  Both
        # return similar keys.  Choosing v3 avoids 301s on some proxies.
        base = os.getenv("FMP_BASE_URL", "https://financialmodelingprep.com/api")
        url = f"{base}/v3/price-target/{sym}"
        params = {"apikey": api_key} if api_key else {}
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return (None, None, None, 0)
        data = resp.json() or []
        # FMP returns a list with a single dict for the symbol
        rec = None
        if isinstance(data, list) and data:
            rec = data[0]
        elif isinstance(data, dict):
            rec = data
        if not isinstance(rec, dict):
            return (None, None, None, 0)
        mean = _safe_float(rec.get("targetMean") or rec.get("targetPrice"))
        high = _safe_float(rec.get("targetHigh"))
        low = _safe_float(rec.get("targetLow"))
        try:
            n = int(rec.get("numberAnalysts") or rec.get("analystRatings") or 0)
        except Exception:
            n = 0
        return (mean, high, low, n)
    except Exception as e:  # pragma: no cover - non-fatal
        log.warning("fmp_target_failed", extra={"error": str(e)})
        return (None, None, None, 0)


def _fetch_yahoo_target(
    ticker: str, *, timeout: int = 8
) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
    """Return (mean, high, low, n_analysts) using yfinance.

    Uses the yfinance ``Ticker.info`` dict to extract ``targetMeanPrice``,
    ``targetHighPrice``, ``targetLowPrice`` and ``numberOfAnalystOpinions``.
    When yfinance is unavailable or any key is missing, returns (None, None,
    None, 0).
    """
    if yf is None:  # pragma: no cover
        return (None, None, None, 0)
    try:
        sym = ticker.strip().upper()
        if not sym:
            return (None, None, None, 0)
        t = yf.Ticker(sym)
        info = {}
        try:
            info = t.info  # note: info may internally fetch network data
        except Exception:
            info = {}
        mean = _safe_float(info.get("targetMeanPrice"))
        high = _safe_float(info.get("targetHighPrice"))
        low = _safe_float(info.get("targetLowPrice"))
        try:
            n = int(info.get("numberOfAnalystOpinions") or 0)
        except Exception:
            n = 0
        return (mean, high, low, n)
    except Exception as e:  # pragma: no cover - non-fatal
        log.warning("yahoo_target_failed", extra={"error": str(e)})
        return (None, None, None, 0)


def get_analyst_signal(ticker: str) -> Optional[Dict[str, Any]]:
    """Return analyst signal details for ``ticker``.

    The returned dict includes the consensus target price, implied return
    percentage relative to the latest market price, the number of analysts,
    and a discrete label in ``{"Bullish", "Neutral", "Bearish"}`` based on
    ``ANALYST_RETURN_THRESHOLD``.  When data cannot be fetched (no price
    or no target), ``None`` is returned.  This function reads the current
    settings via :func:`catalyst_bot.config.get_settings`.

    Returns
    -------
    Optional[Dict[str, Any]]
        Dict with keys ``target_mean``, ``target_high``, ``target_low``,
        ``n_analysts``, ``implied_return``, ``analyst_label`` and
        ``provider`` when available; otherwise None.
    """
    # Check feature flag
    try:
        settings = get_settings()
        if not getattr(settings, "feature_analyst_signals", False):
            return None
    except Exception:
        # If settings cannot be loaded, fall back to env check
        if os.getenv("FEATURE_ANALYST_SIGNALS", "0").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return None

        # Construct a minimal settings object stub
        class S:
            pass

        settings = S()
        settings.analyst_return_threshold = float(
            os.getenv("ANALYST_RETURN_THRESHOLD", "10.0").strip() or "10.0"
        )
        settings.analyst_provider = (
            os.getenv("ANALYST_PROVIDER", "fmp").strip() or "fmp"
        )
        settings.analyst_api_key = os.getenv("ANALYST_API_KEY", "").strip()
        # FMP key fallback
        settings.fmp_api_key = os.getenv("FMP_API_KEY", "").strip()

    sym = ticker.strip().upper() if ticker else ""
    if not sym:
        return None
    provider = getattr(settings, "analyst_provider", "fmp") or "fmp"
    api_key = getattr(settings, "analyst_api_key", "") or getattr(
        settings, "fmp_api_key", ""
    )

    # Fetch target depending on provider
    if provider.lower() == "fmp":
        mean, high, low, n = _fetch_fmp_target(sym, api_key)
    elif provider.lower() in {"yahoo", "yf", "yfinance"}:
        mean, high, low, n = _fetch_yahoo_target(sym)
    else:
        # Unknown provider: no data
        log.warning("unknown_analyst_provider", extra={"provider": provider})
        return None
    if mean is None or mean <= 0:
        # No valid target
        return None
    # Obtain last price to compute return
    last_price = None
    try:
        if get_last_price_snapshot is not None:
            lp, _ = get_last_price_snapshot(sym)
            if isinstance(lp, (int, float)):
                last_price = float(lp)
    except Exception:
        last_price = None
    if not last_price or last_price <= 0:
        return None
    # Compute implied return percentage
    implied_return = ((mean - last_price) / last_price) * 100.0
    thresh = float(getattr(settings, "analyst_return_threshold", 10.0))
    label: str = "Neutral"
    try:
        if implied_return >= thresh:
            label = "Bullish"
        elif implied_return <= -thresh:
            label = "Bearish"
        else:
            label = "Neutral"
    except Exception:
        label = "Neutral"
    return {
        "target_mean": mean,
        "target_high": high,
        "target_low": low,
        "n_analysts": n,
        "implied_return": implied_return,
        "analyst_label": label,
        "provider": provider,
    }
