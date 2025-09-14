# Catalyst Bot

The catalyst bot is a live news monitoring tool that surfaces
potential trading catalysts for low‑priced U.S. equities. It ingests
press releases and news articles from official PR wire services via
RSS, scores them based on sentiment and catalyst keywords, and sends
alerts to Discord with a dark‑themed candlestick chart overlayed with
VWAP. An end‑of‑day (or pre‑market) analyzer processes the prior
session's events to simulate trades and adapt keyword weights over time.

## Setup

1. **Clone the repository** (or download it as a ZIP) and navigate into it.
2. Create a virtual environment (Python 3.11+ recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the `env.example.ini` file to `.env` and fill in your secrets.  At a
   minimum you must provide a Discord webhook URL (`DISCORD_WEBHOOK_URL`) and
   an Alpha Vantage API key (`ALPHAVANTAGE_API_KEY`) to obtain price
   snapshots.  See the **Configuration** section below for details on all
   available environment variables and feature flags.

5. (Optional) Export your Finviz universe and Alpha Vantage listing status
   CSVs into the ``data`` directory.  The bot will function without these
   files but may alert on a broader universe.

6. Initialise the bot’s databases.  On a fresh clone you should run the
   database bootstrap script once to create all required SQLite files and
   switch them to WAL mode:

   ```bash
   python -m catalyst_bot.jobs.db_init
   ```

7. (Optional) Pull the latest earnings calendar from Alpha Vantage.  To
   populate the earnings annotations used by the analyzer, run:

   ```bash
   python -m catalyst_bot.jobs.earnings_pull
   ```

   The results will be stored in the file specified by
   ``EARNINGS_CALENDAR_CACHE`` (default ``data/earnings_calendar.csv``).

## Running the Live Bot

To execute a single cycle of the bot (ingest, score, and alert):

```bash
python -m catalyst_bot.runner --once
```

To run continuously with a delay between cycles (as defined by
``LOOP_SECONDS``):

```bash
python -m catalyst_bot.runner --loop
```

## Running the Analyzer

After market close or before the open, run the analyzer to evaluate
the prior session's alerts and update keyword weights:

```bash
python -m catalyst_bot.analyzer --date 2025-08-21
```

Omitting the ``--date`` flag will analyze the last 24 hours of
ingested news instead of a specific date.

## Testing

Unit tests are provided under the ``tests`` directory and can be run
with ``pytest``. Ensure that the ``src`` directory is on your
``PYTHONPATH`` (handled automatically in ``tests/__init__.py``).

```bash
pip install pytest  # if not already installed
pytest
```

## Data

The bot persists raw and processed data under the ``data`` directory
and generated charts under ``out/charts``. These directories are
created automatically at runtime. Logs can be found under
``data/logs``. See the **Configuration** section below for details on
environment variables and feature flags.

## Configuration

Catalyst Bot’s behaviour is controlled via environment variables.  Copy
``env.example.ini`` to ``.env`` and customise the following sections to
enable or disable features:

- **Discord webhooks:** Set `DISCORD_WEBHOOK_URL` to the webhook for your
  alerts channel.  Optionally set `DISCORD_ADMIN_WEBHOOK` for
  heartbeats and analyzer summaries.
- **Alpha Vantage:** Provide `ALPHAVANTAGE_API_KEY` for price snapshots and
  earnings calendar pulls.  You can override the earnings cache
  location via `EARNINGS_CALENDAR_CACHE`.
- **Finviz:** Set either `FINVIZ_AUTH_TOKEN` or `FINVIZ_ELITE_AUTH` with
  your Finviz token.  The bot will fall back to `FINVIZ_ELITE_AUTH` when
  `FINVIZ_AUTH_TOKEN` is unset.  To ingest Finviz’s CSV export feed,
  specify a URL in `FINVIZ_NEWS_EXPORT_URL` and enable
  `FEATURE_FINVIZ_NEWS_EXPORT=1`.
- **Real‑time quote providers:** To prefer Tiingo quotes, set
  `FEATURE_TIINGO=1` and provide `TIINGO_API_KEY`.  Adjust
  `MARKET_PROVIDER_ORDER` (default ``tiingo,av,yf``) to change the
  provider priority or omit providers entirely (e.g. ``av,yf`` to skip
  Tiingo).
- **Sentiment and feeds:** Enable FMP sentiment parsing with
  `FEATURE_FMP_SENTIMENT=1` (optional `FMP_API_KEY` if you have one).
  Finviz news ingestion is controlled by `FEATURE_FINVIZ_NEWS` and
  parameters like `FINVIZ_NEWS_KIND`, `FINVIZ_NEWS_TICKERS` and
  `FINVIZ_NEWS_INCLUDE_BLOGS`.
- **Watchlist:** Turn on `FEATURE_WATCHLIST=1` and specify a CSV via
  `WATCHLIST_CSV` to bypass price filtering for your favourite tickers.
- **Charts & indicators:** Set `FEATURE_RICH_ALERTS=1` to attach a
  candlestick chart to each alert.  Enable `FEATURE_INDICATORS=1` to
  include VWAP and RSI values in alert embeds.
- **Alpaca streaming:** To receive short‑term price updates after an
  alert, enable `FEATURE_ALPACA_STREAM=1` and supply `ALPACA_API_KEY`,
  `ALPACA_SECRET` and `STREAM_SAMPLE_WINDOW_SEC` (e.g. ``10`` for
  ten seconds).
- **Admin & approvals:** Set `FEATURE_ADMIN_EMBED=1` to post analyzer
  summaries as rich embeds to your admin channel.  Enable
  `FEATURE_APPROVAL_LOOP=1` to require manual approval of keyword
  weight adjustments; specify the directory for approval markers via
  `APPROVAL_DIR`.
- **Logging:** Choose a `LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR) and set
  `LOG_PLAIN=1` for human‑readable console logs.  By default the console
  outputs JSON lines and a structured log is always written to
  ``data/logs/bot.jsonl``.

Refer to ``env.example.ini`` for a full list of supported variables and
their default values.