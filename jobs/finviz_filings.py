# jobs/finviz_filings.py
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from catalyst_bot import alerts
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
    """Finviz commonly shows 1/26/2015; sometimes ISO. Accept either."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(ymd, fmt)
            return d >= cutoff
        except ValueError:
            continue
    return False


def _normalize_date(ymd: str) -> str | None:
    """Return ISO-8601 YYYY-MM-DD if parseable; else None."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(ymd, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _maybe_alert(row: dict) -> None:
    """Send a single, unified alert through alerts.send_alert_safe()."""
    ticker = (row.get("ticker") or "").upper()
    form = row.get("filing_type") or row.get("form") or ""
    link = row.get("url")
    fdate_raw = row.get("filing_date") or ""
    fdate_iso = _normalize_date(fdate_raw) or fdate_raw  # keep original if unknown

    if not ticker or not form:
        # Not enough to alert; quietly skip.
        return

    payload = {
        "channel": "filings",
        "ticker": ticker,
        "title": f"{ticker} filed {form}",
        "url": link,
        "form": form,
        "when": fdate_iso,
    }
    alerts.send_alert_safe(payload)


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)

    cutoff = datetime.utcnow() - timedelta(days=RECENT_DAYS)

    # Pull by major tickers, or None (general stream)
    tickers = [None, "AAPL", "MSFT", "AMZN", "NVDA", "TSLA", "GOOGL", "META"]

    for tk in tickers:
        rows = export_latest_filings(ticker=tk)
        log.info("ingested_filings")

        # keep only recent
        rows = [
            r
            for r in rows
            if r.get("filing_date") and _is_recent(str(r["filing_date"]), cutoff)
        ]

        with conn:
            for r in rows:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO finviz_filings
                      (ticker, filing_type, filing_date, title, url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (r.get("ticker") or "").upper(),
                        r.get("filing_type"),
                        r.get("filing_date"),
                        r.get("title"),
                        r.get("url"),
                    ),
                )
                if cur.rowcount:  # new insert (not ignored)
                    _maybe_alert(r)

    log.info("filings_complete")


if __name__ == "__main__":  # pragma: no cover
    main()
