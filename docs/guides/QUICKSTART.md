# Quick Start Guide - Interactive Admin Controls

## TL;DR - Get Running in 5 Minutes

### 1. Install Cloudflared (one time)
```bash
# Download from: https://github.com/cloudflare/cloudflared/releases/latest
# Or use Chocolatey:
choco install cloudflared
```

### 2. Start Everything
```bash
# Option A: Use the startup script (easiest)
start_with_interactions.bat

# Option B: Manual (3 terminals)
# Terminal 1: Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8081

# Terminal 2: Interaction Server
.venv\Scripts\python interaction_server.py

# Terminal 3: Bot
.venv\Scripts\python -m catalyst_bot.runner
```

### 3. Configure Discord
1. Copy the `trycloudflare.com` URL from Terminal 1
2. Go to https://discord.com/developers/applications
3. Select your app → General Information
4. Set Interactions Endpoint URL: `https://YOUR-URL.trycloudflare.com/interactions`
5. Save

### 4. Test It
```bash
# Generate a test report
python test_admin_report.py

# Or wait for nightly report (21:30 UTC)
```

### 5. Click Buttons!
- 📊 **View Details** - See full breakdown
- ✅ **Approve Changes** - Apply recommendations
- ❌ **Reject Changes** - Keep current settings
- ⚙️ **Custom Adjust** - Manual parameter tuning

---

## What Gets Adjusted?

The system automatically recommends changes to:
- Sentiment thresholds (MIN_SCORE, MIN_SENT_ABS)
- Price filters (PRICE_CEILING, PRICE_FLOOR)
- Confidence tiers (CONFIDENCE_HIGH, CONFIDENCE_MODERATE)
- Alert rate limits (MAX_ALERTS_PER_CYCLE)
- Keyword category weights
- And more...

All based on actual backtest performance!

---

## Daily Workflow

1. **21:30 UTC** - Admin report posted to Discord
2. **Review** - Click "View Details" to see metrics
3. **Decide** - Approve/Reject/Custom adjust
4. **Monitor** - Check next day's performance

---

## Troubleshooting

**Buttons don't work?**
- Check all 3 components are running (cloudflared, server, bot)
- Verify Discord endpoint URL is correct
- Check logs: `data/logs/bot.jsonl`

**No report posted?**
- Check `FEATURE_ADMIN_REPORTS=1` in env.env
- Check `DISCORD_ADMIN_WEBHOOK` is set
- Run `python test_admin_report.py` to test manually

**Tunnel URL changed?**
- This is normal for Quick Tunnel
- Update Discord endpoint URL
- Or use Named Tunnel for permanent URL

---

## Files You Created

```
catalyst-bot/
├── interaction_server.py          ← Discord button handler server
├── test_admin_report.py          ← Manual report generator
├── start_with_interactions.bat   ← Startup script
├── CLOUDFLARE_TUNNEL_SETUP.md    ← Detailed tunnel guide
├── ADMIN_CONTROLS_GUIDE.md       ← Full documentation
└── env.env                       ← FEATURE_ADMIN_REPORTS=1
```

---

## What's Running?

1. **Cloudflare Tunnel** - Exposes localhost to internet
2. **Interaction Server** - Receives Discord button clicks
3. **Catalyst Bot** - Main bot + nightly reports

All 3 must be running for buttons to work!

---

## Cost: $0.00/month Forever ✨

No credit card. No trials. No surprises.

---

## Need More Help?

- **Full Setup**: See `CLOUDFLARE_TUNNEL_SETUP.md`
- **Features**: See `ADMIN_CONTROLS_GUIDE.md`
- **Logs**: Check `data/logs/bot.jsonl`
- **Issues**: https://github.com/your-repo/issues
