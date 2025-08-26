"""
Ticker Resolver v1

Goal
----
Best-effort ticker extraction with two stages:
1) Title pattern matching (no network).
2) Optional HTML page scrape (network, short timeout), gated by FEATURE_TICKER_RESOLVER_HTML.

Design
------
- No required changes to existing code. Provide `resolve_from_source(...)` that can be
  called as a fallback from feeds.extract_ticker(title) when it returns None.
- Reads env flags directly to avoid churn in settings.py today.

Env Flags
---------
FEATURE_TICKER_RESOLVER            (default: "true")
FEATURE_TICKER_RESOLVER_HTML       (default: "false")
TICKER_RESOLVER_HTML_TIMEOUT_SEC   (default: "3")
TICKER_RESOLVER_USER_AGENT         (default: custom UA)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

try:
    # If the project has a structured logger, prefer it.
    from catalyst_bot.logging_utils import get_logger  # type: ignore
except Exception:  # pragma: no cover - fallback logger
    import logging

    def get_logger(name: str):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        return logging.getLogger(name)


log = get_logger("ticker_resolver")

# Compile once; support common PR wire headline patterns.
# Examples:
#  - "Acme Corp (NASDAQ: ABC) announces..."
#  - "Something something — NYSE: XYZ"
#  - "Company Name (OTC: ABCD)"
#  - "Company (Nasdaq: ABC)"
#  - "Company [NYSE American: XYZ]"
_EXCH_LABEL = r"(NASDAQ|Nasdaq|NYSE|NYSE\s+American|OTC|OTCQB|OTCQX|CSE|TSX|AMEX)"
_TICKER_CORE = r"[A-Z]{1,5}(?:\.[A-Z])?"  # allow A, ABCD, BRK.B

# Case-insensitive patterns so "wIdg" matches and is normalized to "WIDG".
_FLAGS = re.IGNORECASE
TITLE_PATTERNS = [
    re.compile(rf"\(\s*{_EXCH_LABEL}\s*:\s*({_TICKER_CORE})\s*\)", _FLAGS),
    re.compile(rf"{_EXCH_LABEL}\s*:\s*({_TICKER_CORE})", _FLAGS),
    re.compile(rf"\[\s*{_EXCH_LABEL}\s*:\s*({_TICKER_CORE})\s*\]", _FLAGS),
]

# Very loose symbol guard for fallbacks.
_SYMBOL_RE = re.compile(rf"\b({_TICKER_CORE})\b", _FLAGS)

DEFAULT_UA = (
    "CatalystBot/1.0 (+https://github.com/Amenzel91/catalyst-bot) "
    "Python-requests/RESOLVER"
)


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ResolveResult:
    ticker: Optional[str]
    method: str  # "title", "html", or "none"


def _try_from_title(title: str) -> Optional[str]:
    if not title:
        return None
    for pat in TITLE_PATTERNS:
        m = pat.search(title)
        if m:
            sym = m.group(2 if m.lastindex and m.lastindex >= 2 else 1)
            return sym.upper()
    # Extremely conservative loose fallback: single-hit token that looks
    # like a symbol.
    # Avoid returning common words; require it to be in parentheses or
    # brackets context if ambiguous.
    paren_ctx = re.findall(r"\(([^)]{1,40})\)", title) + re.findall(
        r"\[([^\]]{1,40})\]", title
    )
    for ctx in paren_ctx:
        m = _SYMBOL_RE.search(ctx)
        if m:
            return m.group(1).upper()
    return None


def _try_from_html(url: str) -> Optional[str]:
    """Fetch page and attempt to find a labeled ticker. Short timeouts, safe failure."""
    try:
        import requests  # lazy import so tests without requests can still run
    except Exception:
        return None

    if not url or url.startswith("about:"):
        return None

    timeout = float(os.getenv("TICKER_RESOLVER_HTML_TIMEOUT_SEC", "3"))
    ua = os.getenv("TICKER_RESOLVER_USER_AGENT", DEFAULT_UA)
    headers = {"User-Agent": ua}

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200 or not resp.text:
            return None
        html = resp.text
    except Exception:
        return None

    # Look for explicit "NASDAQ: ABC" etc first
    for pat in TITLE_PATTERNS:
        m = pat.search(html)
        if m:
            sym = m.group(2 if m.lastindex and m.lastindex >= 2 else 1)
            return sym.upper()

    # Then look for likely symbol near exchange words
    exch_words = [
        "Nasdaq",
        "NASDAQ",
        "NYSE",
        "NYSE American",
        "OTC",
        "OTCQX",
        "OTCQB",
        "CSE",
        "TSX",
        "AMEX",
    ]
    for w in exch_words:
        idx = html.find(w)
        if idx != -1:
            window = html[max(0, idx - 50) : idx + 50]
            m = _SYMBOL_RE.search(window)
            if m:
                return m.group(1).upper()

    return None


def resolve_from_source(
    title: str,
    link: Optional[str],
    source_host: Optional[str],
) -> ResolveResult:
    """
    Public entrypoint used by feeds.py fallback.

    Returns:
        ResolveResult(ticker=<str|None>, method="title"|"html"|"none")
    """
    if not _env_flag("FEATURE_TICKER_RESOLVER", "true"):
        return ResolveResult(ticker=None, method="none")

    # Stage 1: title
    t = _try_from_title(title or "")
    if t:
        return ResolveResult(ticker=t, method="title")

    # Stage 2: optional HTML probe (opt-in)
    if _env_flag("FEATURE_TICKER_RESOLVER_HTML", "false") and link:
        h = _try_from_html(link)
        if h:
            return ResolveResult(ticker=h, method="html")

    return ResolveResult(ticker=None, method="none")
