# Catalyst Bot - Discord Interactions Worker

This Cloudflare Worker handles Discord interaction callbacks (button clicks, slash commands) for the Catalyst Bot. It provides a serverless, globally distributed endpoint for Discord interactions with low latency and high availability.

## Overview

The worker handles three types of Discord interactions:

1. **PING (Type 1)**: Discord endpoint verification
2. **APPLICATION_COMMAND (Type 2)**: Slash commands like `/check`, `/admin`, etc.
3. **MESSAGE_COMPONENT (Type 3)**: Button clicks on chart timeframe selectors

## Features

- ✅ Ed25519 signature verification for security
- ✅ PING response for Discord endpoint verification
- ✅ Button click handling (chart timeframe switches)
- ✅ Slash command routing
- ✅ Health check endpoint
- ✅ Error handling with user-friendly messages
- ✅ Globally distributed via Cloudflare's edge network

## Prerequisites

1. **Cloudflare Account**: Free account at [cloudflare.com](https://cloudflare.com)
2. **Node.js**: v16 or higher
3. **npm or yarn**: Package manager
4. **Discord Application**: Bot with public key and bot token

## Installation

### 1. Install Wrangler CLI

Wrangler is Cloudflare's command-line tool for managing Workers.

```bash
# Using npm
npm install -g wrangler

# Using yarn
yarn global add wrangler

# Verify installation
wrangler --version
```

### 2. Authenticate with Cloudflare

```bash
wrangler login
```

This will open a browser window to authenticate with your Cloudflare account.

### 3. Configure Secrets

Set your Discord credentials as encrypted secrets:

```bash
# Navigate to the worker directory
cd workers/interactions

# Set Discord public key (from Discord Developer Portal)
wrangler secret put DISCORD_PUBLIC_KEY
# Paste your public key when prompted

# Set Discord bot token (from Discord Developer Portal)
wrangler secret put DISCORD_BOT_TOKEN
# Paste your bot token when prompted
```

**Important**: Never commit secrets to git! Use `wrangler secret put` to set them securely.

## Deployment

### Deploy to Production

```bash
# From workers/interactions directory
wrangler deploy
```

After deployment, Wrangler will output your worker URL:
```
Published catalyst-bot-interactions (1.23 sec)
  https://catalyst-bot-interactions.<your-subdomain>.workers.dev
```

### Deploy to Staging (Optional)

You can create a staging environment for testing:

```bash
# Create a staging version
wrangler deploy --env staging
```

To use environments, add this to `wrangler.toml`:

```toml
[env.staging]
name = "catalyst-bot-interactions-staging"
vars = { ENVIRONMENT = "staging" }
```

## Configuration

### Update Discord Application

After deploying, configure your Discord application to use the worker URL:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Navigate to **General Information**
4. Set **Interactions Endpoint URL** to:
   ```
   https://catalyst-bot-interactions.<your-subdomain>.workers.dev/interactions
   ```
5. Click **Save Changes**

Discord will send a PING to verify the endpoint. If the worker is configured correctly, the verification will succeed.

### Environment Variables

Configure non-secret environment variables in `wrangler.toml`:

```toml
[vars]
ENVIRONMENT = "production"
LOG_LEVEL = "info"
```

## Local Development

### Run Locally

Test the worker locally before deploying:

```bash
# Start local dev server
wrangler dev

# The worker will be available at http://localhost:8787
```

**Note**: Discord cannot send requests to localhost. For local testing with Discord, use a tunnel service like [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/) or [ngrok](https://ngrok.com/).

### Local Testing with Cloudflare Tunnel

```bash
# Install cloudflared
# See: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

# Run tunnel
cloudflared tunnel --url http://localhost:8787

# Use the provided URL in Discord's Interactions Endpoint URL
```

### Testing with curl

```bash
# Health check
curl https://catalyst-bot-interactions.<your-subdomain>.workers.dev/health

# Expected response:
# {"status":"healthy"}
```

## Testing Discord Interactions

### Verify Endpoint

Discord will automatically test the endpoint when you save the Interactions Endpoint URL. It sends a PING (type 1) and expects a PONG response.

### Test Button Clicks

1. Deploy a message with buttons using your bot
2. Click a button
3. Check the worker logs:
   ```bash
   wrangler tail
   ```

### Test Slash Commands

1. Register slash commands in Discord Developer Portal
2. Use a command in Discord (e.g., `/check AAPL`)
3. Monitor logs with `wrangler tail`

## Monitoring and Logs

### View Real-Time Logs

```bash
wrangler tail
```

This streams live logs from your worker. Keep it running while testing interactions.

### Filter Logs

```bash
# Filter by status code
wrangler tail --status ok

# Filter by method
wrangler tail --method POST

# Filter by search term
wrangler tail --search "error"
```

### Cloudflare Dashboard

View detailed analytics and logs at:
- Analytics: [Cloudflare Dashboard > Workers & Pages](https://dash.cloudflare.com/?to=/:account/workers)
- Logs: Click on your worker > Logs

## Worker Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Info page showing worker is running |
| `/interactions` | POST | Discord interaction callback handler |
| `/health` | GET | Health check endpoint |

## Security

### Signature Verification

The worker verifies every incoming request using Discord's Ed25519 signature verification:

1. Extracts `X-Signature-Ed25519` and `X-Signature-Timestamp` headers
2. Reconstructs the signed message (`timestamp + body`)
3. Verifies signature using Discord public key
4. Rejects requests with invalid signatures (401 Unauthorized)

**Never disable signature verification in production!**

### Secrets Management

- Secrets are encrypted at rest by Cloudflare
- Accessible only to the worker via `env.SECRET_NAME`
- Not visible in wrangler.toml or logs
- Rotatable using `wrangler secret put`

### Rate Limiting

Cloudflare Workers automatically handle DDoS protection. For additional rate limiting, consider using [Cloudflare Rate Limiting](https://developers.cloudflare.com/waf/rate-limiting-rules/).

## Troubleshooting

### "Invalid signature" errors

**Cause**: Discord public key is incorrect or not set

**Solution**:
```bash
wrangler secret put DISCORD_PUBLIC_KEY
# Verify the key from Discord Developer Portal > General Information
```

### "DISCORD_PUBLIC_KEY not configured"

**Cause**: Secret not set or worker not redeployed after setting secret

**Solution**:
```bash
wrangler secret put DISCORD_PUBLIC_KEY
wrangler deploy
```

### Discord endpoint verification fails

**Cause**: Worker not responding correctly to PING

**Solution**:
1. Check worker logs: `wrangler tail`
2. Test health endpoint: `curl https://your-worker.workers.dev/health`
3. Verify PING response returns `{"type":1}`

### 404 on /interactions

**Cause**: Discord is sending to wrong URL or route not configured

**Solution**:
- Verify Discord Interactions Endpoint URL includes `/interactions` path
- Check worker logs to see what path Discord is hitting

### Worker crashes or timeouts

**Cause**: Synchronous blocking operations or infinite loops

**Solution**:
- Use `async/await` for all I/O operations
- Add timeouts to external API calls
- Check logs for errors: `wrangler tail`

## Migration from Flask Server

If you're migrating from the Flask-based `scripts/interaction_server.py`:

1. **Deploy worker** as described above
2. **Update Discord endpoint URL** to worker URL
3. **Test interactions** thoroughly
4. **Monitor logs** for any errors
5. **Shut down Flask server** once worker is stable

### Benefits of Worker vs Flask

| Feature | Cloudflare Worker | Flask Server |
|---------|-------------------|--------------|
| **Latency** | ~10ms globally | Varies by location |
| **Availability** | 99.99%+ SLA | Depends on hosting |
| **Scaling** | Automatic | Manual |
| **Cost** | Free tier: 100k req/day | Server costs |
| **Maintenance** | Minimal | Server upkeep |
| **Cold starts** | None | Depends on setup |

## Advanced Configuration

### Custom Domain

Use your own domain instead of `.workers.dev`:

1. Add domain to Cloudflare
2. Update `wrangler.toml`:
   ```toml
   routes = [
     { pattern = "interactions.yourdomain.com/*", zone_name = "yourdomain.com" }
   ]
   ```
3. Deploy: `wrangler deploy`

### Multiple Environments

Support dev/staging/production:

```toml
# wrangler.toml
[env.dev]
name = "catalyst-bot-interactions-dev"
vars = { ENVIRONMENT = "development" }

[env.staging]
name = "catalyst-bot-interactions-staging"
vars = { ENVIRONMENT = "staging" }

[env.production]
name = "catalyst-bot-interactions"
vars = { ENVIRONMENT = "production" }
```

Deploy to specific environment:
```bash
wrangler deploy --env staging
```

### Durable Objects (Advanced)

For stateful operations (session tracking, rate limiting), consider using [Durable Objects](https://developers.cloudflare.com/workers/learning/using-durable-objects/).

## Performance Tips

1. **Keep responses fast**: Target <50ms response time
2. **Use async operations**: Always `await` I/O calls
3. **Minimize external API calls**: Cache when possible
4. **Defer heavy work**: Use webhooks for time-consuming tasks
5. **Monitor CPU time**: Stay under limits (10ms free, 50ms paid)

## Resources

- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Discord Interactions API](https://discord.com/developers/docs/interactions/receiving-and-responding)
- [Wrangler CLI Reference](https://developers.cloudflare.com/workers/wrangler/commands/)
- [Discord Developer Portal](https://discord.com/developers/applications)

## Support

For issues or questions:

1. Check worker logs: `wrangler tail`
2. Review Discord Developer Portal errors
3. Test health endpoint
4. Check Cloudflare Workers dashboard

## License

Same license as main Catalyst Bot project.
