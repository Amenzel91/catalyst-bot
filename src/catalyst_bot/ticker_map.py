import os
import re
import sqlite3

_CIK_RE = re.compile(r"/edgar/data/(\d+)/", re.IGNORECASE)


def load_cik_to_ticker(db_path=None):
    db_path = db_path or os.getenv("TICKERS_DB_PATH", "data/tickers.db")
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT cik, ticker FROM tickers").fetchall()
    conn.close()
    m = {}
    for cik, ticker in rows:
        try:
            s = str(int(cik))
        except Exception:
            s = str(cik)
        m[s] = ticker
        m[s.zfill(10)] = ticker  # SEC sometimes pads to 10
    return m


def cik_from_text(text: str | None):
    if not text:
        return None
    m = _CIK_RE.search(text)
    return m.group(1) if m else None
