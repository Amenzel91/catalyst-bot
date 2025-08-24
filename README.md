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

4. Copy the `.env.example` file to `.env` and fill in your secrets (Discord
   webhook, Alpha Vantage API key, optional Finviz credentials, etc.).

5. (Optional) Export your Finviz universe and Alpha Vantage listing status
   CSVs into the ``data`` directory. The bot will function without
   these files but may alert on a broader universe.

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
``data/logs``. See ``.env.example`` for configuration details.