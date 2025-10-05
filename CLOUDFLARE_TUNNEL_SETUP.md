# Cloudflare Tunnel Setup Guide

This guide will help you set up Cloudflare Tunnel for Discord button interactions.

## Why Cloudflare Tunnel?

- ✅ **100% FREE** forever - No trial, no credit card
- ✅ **Stable URL** - Never changes (unlike ngrok free)
- ✅ **Runs locally** - Works on your current machine
- ✅ **Production-ready** - Used by real companies
- ✅ **Zero config** - Quick Tunnel needs no setup

## Option A: Quick Tunnel (Easiest - 5 minutes)

This is the fastest way to get started. The URL changes each time you restart, but it's perfect for testing.

### 1. Install Cloudflared

**Windows (via Chocolatey):**
```bash
choco install cloudflared
```

**Windows (manual download):**
1. Download from: https://github.com/cloudflare/cloudflared/releases/latest
2. Get `cloudflared-windows-amd64.exe`
3. Rename to `cloudflared.exe`
4. Add to PATH or put in your project folder

**Verify installation:**
```bash
cloudflared --version
```

### 2. Start Quick Tunnel

Open **Terminal 1** and run:
```bash
cloudflared tunnel --url http://localhost:8081
```

You'll see output like:
```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://random-name-1234.trycloudflare.com                                                |
+--------------------------------------------------------------------------------------------+
```

**Copy that URL!** You'll need it for Discord.

### 3. Start Interaction Server

Open **Terminal 2** and run:
```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
.venv\Scripts\python interaction_server.py
```

Server will start on http://localhost:8081

### 4. Configure Discord

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your Application (or create one)
3. Go to **General Information**
4. Find **Interactions Endpoint URL**
5. Enter: `https://your-random-name.trycloudflare.com/interactions`
6. Click **Save Changes**

Discord will send a verification request. If your server is running, it will respond automatically.

### 5. Start Bot

Open **Terminal 3** and run:
```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
.venv\Scripts\python -m catalyst_bot.runner
```

### 6. Test It!

Wait for the nightly admin report (21:30 UTC) or run:
```bash
python test_admin_report.py
```

Click the buttons in Discord - they should work!

---

## Option B: Named Tunnel (Permanent URL)

This creates a stable URL that never changes. Perfect for production.

### 1. Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This opens a browser to authorize. You'll need a free Cloudflare account.

### 2. Create Tunnel

```bash
cloudflared tunnel create catalyst-bot
```

You'll see:
```
Tunnel credentials written to C:\Users\YourName\.cloudflared\UUID.json
Created tunnel catalyst-bot with id UUID
```

**Copy the UUID** - you'll need it next.

### 3. Create Config File

Create `cloudflared-config.yml` in your project folder:

```yaml
tunnel: YOUR_TUNNEL_UUID_HERE
credentials-file: C:\Users\YourName\.cloudflared\YOUR_TUNNEL_UUID_HERE.json

ingress:
  # Route to interaction server
  - hostname: catalyst-bot.yourdomain.com  # Or use a trycloudflare.com subdomain
    service: http://localhost:8081

  # Catch-all rule (required)
  - service: http_status:404
```

**If you don't have a domain**, you can use a free subdomain:
```yaml
tunnel: YOUR_TUNNEL_UUID_HERE
credentials-file: C:\Users\YourName\.cloudflared\YOUR_TUNNEL_UUID_HERE.json

ingress:
  - service: http://localhost:8081
```

### 4. Configure DNS (if using custom domain)

```bash
cloudflared tunnel route dns catalyst-bot catalyst-bot.yourdomain.com
```

This creates a CNAME record pointing to your tunnel.

### 5. Start Tunnel

```bash
cloudflared tunnel --config cloudflared-config.yml run catalyst-bot
```

Your tunnel is now running at `https://catalyst-bot.yourdomain.com`

### 6. Follow Steps 3-6 from Option A

Configure Discord with your permanent URL, then start the interaction server and bot.

---

## Easy Mode: Use the Startup Script

We've created a batch file that starts everything for you!

```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
start_with_interactions.bat
```

This will:
1. Check if Flask and cloudflared are installed
2. Start Cloudflare Tunnel
3. Show you the public URL
4. Wait for you to configure Discord
5. Start interaction server
6. Start the bot

Press Ctrl+C to stop everything.

---

## Troubleshooting

### "cloudflared not found"

**Solution 1:** Install via Chocolatey
```bash
choco install cloudflared
```

**Solution 2:** Download manually
1. Get from: https://github.com/cloudflare/cloudflared/releases/latest
2. Add to PATH or use full path

### "Discord verification failed"

**Possible causes:**
- Tunnel not running
- Interaction server not running
- Wrong URL in Discord settings
- Firewall blocking cloudflared

**Check:**
```bash
# Test if tunnel is working
curl https://your-tunnel-url.trycloudflare.com/health

# Should return: {"status":"healthy"}
```

### "Buttons not responding"

**Check:**
1. Is cloudflared tunnel running?
2. Is interaction_server.py running?
3. Is Discord endpoint URL correct?
4. Check logs in `data/logs/bot.jsonl`

### "Tunnel URL changes every restart"

This is normal for Quick Tunnel (Option A). If you want a permanent URL:
- Use Named Tunnel (Option B)
- Or keep the Quick Tunnel terminal open (don't restart it)

### Port 8081 already in use

Change the port in both files:

**interaction_server.py:**
```python
app.run(host='0.0.0.0', port=8082)  # Change 8081 to 8082
```

**Cloudflared command:**
```bash
cloudflared tunnel --url http://localhost:8082
```

---

## Advanced: Auto-Start on Boot

### Windows Task Scheduler

1. Create `start_tunnel.bat`:
```batch
@echo off
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
cloudflared tunnel --config cloudflared-config.yml run catalyst-bot
```

2. Open Task Scheduler
3. Create Basic Task
4. Set trigger: "When the computer starts"
5. Action: Start a program
6. Program: `C:\path\to\start_tunnel.bat`
7. Enable "Run whether user is logged on or not"

Repeat for interaction_server.py and the bot.

---

## Security Notes

### Cloudflare Tunnel is Secure

- All traffic is encrypted (TLS)
- No inbound ports opened on your firewall
- Cloudflare DDoS protection included
- Only HTTP/HTTPS traffic allowed

### Best Practices

1. **Don't expose sensitive endpoints**
   - Only `/interactions` should be public
   - Other endpoints stay local

2. **Validate Discord requests**
   - Our handler verifies Discord signatures
   - Rejects invalid requests

3. **Monitor logs**
   - Check `data/logs/bot.jsonl` regularly
   - Watch for unusual interaction patterns

4. **Keep credentials safe**
   - Don't commit `.cloudflared/` to git
   - Don't share tunnel UUIDs publicly

---

## Cost Breakdown

| Service | Cost | Features |
|---------|------|----------|
| Cloudflare Tunnel | **FREE** | Unlimited traffic, unlimited bandwidth |
| Discord Application | **FREE** | Unlimited interactions |
| Flask Server | **FREE** | Runs locally on your machine |
| **TOTAL** | **$0.00/month** | Forever |

No credit card required. No surprise charges. Completely free.

---

## Alternative: Cloud Deployment

If you prefer not to run locally, consider:

### Railway.app ($5/month credit, ~$3/month usage)
- Deploy from GitHub
- Stable URL
- Auto-scaling
- Easy setup

### Render.com (FREE tier)
- Free web services
- Auto-deploy from GitHub
- Sleeps after 15min inactivity

### Oracle Cloud (Always Free)
- 2 free VMs forever
- More complex setup
- Full control

But honestly, **Cloudflare Tunnel is the best option** for your use case:
- Runs on your current machine (no new server needed)
- Zero cost forever
- Works immediately
- Production-ready

---

## FAQ

**Q: Does the tunnel stay running if I close the terminal?**
A: No, you need to keep the terminal open or run it as a service.

**Q: Can I use this in production?**
A: Yes! Cloudflare Tunnel is production-grade and used by major companies.

**Q: What if my internet goes down?**
A: The tunnel will reconnect automatically when internet is restored.

**Q: How much bandwidth do I get?**
A: Unlimited! No bandwidth limits on Cloudflare Tunnel.

**Q: Can I run multiple tunnels?**
A: Yes, you can create multiple tunnels for different services.

**Q: Is there a rate limit on interactions?**
A: Discord limits to ~5 interactions/second/user. Cloudflare has no limits.

**Q: Can I monitor tunnel status?**
A: Yes, use `cloudflared tunnel info catalyst-bot` to see status.

---

## Next Steps

1. ✅ Install cloudflared
2. ✅ Start Quick Tunnel
3. ✅ Start interaction server
4. ✅ Configure Discord endpoint
5. ✅ Start bot
6. ✅ Test admin report buttons

You're all set! Enjoy your interactive admin controls with zero cost. 🚀

---

**Need help?** Check the logs:
- Tunnel: Terminal where cloudflared is running
- Server: Terminal where interaction_server.py is running
- Bot: `data/logs/bot.jsonl`

**Still stuck?** Create an issue on GitHub with your logs.
