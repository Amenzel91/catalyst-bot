# Simulation Environment - Quick Reference

## Quick Start

```bash
# Default: Nov 12 2024, morning preset (8:45-9:45 EST), 6x speed
# Takes ~10 minutes real time
python -m catalyst_bot.simulation.cli

# Test SEC filing period
python -m catalyst_bot.simulation.cli --preset sec

# Full day at instant speed
python -m catalyst_bot.simulation.cli --preset full --speed 0
```

---

## Time Presets

| Preset | Time (EST) | Use Case |
|--------|------------|----------|
| `morning` | 8:45-9:45 | News rush, high activity (default) |
| `sec` | 3:30-4:30 | SEC filing window |
| `open` | 9:30-10:30 | Market open hour |
| `close` | 3:00-4:00 | Market close hour |
| `full` | 4:00am-5:00pm | Full trading day |

---

## .env Configuration

```ini
# ============================================================================
# SIMULATION MODE - Master Controls
# ============================================================================

# Enable simulation mode (0=live, 1=simulation)
SIMULATION_MODE=0

# Date to simulate (default: Nov 12, 2024)
SIMULATION_DATE=2024-11-12

# Time preset: "morning", "sec", "open", "close", "full"
SIMULATION_PRESET=morning

# Speed: 1.0=realtime, 6.0=6x (default), 0=instant
SIMULATION_SPEED=6.0

# Custom time override (ignored if preset is set)
SIMULATION_START_TIME_CST=
SIMULATION_END_TIME_CST=

# ============================================================================
# COMPONENT BEHAVIOR
# ============================================================================

# LLM (Gemini): 1=LIVE (default), 0=skip
SIMULATION_LLM_ENABLED=1

# Local sentiment (VADER/FinBERT): 1=LIVE (default)
SIMULATION_LOCAL_SENTIMENT=1

# External sentiment APIs: 0=MOCKED (default)
SIMULATION_EXTERNAL_SENTIMENT=0

# Chart generation: 0=DISABLED (default)
SIMULATION_CHARTS_ENABLED=0

# ============================================================================
# DATA SOURCES
# ============================================================================

# Price data: "tiingo", "yfinance", "cached"
SIMULATION_PRICE_SOURCE=tiingo

# News data: "finnhub", "cached"
SIMULATION_NEWS_SOURCE=finnhub

# Skip tickers with incomplete data (recommended)
SIMULATION_SKIP_INCOMPLETE=1

# Cache directory
SIMULATION_CACHE_DIR=data/simulation_cache

# ============================================================================
# OUTPUT CONFIGURATION
# ============================================================================

# Alerts: "discord_test" (default), "local_only", "disabled"
SIMULATION_ALERT_OUTPUT=discord_test

# Simulation database (separate from production)
SIMULATION_DB_PATH=data/simulation.db

# Log directory
SIMULATION_LOG_DIR=data/simulation_logs

# ============================================================================
# MOCK BROKER
# ============================================================================

SIMULATION_STARTING_CASH=10000.0
SIMULATION_SLIPPAGE_MODEL=adaptive
SIMULATION_SLIPPAGE_PCT=0.5
SIMULATION_MAX_VOLUME_PCT=5.0
```

---

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--date` | Simulation date (YYYY-MM-DD) | 2024-11-12 |
| `--preset` | Time preset | morning |
| `--speed` | Speed multiplier (0=instant) | 6.0 |
| `--start-time` | Custom start (HH:MM CST) | from preset |
| `--end-time` | Custom end (HH:MM CST) | from preset |
| `--cash` | Starting cash | 10000 |
| `--alerts` | discord/local/disabled | discord |
| `--dry-run` | Validate config, check APIs, don't run | False |
| `--no-cache` | Force fresh data fetch | False |
| `-v` | Verbose logging | False |

---

## CLI Examples

```bash
# Morning test (default - takes ~10 min)
python -m catalyst_bot.simulation.cli

# SEC filing period
python -m catalyst_bot.simulation.cli --preset sec

# Custom time range
python -m catalyst_bot.simulation.cli --start-time 08:00 --end-time 10:00

# Instant speed, local alerts only
python -m catalyst_bot.simulation.cli --speed 0 --alerts local

# Full day with verbose output
python -m catalyst_bot.simulation.cli --preset full --speed 0 -v

# Validate config without running (dry run)
python -m catalyst_bot.simulation.cli --dry-run

# Force fresh data (ignore cache)
python -m catalyst_bot.simulation.cli --no-cache
```

---

## Switching Between Live and Simulation

### To run in simulation mode:
```bash
# Option 1: Set env var
export SIMULATION_MODE=1
python -m catalyst_bot.runner --loop

# Option 2: Use CLI directly
python -m catalyst_bot.simulation.cli
```

### To run in live mode:
```bash
# Ensure SIMULATION_MODE=0 or unset
unset SIMULATION_MODE
python -m catalyst_bot.runner --loop
```

---

## Output Files

| File | Content |
|------|---------|
| `data/simulation.db` | All simulation trades and events |
| `data/simulation_logs/sim_*.log` | Per-run log files |
| `data/simulation_cache/*.json` | Cached historical data |

---

## Data Isolation

All simulation data is automatically:
1. Stored in separate database (`simulation.db`)
2. Tagged with `simulation_run_id`
3. Marked with `is_simulation=true`
4. Logged to separate log files

**Production data is never modified during simulations.**
