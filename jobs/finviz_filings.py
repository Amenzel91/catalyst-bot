# jobs/finviz_filings.py
from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from catalyst_bot.finviz_elite import export_latest_filings
from catalyst_bot.logging_utils import get_logger

log = get_logger("finviz_filings")

DB_PATH = os.getenv("MARKET_DB_PATH", os.path.join("data", "market.db"))
RECENT_DAYS = int(os.getenv("FILINGS_RECENT_DAYS", "7"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS finviz_filings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  filing_type TEXT,
  filing_date TEXT,   -- keep as text (original format)
  title TEXT,
  url TEXT
);

CREATE INDEX IF NOT EXISTS idx_filings_ticker ON finviz_filings(ticker);
CREATE UNIQUE INDEX IF NOT EXISTS uq_filings_key
  ON finviz_filings(ticker, COALESCE(filing_type,''), COALESCE(filing_date,''), COALESCE(title,''));
"""

def _is_recent(ymd: str, cutoff: datetime) -> bool:
    fmt_try = ("%m/%d/%Y", "%Y-%m-%d")  # Finviz shows 1/26/2015 or sometimes ISO
    for fmt in fmt_try:
        try:
            d = datetime.strptime(ymd, fmt)
            return d >= cutoff
        except ValueError:
            continue
    # if parse fails, drop it (prefer being conservative for alerts)
    return False

def _maybe_alert(row: dict):
    # Wire this into your real alert pipeline later
    # For now we’ll just log to console for visibility.
    print("[ALERT]", {
        "channel": "filings",
        "ticker": row.get("ticker"),
        "title": row.get("title"),
        "url": row.get("url"),
        "form": row.get("filing_type"),
        "when": row.get("filing_date"),
    })

def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)

    cutoff = datetime.utcnow() - timedelta(days=RECENT_DAYS)

    # Pull by major tickers, or empty (which returns general stream).
    # You can loop a watchlist here; for now do general + a couple of big names.
    tickers = [None, "AAPL", "MSFT", "AMZN", "NVDA", "TSLA", "GOOGL", "META"]

    for tk in tickers:
        rows = export_latest_filings(ticker=tk)
        log.info("ingested_filings")
        # keep only recent
        rows = [r for r in rows if r.get("filing_date") and _is_recent(r["filing_date"], cutoff)]

        with conn:
            for r in rows:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO finviz_filings
                      (ticker, filing_type, filing_date, title, url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        r.get("ticker"),
                        r.get("filing_type"),
                        r.get("filing_date"),
                        r.get("title"),
                        r.get("url"),
                    ),
                )
                if cur.rowcount:  # new
                    _maybe_alert(r)

    log.info("filings_complete")

if __name__ == "__main__":  # pragma: no cover
    main()
