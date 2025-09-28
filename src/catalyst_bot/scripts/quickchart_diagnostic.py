"""
Diagnostic helper for QuickChart integration.

This script can be run manually to troubleshoot QuickChart chart generation
for a given ticker.  It will fetch intraday data via the ``market`` module,
print information about the returned DataFrame, attempt to build a QuickChart
URL using ``get_quickchart_url``, and optionally test the URL with an HTTP
GET request.  If the QuickChart API is disabled or returns ``None``, the
script will also show the fallback yfinance QuickChart URL, if available.

Usage (from repository root):

```
python -m catalyst_bot.scripts.quickchart_diagnostic --ticker AAPL [--fetch]
```

Pass ``--fetch`` to perform an actual HTTP GET of the returned URL.  This
can help verify that the QuickChart endpoint (local or hosted) is accessible
and that the generated chart is non‑empty.  Note that performing the fetch
requires the ``requests`` library to be installed in your environment.

Environment variables respected:

 - ``FEATURE_QUICKCHART``: when set to ``1``, QuickChart generation is
   attempted (default is off).
 - ``QUICKCHART_BASE_URL``: base URL of the QuickChart server.  If this
   ends with ``/chart``, the diagnostic will show both the raw setting and
   the final URL used by ``get_quickchart_url``.
 - ``QUICKCHART_SHORTEN_THRESHOLD``: maximum URL length before using the
   QuickChart ``/chart/create`` endpoint.  The diagnostic prints the
   threshold and whether shortening would be invoked.

This helper does not post to Discord; it only prints to stdout.  Use it
when QuickChart images are not showing up in alerts to identify missing
data, misconfigured environment variables, or network issues.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

from .. import market
from ..charts import get_quickchart_url, _quickchart_url_yfinance


def diagnose_quickchart(ticker: str, *, fetch: bool = False) -> None:
    """Run QuickChart diagnostics for a given ticker and print results."""
    nt = (ticker or "").strip().upper()
    if not nt:
        print("Ticker is empty; aborting", file=sys.stderr)
        return

    print(f"Running QuickChart diagnostics for ticker: {nt}\n")

    # Show relevant environment variables
    feature_qc = os.getenv("FEATURE_QUICKCHART") or os.getenv("FEATURE_QUICKCHART", "0")
    base_env = os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io/chart")
    shorten_threshold = os.getenv("QUICKCHART_SHORTEN_THRESHOLD", "1900")
    print("Environment variables:")
    print(f"  FEATURE_QUICKCHART = {feature_qc}")
    print(f"  QUICKCHART_BASE_URL = {base_env}")
    print(f"  QUICKCHART_SHORTEN_THRESHOLD = {shorten_threshold}\n")

    # Fetch intraday data via market module
    print("Fetching intraday data via market.get_intraday() ...")
    df = market.get_intraday(nt, interval="5min", output_size="compact", prepost=True)
    if df is None or getattr(df, "empty", False):
        print("  No intraday data returned (df is None or empty)\n")
    else:
        print(f"  DataFrame shape: {df.shape}")
        print(f"  First rows:\n{df.head()}\n")

    # Attempt to build QuickChart URL via charts.get_quickchart_url
    print("Building QuickChart URL via get_quickchart_url() ...")
    qc_url = get_quickchart_url(nt, bars=50)
    if not qc_url:
        print("  get_quickchart_url returned None (no chart generated)\n")
    else:
        print(f"  QuickChart URL: {qc_url}")
        print(f"  URL length: {len(qc_url)} characters\n")
        # Show whether the base URL ends with /chart
        if base_env.rstrip("/").endswith("/chart"):
            print("  Note: QUICKCHART_BASE_URL ends with '/chart' — verify that the URL doesn't repeat '/chart' twice.\n")

    # Fallback yfinance QuickChart helper
    print("Building fallback QuickChart via _quickchart_url_yfinance() ...")
    fallback_url = _quickchart_url_yfinance(nt, bars=50)
    if fallback_url:
        print(f"  yfinance fallback URL: {fallback_url}")
        print(f"  URL length: {len(fallback_url)} characters\n")
    else:
        print("  _quickchart_url_yfinance returned None (no fallback chart)\n")

    # Optionally fetch the URL to test HTTP status
    if fetch and requests is not None:
        test_url = qc_url or fallback_url
        if not test_url:
            print("No URL to fetch; skipping HTTP test\n")
        else:
            print(f"Testing HTTP GET for URL: {test_url}")
            try:
                resp = requests.get(test_url, timeout=10)
                print(f"  HTTP status: {resp.status_code}")
                print(f"  Content type: {resp.headers.get('Content-Type')}")
                print(f"  Content length: {len(resp.content)} bytes\n")
            except Exception as err:
                print(f"  HTTP request failed: {err}\n")
    elif fetch and requests is None:
        print("requests library not installed; cannot fetch URL\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuickChart diagnostics helper")
    parser.add_argument("--ticker", required=True, help="Ticker symbol to diagnose")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Perform an HTTP GET on the generated QuickChart URL",
    )
    args = parser.parse_args(argv)
    diagnose_quickchart(args.ticker, fetch=args.fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())