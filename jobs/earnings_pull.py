"""Pull upcoming earnings dates from Alpha Vantage and write to a CSV cache.

This script fetches the earnings calendar from Alpha Vantage's free API and
stores the results in a local CSV file.  The cached file can then be
consumed by the analyzer to annotate events occurring on earnings days.

Usage::

    ALPHAVANTAGE_API_KEY=... python jobs/earnings_pull.py

Environment variables:

* **ALPHAVANTAGE_API_KEY** – Your Alpha Vantage API key (required).
* **EARNINGS_HORIZON** – How far ahead to look.  One of ``3month``, ``6month``
  or ``12month``.  Defaults to ``3month``.
* **EARNINGS_CALENDAR_CACHE** – Path to write the CSV.  Defaults to
  ``data/earnings_calendar.csv`` relative to the repo root.

Alpha Vantage returns CSV for the earnings calendar endpoint.  We simply
fetch the content and write it to disk verbatim.  On failure (non‑200
response or network error), the script exits with a non‑zero status.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import requests


def _get_cache_path() -> Path:
    """Return the absolute path to the earnings calendar cache file."""
    # Default to data/earnings_calendar.csv in the project root
    cache = os.getenv("EARNINGS_CALENDAR_CACHE", "data/earnings_calendar.csv")
    return Path(cache).resolve()


def _fetch_earnings_csv(api_key: str, horizon: str = "3month") -> Optional[str]:
    """Fetch the earnings calendar CSV from Alpha Vantage.

    Parameters
    ----------
    api_key : str
        Your Alpha Vantage API key.
    horizon : str
        Horizon to request (3month, 6month or 12month).

    Returns
    -------
    Optional[str]
        The CSV text if the request succeeds (status 200), else ``None``.
    """
    url = (
        f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR"
        f"&horizon={horizon}&apikey={api_key}"
    )
    try:
        resp = requests.get(url, timeout=30)
    except Exception as e:
        print(f"Error fetching earnings calendar: {e}", file=sys.stderr)
        return None
    if resp.status_code != 200:
        print(
            f"Error: Received HTTP {resp.status_code} from Alpha Vantage",
            file=sys.stderr,
        )
        return None
    return resp.text


def main() -> int:
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if not api_key:
        print("ALPHAVANTAGE_API_KEY is not set", file=sys.stderr)
        return 1
    horizon = os.getenv("EARNINGS_HORIZON", "3month").strip().lower()
    if horizon not in {"3month", "6month", "12month"}:
        print(
            f"EARNINGS_HORIZON must be one of 3month/6month/12month (got {horizon})",
            file=sys.stderr,
        )
        return 1
    csv_text = _fetch_earnings_csv(api_key, horizon=horizon)
    if csv_text is None:
        return 1
    cache_path = _get_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Security: csv_text contains only public earnings calendar data from Alpha Vantage API response.
        # The API key is in the request URL (line 58) but NOT in the response body.
        # This is a false positive from CodeQL - the CSV response doesn't contain sensitive information.
        cache_path.write_text(csv_text, encoding="utf-8")
    except Exception as e:
        print(f"Error writing earnings calendar cache: {e}", file=sys.stderr)
        return 1
    # Optionally print summary: number of lines (excluding header)
    num_rows = max(0, csv_text.count("\n") - 1)
    print(f"Earnings calendar saved to {cache_path} ({num_rows} rows)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
