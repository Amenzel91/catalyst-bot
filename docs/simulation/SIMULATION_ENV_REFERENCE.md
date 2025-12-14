# Simulation Environment - Quick Reference

## .env Configuration

Add these to your `.env` file to control simulation mode:

```ini
# ============================================================================
# SIMULATION MODE - Master Controls
# ============================================================================

# Enable simulation mode (0=live trading, 1=simulation)
SIMULATION_MODE=0

# Date to simulate (YYYY-MM-DD) - random recent day if empty
SIMULATION_DATE=

# Speed: 1.0=realtime, 10.0=10x faster, 0=instant
SIMULATION_SPEED=10.0

# ============================================================================
# TIME CONTROL (CST timezone)
# ============================================================================

# Start simulation at this time (HH:MM) - default 04:00 (premarket)
SIMULATION_START_TIME_CST=

# End simulation at this time (HH:MM) - default 17:00 (after hours)
SIMULATION_END_TIME_CST=

# ============================================================================
# DATA SOURCES
# ============================================================================

# Price data: "tiingo", "yfinance", "cached"
SIMULATION_PRICE_SOURCE=tiingo

# News data: "finnhub", "cached"
SIMULATION_NEWS_SOURCE=finnhub

# Cache directory for simulation data
SIMULATION_CACHE_DIR=data/simulation_cache

# ============================================================================
# OUTPUT CONFIGURATION
# ============================================================================

# Where to send alerts: "discord_test", "local_only", "disabled"
SIMULATION_ALERT_OUTPUT=local_only

# Database for simulation data (keeps production clean)
SIMULATION_DB_PATH=data/simulation.db

# Log directory for simulation runs
SIMULATION_LOG_DIR=data/simulation_logs

# ============================================================================
# MOCK BROKER SETTINGS
# ============================================================================

# Starting portfolio cash
SIMULATION_STARTING_CASH=10000.0

# Slippage model: "none", "fixed", "adaptive"
SIMULATION_SLIPPAGE_MODEL=adaptive

# Fixed slippage % (if using fixed model)
SIMULATION_SLIPPAGE_PCT=0.5

# Max % of daily volume per trade
SIMULATION_MAX_VOLUME_PCT=5.0
```

---

## CLI Usage

### Basic Commands

```bash
# Run with defaults (random date, 10x speed)
python -m catalyst_bot.simulation.cli

# Specific date
python -m catalyst_bot.simulation.cli --date 2025-01-15

# Maximum speed (instant)
python -m catalyst_bot.simulation.cli --speed 0

# Stress test morning news rush (8am CST)
python -m catalyst_bot.simulation.cli --date 2025-01-15 --start-time 08:00

# Different starting cash
python -m catalyst_bot.simulation.cli --cash 25000

# Verbose output
python -m catalyst_bot.simulation.cli -v
```

### CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--date` | Simulation date (YYYY-MM-DD) | Random recent day |
| `--speed` | Speed multiplier (0=instant) | 10.0 |
| `--start-time` | Start time in CST (HH:MM) | 04:00 |
| `--end-time` | End time in CST (HH:MM) | 17:00 |
| `--cash` | Starting portfolio cash | 10000 |
| `--alerts` | Alert mode (discord/local/disabled) | local |
| `-v` | Verbose logging | False |

---

## Quick Start

### 1. Test a random recent day
```bash
python -m catalyst_bot.simulation.cli
```

### 2. Test a specific historical day
```bash
python -m catalyst_bot.simulation.cli --date 2025-01-10 --speed 0
```

### 3. Stress test high-traffic period
```bash
python -m catalyst_bot.simulation.cli --date 2025-01-15 --start-time 08:00 --end-time 10:00 --speed 1
```

### 4. Test with production-like settings
```bash
python -m catalyst_bot.simulation.cli --date 2025-01-15 --speed 1 --alerts discord
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
