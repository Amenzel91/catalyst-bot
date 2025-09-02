# -*- coding: utf-8 -*-
"""Lightweight ticker extraction from PR/news titles.

Default scope: US-listed symbols you can trade on Webull/Robinhood
(Nasdaq, NYSE, NYSE American, AMEX, NYSE Arca, Cboe) + $TICKER.

Env/args toggles:
- ALLOW_OTC_TICKERS=1           -> include OTC/OTCMKTS/OTCQX/OTCQB exchange prefixes
- DOLLAR_TICKERS_REQUIRE_EXCHANGE=1 -> disable loose $TICKER matches (exchange-qualified only)
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Pattern, Tuple

# -----------------------
# Base exchange patterns
# -----------------------

# Keep this list tight for the core platforms.
_EXCH_PREFIX_CORE = r"(?:NASDAQ|Nasdaq|NYSE(?:\s+American)?|AMEX|NYSE\s*Arca|CBOE|Cboe)"

# Optional OTC family (opt-in).
_OTC_PREFIX = r"(?:OTC(?:MKTS)?|OTCQX|OTCQB|OTC\s*Markets?)"

# Core ticker shape:
#  - starts with a letter
#  - letters/digits/.- up to 5 more (total 1-6) => covers BRK.A, BF.B, GOOG, GOOGL
_TICKER_CORE = r"([A-Z][A-Z0-9.\-]{0,5})"

# Dollar-prefixed pattern: "... $ABCD ..."
_DOLLAR_PATTERN = rf"(?:(?<!\w)\${_TICKER_CORE}\b)"


def _build_regex(allow_otc: bool, require_exch_for_dollar: bool) -> Pattern[str]:
    exch_prefix = rf"(?:{_EXCH_PREFIX_CORE}{'|' + _OTC_PREFIX if allow_otc else ''})"
    exch_pattern = rf"\b{exch_prefix}\s*[:\-]\s*\$?{_TICKER_CORE}\b"
    combined = (
        exch_pattern
        if require_exch_for_dollar
        else rf"{exch_pattern}|{_DOLLAR_PATTERN}"
    )
    return re.compile(combined, re.IGNORECASE)


# Small cache so we don't recompile every call
_RE_CACHE: Dict[Tuple[bool, bool], Pattern[str]] = {}


def _get_regex(
    allow_otc: Optional[bool],
    require_exch_for_dollar: Optional[bool],
) -> Pattern[str]:
    # Resolve flags from env if not provided as args
    if allow_otc is None:
        allow_otc = str(os.getenv("ALLOW_OTC_TICKERS", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if require_exch_for_dollar is None:
        require_exch_for_dollar = str(
            os.getenv("DOLLAR_TICKERS_REQUIRE_EXCHANGE", "0")
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    key = (bool(allow_otc), bool(require_exch_for_dollar))
    re_pat = _RE_CACHE.get(key)
    if re_pat is None:
        re_pat = _build_regex(allow_otc, require_exch_for_dollar)
        _RE_CACHE[key] = re_pat
    return re_pat


def _norm(t: str) -> str:
    return (t or "").strip().upper()


def ticker_from_title(
    title: Optional[str],
    *,
    allow_otc: Optional[bool] = None,
    require_exch_for_dollar: Optional[bool] = None,
) -> Optional[str]:
    """Return the first matched ticker from a title, or None.

    Args override env toggles when provided.
    """
    if not title:
        return None
    pat = _get_regex(allow_otc, require_exch_for_dollar)
    m = pat.search(title)
    if not m:
        return None
    # Take first non-empty group so this works for both shapes (with/without $-branch)
    raw = next((g for g in m.groups() if g), None)
    return _norm(raw) if raw else None


def extract_tickers_from_title(
    title: Optional[str],
    *,
    allow_otc: Optional[bool] = None,
    require_exch_for_dollar: Optional[bool] = None,
) -> List[str]:
    """Return all unique tickers in reading order from a title.

    Args override env toggles when provided.
    """
    if not title:
        return []
    pat = _get_regex(allow_otc, require_exch_for_dollar)
    seen = set()
    out: List[str] = []
    for m in pat.finditer(title):
        raw = next((g for g in m.groups() if g), None)
        if not raw:
            continue
        t = _norm(raw)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


if __name__ == "__main__":
    # quick self-checks
    tests = [
        ("Alpha (Nasdaq: ABCD) + $EFGH; OTCMKTS: XYZ should be ignored", {}),
        ("Up-listing news OTCMKTS: XYZ, plus (Nasdaq: ABCD)", {"allow_otc": True}),
        (
            "Just $ABCD with no exchange should be dropped; but (NYSE: XYZ) should pass",
            {"require_exch_for_dollar": True},
        ),
    ]
    for s, opts in tests:
        print(s, "->", extract_tickers_from_title(s, **opts))
