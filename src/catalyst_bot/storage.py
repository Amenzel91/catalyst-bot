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


def init_optimized_connection(db_path: str, timeout: int = 30) -> sqlite3.Connection:
    """
    Initialize SQLite connection with performance optimizations.

    Week 1 Optimization: Enable WAL mode and optimal pragmas for better
    concurrency and performance.

    Parameters
    ----------
    db_path : str
        Path to SQLite database file
    timeout : int, optional
        Connection timeout in seconds (default: 30)

    Returns
    -------
    sqlite3.Connection
        Optimized SQLite connection

    Environment Variables
    --------------------
    SQLITE_WAL_MODE : str
        Enable Write-Ahead Logging (1=on, 0=off, default: 1)
    SQLITE_SYNCHRONOUS : str
        Synchronous mode (FULL=safest, NORMAL=balanced, OFF=fastest, default: NORMAL)
    SQLITE_CACHE_SIZE : str
        Cache size in pages (default: 10000 pages ~40MB)
    SQLITE_MMAP_SIZE : str
        Memory-mapped I/O size in bytes (default: 30GB)
    """
    _ensure_dir(db_path)
    conn = sqlite3.connect(db_path, timeout=timeout)

    # Enable WAL mode for better concurrency (configurable)
    if os.getenv("SQLITE_WAL_MODE", "1") == "1":
        conn.execute("PRAGMA journal_mode=WAL")
        # Set WAL auto-checkpoint to 500 pages (prevents WAL bloat)
        conn.execute("PRAGMA wal_autocheckpoint=500")

    # Balance between safety and speed
    synchronous_mode = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL")
    conn.execute(f"PRAGMA synchronous={synchronous_mode}")

    # Increase cache size (negative = KB, positive = pages)
    cache_size = int(os.getenv("SQLITE_CACHE_SIZE", "10000"))
    conn.execute(f"PRAGMA cache_size={cache_size}")

    # Enable memory-mapped I/O (30GB default)
    mmap_size = int(os.getenv("SQLITE_MMAP_SIZE", "30000000000"))
    conn.execute(f"PRAGMA mmap_size={mmap_size}")

    # Use memory for temporary tables
    conn.execute("PRAGMA temp_store=MEMORY")

    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Create tables and indexes for the market database if missing.

    This migration is idempotent: it will not fail if the tables already
    exist.  It is designed to tolerate older schemas that may be
    missing columns referenced by the indexes.  Any errors encountered
    during index creation are suppressed to avoid breaking the caller.

    Parameters
    ----------
    conn : sqlite3.Connection
        An open SQLite connection.  The caller is responsible for
        closing the connection.
    """
    # Create the finviz_screener_snapshots table with the latest schema.
    try:
        conn.execute(
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
            """
        )
    except Exception:
        # If the table exists with a different schema, ignore the error.
        pass
    # Create indexes on finviz_screener_snapshots.  Suppress errors if
    # the columns are missing in older schemas.
    try:
        # Define SQL separately to keep line lengths within 100 characters.
        sql_time_idx = (
            "CREATE INDEX IF NOT EXISTS idx_finviz_snap_time "
            "ON finviz_screener_snapshots(captured_at);"
        )
        conn.execute(sql_time_idx)
    except sqlite3.OperationalError:
        # Older schemas may not have the captured_at column; skip index creation.
        pass
    except Exception:
        pass
    try:
        sql_ticker_idx = (
            "CREATE INDEX IF NOT EXISTS idx_finviz_snap_ticker "
            "ON finviz_screener_snapshots(ticker);"
        )
        conn.execute(sql_ticker_idx)
    except sqlite3.OperationalError:
        # Column may be missing in legacy schemas.
        pass
    except Exception:
        pass
    # Create the finviz_filings table.
    try:
        conn.execute(
            """
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
            """
        )
    except Exception:
        pass
    # Create indexes on finviz_filings.  Ignore errors if columns are missing.
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_finviz_filings_time ON finviz_filings(captured_at);"
        )
    except sqlite3.OperationalError:
        pass
    except Exception:
        pass
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_finviz_filings_ticker ON finviz_filings(ticker);"
        )
    except sqlite3.OperationalError:
        pass
    except Exception:
        pass
    try:
        conn.commit()
    except Exception:
        pass


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
            (
                "INSERT INTO finviz_screener_snapshots("
                "captured_at,screen_key,ticker,price,change,relvolume,raw_json"
                ") VALUES (?,?,?,?,?,?,?)"
            ),
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
            (
                "INSERT OR IGNORE INTO finviz_filings("
                "captured_at,ticker,form,filing_date,title,link,raw_json"
                ") VALUES (?,?,?,?,?,?,?)"
            ),
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
