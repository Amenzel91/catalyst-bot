# Quick Start: Discord Slash Commands

## Setup (5 minutes)

### 1. Add Application ID to .env

Open `.env` and find this section:
```ini
# --- WAVE 7.1: Discord Slash Commands & Embeds ---
DISCORD_APPLICATION_ID=
```

Add your Discord Application ID:
```ini
DISCORD_APPLICATION_ID=1398521447726583808
```

**Where to get it:**
1. Go to https://discord.com/developers/applications
2. Click your bot application
3. Copy the "Application ID" from General Information

### 2. Register Commands

**For instant testing (recommended):**
```bash
python register_commands.py --guild 1397051728494333962
```

**For all servers (takes ~1 hour):**
```bash
python register_commands.py --global
```

### 3. Test Commands

In Discord, type `/` and you should see:
- `/chart` - Generate price charts
- `/watchlist` - Manage your watchlist
- `/stats` - Bot statistics
- `/backtest` - Historical backtests
- `/sentiment` - Sentiment analysis
- `/help` - Command help

## Command Examples

### Generate a Chart
```
/chart ticker:AAPL
/chart ticker:TSLA timeframe:1M
```

### Manage Watchlist
```
/watchlist action:add ticker:AAPL
/watchlist action:list
/watchlist action:remove ticker:AAPL
/watchlist action:clear
```

### View Statistics
```
/stats
/stats period:30d
```

### Run Backtest
```
/backtest ticker:AAPL
/backtest ticker:TSLA days:60
```

### Check Sentiment
```
/sentiment ticker:AAPL
```

### Get Help
```
/help
```

## Troubleshooting

**Commands not showing?**
1. Make sure `DISCORD_APPLICATION_ID` is set in `.env`
2. Re-run: `python register_commands.py --guild 1397051728494333962`
3. Restart Discord (Ctrl+R)

**Commands failing?**
1. Check interaction server is running: `python interaction_server.py`
2. Verify `.env` has `FEATURE_SLASH_COMMANDS=1`

**Rate limit errors?**
- Wait 3 seconds between commands (configurable)

## What's Next?

See `SLASH_COMMANDS_README.md` for:
- Detailed command documentation
- Architecture overview
- Advanced configuration
- Production deployment guide
