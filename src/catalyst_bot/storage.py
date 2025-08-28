# src/catalyst_bot/storage.py
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import time

DB_PATH = os.getenv("MARKET_DB_PATH", "data/market.db")


def _ensure_dir(p: str):
    pathlib.Path(os.path.dirname(p) or ".").mkdir(parents=True, exist_ok=True)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    _ensure_dir(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=4000;")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS finviz_screener_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          captured_at INTEGER NOT NULL,
          screen_key TEXT NOT NULL,
          ticker TEXT,
          price REAL,
          change REAL,
          relvolume REAL,
          raw_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_finviz_snap_time ON finviz_screener_snapshots(captured_at);
        CREATE INDEX IF NOT EXISTS idx_finviz_snap_ticker ON finviz_screener_snapshots(ticker);

        CREATE TABLE IF NOT EXISTS finviz_filings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          captured_at INTEGER NOT NULL,
          ticker TEXT NOT NULL,
          form TEXT,
          filing_date TEXT,
          title TEXT,
          link TEXT,
          raw_json TEXT NOT NULL,
          UNIQUE(ticker, form, filing_date, title) ON CONFLICT IGNORE
        );

        CREATE INDEX IF NOT EXISTS idx_finviz_filings_time ON finviz_filings(captured_at);
        CREATE INDEX IF NOT EXISTS idx_finviz_filings_ticker ON finviz_filings(ticker);
        """
    )
    conn.commit()


def now_ts() -> int:
    return int(time.time())


def insert_screener_rows(
    conn: sqlite3.Connection, screen_key: str, rows: list[dict]
) -> int:
    ts = now_ts()
    cur = conn.cursor()
    n = 0
    for r in rows:
        # Column names vary by view; try common ones safely
        ticker = (r.get("Ticker") or r.get("ticker") or "").upper() or None
        price = _to_float(r.get("Price") or r.get("price"))
        change = _pct_to_float(r.get("Change") or r.get("change"))
        relvol = _to_float(
            r.get("Rel Volume") or r.get("RelVolume") or r.get("relvolume")
        )
        cur.execute(
            "INSERT INTO finviz_screener_snapshots("
            "captured_at, screen_key, ticker, price, change, relvolume, raw_json"
            ") VALUES (?,?,?,?,?,?,?)",
            (ts, screen_key, ticker, price, change, relvol, json.dumps(r)),
        )
        n += 1
    conn.commit()
    return n


def insert_filings(conn: sqlite3.Connection, ticker: str, rows: list[dict]) -> int:
    ts = now_ts()
    cur = conn.cursor()
    n = 0
    for r in rows:
        form = (r.get("Form") or r.get("form") or r.get("Type") or "").strip() or None
        fdate = (
            r.get("Filing Date") or r.get("filingDate") or r.get("Date") or ""
        ).strip() or None
        title = (r.get("Title") or r.get("title") or "").strip() or None
        link = (r.get("Link") or r.get("link") or "").strip() or None
        cur.execute(
            "INSERT OR IGNORE INTO finviz_filings("
            "captured_at, ticker, form, filing_date, title, link, raw_json"
            ") VALUES (?,?,?,?,?,?,?)",
            (ts, ticker.upper(), form, fdate, title, link, json.dumps(r)),
        )
        n += cur.rowcount > 0
    conn.commit()
    return int(n)


def _to_float(x):
    try:
        if isinstance(x, str):
            x = x.replace(",", "")
        return float(x)
    except Exception:
        return None


def _pct_to_float(x):
    try:
        if isinstance(x, str):
            x = x.strip().replace("%", "")
        return float(x)
    except Exception:
        return None
