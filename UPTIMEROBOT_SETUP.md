# UptimeRobot Setup Guide

This guide walks you through setting up external monitoring for Catalyst-Bot using UptimeRobot, a free uptime monitoring service.

## What is UptimeRobot?

UptimeRobot monitors your bot's health endpoint and alerts you via email, SMS, or Discord webhook if the bot becomes unresponsive. This provides an extra layer of monitoring beyond the built-in watchdog.

**Free Tier Includes:**
- 50 monitors
- 5-minute check intervals
- Email and webhook alerts
- Public status pages

## Prerequisites

1. **Cloudflare Tunnel**: Your bot must be accessible via a public URL (Cloudflare tunnel)
2. **Health Endpoint**: The bot's health endpoint must be running (enabled by default)
3. **UptimeRobot Account**: Create a free account at [https://uptimerobot.com](https://uptimerobot.com)

## Step 1: Verify Health Endpoint

Before setting up UptimeRobot, verify your health endpoint is working:

### Local Test (without tunnel)
```bash
curl http://localhost:8080/health/ping
# Expected output: ok
```

### Remote Test (with Cloudflare tunnel)
```bash
curl https://your-tunnel.trycloudflare.com/health/ping
# Expected output: ok
```

If you get an error, check:
- Is the bot running?
- Is `FEATURE_HEALTH_ENDPOINT=1` in your `.env`?
- Is the Cloudflare tunnel running?
- Is the correct port configured (`HEALTH_CHECK_PORT=8080`)?

## Step 2: Create UptimeRobot Account

1. Go to [https://uptimerobot.com](https://uptimerobot.com)
2. Click "Register" (top right)
3. Sign up with email or Google account
4. Verify your email address

## Step 3: Add Monitor

1. Log in to UptimeRobot dashboard
2. Click "+ Add New Monitor"
3. Configure the monitor:

### Monitor Configuration

| Field | Value |
|-------|-------|
| **Monitor Type** | HTTP(s) |
| **Friendly Name** | `Catalyst-Bot Health Check` |
| **URL (or IP)** | `https://your-tunnel.trycloudflare.com/health/ping` |
| **Monitoring Interval** | `5 minutes` (free tier) |

**Important:** Replace `your-tunnel.trycloudflare.com` with your actual Cloudflare tunnel URL.

### Advanced Settings

Click "Advanced Settings" and configure:

| Field | Value | Notes |
|-------|-------|-------|
| **Keyword** | `ok` | UptimeRobot will verify the response contains "ok" |
| **Keyword Type** | `exists` | Alert if keyword is NOT found |
| **HTTP Method** | `GET (Head)` | Most efficient method |
| **Custom HTTP Headers** | _(leave empty)_ | Not needed |
| **Timeout** | `30 seconds` | Default is fine |

### Alert Contacts

4. Scroll down to "Alert Contacts to Notify"
5. Click "Add a new alert contact" if you haven't added any

#### Email Alerts
- Most basic option
- Enabled by default
- Make sure to verify your email

#### SMS Alerts (Optional)
- Requires phone number verification
- May have limits on free tier
- Good for critical alerts

#### Discord Webhook Alerts (Recommended)
This is the best option for Discord-based monitoring:

1. In Discord, go to your admin channel
2. Click the gear icon (Edit Channel)
3. Go to "Integrations" → "Webhooks"
4. Click "New Webhook"
5. Name it "UptimeRobot Alerts"
6. Copy the webhook URL

Back in UptimeRobot:
1. Click "Add a new alert contact"
2. Select "Webhook"
3. Paste your Discord webhook URL
4. Set "POST Value (JSON Format)" to:

```json
{
  "content": "🚨 **Catalyst-Bot Alert**",
  "embeds": [{
    "title": "*monitorFriendlyName*",
    "description": "Status: *alertType*\nReason: *alertDetails*",
    "color": 16711680,
    "timestamp": "*alertDateTime*"
  }]
}
```

5. Click "Test Alert Contact" to verify it works
6. Save the alert contact

## Step 4: Configure Notification Settings

After adding alert contacts, configure when to be notified:

1. In the monitor settings, select which contacts to notify
2. Recommended: Enable alerts for **"Down"** events only (not every check)
3. Threshold: Alert after **2 failed checks** (reduces false alarms)

This means UptimeRobot will wait for 2 consecutive failures (10 minutes) before alerting.

## Step 5: Public Status Page (Optional)

Create a public status page to share with your team or users:

1. Go to "My Status Pages" in the left sidebar
2. Click "+ Add New Status Page"
3. Select your Catalyst-Bot monitor
4. Choose a custom URL slug (e.g., `catalyst-bot-status`)
5. Enable "Show Uptime Percentages"
6. Save and get your public URL

Share this URL: `https://stats.uptimerobot.com/your-slug`

## Step 6: Verify Setup

Test your configuration:

1. **Stop the bot** temporarily:
   ```bash
   net stop CatalystBot
   ```

2. Wait 10-15 minutes (2 failed checks at 5-minute intervals)

3. You should receive an alert via your configured channels

4. **Start the bot** again:
   ```bash
   net start CatalystBot
   ```

5. You should receive a "back up" notification

## Configuration Reference

Here's a complete configuration template:

```
Monitor Name: Catalyst-Bot Health Check
Monitor Type: HTTP(s)
URL: https://your-tunnel.trycloudflare.com/health/ping
Monitoring Interval: 5 minutes
Keyword: ok
Keyword Type: exists
Alert Contacts: [Your email, Discord webhook]
Notification Threshold: 2 failed checks
Alert for: Down events only
```

## Troubleshooting

### "Monitor is down" but bot is running

**Possible causes:**
- Cloudflare tunnel is down (restart it)
- Health endpoint port mismatch (check `HEALTH_CHECK_PORT`)
- Firewall blocking external requests
- Bot is frozen (check logs)

**Test manually:**
```bash
curl -v https://your-tunnel.trycloudflare.com/health/ping
```

### Alerts not being sent

**Check:**
- Alert contacts are selected in monitor settings
- Email is verified
- Discord webhook URL is correct
- Notification threshold is not too high

### Too many false alarms

**Solutions:**
- Increase notification threshold to 3 failed checks
- Use the watchdog to auto-restart before UptimeRobot notices
- Check bot logs for frequent crashes

## Advanced: Multiple Monitors

For comprehensive monitoring, set up multiple monitors:

1. **Primary Health Check** (`/health/ping`)
   - Interval: 5 minutes
   - Alerts: Email + Discord

2. **Detailed Health** (`/health/detailed`)
   - Interval: 10 minutes
   - Alerts: Email only
   - Keyword: `"status": "healthy"`

3. **Cloudflare Tunnel** (root URL)
   - Interval: 15 minutes
   - Ensures tunnel is running

## Integration with Watchdog

The watchdog and UptimeRobot work together:

1. **Watchdog** monitors locally and restarts the bot quickly (60s intervals)
2. **UptimeRobot** monitors externally and alerts you if watchdog fails

This provides redundancy:
- If bot crashes → Watchdog restarts it (no UptimeRobot alert)
- If bot + watchdog both down → UptimeRobot alerts you
- If tunnel is down → UptimeRobot alerts you

## Cost and Limits

**Free Tier:**
- 50 monitors
- 5-minute intervals
- Unlimited alerts
- Public status page

**Paid Tiers** (if needed):
- 1-minute intervals
- SMS alerts
- Advanced reports
- Starts at $7/month

For a single bot, the free tier is more than sufficient.

## Next Steps

After setting up UptimeRobot:

1. ✅ Monitor the status page for a few days
2. ✅ Tune alert thresholds based on actual uptime
3. ✅ Document your tunnel URL in a secure location
4. ✅ Set up the watchdog for local monitoring
5. ✅ Review alerts weekly and adjust as needed

## Support

- **UptimeRobot Docs**: [https://blog.uptimerobot.com/web-api-documentation/](https://blog.uptimerobot.com/web-api-documentation/)
- **Cloudflare Tunnel Docs**: [https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- **Catalyst-Bot Issues**: [GitHub Issues](https://github.com/Amenzel91/catalyst-bot/issues)

---

**WAVE 2.3: 24/7 Deployment Infrastructure**
