# import_tickers_from_ndjson.py
from __future__ import annotations

import json, os, sqlite3, sys, pathlib

def ensure_dir(p: str):
    pathlib.Path(os.path.dirname(p) or ".").mkdir(parents=True, exist_ok=True)

def iter_records(input_path: str):
    # NDJSON (one JSON obj per line)
    if input_path.lower().endswith(".ndjson"):
        with open(input_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.lstrip("\ufeff").strip()
                if not line:
                    continue
                yield json.loads(line)
        return
    # Giant .json (list or dict-of-objects)
    with open(input_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    rows = data.values() if isinstance(data, dict) else data
    for obj in rows:
        yield obj

def main():
    if len(sys.argv) < 3:
        print("Usage: python import_tickers_from_ndjson.py <input.ndjson|.json> <output.db>")
        sys.exit(2)

    in_path = sys.argv[1]
    db_path = sys.argv[2]

    if not os.path.exists(in_path):
        print(f"Input file not found: {in_path}")
        sys.exit(1)

    ensure_dir(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
              ticker   TEXT PRIMARY KEY,
              cik      INTEGER NOT NULL,
              name     TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickers_name ON tickers(name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickers_cik ON tickers(cik);")

        conn.execute("BEGIN;")
        for obj in iter_records(in_path):
            cik = int(obj["cik_str"])
            ticker = obj["ticker"].upper().strip()
            name = obj["title"].strip()
            conn.execute("""
                INSERT INTO tickers(ticker,cik,name)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                  cik=excluded.cik,
                  name=excluded.name
            """, (ticker, cik, name))
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM tickers;").fetchone()[0]
        print(f"Import complete. tickers.db path: {os.path.abspath(db_path)}")
        print(f"Total rows now in tickers: {total}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
