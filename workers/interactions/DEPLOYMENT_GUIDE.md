# Cloudflare Worker Deployment Guide

Step-by-step guide to deploy the Discord Interactions Worker for Catalyst Bot.

## Prerequisites Checklist

- [ ] Cloudflare account (free tier is fine)
- [ ] Discord application created
- [ ] Discord public key (from Developer Portal)
- [ ] Discord bot token (from Developer Portal)
- [ ] Node.js v16+ installed
- [ ] npm or yarn installed

## Step 1: Install Wrangler

```bash
# Install globally
npm install -g wrangler

# Or use npx (no global install)
npx wrangler --version
```

## Step 2: Authenticate

```bash
# Login to Cloudflare
wrangler login
```

This opens a browser window. Authenticate and return to terminal.

## Step 3: Install Dependencies

```bash
# Navigate to worker directory
cd workers/interactions

# Install dependencies
npm install
```

## Step 4: Configure Secrets

```bash
# Set Discord public key
wrangler secret put DISCORD_PUBLIC_KEY
# When prompted, paste your Discord public key from Developer Portal

# Set Discord bot token
wrangler secret put DISCORD_BOT_TOKEN
# When prompted, paste your Discord bot token from Developer Portal
```

**Important**: These secrets are encrypted and stored securely. Never commit them to git!

## Step 5: Test Locally (Optional but Recommended)

```bash
# Start local dev server
npm run dev

# In another terminal, test health endpoint
curl http://localhost:8787/health

# Expected: {"status":"healthy"}
```

## Step 6: Deploy to Production

```bash
# Deploy
npm run deploy

# Note the worker URL from output:
# https://catalyst-bot-interactions.<your-subdomain>.workers.dev
```

## Step 7: Configure Discord

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Go to **General Information**
4. Find **Interactions Endpoint URL**
5. Enter: `https://catalyst-bot-interactions.<your-subdomain>.workers.dev/interactions`
6. Click **Save Changes**

Discord will verify the endpoint by sending a PING. If successful, you'll see a green checkmark.

## Step 8: Verify Deployment

```bash
# Monitor logs
npm run tail

# In Discord, test a slash command or button
# You should see logs appear in real-time
```

## Step 9: Test Interactions

### Test with Button Click

1. Send a message with buttons using your bot
2. Click a button
3. Check logs: `npm run tail`
4. Verify the worker responds correctly

### Test with Slash Command

1. Use a slash command in Discord (e.g., `/check AAPL`)
2. Check logs for request
3. Verify response appears in Discord

## Troubleshooting

### Discord Verification Fails

**Symptom**: Discord shows "The URL did not respond with a valid interaction response"

**Solutions**:
1. Check worker URL is correct (includes `/interactions`)
2. Verify DISCORD_PUBLIC_KEY is set: `wrangler secret list`
3. Check logs: `npm run tail`
4. Test health endpoint: `curl https://your-worker.workers.dev/health`

### Invalid Signature Errors

**Symptom**: Logs show "Invalid Discord signature"

**Solutions**:
1. Verify DISCORD_PUBLIC_KEY matches Discord Developer Portal
2. Redeploy after setting secrets: `npm run deploy`
3. Check Discord public key for typos

### 404 Errors

**Symptom**: Discord gets 404 when hitting endpoint

**Solutions**:
1. Verify URL includes `/interactions` path
2. Check worker is deployed: `wrangler deployments list`
3. Test root endpoint: `curl https://your-worker.workers.dev/`

### Worker Timeout

**Symptom**: Requests timeout or return 524 errors

**Solutions**:
1. Check for infinite loops in code
2. Add timeouts to external API calls
3. Review logs for errors: `npm run tail`

## Post-Deployment

### Monitor Performance

```bash
# Real-time logs
npm run tail

# View in dashboard
# https://dash.cloudflare.com > Workers & Pages > catalyst-bot-interactions
```

### Update Worker

```bash
# Make code changes
# Then redeploy
npm run deploy
```

### Rotate Secrets

```bash
# Update a secret
wrangler secret put DISCORD_BOT_TOKEN

# Deploy to apply changes
npm run deploy
```

### Rollback Deployment

```bash
# List recent deployments
wrangler deployments list

# Rollback to previous version
wrangler rollback <deployment-id>
```

## Production Checklist

Before going live:

- [ ] Worker deployed successfully
- [ ] Discord endpoint URL configured
- [ ] Discord verification successful (green checkmark)
- [ ] Tested button clicks work
- [ ] Tested slash commands work
- [ ] Logs monitoring setup (bookmark dashboard)
- [ ] Secrets properly configured
- [ ] Health endpoint responds correctly
- [ ] Error handling tested
- [ ] Documentation reviewed

## Maintenance

### Regular Tasks

- **Weekly**: Check worker analytics for errors
- **Monthly**: Review logs for issues
- **Quarterly**: Update wrangler: `npm install -g wrangler@latest`

### Monitoring

Set up alerts in Cloudflare Dashboard:
1. Go to Workers & Pages > catalyst-bot-interactions
2. Click "Metrics & Analytics"
3. Set up email alerts for errors

## Cost Estimate

Cloudflare Workers Free Tier:
- **Requests**: 100,000 per day
- **CPU time**: 10ms per request
- **Total**: $0/month

For typical Discord bot usage (~1,000 interactions/day), the free tier is sufficient.

If you exceed limits:
- **Paid plan**: $5/month for 10M requests
- [Pricing details](https://developers.cloudflare.com/workers/platform/pricing/)

## Migration from Flask

If migrating from `scripts/interaction_server.py`:

1. Deploy worker (steps above)
2. Test worker with health endpoint
3. Update Discord endpoint URL to worker
4. Monitor for 24 hours
5. If stable, shut down Flask server
6. Update documentation/configs

**Rollback plan**: Keep Flask server running for 1 week after migration, just in case.

## Advanced Setup

### Custom Domain

To use `interactions.yourdomain.com` instead of `.workers.dev`:

1. Add domain to Cloudflare DNS
2. Update `wrangler.toml`:
   ```toml
   routes = [
     { pattern = "interactions.yourdomain.com/*", zone_name = "yourdomain.com" }
   ]
   ```
3. Deploy: `npm run deploy`

### Staging Environment

Create a staging worker for testing:

1. Update `wrangler.toml`:
   ```toml
   [env.staging]
   name = "catalyst-bot-interactions-staging"
   ```

2. Deploy staging: `npm run deploy:staging`

3. Use staging URL in a test Discord application

## Support

- **Cloudflare Workers Docs**: https://developers.cloudflare.com/workers/
- **Discord API Docs**: https://discord.com/developers/docs
- **Wrangler Docs**: https://developers.cloudflare.com/workers/wrangler/

## Next Steps

After successful deployment:

1. Monitor logs for 24-48 hours
2. Test all interaction types thoroughly
3. Update documentation with your specific worker URL
4. Consider adding custom domain
5. Set up monitoring/alerts
6. Plan for scaling (if needed)

Congratulations! Your Discord Interactions Worker is now live! 🎉
