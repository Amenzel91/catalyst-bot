# Discord Slash Commands - Testing & Usage Guide

**Last Updated:** October 4, 2025
**Status:** ✅ Implemented - Ready for Testing

---

## Overview

The Catalyst-Bot now supports Discord slash commands for admin controls, allowing real-time bot configuration directly from Discord without touching code or config files.

---

## Available Commands

### `/admin report [date]`
Generate and post admin performance report.

**Parameters:**
- `date` (optional): Report date in YYYY-MM-DD format (default: yesterday)

**Example:**
```
/admin report
/admin report date:2025-10-03
```

**Response:**
- Full admin report embed with backtest metrics
- Interactive buttons (View Details, Approve Changes, Reject, Custom)
- Posted to current channel

---

### `/admin set <parameter> <value>`
Update a bot parameter in real-time.

**Parameters:**
- `parameter` (required): Parameter name (e.g., MIN_SCORE, PRICE_CEILING)
- `value` (required): New parameter value

**Examples:**
```
/admin set parameter:MIN_SCORE value:0.3
/admin set parameter:PRICE_CEILING value:7.5
/admin set parameter:MAX_ALERTS_PER_CYCLE value:30
```

**Response:**
- Success embed showing parameter name and new value
- Automatic configuration backup created
- Environment reloaded without bot restart

**Validated Parameters:**
| Parameter | Type | Range | Example |
|-----------|------|-------|---------|
| MIN_SCORE | float | 0-1 | 0.3 |
| MIN_SENT_ABS | float | 0-1 | 0.2 |
| PRICE_CEILING | float | >0 | 10.0 |
| PRICE_FLOOR | float | ≥0 | 0.1 |
| CONFIDENCE_HIGH | float | 0-1 | 0.85 |
| CONFIDENCE_MODERATE | float | 0-1 | 0.6 |
| MAX_ALERTS_PER_CYCLE | int | >0 | 40 |
| ANALYZER_HIT_UP_THRESHOLD_PCT | float | >0 | 7.0 |
| ANALYZER_HIT_DOWN_THRESHOLD_PCT | float | <0 | -5.0 |
| BREAKOUT_MIN_AVG_VOL | int | ≥0 | 500000 |
| BREAKOUT_MIN_RELVOL | float | >0 | 2.0 |

---

### `/admin rollback`
Rollback to previous configuration.

**Parameters:** None

**Example:**
```
/admin rollback
```

**Response:**
- Confirmation embed showing rollback success
- Reverts to most recent backup from `data/config_backups/`
- Environment reloaded with previous values

---

### `/admin stats`
Show current parameter values.

**Parameters:** None

**Example:**
```
/admin stats
```

**Response:**
- Ephemeral embed (only visible to you) with current values
- Organized by category: Sentiment, Price, Alerts, Confidence, Analyzer, Breakout
- Quick reference for current bot configuration

---

## Setup Instructions

### Step 1: Get Required Credentials

1. **Discord Application ID** (if not auto-detected):
   - Go to https://discord.com/developers/applications
   - Select your bot application
   - Copy "Application ID" from General Information
   - Add to `.env`: `DISCORD_APPLICATION_ID=your_app_id`

2. **Discord Guild ID** (for instant command updates):
   - Enable Developer Mode in Discord (Settings > Advanced > Developer Mode)
   - Right-click your server → Copy ID
   - Add to `.env`: `DISCORD_GUILD_ID=your_guild_id`

3. **Verify Bot Token**:
   - Ensure `DISCORD_BOT_TOKEN` is set in `.env`
   - Should start with `MTM5...`

### Step 2: Register Slash Commands

```bash
# Run registration script
python register_slash_commands.py

# Choose option 1 for guild-specific (instant, recommended for testing)
# Choose option 2 for global (takes ~1 hour to propagate)
# Choose option 3 for both
```

**Expected Output:**
```
Discord Slash Command Registration
============================================================
Application ID: 1398521447726583808
Guild ID: 1406830487904718919
============================================================

Options:
  1. Register guild-specific commands (instant, recommended for testing)
  2. Register global commands (takes ~1 hour)
  3. Register both
  4. List registered commands
  5. Exit

Enter choice (1-5): 1

============================================================
Registering GUILD commands for guild 1406830487904718919 (instant)
============================================================

Registering: /admin
  [OK] Successfully registered /admin
  [INFO] Command ID: 1234567890123456789
```

### Step 3: Start Interaction Server

```bash
# Terminal 1: Start interaction server
python interaction_server.py
```

**Expected Output:**
```
============================================================
Discord Interaction Server
============================================================
Server starting on http://localhost:8081
Interaction endpoint: POST /interactions
============================================================
```

### Step 4: Set Up Cloudflare Tunnel

```bash
# Terminal 2: Start Cloudflare tunnel
cloudflare-tunnel-windows-amd64.exe tunnel --url http://localhost:8081
```

**Expected Output:**
```
Your quick Tunnel has been created! Visit it at:
https://random-name-1234.trycloudflare.com
```

### Step 5: Configure Discord Interaction URL

1. Go to https://discord.com/developers/applications
2. Select your bot application
3. Go to "General Information"
4. Under "Interactions Endpoint URL", paste your Cloudflare tunnel URL + `/interactions`:
   ```
   https://random-name-1234.trycloudflare.com/interactions
   ```
5. Click "Save Changes"
6. Discord will send a PING request to verify the endpoint

**Verification Success:**
```
[DEBUG] Interaction type: 1
[DEBUG] Responding to PING with type=1
```

---

## Testing Workflow

### Test 1: `/admin stats` (Safest - Read-Only)

1. In Discord, type `/admin stats`
2. Press Enter
3. Expected: Ephemeral embed showing current parameter values

**Troubleshooting:**
- Command not showing? Re-register commands and wait 1-2 minutes
- "Application did not respond"? Check interaction server logs
- "Invalid signature"? Verify `DISCORD_PUBLIC_KEY` in .env

### Test 2: `/admin report` (Safe - Read-Only)

1. Ensure sample events exist:
   ```bash
   python test_admin_controls.py
   ```
2. In Discord, type `/admin report`
3. Expected: Full admin report with buttons
4. Click "View Details" to test button interaction

**Troubleshooting:**
- "No data" in report? Run test script to create sample events
- Buttons not showing? Verify `DISCORD_BOT_TOKEN` is configured
- Report shows 0 trades? Check `data/events.jsonl` has entries

### Test 3: `/admin set` (Caution - Modifies Config)

1. Backup current .env first:
   ```bash
   cp .env .env.backup_manual
   ```
2. In Discord, type:
   ```
   /admin set parameter:MIN_SCORE value:0.25
   ```
3. Expected: Success embed confirming update
4. Verify change:
   ```
   /admin stats
   ```
5. Should show `MIN_SCORE: 0.25`

**Rollback if needed:**
```
/admin rollback
```

### Test 4: `/admin rollback` (Recovery)

1. After making a change with `/admin set`, run:
   ```
   /admin rollback
   ```
2. Expected: Confirmation embed
3. Verify rollback with `/admin stats`

---

## Implementation Details

### Files Created/Modified

1. **`src/catalyst_bot/slash_commands.py`** (NEW)
   - Command handler for `/admin` subcommands
   - Implements report, set, rollback, stats handlers
   - Validates parameters before applying changes

2. **`interaction_server.py`** (MODIFIED)
   - Added slash command routing (type 2 interactions)
   - Fixed .env path (`env.env` → `.env`)
   - Handles both slash commands and button clicks

3. **`register_slash_commands.py`** (NEW)
   - Discord API integration for command registration
   - Supports both global and guild-specific registration
   - Auto-detects APPLICATION_ID from bot token

### Interaction Flow

```
User types /admin set → Discord API → Cloudflare Tunnel → Interaction Server (localhost:8081)
                                                              ↓
                                                    slash_commands.py
                                                              ↓
                                                    validate_parameter()
                                                              ↓
                                                    apply_parameter_changes()
                                                              ↓
                                                    Update .env + Reload
                                                              ↓
                                            Return success embed to Discord
```

---

## Security Considerations

1. **Signature Verification**: All interactions verified with Ed25519 signature
2. **Parameter Validation**: Strict type and range checking before applying
3. **Automatic Backups**: Every change creates timestamped backup
4. **Rollback Support**: Can revert to any previous configuration
5. **Ephemeral Responses**: Stats shown only to command user (flags: 64)

---

## Troubleshooting

### Commands not showing in Discord?

**Cause:** Commands not registered or propagation delay

**Solution:**
```bash
# Re-register guild-specific (instant)
python register_slash_commands.py
# Choose option 1

# Wait 1-2 minutes, then reload Discord (Ctrl+R)
```

### "Application did not respond" error?

**Cause:** Interaction server not running or unreachable

**Solution:**
1. Check interaction server is running: `http://localhost:8081/health`
2. Check Cloudflare tunnel is active and URL is correct
3. Verify Discord interaction URL matches tunnel URL + `/interactions`

### "Invalid signature" error?

**Cause:** `DISCORD_PUBLIC_KEY` mismatch or missing

**Solution:**
1. Go to Discord Developer Portal → Your App → General Information
2. Copy "Public Key"
3. Update `.env`: `DISCORD_PUBLIC_KEY=your_public_key`
4. Restart interaction server

### Parameter update not applying?

**Cause:** Validation failed or .env path incorrect

**Solution:**
1. Check validation rules (see table above)
2. Verify `.env` file exists (not `env.env`)
3. Check logs: `data/logs/bot.jsonl`
4. Try manual rollback: `/admin rollback`

### Slash commands work but buttons don't?

**Cause:** Button handler not routing correctly

**Solution:**
1. Check interaction server logs for type=3 messages
2. Verify `DISCORD_BOT_TOKEN` is set (buttons require bot API)
3. Test button separately by clicking existing admin report buttons

---

## Next Steps

### Wave 1.1 Completion Checklist
- ✅ Admin report generation
- ✅ Button interaction handlers
- ✅ Parameter validation & updates
- ✅ Rollback functionality
- ✅ Slash command handlers
- ✅ Command registration script
- ⏳ End-to-end testing with live Discord
- ⏳ Add trading discipline rules (max daily alerts, cooldowns)

### Wave 1.2: Real-Time Breakout Feedback
- Track alert performance 15min, 1hr, 4hr, 1day after posting
- Measure: price change %, volume change %, breakout confirmation
- Store results in SQLite
- Generate weekly "best/worst catalyst types" report
- Auto-suggest parameter changes based on feedback

---

## Command Reference Quick Card

```
┌─────────────────────────────────────────────────────┐
│           CATALYST-BOT SLASH COMMANDS               │
├─────────────────────────────────────────────────────┤
│ /admin report [date]                                │
│   → Generate admin performance report               │
│                                                     │
│ /admin set <parameter> <value>                      │
│   → Update bot parameter (auto-backup)              │
│                                                     │
│ /admin rollback                                     │
│   → Revert to previous configuration                │
│                                                     │
│ /admin stats                                        │
│   → Show current parameter values                   │
└─────────────────────────────────────────────────────┘

Examples:
  /admin report date:2025-10-03
  /admin set parameter:MIN_SCORE value:0.3
  /admin set parameter:PRICE_CEILING value:7.5
  /admin rollback
  /admin stats
```

---

**Implementation Complete: October 4, 2025**
**Ready for Live Testing**
