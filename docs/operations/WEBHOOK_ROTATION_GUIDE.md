# 🔒 Webhook Rotation Guide

## Compromised Webhooks (DELETE THESE IN DISCORD)

These webhook URLs were exposed in your public GitHub history and must be deleted:

### Main Webhook
- **ID**: `1397052240212262952`
- **Partial Token**: `H98Z1ZyiqNJw3Z46-ATdgLk...`
- **Full URL**: `https://discord.com/api/webhooks/1397052240212262952/H98Z1ZyiqNJw3Z46-ATdgLkEgcM4LTPUUEYlNTyItzSxGlls7mmBcFMmt2vZXL4ukHj5`

### Admin Webhook
- **ID**: `1406830521631248515`
- **Partial Token**: `MTM5ODUyMTQ0Nzcyj...`
- **Full URL**: `https://discord.com/api/webhooks/1406830521631248515/MTM5ODUyMTQ0NzcyNjU4MzgwOA.GkBKvN.gzXfy7rSyCIltmi02w4RKFJAvHhcpz2rtXTqCE`

---

## How to Rotate Webhooks

### Step 1: Delete Old Webhooks in Discord

1. Open your Discord server
2. Go to **Server Settings** → **Integrations** → **Webhooks**
3. Find webhook with ID ending in `2952` (main webhook)
4. Click **Delete Webhook** → Confirm
5. Find webhook with ID ending in `8515` (admin webhook)
6. Click **Delete Webhook** → Confirm

### Step 2: Create New Webhooks

**For Main Alerts:**
1. Click **New Webhook**
2. Name: `Catalyst Bot Alerts` (or whatever you prefer)
3. Select channel: `#stock-alerts` (or your preferred channel)
4. Click **Copy Webhook URL**
5. Save this URL - you'll need it for Step 3

**For Admin Messages (Optional but Recommended):**
1. Click **New Webhook**
2. Name: `Catalyst Bot Admin`
3. Select channel: `#bot-admin` (or your preferred channel)
4. Click **Copy Webhook URL**
5. Save this URL - you'll need it for Step 3

### Step 3: Update Your `.env` Files

**Update `.env` (production):**
```env
# Replace these with your NEW webhook URLs from Step 2
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_NEW_ID/YOUR_NEW_TOKEN
DISCORD_ADMIN_WEBHOOK=https://discord.com/api/webhooks/YOUR_NEW_ADMIN_ID/YOUR_NEW_ADMIN_TOKEN
```

**Update `.env.staging` (staging environment):**
```env
# Replace these with your NEW webhook URLs from Step 2
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_NEW_ID/YOUR_NEW_TOKEN
DISCORD_ADMIN_WEBHOOK=https://discord.com/api/webhooks/YOUR_NEW_ADMIN_ID/YOUR_NEW_ADMIN_TOKEN
```

### Step 4: Test the New Webhooks

Run a quick test to make sure the new webhooks work:
```bash
python -m catalyst_bot.runner --once
```

Check your Discord channels to confirm alerts are posting to the correct channels.

---

## After Rotation Complete

Once you've:
1. ✅ Deleted old webhooks in Discord
2. ✅ Created new webhooks
3. ✅ Updated `.env` and `.env.staging`
4. ✅ Tested that new webhooks work

**Tell Claude to proceed with the force push to GitHub.**

This will upload the cleaned git history (without .env.staging) to GitHub, completing the security remediation.

---

## Security Checklist

- [ ] Old webhooks deleted in Discord
- [ ] New webhooks created
- [ ] `.env` updated with new webhooks
- [ ] `.env.staging` updated with new webhooks
- [ ] Tested bot with new webhooks
- [ ] Ready for force push to GitHub

---

## Why This Matters

Your old webhook URLs are currently **public on GitHub**. Anyone can use them to:
- Spam your Discord channels
- Post fake alerts
- Impersonate your bot

Deleting the webhooks in Discord **immediately** stops this - the URLs become invalid and can't be used anymore.

Once you're done, the cleaned git history (without the secrets) will be pushed to GitHub.
