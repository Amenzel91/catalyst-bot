# Catalyst Bot

Catalyst Bot is a Python 3.11+ live news monitoring tool that surfaces potential trading catalysts for low‑priced U.S. equities. It ingests press releases and news articles from RSS feeds, scores them using sentiment analysis and catalyst keywords, and sends alerts to Discord with charts.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

Bootstrap, build, and test the repository:

- **Set up Python environment** (Python 3.11+ required, 3.12+ recommended):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
  ```

- **Install dependencies** -- takes 2-5 minutes due to compilation. NEVER CANCEL. Set timeout to 10+ minutes:
  ```bash
  pip install -r requirements.txt
  ```
  **If pip installation fails due to network timeouts**, install in batches with retries:
  ```bash
  pip install --retries 5 --timeout 300 --no-cache-dir requests python-dotenv
  pip install --retries 5 --timeout 300 --no-cache-dir pandas numpy
  pip install --retries 5 --timeout 300 --no-cache-dir feedparser beautifulsoup4 lxml
  pip install --retries 5 --timeout 300 --no-cache-dir vaderSentiment tqdm python-dateutil tzdata tenacity yfinance
  ```

- **Install development tools**:
  ```bash
  pip install pytest pre-commit black flake8 isort autoflake
  ```

- **Set up environment configuration**:
  ```bash
  cp env.example.ini .env
  # Edit .env to add required API keys (DISCORD_WEBHOOK_URL and ALPHAVANTAGE_API_KEY minimum)
  ```

- **Initialize databases** (creates SQLite files and sets WAL mode):
  ```bash
  python -m catalyst_bot.jobs.db_init
  ```

- **Run tests** -- takes 3-5 minutes. NEVER CANCEL. Set timeout to 10+ minutes:
  ```bash
  PYTHONPATH=src pytest
  ```

## Running the Application

- **Live bot single cycle** (ingest, score, alert once):
  ```bash
  PYTHONPATH=src python -m catalyst_bot.runner --once
  ```

- **Live bot continuous loop** (runs until stopped):
  ```bash
  PYTHONPATH=src python -m catalyst_bot.runner --loop
  ```

- **Run analyzer** (post-market analysis):
  ```bash
  PYTHONPATH=src python -m catalyst_bot.analyzer --date 2025-01-15
  # Or omit --date to analyze last 24 hours
  ```

- **Pull earnings calendar** (optional):
  ```bash
  PYTHONPATH=src python -m catalyst_bot.jobs.earnings_pull
  ```

## Code Quality and Validation

- **Format code with black**:
  ```bash
  black src/ tests/
  ```

- **Run linting** (uses project's 100-char line limit):
  ```bash
  flake8 --config=.flake8.ini src/ tests/
  ```

- **Run isort** (import sorting):
  ```bash
  isort --profile black src/ tests/
  ```

- **Install and run pre-commit hooks** -- takes 5-10 minutes on first run. NEVER CANCEL. Set timeout to 15+ minutes:
  ```bash
  pre-commit install
  pre-commit run --all-files
  ```

## CRITICAL Build and Test Timing

- **NEVER CANCEL** any build, test, or pre-commit operations
- **pip install -r requirements.txt**: 2-5 minutes (set timeout to 10+ minutes)
- **pytest**: 3-5 minutes (set timeout to 10+ minutes)  
- **pre-commit run --all-files**: 5-10 minutes first run (set timeout to 15+ minutes)
- **Database initialization**: <30 seconds
- **Flake8 linting**: <30 seconds

## Validation Scenarios

After making changes, ALWAYS test these scenarios to ensure functionality:

1. **Database initialization test**:
   ```bash
   rm -rf data/*.db data/dedup/ 2>/dev/null || true
   PYTHONPATH=src python -m catalyst_bot.jobs.db_init
   ls -la data/  # Should show seen_ids.sqlite and other DB files
   ```

2. **Configuration validation**:
   ```bash
   export FEATURE_RECORD_ONLY=1
   export FEATURE_ALERTS=0
   export LOG_LEVEL=INFO
   PYTHONPATH=src python -c "from catalyst_bot.config import get_settings; print('Config loaded:', get_settings().feature_record_only)"
   ```

3. **Runner dry-run test** (safe, no external API calls):
   ```bash
   export FEATURE_RECORD_ONLY=1
   export FEATURE_ALERTS=0
   export PRICE_CEILING=10
   # This will show dependency check message if missing packages, which is expected
   PYTHONPATH=src python -m catalyst_bot.runner --once
   ```

## Directory Structure and Key Files

- **src/catalyst_bot/**: Main application code
  - `runner.py`: Live bot main module
  - `analyzer.py`: Post-market analysis
  - `feeds.py`: RSS feed ingestion
  - `market.py`: Price data and chart generation
  - `alerts.py`: Discord notification system
  - `jobs/db_init.py`: Database setup script

- **tests/**: Unit tests (pytest)
- **data/**: Runtime data directory (created automatically)
  - `seen_ids.sqlite`: Deduplication database
  - `logs/bot.jsonl`: Application logs
  - `earnings_calendar.csv`: Earnings data cache

- **Configuration files**:
  - `.env`: Environment variables (copy from env.example.ini)
  - `.flake8.ini`: Linting configuration (100-char lines)
  - `.pre-commit-config.yaml`: Code quality hooks
  - `pyproject.toml`: Project metadata and build config

## Important Environment Variables

Required for operation:
- `DISCORD_WEBHOOK_URL`: Discord webhook for alerts (required)
- `ALPHAVANTAGE_API_KEY`: Price data API key (required)

Safe testing mode:
- `FEATURE_RECORD_ONLY=1`: Disable actual alerts, only log
- `FEATURE_ALERTS=0`: Disable alert sending entirely
- `PRICE_CEILING=10`: Only process stocks under $10

## Common Issues

- **Missing dependencies error**: Run `pip install -r requirements.txt` in activated venv
- **Module not found**: Always use `PYTHONPATH=src` when running modules
- **Database not found**: Run `python -m catalyst_bot.jobs.db_init` first
- **Network timeouts during pip install**: Use batch installation commands shown above
- **Pre-commit fails**: May be due to network issues, retry or install tools individually

## CI/CD Integration

The GitHub Actions workflow (.github/workflows/ci.yml):
- Uses Python 3.12
- Installs dependencies and development tools
- Runs pre-commit hooks (black, isort, autoflake, flake8)
- Executes test suite with safety environment variables

Always run `pre-commit run --all-files` and `pytest` before committing to ensure CI passes.

## Architecture Notes

- **SQLite databases**: WAL mode for better concurrency
- **RSS feeds**: Handles multiple news sources via feedparser
- **Sentiment analysis**: VADER + external API fallbacks
- **Chart generation**: Matplotlib + QuickChart + Finviz integration
- **Rate limiting**: Built-in Discord webhook rate limiting
- **Deduplication**: Persistent seen-item tracking across restarts