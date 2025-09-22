"""
Options scanner module for Catalyst Bot
-------------------------------------

This module provides a stub implementation for scanning options data for a
given ticker.  The intent of the options scanner is to compute a simple
sentiment score based on unusual options activity.  When enabled via the
``FEATURE_OPTIONS_SCANNER`` feature flag in the bot's configuration, the
``scan_options`` function will be invoked for each ticker and its result
included in the bullishness calculation.  Until a real provider is wired
up, this function returns ``None`` to indicate that no data could be
retrieved.

The return value of ``scan_options`` should be a dictionary with the
following keys:

``score`` (float)
    A numeric sentiment score between -1 and +1.  Positive values
    indicate bullish positioning in the options market while negative
    values indicate bearish positioning.  A score of zero or ``None``
    indicates neutral or unavailable sentiment.

``label`` (str)
    A human‐readable label summarising the sentiment such as
    ``"Bullish"``, ``"Bearish"`` or ``"Neutral"``.

``details`` (dict)
    A freeform dictionary containing additional information about the
    options scan.  This may include metrics like put/call ratios,
    volume thresholds, or any provider specific fields.  The test suite
    does not inspect this field, so implementations are free to
    populate it as needed.

If the scanner cannot obtain any data for a ticker, the function should
return ``None`` to signal the absence of a signal.  Downstream callers
should handle ``None`` gracefully by omitting the options contribution
from the overall sentiment calculation.

You can implement a real scanner by replacing the stubbed implementation
with calls into your data provider.  Make sure that any network
operations are appropriately guarded in tests (e.g. via monkeypatching)
to avoid network calls during CI runs.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def scan_options(ticker: str) -> Optional[Dict[str, Any]]:
    """Return options sentiment for a given ticker.

    The default implementation is a stub that returns ``None``.  A
    production implementation should inspect unusual options activity and
    compute a sentiment score on the range [-1.0, 1.0].

    Parameters
    ----------
    ticker: str
        The stock symbol to analyse.  Must be a non‑empty string.

    Returns
    -------
    Optional[Dict[str, Any]]
        A dictionary with keys ``score``, ``label`` and ``details`` if
        sentiment could be computed, otherwise ``None``.
    """

    if not ticker or not isinstance(ticker, str):
        raise ValueError("ticker must be a non-empty string")

    # Placeholder implementation: return None to indicate no signal
    return None
