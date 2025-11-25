# API Key Rotation Guide
**Date**: November 24, 2025
**Reason**: GitHub Dependabot detected exposed secrets in git history

## 🚨 CRITICAL: These Keys Are Compromised

The following API keys were detected in git history and need immediate rotation:
1. **Anthropic API Key**: `sk-ant-api03-B4nXykLQxUPV6R...`
2. **Discord Bot Token**: `MTM5ODUyMTQ...`
3. **Google API Key**: `AIzaSyD5oG5EDvyGZuYDKY6FAHF...`

---

## Step 1: Anthropic API Key Rotation

### 1.1 Revoke Old Key

1. **Go to**: https://console.anthropic.com/settings/keys
2. **Login** with your Anthropic account credentials
3. **Find the compromised key**:
   - Look for key starting with: `sk-ant-api03-B4nXykLQxUPV6R...`
   - It may be named something like "Catalyst Bot" or "Production"
4. **Click the trash/delete icon** next to the key
5. **Confirm deletion**
   - ⚠️ This will immediately invalidate the key

### 1.2 Create New Key

1. **Still on**: https://console.anthropic.com/settings/keys
2. **Click "Create Key"** button
3. **Name it**: `Catalyst-Bot-Production-2025-11-24` (include date for tracking)
4. **Set permissions** (if available):
   - ✅ Messages API access
   - ❌ Workspace management (not needed)
5. **Click "Create"**
6. **COPY THE KEY IMMEDIATELY** - it will only be shown once
   - Format: `sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXX`
7. **Save to password manager** (1Password, LastPass, etc.)

### 1.3 Update .env File

**File**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\.env`

**Find this line** (around line 162):
```bash
ANTHROPIC_API_KEY=sk-ant-api03-OLD_KEY_HERE
```

**Replace with**:
```bash
ANTHROPIC_API_KEY=sk-ant-api03-NEW_KEY_FROM_STEP_1.2
```

**Save the file**

---

## Step 2: Discord Webhook/Bot Token Rotation

### 2.1 Identify Which Discord Credential

First, determine if it's a **webhook URL** or **bot token**:

**Option A: If it's a Webhook URL**:
- Format: `https://discord.com/api/webhooks/ID/TOKEN`
- The token is the part after the last `/`

**Option B: If it's a Bot Token**:
- Format: `MTM5ODUyMTQ...` (Base64-like string)
- Used for Discord bot applications

### 2.2a Rotate Webhook URL (if applicable)

1. **Open Discord** (desktop or web)
2. **Go to your server**
3. **Right-click on the channel** that receives alerts (e.g., #trading-alerts)
4. **Click "Edit Channel"**
5. **Go to "Integrations"** tab
6. **Find "Webhooks"** section
7. **Find the webhook** named something like:
   - "Catalyst Bot"
   - "Trading Alerts"
   - "Main Webhook"
8. **Click the webhook** to expand
9. **Click "Delete Webhook"**
   - Confirm deletion
   - ⚠️ This immediately invalidates the old webhook

10. **Create new webhook**:
    - Click "New Webhook"
    - **Name**: `Catalyst-Bot-Main-2025-11-24`
    - **Channel**: Same channel as before
    - **Click "Copy Webhook URL"**
    - Save to password manager

11. **Repeat for Admin Webhook** (if you have one):
    - Same steps but for admin/alerts channel
    - Name: `Catalyst-Bot-Admin-2025-11-24`

### 2.2b Rotate Bot Token (if applicable)

1. **Go to**: https://discord.com/developers/applications
2. **Login** with your Discord account
3. **Find your application** (e.g., "Catalyst Bot")
4. **Click on it** to open
5. **Go to "Bot"** section in left sidebar
6. **Click "Reset Token"**
   - ⚠️ Warning will appear saying this invalidates the old token
   - **Confirm reset**
7. **Click "Copy"** to copy new token
   - Format: `MTM5ODUy...` (long base64-like string)
8. **Save to password manager**

### 2.3 Update .env File

**File**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\.env`

**For Webhook URLs** (find around line 10-15):
```bash
# OLD:
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/OLD_ID/OLD_TOKEN
DISCORD_ADMIN_WEBHOOK=https://discord.com/api/webhooks/OLD_ADMIN_ID/OLD_ADMIN_TOKEN

# NEW:
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/NEW_ID/NEW_TOKEN_FROM_STEP_2.2a
DISCORD_ADMIN_WEBHOOK=https://discord.com/api/webhooks/NEW_ADMIN_ID/NEW_ADMIN_TOKEN_FROM_STEP_2.2a
```

**OR for Bot Token** (if applicable):
```bash
# OLD:
DISCORD_BOT_TOKEN=MTM5ODUyMTQOLD_TOKEN

# NEW:
DISCORD_BOT_TOKEN=MTM5ODUyMTQNEW_TOKEN_FROM_STEP_2.2b
```

**Save the file**

---

## Step 3: Google API Key Rotation

### 3.1 Revoke Old Key

1. **Go to**: https://console.cloud.google.com/apis/credentials
2. **Login** with your Google account
3. **Select the correct project** (dropdown at top):
   - Look for project related to Catalyst Bot
   - Or check which project the old key belongs to
4. **Find "API Keys"** section
5. **Locate the compromised key**:
   - Look for key starting with: `AIzaSyD5oG5EDvyGZuYDKY6FAHF...`
   - May be named "Catalyst Bot" or "Trading Bot"
6. **Click the three dots (⋮)** next to the key
7. **Select "Delete"**
   - Confirm deletion
   - ⚠️ This immediately invalidates the key

### 3.2 Create New Key

1. **Still on**: https://console.cloud.google.com/apis/credentials
2. **Click "+ CREATE CREDENTIALS"** at top
3. **Select "API key"**
4. **Key is created automatically**
   - Format: `AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
5. **IMMEDIATELY click "RESTRICT KEY"** (very important!)

### 3.3 Restrict New Key (Security Best Practice)

1. **In the restriction dialog**:

2. **Name the key**:
   - `Catalyst-Bot-Production-2025-11-24`

3. **Application restrictions**:
   - Select "IP addresses"
   - Add your server's public IP address
   - Click "Done"

4. **API restrictions**:
   - Select "Restrict key"
   - Check ONLY the APIs you use:
     - ✅ Google Sheets API (if used)
     - ✅ YouTube Data API v3 (if used for news)
     - ✅ Custom Search API (if used)
     - ❌ Uncheck everything else

5. **Click "SAVE"**

6. **Copy the API key**
   - Should be visible at top of screen
   - Format: `AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

7. **Save to password manager**

### 3.4 Update .env File

**File**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\.env`

**Find this line** (around line 297 based on docs):
```bash
# OLD:
GOOGLE_API_KEY=AIzaSyD5oG5EDvyGZuYDKY6FAHFOLD_KEY

# NEW:
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXNEW_KEY_FROM_STEP_3.2
```

**OR it might be named** (check your .env):
```bash
YOUTUBE_API_KEY=...
GOOGLE_CUSTOM_SEARCH_KEY=...
```

**Save the file**

---

## Step 4: Test New Keys

### 4.1 Stop the Running Bot

```bash
# Find running processes
tasklist | findstr python

# Kill all python processes related to bot
taskkill /F /IM python.exe /FI "WINDOWTITLE eq catalyst-bot"
```

**Or manually**:
- Press Ctrl+C in terminal where bot is running
- Close all bot terminal windows

### 4.2 Test Bot Startup

```bash
cd "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"
python -m catalyst_bot.runner --once
```

**Check for errors**:
- ✅ **SUCCESS**: Bot starts without authentication errors
- ✅ **SUCCESS**: "boot_start" message appears in logs
- ✅ **SUCCESS**: Discord heartbeat sent (check Discord channel)
- ❌ **FAILURE**: "Authentication failed" → Double-check API key copied correctly

### 4.3 Test Individual Services

**Test Anthropic API**:
```bash
python -c "import os; from anthropic import Anthropic; client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY')); print('✅ Anthropic API works!' if client.api_key else '❌ No API key')"
```

**Test Discord Webhook**:
```bash
curl -X POST -H "Content-Type: application/json" -d "{\"content\":\"✅ Test message after key rotation\"}" "YOUR_NEW_DISCORD_WEBHOOK_URL"
```

**Test Google API** (if you use it):
```bash
curl "https://www.googleapis.com/youtube/v3/videos?part=snippet&key=YOUR_NEW_GOOGLE_API_KEY&id=dQw4w9WgXcQ"
```

---

## Step 5: Mark GitHub Alerts as Resolved

### 5.1 Go to GitHub Secret Scanning Alerts

1. **Go to**: https://github.com/YOUR_USERNAME/catalyst-bot/security/secret-scanning
   - Replace `YOUR_USERNAME` with your GitHub username

2. **Login** to GitHub if needed

3. **You should see 3 alerts**:
   - Anthropic API Key
   - Discord Bot Token
   - Google API Key

### 5.2 Close Each Alert

**For EACH alert**:

1. **Click on the alert** to open details

2. **Verify it's the OLD key**:
   - Check the exposed value matches the old key
   - Check it's in `docs/operations/` files

3. **Click "Close as"** dropdown

4. **Select "Revoked"**
   - This tells GitHub you've rotated the key

5. **Add comment** (optional but recommended):
   ```
   Key rotated on 2025-11-24. Old key revoked from provider.
   New key added to .env (not committed to git).
   ```

6. **Click "Close alert"**

7. **Repeat for other 2 alerts**

---

## Step 6: Verify .env File Security

### 6.1 Check .gitignore

**File**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\.gitignore`

**Verify these lines exist**:
```gitignore
# Environment variables
.env
.env.local
.env.*.local
.env.production
.env.staging

# Secrets
*.key
*.pem
secrets/
```

**If missing**, add them to `.gitignore`

### 6.2 Verify .env Not Committed

```bash
cd "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"
git status
```

**Output should NOT show**:
- ❌ `.env` in "Changes to be committed"
- ❌ `.env` in "Changes not staged for commit"

**If .env appears**:
```bash
# Remove from staging
git reset HEAD .env

# Add to .gitignore if not already there
echo .env >> .gitignore
```

---

## Step 7: Document Changes

### 7.1 Update Password Manager

**In your password manager** (1Password, LastPass, etc.):

1. **Create new entries**:
   - Title: `Catalyst Bot - Anthropic API (Rotated 2025-11-24)`
   - Username: (your email or account)
   - Password: `sk-ant-api03-NEWKEY...`
   - URL: https://console.anthropic.com
   - Notes: "Rotated due to GitHub secret exposure"

2. **Repeat for Discord and Google keys**

3. **Mark old entries as "Compromised"** or delete them

### 7.2 Update Documentation

**Optional**: Create a note in your project docs:

**File**: `docs/CHANGELOG.md` or `docs/operations/KEY_ROTATION_LOG.md`

```markdown
## 2025-11-24: Security - API Key Rotation

**Reason**: GitHub Dependabot detected exposed secrets in git history

**Keys Rotated**:
- ✅ Anthropic API Key (sk-ant-api03-B4n...)
- ✅ Discord Webhook URLs (main + admin)
- ✅ Google API Key (AIzaSyD5o...)

**Actions Taken**:
1. Old keys revoked from provider portals
2. New keys generated with proper restrictions
3. .env file updated with new keys
4. Bot tested and verified working
5. GitHub alerts marked as "Revoked"

**New Key Names**:
- Anthropic: `Catalyst-Bot-Production-2025-11-24`
- Discord: `Catalyst-Bot-Main-2025-11-24`, `Catalyst-Bot-Admin-2025-11-24`
- Google: `Catalyst-Bot-Production-2025-11-24`
```

---

## ⚠️ Important Reminders

### DO:
- ✅ Save all new keys to password manager IMMEDIATELY
- ✅ Test bot after each key rotation
- ✅ Keep .env file local only (never commit)
- ✅ Use restricted keys (IP restrictions, API restrictions)
- ✅ Name keys with dates for tracking
- ✅ Mark GitHub alerts as "Revoked"

### DON'T:
- ❌ Commit .env to git
- ❌ Share keys in Slack/Discord/email
- ❌ Use the same key in multiple projects
- ❌ Skip testing after rotation
- ❌ Forget to revoke old keys
- ❌ Leave unrestricted Google API keys

---

## Troubleshooting

### "Authentication failed" Error

**Problem**: Bot won't start after key rotation

**Solution**:
1. Double-check key copied correctly (no extra spaces)
2. Verify key is active in provider portal
3. Check .env file syntax (no quotes around values)
4. Restart terminal/reload environment variables

### Discord Webhook Not Working

**Problem**: No messages appearing in Discord channel

**Solution**:
1. Test webhook with curl command (Step 4.3)
2. Verify webhook URL includes both ID and TOKEN
3. Check webhook still exists in Discord channel settings
4. Verify channel permissions (webhook needs send permission)

### Google API 403 Forbidden

**Problem**: Google API returns "Access Denied"

**Solution**:
1. Check API is enabled in Google Cloud Console
2. Verify IP restriction includes your server IP
3. Verify API restriction includes the API you're using
4. Wait 5 minutes for restrictions to propagate

---

## Completion Checklist

- [ ] **Anthropic**: Old key revoked ✓
- [ ] **Anthropic**: New key created ✓
- [ ] **Anthropic**: .env updated ✓
- [ ] **Discord**: Old webhook/token revoked ✓
- [ ] **Discord**: New webhook/token created ✓
- [ ] **Discord**: .env updated ✓
- [ ] **Google**: Old key revoked ✓
- [ ] **Google**: New key created with restrictions ✓
- [ ] **Google**: .env updated ✓
- [ ] **Testing**: Bot starts without errors ✓
- [ ] **Testing**: Discord heartbeat received ✓
- [ ] **Testing**: API calls work ✓
- [ ] **GitHub**: All 3 alerts marked as "Revoked" ✓
- [ ] **.gitignore**: .env is excluded ✓
- [ ] **Password Manager**: New keys saved ✓
- [ ] **Documentation**: Changes logged ✓

---

## Emergency Contacts

If you encounter issues during rotation:

- **Anthropic Support**: support@anthropic.com
- **Discord Developer Support**: https://discord.com/developers/docs
- **Google Cloud Support**: https://cloud.google.com/support

---

**Estimated Time**: 30-45 minutes total
**Difficulty**: Medium
**Risk**: Low (if followed carefully)

Once completed, the exposed secrets will be neutralized and your bot will be secure!
