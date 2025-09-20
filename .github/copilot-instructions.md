# Catalyst Bot Development Instructions

**ALWAYS follow these instructions first and only fall back to additional search or bash commands when the information here is incomplete or found to be in error.**

Catalyst Bot is a live news monitoring tool that surfaces potential trading catalysts for low-priced U.S. equities. It ingests press releases and news articles from RSS feeds, scores them based on sentiment and catalyst keywords, and sends alerts to Discord with charts.

## Working Effectively

### Initial Setup (NEVER CANCEL - Allow 15+ minutes for full setup)
```bash
# 1. Create virtual environment (Python 3.11+ required)
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows

# 2. Install dependencies - NEVER CANCEL: takes 5-10 minutes due to large dependencies
# Set timeout to 20+ minutes to avoid premature cancellation
# NOTE: Network issues may cause timeouts. If pip install fails with ReadTimeoutError:
pip install --timeout 300 --retries 5 -r requirements.txt

# If full install fails, try installing core dependencies first:
# pip install requests python-dotenv pandas numpy feedparser beautifulsoup4 pytest

# 3. Copy environment configuration
cp env.example.ini .env

# 4. Initialize databases (required for first run) - takes ~0.1 seconds
python -m catalyst_bot.jobs.db_init

# 5. (Optional) Pull earnings calendar data
python -m catalyst_bot.jobs.earnings_pull
```

### Build and Development Commands

**CRITICAL: Use long timeouts for all operations. NEVER CANCEL builds or tests.**

```bash
# Install pre-commit hooks - takes 2-3 minutes first time
# NEVER CANCEL: timeout should be 10+ minutes
pre-commit install

# Run code quality checks - takes 3-5 minutes
# NEVER CANCEL: timeout should be 15+ minutes  
pre-commit run --all-files

# Run tests - takes 2-3 minutes
# NEVER CANCEL: timeout should be 10+ minutes
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_runner.py -v
```

### Running the Application

```bash
# Run single cycle (ingest, score, alert) - takes 30-60 seconds
python -m catalyst_bot.runner --once

# Run continuously with default loop interval
python -m catalyst_bot.runner --loop

# Alternative main.py entry point
python main.py run --once
python main.py run --loop

# Run analyzer (after market close/before open) - takes 1-2 minutes
python -m catalyst_bot.analyzer --date 2025-08-21
python main.py analyze --date 2025-08-21

# Utility script for single run then stop
python tools/run_once.py
```

### PowerShell Development Helpers (Windows)
```powershell
# Source development helpers
. .\scripts\dev.ps1

# Set staging environment
Set-CatalystEnv -Dotenv ".env.staging"

# Run once with custom parameters
Start-CatalystOnce -MinScore "1.0" -MinSentAbs "0.1"

# Test Discord webhook
Test-DiscordWebhook -Message "Test alert"

# Show current environment
Show-CatalystEnv
```

## Configuration Requirements

**CRITICAL: The bot requires external API keys to function. Copy `env.example.ini` to `.env` and configure:**

- **DISCORD_WEBHOOK_URL**: Required for alerts
- **ALPHAVANTAGE_API_KEY**: Required for price snapshots
- **FINVIZ_AUTH_TOKEN**: Optional but recommended for enhanced news feeds

**The application WILL FAIL without at minimum Discord webhook URL and Alpha Vantage API key.**

## Validation Scenarios

**ALWAYS validate changes with these end-to-end scenarios:**

### Basic Functionality Test
```bash
# 1. Set up test environment
export FEATURE_RECORD_ONLY=1  # Prevents actual Discord alerts
export FEATURE_ALERTS=0       # Disables alert posting
export PRICE_CEILING=10       # Limits to stocks under $10

# 2. Run single cycle and verify no errors
python -m catalyst_bot.runner --once

# 3. Check logs for successful completion (look for "CYCLE_DONE")
tail -n 20 data/logs/bot.jsonl
```

### Database Functionality Test
```bash
# Test database initialization
python -m catalyst_bot.jobs.db_init

# Verify databases exist
ls -la data/*.db

# Test database connectivity
python -c "from catalyst_bot.market_db import connect; print('DB connection OK')"
```

### Module Import Test
```bash
# Test core module imports
python -c "
import sys
sys.path.insert(0, 'src')
from catalyst_bot import runner, analyzer, alerts
print('All core modules import successfully')
"
```

## Repository Structure and Key Areas

### Core Source Code (`src/catalyst_bot/`)
- **`runner.py`**: Main application entry point and cycle logic
- **`analyzer.py`**: End-of-day analysis and keyword weight updates
- **`alerts.py`**: Discord webhook posting and alert formatting
- **`feeds.py`**: RSS feed ingestion and parsing
- **`classify.py`**: Event classification and scoring
- **`market_db.py`**: Database connection and schema management

### Important Directories
- **`tests/`**: Unit tests with dependency stubs for external packages
- **`data/`**: SQLite databases, logs, and cached data (auto-created)
- **`scripts/`**: PowerShell and development utilities
- **`tools/`**: Python utility scripts
- **`.github/workflows/`**: CI/CD configuration

### Configuration Files
- **`env.example.ini`**: Template for environment variables
- **`.pre-commit-config.yaml`**: Code quality tool configuration
- **`requirements.txt`**: Python dependencies
- **`pyproject.toml`**: Build system configuration

## Common Issues and Troubleshooting

### Dependency Installation Failures
```bash
# If pip install fails due to network timeouts (ReadTimeoutError):
pip install --timeout 300 --retries 5 -r requirements.txt

# Install core dependencies first if full install fails:
pip install requests python-dotenv pandas numpy feedparser beautifulsoup4 pytest pre-commit

# For development without external dependencies, the test suite includes stubs:
PYTHONPATH=src pytest  # Uses test stubs for missing packages
```

### Missing API Keys or Dependencies
```bash
# The runner will show helpful error messages for missing dependencies:
python -m catalyst_bot.runner --once
# Example output: "[Startup dependency check] Missing Python package: feedparser"
# Fix: pip install feedparser

# For missing API keys, check the .env file:
cat .env
# Ensure DISCORD_WEBHOOK_URL and ALPHAVANTAGE_API_KEY are set
```

### Database Issues
```bash
# Re-initialize databases if corrupted (databases created in ~0.1 seconds):
rm -f data/*.db data/*.sqlite
python -m catalyst_bot.jobs.db_init

# Verify databases exist:
ls -la data/*.db data/*.sqlite
# Expected files: market.db, seen_ids.sqlite, tickers.db
```

## CI/CD and Code Quality

**The CI pipeline runs:**
1. **pre-commit checks** (formatting, linting) - 3-5 minutes
2. **pytest** test suite - 2-3 minutes

**ALWAYS run these before committing:**
```bash
# Format and lint code
pre-commit run --all-files

# Run tests  
pytest

# Both must pass for CI to succeed
```

## Performance and Timing Expectations

- **Initial setup**: 10-15 minutes (including dependency installation)
- **Single bot cycle**: 30-60 seconds
- **Test suite**: 2-3 minutes
- **Pre-commit checks**: 3-5 minutes
- **Analyzer run**: 1-2 minutes

**NEVER CANCEL any of these operations. Set timeouts to at least double the expected time.**

## External Dependencies and Limitations

- **Internet required**: For RSS feeds, price data, Discord webhooks
- **External APIs**: Alpha Vantage (required), Finviz Elite (optional), Discord (required)
- **Market hours awareness**: Best results during U.S. market hours
- **Rate limiting**: Built-in Discord webhook rate limiting and retry logic
- **Network timeouts**: Dependency installation may fail in environments with limited network access
  - The test suite includes stubs for external packages to allow development without all dependencies
  - Core functionality can be tested with minimal dependencies installed

### Offline Development Mode
For development when external dependencies are unavailable:
```bash
# Set environment to disable external calls
export FEATURE_RECORD_ONLY=1     # Disable Discord posting
export FEATURE_ALERTS=0          # Disable alerts entirely

# Use test environment with stubs
PYTHONPATH=src pytest tests/     # Runs with dependency stubs
```

## Development Best Practices

- **Always test with `FEATURE_RECORD_ONLY=1`** to prevent accidental live alerts
- **Use staging environment**: Copy `env.example.ini` to `.env.staging` for testing
- **Check logs**: Application logs to `data/logs/bot.jsonl` in structured JSON format
- **Validate externally**: Test Discord webhooks with `Test-DiscordWebhook` PowerShell function
- **Monitor resources**: Bot can run continuously with `--loop` but monitor memory usage

## Common File Outputs

When the bot runs successfully, you'll see:
```
data/
├── market.db           # SQLite database
├── logs/bot.jsonl      # Structured application logs  
├── events.jsonl        # Raw event data
└── analyzer/           # Analysis outputs and summaries
```

The application will create these directories automatically on first run.