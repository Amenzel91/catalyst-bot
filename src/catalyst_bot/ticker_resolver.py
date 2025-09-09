# src/catalyst_bot/ticker_resolver.py
from __future__ import annotations

import logging
import os
import pathlib
import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

# Export only public classes defined in this module. We do not expose any
# helpers or undefined names here to avoid flake8 F822.
__all__ = [
    # public classes exposed by this module
    "TickerResolver",
    "TickerRecord",
    "ResolveResult",
    # headline parsing helpers
    "_try_from_title",
    "resolve_from_source",
]


@dataclass(frozen=True)
class ResolveResult:
    """
    Encapsulate the result of a ticker-resolution attempt.
    `ticker` is the extracted symbol, or None if nothing was found.
    `method` is 'title' when a ticker was found via the headline, else 'none'.
    """

    ticker: Optional[str]
    method: str
    # "title" when a ticker was extracted from the headline
    # or "none" otherwise.


# Resolve the default database path:
# repo_root / data / tickers.db  (or override with env TICKERS_DB_PATH)
def _default_db_path() -> str:
    env = os.getenv("TICKERS_DB_PATH")
    if env:
        return env
    # src/catalyst_bot/ticker_resolver.py -> .../src -> repo root
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "tickers.db")


@dataclass(frozen=True)
class TickerRecord:
    cik: int
    ticker: str
    name: str


class TickerResolver:
    """
    SQLite-backed resolver for tickers and company names.

    - Exact ticker match: fast O(log n) via index.
    - Normalization: handles 'BRK.B', 'BRKB', '$nvda', stray spaces/punct.
    - Name search: simple AND-of-tokens using LIKE with a few ranking heuristics.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or _default_db_path()
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(
                f"Tickers DB not found at {self.db_path}. "
                "Create it via import_tickers_from_ndjson.py."
            )
        self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # small perf bump / consistency
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    # --------------------------
    # Public API
    # --------------------------
    def resolve(self, query: str, limit: int = 5) -> List[TickerRecord]:
        """
        Auto-detect whether the query is likely a ticker or a name,
        then return up to `limit` best matches.
        """
        q = _clean(query)
        if not q:
            return []

        # Likely a ticker if short and mostly alnum with A/B share suffixes, etc.
        if _looks_like_ticker(q):
            hit = self._by_ticker(q)
            if hit:
                return [hit]
            # If exact miss, try name search as a fallback
            return self._by_name(q, limit=limit)

        # Otherwise treat as company name
        return self._by_name(q, limit=limit)

    def resolve_one(self, query: str) -> Optional[TickerRecord]:
        """Return the single best match, if any."""
        rows = self.resolve(query, limit=1)
        return rows[0] if rows else None

    # --------------------------
    # Internals
    # --------------------------
    def _by_ticker(self, raw: str) -> Optional[TickerRecord]:
        """
        Try a series of normalizations to find a ticker:
         - exact
         - dot <-> dash (BRK.B <-> BRK-B)
         - strip dash (BRKB)
         - uppercase already applied in _clean
        """
        q = raw.upper()

        # 1) exact (case-insensitive)
        row = self._one(
            "SELECT cik,ticker,name FROM tickers WHERE ticker = ? COLLATE NOCASE",
            (q,),
        )
        if row:
            return _row_to_rec(row)

        # 2) dot->dash form (BRK.B -> BRK-B)
        alt_dash = q.replace(".", "-")
        if alt_dash != q:
            row = self._one(
                "SELECT cik,ticker,name FROM tickers WHERE ticker = ? COLLATE NOCASE",
                (alt_dash,),
            )
            if row:
                return _row_to_rec(row)

        # 3) dash->dot form (BRK-B -> BRK.B) — some people type dots
        alt_dot = q.replace("-", ".")
        if alt_dot != q:
            row = self._one(
                "SELECT cik,ticker,name FROM tickers WHERE ticker = ? COLLATE NOCASE",
                (alt_dot,),
            )
            if row:
                return _row_to_rec(row)

        # 4) compact form (BRKB) against stored ticker with dashes removed
        compact = q.replace("-", "").replace(".", "")
        sql = (
            "SELECT cik,ticker,name FROM tickers "
            "WHERE REPLACE(REPLACE(ticker,'-',''),'.','') = ? COLLATE NOCASE"
        )
        row = self._one(sql, (compact,))
        if row:
            return _row_to_rec(row)

        return None

    def _by_name(self, raw: str, limit: int = 5) -> List[TickerRecord]:
        """
        Token-AND search with LIKE. Prioritize:
          - prefix match on first token
          - shorter names
        """
        tokens = _name_tokens(raw)
        if not tokens:
            return []

        # Build WHERE: name LIKE ? AND name LIKE ? ...
        wheres = " AND ".join(["name LIKE ?"] * len(tokens))
        params: List[str] = [f"%{t}%" for t in tokens]

        # Ranking:
        #  - exact-ish prefix on first token first (e.g., 'APPLE%')
        #  - then shorter names
        first = tokens[0]
        order = """
            ORDER BY
              CASE WHEN UPPER(name) LIKE ? THEN 0 ELSE 1 END,
              LENGTH(name) ASC,
              ticker ASC
            LIMIT ?
        """
        params.extend([f"{first}%".upper(), limit])

        sql = f"SELECT cik,ticker,name FROM tickers WHERE {wheres} {order}"
        rows = list(self._all(sql, tuple(params)))
        return [_row_to_rec(r) for r in rows]

    def _one(self, sql: str, params: Tuple) -> Optional[sqlite3.Row]:
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return row

    def _all(self, sql: str, params: Tuple) -> Iterable[sqlite3.Row]:
        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows


# --------------------------
# Helpers
# --------------------------
_PUNCT_RE = re.compile(r"[\s\$\#\@\!\?\,\;\:\(\)\[\]\{\}]+")


def _clean(q: str) -> str:
    # trim, normalize spaces/punct, uppercase
    q = q.strip()
    q = _PUNCT_RE.sub(" ", q)
    return q.upper().strip()


def _looks_like_ticker(q: str) -> bool:
    # Heuristics: short, mostly A-Z0-9, allows . or - for share classes
    if len(q) <= 6 and re.fullmatch(r"[A-Z0-9][A-Z0-9\.\-]{0,5}", q):
        return True
    # leading $NVDA style
    if q.startswith("$") and len(q) <= 7:
        return True
    return False


_STOPWORDS = {
    "INC",
    "CORP",
    "PLC",
    "LLC",
    "CO",
    "COMPANY",
    "SA",
    "NV",
    "LP",
    "LTD",
    "GROUP",
}


def _name_tokens(q: str) -> List[str]:
    # keep alnum words; drop common suffixes
    words = re.findall(r"[A-Z0-9]+", q.upper())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _row_to_rec(r: sqlite3.Row) -> TickerRecord:
    return TickerRecord(cik=int(r["cik"]), ticker=str(r["ticker"]), name=str(r["name"]))


# -----------------------------------------------------
# Title-based resolution helpers
# -----------------------------------------------------
# These functions allow extraction of ticker symbols directly from news headlines
# or other text strings. They are intentionally lightweight and do not rely on
# database lookups. Patterns focus on U.S. exchanges (e.g., NASDAQ, NYSE,
# NYSE American, AMEX, OTC) and accept tickers of up to five characters with
# optional dot or dash. See tests in ``test_ticker_resolver.py`` for examples.

# Exchange names we recognise. Separate into a verbose regex with verbose flag
_EXCH_PATTERN = r"""
    (?:
        NASDAQ|Nasdaq|NYSE\ American|NYSE|AMEX|
        OTC(?:MKTS|QB|QX)?|OTC
    )
"""

# Allowed ticker characters. Typically 1–5 alphanumerics with optional dot/dash.
_TICKER_PATTERN = r"([A-Za-z\d\.\-]{1,5})"

# Compile a pattern that matches something like "(NASDAQ: ABC)" or "NYSE: XYZ"
_TITLE_REGEX = re.compile(
    rf"""
    # Optional opening bracket or brace
    [\(\[\{{]?\s*
    {_EXCH_PATTERN}\s*[:\-]\s*
    {_TICKER_PATTERN}
    \s*[\)\]\}}]?  # optional closing bracket or brace
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _sanitize_ticker(raw: str) -> Optional[str]:
    """Normalize raw ticker capture to uppercase and ensure it resembles a ticker.

    Strips stray punctuation, uppercases letters, and validates against a simple
    pattern (leading letter followed by up to four alphanumerics, dot, or dash).
    Returns None if the result does not appear to be a plausible ticker.
    """
    if not raw:
        return None
    t = raw.strip().upper().rstrip(".")
    # Accept patterns like "BRK.B", "BRK-B", "ABC", "AAPL". Reject if invalid.
    if not re.fullmatch(r"[A-Z][A-Z0-9\.-]{0,4}", t):
        return None
    return t


def _try_from_title(title: Optional[str]) -> Optional[str]:
    """Attempt to extract a ticker symbol from a headline or title.

    Supported formats include:
      - "Acme Corp (NASDAQ: ABC) announces..." → "ABC"
      - "Example — NYSE: XYZ completes merger" → "XYZ"
      - "Company [OTC: ABCD] files 8-K" → "ABCD"
      - "WidgetCo (Nasdaq: wIdg) to present" → "WIDG"

    Returns the uppercased ticker string if a match is found, otherwise None.
    """
    if not title:
        return None
    m = _TITLE_REGEX.search(title)
    if not m:
        return None
    return _sanitize_ticker(m.group(1))


def resolve_from_source(
    title: Optional[str], source_name: Optional[str], url: Optional[str]
) -> ResolveResult:
    """Resolve a ticker and method from a source description.

    The resolver currently only inspects the headline/title for exchange-tagged
    tickers. It returns a ResolveResult containing the extracted ticker (if
    found) and a method string indicating how the resolution was made. Future
    implementations may inspect the URL or source-specific fields to extract
    tickers.

    Parameters
    ----------
    title : Optional[str]
        The headline or title text from which to extract a ticker.
    source_name : Optional[str]
        Currently unused; reserved for future enhancements.
    url : Optional[str]
        Currently unused; reserved for future enhancements.

    Returns
    -------
    ResolveResult
        A dataclass with ``ticker`` and ``method`` fields. ``method`` is
        "title" if a ticker was extracted from the headline; otherwise
        "none".
    """
    ticker = _try_from_title(title)
    if ticker:
        return ResolveResult(ticker=ticker, method="title")
    return ResolveResult(ticker=None, method="none")


# --------------------------
# CLI (handy for quick tests)
# --------------------------
if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    p = argparse.ArgumentParser(description="Resolve tickers/company names via SQLite.")
    p.add_argument("query", help="Ticker or company name to resolve")
    p.add_argument(
        "--db", dest="db_path", default=None, help="Path to tickers.db (optional)"
    )
    p.add_argument(
        "--limit", type=int, default=5, help="Max rows to return for name search"
    )
    args = p.parse_args()

    r = TickerResolver(db_path=args.db_path)
    rows = r.resolve(args.query, limit=args.limit)
    print(json.dumps([row.__dict__ for row in rows], indent=2))
