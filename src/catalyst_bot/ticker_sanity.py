"""
Ticker Sanity Rules

Purpose
-------
Downstream classifier noise in logs was caused by junk tickers like "FILER" or
country codes (e.g., "AT", "AU") bubbling up from certain sources.
This module applies lightweight, US-listed oriented validation.

Behavior
--------
- Uppercases and strips surrounding whitespace.
- Rejects strings that aren't 1-5 alphas (allow a single '.' for classes like BRK.B).
- Rejects known junk tokens: "FILER".
- Rejects a small set of problematic 2-letter country codes seen in feeds: {"AT", "AU"}.
- Returns `None` on rejection; otherwise returns cleaned ticker.

Flags
-----
The site hook controls whether sanitation is applied (HOOK_TICKER_SANITY=true).
"""

from __future__ import annotations

import re
from typing import Optional

# allow A, AA, AAPL, BRK.B (one optional class dot)
_VALID_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

# minimal stoplist based on observed logs (keep conservative)
_STOP = {"FILER"}

# small set of mis-extracted country codes we saw
_BAD_2LETTER = {"AT", "AU"}


def sanitize_ticker(value: object) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None

    if s in _STOP:
        return None

    if len(s) == 2 and s in _BAD_2LETTER:
        return None

    if not _VALID_RE.match(s):
        return None

    return s
