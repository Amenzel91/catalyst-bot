# jobs/finviz_ingest.py
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from catalyst_bot.finviz_elite import screener_unusual_volume
from catalyst_bot.logging_utils import get_logger

log = get_logger("finviz_ingest")

DB_PATH = os.getenv("MARKET_DB_PATH", os.path.join("data", "market.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS finviz_screener_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,                 -- ISO8601 UTC
  preset TEXT,
  ticker TEXT NOT NULL,
  company TEXT,
  sector TEXT,
  industry TEXT,
  country TEXT,
  price REAL,
  change REAL,                      -- percent (e.g., 2.34)
  volume INTEGER,
  avgvol INTEGER,
  relvolume REAL,
  marketcap TEXT,
  perf_day REAL,
  perf_week REAL,
  perf_month REAL,
  perf_quarter REAL,
  perf_halfy REAL,
  perf_year REAL,
  vol_w REAL,
  vol_m REAL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_preset_ts ON finviz_screener_snapshots(preset, ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker ON finviz_screener_snapshots(ticker);
CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_key
  ON finviz_screener_snapshots(ticker, ts, COALESCE(preset,''));
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)

    ts = _utcnow_iso()
    preset = "unusual_volume"

    rows = screener_unusual_volume()
    log.info("ingested_screen")
    with conn:
        for r in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO finviz_screener_snapshots
                  (ts, preset, ticker, company, sector, industry, country,
                   price, change, volume, avgvol, relvolume, marketcap,
                   perf_day, perf_week, perf_month, perf_quarter, perf_halfy, perf_year,
                   vol_w, vol_m)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?,
                   ?, ?)
                """,
                (
                    ts,
                    preset,
                    r.get("ticker"),
                    r.get("company"),
                    r.get("sector"),
                    r.get("industry"),
                    r.get("country"),
                    r.get("price"),
                    r.get("change"),
                    r.get("volume"),
                    r.get("avgvol"),
                    r.get("relvolume"),
                    r.get("marketcap"),
                    r.get("perf_day"),
                    r.get("perf_week"),
                    r.get("perf_month"),
                    r.get("perf_quarter"),
                    r.get("perf_halfy"),
                    r.get("perf_year"),
                    r.get("vol_w"),
                    r.get("vol_m"),
                ),
            )

    log.info("ingest_complete")


if __name__ == "__main__":  # pragma: no cover
    main()
