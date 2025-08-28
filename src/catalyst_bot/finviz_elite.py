# src/catalyst_bot/finviz_elite.py
from __future__ import annotations
import os, io, csv, logging, typing as T, argparse, json
import requests
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Optional: auto-load .env if present ---
try:  # no hard dependency; only if installed
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()  # loads .env from cwd/upwards
except Exception:
    pass

log = logging.getLogger(__name__)

FINVIZ_ELITE_BASE = "https://elite.finviz.com"

def _get_auth_token() -> str:
    """
    Resolve the Finviz token from multiple places:
      1) FINVIZ_ELITE_AUTH
      2) FINVIZ_ELITE_TOKEN (alias)
      3) FINVIZ_AUTH (alias)
      4) data/finviz_token.txt (if present; first line)
    """
    candidates = [
        os.getenv("FINVIZ_ELITE_AUTH", "").strip(),
        os.getenv("FINVIZ_ELITE_TOKEN", "").strip(),
        os.getenv("FINVIZ_AUTH", "").strip(),
    ]
    for tok in candidates:
        if tok:
            return tok

    # fallback file (kept out of git)
    token_file = os.path.join("data", "finviz_token.txt")
    try:
        if os.path.exists(token_file):
            with open(token_file, "r", encoding="utf-8-sig") as f:
                first = (f.readline() or "").strip()
                if first:
                    return first
    except Exception:
        pass

    # final: explain how to fix
    raise RuntimeError(
        "FINVIZ_ELITE_AUTH is not set. Set it in your shell, .env, or put the token in data/finviz_token.txt.\n"
        "Examples:\n"
        "  PowerShell (this session):  $env:FINVIZ_ELITE_AUTH = \"<token>\"\n"
        "  Persist for user:           [Environment]::SetEnvironmentVariable(\"FINVIZ_ELITE_AUTH\",\"<token>\",\"User\")\n"
        "  .env file:                  FINVIZ_ELITE_AUTH=<token>\n"
        "  File fallback:              echo <token> > data\\finviz_token.txt"
    )

def _session(timeout: float = 15.0) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4, read=4, connect=4, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.request = T.cast(T.Callable[..., requests.Response], _with_timeout(s.request, timeout))  # type: ignore
    return s

def _with_timeout(fn, timeout):
    def wrapped(method, url, **kw):
        kw.setdefault("timeout", timeout)
        return fn(method, url, **kw)
    return wrapped

def _read_csv_bytes(b: bytes) -> list[dict[str, str]]:
    txt = b.decode("utf-8", errors="replace").lstrip("\ufeff")
    txt = "\n".join(line for line in txt.splitlines() if line.strip())
    if not txt or "," not in txt:
        return []
    reader = csv.DictReader(io.StringIO(txt))
    return [dict(row) for row in reader]

# -------- Public API --------

def export_screener(*, filters: str, auth: str | None = None) -> list[dict[str, str]]:
    """
    Finviz Elite Screener CSV export.
    `filters` is the Finviz query string (e.g. v=111&f=...&c=ticker,price,change)
    """
    token = (auth or _get_auth_token()).strip()
    url = f"{FINVIZ_ELITE_BASE}/export.ashx?{filters}&auth={token}" if filters else f"{FINVIZ_ELITE_BASE}/export.ashx?auth={token}"
    s = _session()
    resp = s.get(url)
    resp.raise_for_status()
    rows = _read_csv_bytes(resp.content)
    log.info("finviz_screener_rows", extra={"rows": len(rows)})
    return rows

def export_latest_filings(*, ticker: str, order_by: str = "filingDate", extra_params: dict[str, str] | None = None, auth: str | None = None) -> list[dict[str, str]]:
    """
    Latest Filings CSV export for a single ticker.
    /export/latest-filings?t=<T>&o=<ORDER>&auth=<TOKEN>
    """
    token = (auth or _get_auth_token()).strip()
    q = {"t": ticker.upper(), "o": order_by, "auth": token}
    if extra_params:
        q.update(extra_params)
    url = f"{FINVIZ_ELITE_BASE}/export/latest-filings?{urlencode(q)}"
    s = _session()
    resp = s.get(url)
    resp.raise_for_status()
    rows = _read_csv_bytes(resp.content)
    log.info("finviz_filings_rows", extra={"ticker": ticker.upper(), "rows": len(rows)})
    return rows

# Convenience presets
def screener_unusual_volume(min_price: float = 5.0, min_relvol: float = 2.0) -> list[dict[str, str]]:
    f = [
        "v=111",
        f"f=sh_price_o{int(min_price)},ta_relvolume_o{min_relvol}",
    ]
    cols = "ticker,company,sector,industry,price,change,volume,relvolume,avgvol"
    filters = "&".join(f) + f"&c={cols}"
    return export_screener(filters=filters)

def screener_breakouts_largecap_nasdaq() -> list[dict[str, str]]:
    filters = (
        "v=111"
        "&f=cap_largeover,exch_nasd,ta_sma200_pb,ta_sma50_pb,ta_highlow52w_nh"
        "&c=ticker,company,sector,industry,price,change,volume,relvolume,avgvol,rsit"
    )
    return export_screener(filters=filters)

# -------- CLI --------

def _main_cli():
    ap = argparse.ArgumentParser(description="Finviz Elite CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_scr = sub.add_parser("screen", help="Run a screener export")
    ap_scr.add_argument("--filters", help="Finviz query string (v=...&f=...&c=...)", required=False)
    ap_scr.add_argument("--preset", choices=["unusual_volume", "breakouts"], help="Use a built-in preset")
    ap_scr.add_argument("--auth", help="Override auth token", required=False)

    ap_fil = sub.add_parser("filings", help="Fetch latest filings for a ticker")
    ap_fil.add_argument("ticker")
    ap_fil.add_argument("--auth", help="Override auth token", required=False)

    args = ap.parse_args()
    if args.cmd == "screen":
        if args.preset == "unusual_volume":
            rows = screener_unusual_volume()
        elif args.preset == "breakouts":
            rows = screener_breakouts_largecap_nasdaq()
        else:
            if not args.filters:
                raise SystemExit("--filters or --preset is required")
            rows = export_screener(filters=args.filters, auth=args.auth)
        print(json.dumps(rows, indent=2))
    elif args.cmd == "filings":
        rows = export_latest_filings(ticker=args.ticker, auth=args.auth)
        print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    _main_cli()
