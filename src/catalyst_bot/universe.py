from __future__ import annotations

import csv
import io
from typing import Optional, Set, Tuple

import requests

from .logging_utils import get_logger

log = get_logger("universe")

USER_AGENT = "CatalystBot/1.0 (+https://example.local)"

# Finviz Elite CSV export endpoint.
# v=111: Screener "Overview" view. ft=4: CSV export.
EXPORT_URL = "https://elite.finviz.com/export.ashx"


def _is_probable_etf(row: dict) -> bool:
    """
    Heuristics to skip ETFs:
    - 'ETF' appears in 'Company', 'Sector', or 'Industry' columns
      (case-insensitive)
    """
    for key in ("Company", "Sector", "Industry"):
        val = (row.get(key) or "").upper()
        if "ETF" in val:
            return True
    return False


def _extract_ticker(row: dict) -> Optional[str]:
    """
    Finviz CSV commonly uses 'Ticker'. Fall back to first column guess.
    """
    for k in ("Ticker", "ticker", "Symbol", "symbol"):
        t = (row.get(k) or "").strip().upper()
        if t:
            return t
    if row:
        first_key = list(row.keys())[0]
        t = (row.get(first_key) or "").strip().upper()
        if t and len(t) <= 5 and t.isalnum():
            return t
    return None


def _download_export(
    price_ceiling: float, cookie: str, timeout: int = 20
) -> Optional[str]:
    """
    Fetch CSV text from Finviz Elite. Return text on success, else None.
    """
    params = {
        "v": "111",
        "ft": "4",
        "f": f"sh_price_u{int(price_ceiling)}",
    }
    try:
        resp = requests.get(
            EXPORT_URL,
            params=params,
            headers={
                "Cookie": cookie,
                "User-Agent": USER_AGENT,
                "Accept": "text/csv,*/*;q=0.5",
            },
            timeout=timeout,
        )
    except Exception as err:
        log.warning("finviz_export_http_error err=%s", str(err))
        return None

    if resp.status_code != 200:
        log.info("finviz_export_http status=%s", resp.status_code)
        return None

    text = resp.text or ""
    if "Ticker" not in text and "Symbol" not in text:
        log.info("finviz_export_no_standard_header")
    return text


def get_universe_tickers(
    price_ceiling: float, cookie: str, timeout: int = 20, max_rows: int = 10000
) -> Tuple[Set[str], int]:
    """
    Returns (tickers_set, raw_rows_count).
    On failure or missing cookie, returns (empty_set, 0).
    """
    if not cookie:
        return set(), 0

    text = _download_export(price_ceiling, cookie, timeout=timeout)
    if not text:
        return set(), 0

    tickers: Set[str] = set()
    total_rows = 0

    try:
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        for row in reader:
            total_rows += 1
            if total_rows > max_rows:
                break
            if _is_probable_etf(row):
                continue
            t = _extract_ticker(row)
            if t:
                tickers.add(t)
    except Exception as err:
        log.warning("finviz_export_parse_error err=%s", str(err))
        return set(), 0

    return tickers, total_rows
