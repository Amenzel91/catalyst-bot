# WAVE BETA 3: Slash Commands - Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Setup Environment

Add to your `.env` file:
```bash
# Required
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_APPLICATION_ID=your_application_id_here

# Optional (for testing)
DISCORD_GUILD_ID=your_test_server_id_here

# Feature flags
FEATURE_QUICKCHART=1           # Enable chart generation
FEATURE_ML_SENTIMENT=1         # Enable ML sentiment
WATCHLIST_MAX_SIZE=50          # Max watchlist size
SLASH_COMMAND_COOLDOWN=3       # Cooldown in seconds
```

### 2. Register Commands

```bash
# For testing (instant, guild-specific)
python register_commands.py --guild YOUR_GUILD_ID

# For production (takes up to 1 hour, available in all servers)
python register_commands.py --global
```

### 3. Test Commands

```bash
# Run local tests
python test_commands.py

# Then test in Discord:
/chart ticker:AAPL timeframe:5D
/watchlist action:add ticker:TSLA
/sentiment ticker:NVDA
/stats period:7d
```

---

## 📋 Available Commands

### /chart - Generate Price Charts
```
/chart ticker:AAPL timeframe:5D
```
**Timeframes:** 1D, 5D, 1M, 3M, 1Y
**Features:** Price, change %, volume, VWAP, RSI

### /watchlist - Manage Personal Watchlist
```
/watchlist action:add ticker:TSLA
/watchlist action:remove ticker:TSLA
/watchlist action:list
/watchlist action:clear
```
**Max:** 50 tickers per user
**Storage:** `data/watchlists/{user_id}.json`

### /sentiment - Ticker Sentiment Analysis
```
/sentiment ticker:NVDA
```
**Sources:** VADER, FinBERT, Earnings, Mistral LLM
**Output:** Score (-1 to +1), classification, recent news

### /stats - Bot Performance Statistics
```
/stats period:7d
```
**Periods:** 1d, 7d, 30d, all
**Metrics:** Total alerts, unique tickers, avg score, win rate

### /backtest - Historical Alert Backtesting
```
/backtest ticker:AAPL days:30
```
**Output:** Win rate, avg return, best/worst trades

### /help - Show Command Help
```
/help
```

---

## 🛠️ Troubleshooting

### Commands Not Showing in Discord?
```bash
# 1. Check your application ID
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('DISCORD_APPLICATION_ID'))"

# 2. Verify commands are registered
python register_commands.py --list

# 3. Use guild commands for instant testing
python register_commands.py --guild YOUR_GUILD_ID
```

### Chart Command Returns "Feature Disabled"?
```bash
# Enable QuickChart in .env
FEATURE_QUICKCHART=1
```

### Sentiment Command Returns "No Data"?
- Ensure `data/events.jsonl` exists with ticker data
- Check ML models are loaded
- Verify Ollama is running (for LLM sentiment)

### Watchlist Not Persisting?
```bash
# Create directory if missing
mkdir -p data/watchlists

# Check permissions
ls -la data/watchlists/
```

---

## 📁 File Structure

```
catalyst-bot/
├── src/catalyst_bot/
│   ├── slash_commands.py              # Main routing
│   ├── commands/
│   │   ├── handlers.py                # Command implementations
│   │   ├── embeds.py                  # Discord embed builders
│   │   ├── errors.py                  # Error response templates
│   │   └── command_registry.py        # Command definitions
│   ├── user_watchlist.py              # Watchlist storage
│   ├── chart_parallel.py              # Parallel chart generation
│   ├── charts.py                      # QuickChart integration
│   └── classify.py                    # Sentiment analysis
├── register_commands.py               # Discord API registration
├── test_commands.py                   # Test suite
└── data/
    ├── watchlists/{user_id}.json      # Per-user watchlists
    └── events.jsonl                   # Event log
```

---

## 🔧 Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | (required) | Discord bot authentication token |
| `DISCORD_APPLICATION_ID` | (required) | Discord application ID |
| `DISCORD_GUILD_ID` | (optional) | Test server ID for instant commands |
| `FEATURE_QUICKCHART` | 0 | Enable chart generation |
| `QUICKCHART_BASE_URL` | https://quickchart.io | QuickChart server URL |
| `WATCHLIST_MAX_SIZE` | 50 | Max tickers per user |
| `SLASH_COMMAND_COOLDOWN` | 3 | Rate limit (seconds) |
| `FEATURE_ML_SENTIMENT` | 1 | Enable FinBERT sentiment |
| `SENTIMENT_WEIGHT_VADER` | 0.25 | VADER sentiment weight |
| `SENTIMENT_WEIGHT_ML` | 0.25 | FinBERT sentiment weight |
| `SENTIMENT_WEIGHT_EARNINGS` | 0.35 | Earnings sentiment weight |
| `SENTIMENT_WEIGHT_LLM` | 0.15 | LLM sentiment weight |

---

## 🧪 Testing

### Run All Tests
```bash
python test_commands.py
```

### Test Specific Commands
```python
# In Python REPL
from catalyst_bot.commands.handlers import *

# Test chart
result = handle_chart_command("AAPL", "5D", "test_user_123")
print(result)

# Test watchlist
result = handle_watchlist_command("add", "TSLA", "test_user_123")
print(result)
```

### Expected Test Output
```
============================================================
=============== SLASH COMMAND TESTS ========================
============================================================

Testing /chart command
SUCCESS: Chart command works!

Testing /watchlist commands
SUCCESS: Watchlist commands work!

Testing /stats command
SUCCESS: Stats command works!

Testing /backtest command
SUCCESS: Backtest command works!

Testing /sentiment command
SUCCESS: Sentiment command works!

Testing /help command
SUCCESS: Help command works!

============================================================
All tests passed!
============================================================
```

---

## 📚 Additional Resources

- **Full Implementation Report:** `WAVE_BETA_3_IMPLEMENTATION_REPORT.md`
- **Admin Commands:** `ADMIN_COMMANDS_QUICK_REF.md`
- **Setup Guide:** `COMMANDS_SETUP_GUIDE.md`
- **Technical Docs:** `SLASH_COMMANDS_README.md`

---

## 🎯 Production Deployment

### Pre-Deployment Checklist
- [ ] Discord bot credentials configured
- [ ] Commands registered (guild or global)
- [ ] All tests passing
- [ ] Feature flags enabled
- [ ] Data directories created
- [ ] Logs monitored

### Deployment Steps
```bash
# 1. Test locally
python test_commands.py

# 2. Register to test server
python register_commands.py --guild YOUR_GUILD_ID

# 3. Test in Discord

# 4. Register globally
python register_commands.py --global

# 5. Monitor logs
tail -f data/logs/bot.jsonl
```

### Post-Deployment
- Test each command in Discord
- Verify embeds render on mobile
- Check rate limiting
- Monitor error rates
- Verify watchlist persistence

---

## 💡 Tips

### Rate Limiting
- Each user has a 3-second cooldown per command
- Prevents spam and server overload
- Configurable via `SLASH_COMMAND_COOLDOWN`

### Mobile Optimization
- All embeds tested on mobile
- Concise field names
- Inline fields for compact layout
- No excessive line breaks

### Error Handling
- User-friendly error messages
- No stack traces exposed
- Ephemeral errors (only visible to user)
- Detailed server-side logging

---

## 🚨 Common Errors

### "Invalid ticker symbol"
- Ticker must be uppercase, alphanumeric, max 6 chars
- Example: AAPL ✅, aapl ❌, APPLE ❌

### "Watchlist is full"
- Max 50 tickers per user (configurable)
- Use `/watchlist action:clear` to reset

### "No sentiment data available"
- Ticker needs data in `events.jsonl`
- Check if ticker is recently listed
- Verify ML models are loaded

### "Please wait X seconds"
- Rate limit active
- Wait the specified time
- Prevents command spam

---

**Quick Start Version:** 1.0
**Last Updated:** 2025-10-06
**Status:** ✅ Production Ready
