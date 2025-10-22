# Quick Start Guide - Cloudflare Worker

Get your Discord Interactions Worker running in 10 minutes.

## Prerequisites

- Cloudflare account (free)
- Discord application public key
- Discord bot token
- Node.js installed

## 5-Step Deployment

### 1. Install Wrangler

```bash
npm install -g wrangler
wrangler login
```

### 2. Navigate and Install

```bash
cd workers/interactions
npm install
```

### 3. Set Secrets

```bash
wrangler secret put DISCORD_PUBLIC_KEY
# Paste your public key

wrangler secret put DISCORD_BOT_TOKEN
# Paste your bot token
```

### 4. Deploy

```bash
npm run deploy
```

Copy the worker URL from output.

### 5. Configure Discord

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your app
3. General Information → Interactions Endpoint URL
4. Paste: `https://your-worker.workers.dev/interactions`
5. Save Changes (Discord will verify)

✅ Done! Your worker is live.

## Common Commands

```bash
# Deploy to production
npm run deploy

# Monitor logs in real-time
npm run tail

# Test locally
npm run dev

# Check health
curl https://your-worker.workers.dev/health
```

## Testing

### Test Button Click

1. Send message with buttons
2. Click a button
3. Check logs: `npm run tail`

### Test Slash Command

1. Use `/check AAPL` in Discord
2. Check logs for request
3. Verify response

## Troubleshooting

### Discord Verification Fails

```bash
# 1. Check secrets are set
wrangler secret list

# 2. Verify URL is correct
# Must be: https://your-worker.workers.dev/interactions

# 3. Check logs
npm run tail
```

### Invalid Signature

```bash
# Re-set the public key
wrangler secret put DISCORD_PUBLIC_KEY

# Redeploy
npm run deploy
```

## Next Steps

- [ ] Test all interaction types
- [ ] Monitor logs for 24 hours
- [ ] Set up dashboard alerts
- [ ] Update documentation with your URL
- [ ] Consider custom domain
- [ ] Plan for scaling

## Resources

- [Full README](./README.md)
- [Deployment Guide](./DEPLOYMENT_GUIDE.md)
- [Migration Comparison](../MIGRATION_COMPARISON.md)
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)

## Support

Issues? Check:

1. Worker logs: `npm run tail`
2. Health endpoint: `curl https://your-worker.workers.dev/health`
3. Discord Developer Portal errors
4. Cloudflare dashboard: [dash.cloudflare.com](https://dash.cloudflare.com)

---

**Total time**: ~10 minutes
**Cost**: $0/month (free tier)
**Availability**: 99.99%+
**Latency**: <50ms globally
