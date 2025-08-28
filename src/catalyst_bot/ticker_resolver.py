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
        row = self._one(
            "SELECT cik, ticker, name FROM tickers "
            "WHERE REPLACE(REPLACE(ticker,'-',''),'.','') = ? COLLATE NOCASE",
            (compact,),
        )
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
        " AND ".join(["name LIKE ?"] * len(tokens))
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

        sql = (
            "SELECT cik, ticker, name FROM tickers "
            "WHERE " + " AND ".join(["name LIKE ?"] * len(tokens)) + " " + order
        )
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
