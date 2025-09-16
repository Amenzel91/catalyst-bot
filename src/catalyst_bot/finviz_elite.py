# src/catalyst_bot/finviz_elite.py
from __future__ import annotations

import csv
import io
import os
import re
from typing import Any, Dict, List, Optional

import requests

try:
    from catalyst_bot.logging_utils import get_logger  # type: ignore
except Exception:  # pragma: no cover
    import logging

    def get_logger(name: str):
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        return logging.getLogger(name)  # type: ignore


log = get_logger("catalyst_bot.finviz_elite")

FINVIZ_BASE = "https://finviz.com"
PATH_SCREENER_EXPORT = "/export.ashx"
PATH_NEWS_FILINGS = "/news.ashx"


def _require_auth() -> str:
    """
    Prefer explicit argument; else FINVIZ_ELITE_AUTH, then FINVIZ_AUTH_TOKEN.
    """
    tok = (
        os.getenv("FINVIZ_ELITE_AUTH", "") or os.getenv("FINVIZ_AUTH_TOKEN", "")
    ).strip()
    if not tok:
        raise RuntimeError("FINVIZ_ELITE_AUTH/FINVIZ_AUTH_TOKEN is not set.")
    return tok


def _finviz_get(
    path: str, params: Dict[str, Any], auth: Optional[str] = None
) -> requests.Response:
    token = auth or _require_auth()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": f"elite={token}",
        "Accept": "*/*",
    }
    url = FINVIZ_BASE + path
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp


# ---- CSV parsing & normalization ----

# Loose mapper for common simple headers; everything else uses heuristics.
_BASE_MAP = {
    "ticker": "ticker",
    "company": "company",
    "sector": "sector",
    "industry": "industry",
    "country": "country",
    "price": "price",
    "change": "change",
    "market cap": "marketcap",
    "avg volume": "avgvol",
    "avg. volume": "avgvol",
    "volume": "volume",
    "volatility w": "vol_w",
    "volatility m": "vol_m",
    "perf day": "perf_day",
    "perf week": "perf_week",
    "perf month": "perf_month",
    "perf quarter": "perf_quarter",
    "perf half y": "perf_halfy",
    "perf year": "perf_year",
}


def _norm_key(k: str) -> str:
    raw = (k or "").strip()
    s = raw.lower().replace("\xa0", " ")
    s = re.sub(r"[.\u200b]+", "", s).strip()

    # direct map first
    if s in _BASE_MAP:
        return _BASE_MAP[s]

    # heuristic catch-alls
    if "rel volume" in s or "relative volume" in s:
        return "relvolume"
    if "avg" in s and "volume" in s:
        return "avgvol"

    # fallback: snake-case
    return re.sub(r"\s+", "_", s)


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in {"-", "—"}:
        return None
    s = s.replace(",", "").replace("%", "")
    try:
        return float(s)
    except Exception:
        return None


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in {"-", "—"}:
        return None
    try:
        return int(s.replace(",", ""))
    except Exception:
        return None


def _parse_csv_rows(text: str) -> List[Dict[str, Any]]:
    f = io.StringIO(text)
    reader = csv.reader(f)
    rows = list(reader)
    if not rows:
        return []

    headers_raw = rows[0]
    headers = [_norm_key(h) for h in headers_raw]
    log.info("finviz_screener_rows", extra={"headers": headers_raw})

    out: List[Dict[str, Any]] = []
    for r in rows[1:]:
        d = dict(zip(headers, r))

        # normalize common numerics if present
        if "price" in d:
            d["price"] = _to_float(d.get("price"))
        if "change" in d:
            d["change"] = _to_float(d.get("change"))
        if "relvolume" in d:
            d["relvolume"] = _to_float(d.get("relvolume"))
        if "volume" in d:
            d["volume"] = _to_int(d.get("volume"))
        if "avgvol" in d:
            d["avgvol"] = _to_int(d.get("avgvol"))

        out.append(d)
    return out


# ---- Public helpers ----


def export_screener(
    filters: str,
    auth: Optional[str] = None,
    view: Optional[str] = None,
    signal: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return normalized rows from a Finviz screener export.

    Parameters
    ----------
    filters : str
        A comma‑separated Finviz filter string (e.g. ``"sh_avgvol_o300,sh_relvol_o1.5"``).
        Prefix ``f=`` is not required; it will be added automatically.
    auth : Optional[str], optional
        Elite authentication token.  If not provided, the environment
        variables FINVIZ_AUTH_TOKEN or FINVIZ_ELITE_AUTH are used.
    view : Optional[str], optional
        Numeric view identifier controlling which columns Finviz returns.  If
        None, the environment variable FINVIZ_SCREENER_VIEW is consulted
        (default "152" for a rich set).  See Finviz documentation for
        available views.
    signal : Optional[str], optional
        When provided, include a Finviz ``signal`` parameter in the export
        request.  Signals allow filtering by technical patterns or market
        events (e.g. "ta_newhigh" for new highs).  If omitted, no signal
        filter is applied.  See https://finviz.com/screener.ashx for
        supported values.

    Returns
    -------
    List[Dict[str, Any]]
        Normalised rows where column names have been transformed to
        snake‑case keys and numeric values parsed.  An empty list is
        returned on any error.
    """
    try:
        view_id = (view or os.getenv("FINVIZ_SCREENER_VIEW", "152").strip()) or "152"
        params: Dict[str, Any] = {"v": view_id, "f": filters}
        if signal:
            params["s"] = signal
        resp = _finviz_get(PATH_SCREENER_EXPORT, params, auth=auth)
        return _parse_csv_rows(resp.text)
    except Exception:
        return []


def export_latest_filings(
    ticker: Optional[str] = None, auth: Optional[str] = None
) -> List[Dict[str, Any]]:
    params = {"type": "filings"}
    if ticker:
        params["q"] = ticker.upper().strip()

    resp = _finviz_get(PATH_NEWS_FILINGS, params, auth=auth)
    html = resp.text

    rows: List[Dict[str, Any]] = []
    try:
        import re
        from html import unescape

        tr_pat = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
        td_pat = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
        href_pat = re.compile(r'href="([^"]+)"', re.I)

        for tr_html in tr_pat.findall(html):
            tds = td_pat.findall(tr_html)
            if len(tds) < 3:
                continue
            cols = [unescape(re.sub(r"<[^>]+>", "", td)).strip() for td in tds]
            date_str = cols[0]
            tk = cols[1].split()[0].upper().strip() if cols[1] else None
            title = cols[2]
            link_m = href_pat.search(tds[2])
            url = (FINVIZ_BASE + link_m.group(1)) if link_m else None

            form = None
            for piece in cols[2:]:
                m = re.search(
                    r"\b(8-K|10-K|10-Q|S-1|6-K|20-F|SC 13G|SC 13D)\b", piece, re.I
                )
                if m:
                    form = m.group(1).upper()
                    break

            if not tk:
                continue
            rows.append(
                {
                    "filing_date": date_str,
                    "ticker": tk,
                    "title": title,
                    "url": url,
                    "filing_type": form,
                }
            )
    except Exception:
        pass

    log.info("finviz_filings_rows")
    return rows


def screener_unusual_volume(
    min_avg_vol: int = 300_000, min_relvol: float = 1.5
) -> List[Dict[str, Any]]:
    filters = f"sh_avgvol_o{min_avg_vol},sh_relvol_o{min_relvol}"
    return export_screener(filters=filters)
