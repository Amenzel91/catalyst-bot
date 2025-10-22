# Catalyst Bot - Cloudflare Workers

This directory contains Cloudflare Workers for the Catalyst Bot, providing serverless, edge-deployed infrastructure for handling Discord interactions and other real-time operations.

## Overview

Cloudflare Workers run on Cloudflare's global edge network (250+ locations), providing:

- **Ultra-low latency**: <50ms response times globally
- **Infinite scaling**: Automatically handles traffic spikes
- **Zero maintenance**: No servers to manage
- **High availability**: 99.99%+ uptime SLA
- **Cost-effective**: Free tier covers most use cases

## Available Workers

### 1. Interactions Worker (`interactions/`)

Handles Discord interaction callbacks (button clicks, slash commands).

**Purpose**: Replace the Flask-based `scripts/interaction_server.py` with a globally distributed, serverless solution.

**Features**:
- ✅ Ed25519 signature verification
- ✅ PING response for Discord verification
- ✅ MESSAGE_COMPONENT handling (button clicks)
- ✅ APPLICATION_COMMAND handling (slash commands)
- ✅ Health check endpoint
- ✅ Comprehensive error handling

**Quick Start**:
```bash
cd interactions
npm install
wrangler login
wrangler secret put DISCORD_PUBLIC_KEY
wrangler secret put DISCORD_BOT_TOKEN
npm run deploy
```

**Documentation**:
- [Quick Start Guide](./interactions/QUICK_START.md) - 10-minute setup
- [Full README](./interactions/README.md) - Comprehensive guide
- [Deployment Guide](./interactions/DEPLOYMENT_GUIDE.md) - Step-by-step deployment
- [Migration Comparison](./MIGRATION_COMPARISON.md) - Flask vs Worker analysis

## Architecture

```
Discord API
    │
    ↓ HTTPS
Cloudflare Edge Network
    │
    ├─→ Interactions Worker (POST /interactions)
    │   ├─ Signature verification
    │   ├─ PING handling
    │   ├─ Button click routing
    │   └─ Slash command routing
    │
    └─→ Backend Service (Python) [Optional]
        ├─ Chart generation
        ├─ Data analysis
        ├─ LLM operations
        └─ Database queries
```

## When to Use Workers

**✅ Good Use Cases**:
- Discord interaction endpoints (low latency critical)
- Webhook handlers
- API gateways and routing
- Edge caching and content delivery
- Real-time data transformation
- Authentication and authorization

**❌ Not Ideal For**:
- Long-running processes (>50ms CPU time)
- Heavy computational tasks
- Large file processing
- Complex database queries
- Operations requiring Python-specific libraries

**💡 Hybrid Approach** (Recommended for Catalyst Bot):
- **Worker**: Handle edge operations (signature verification, routing, quick responses)
- **Backend**: Handle complex operations (chart generation, data analysis, LLM calls)

## Project Structure

```
workers/
├── README.md                      # This file
├── MIGRATION_COMPARISON.md        # Flask vs Worker comparison
│
└── interactions/                  # Discord Interactions Worker
    ├── index.js                   # Main worker code
    ├── wrangler.toml              # Cloudflare configuration
    ├── package.json               # Dependencies and scripts
    ├── .gitignore                 # Git ignore rules
    ├── README.md                  # Full documentation
    ├── QUICK_START.md             # 10-minute setup guide
    ├── DEPLOYMENT_GUIDE.md        # Step-by-step deployment
    └── test-worker.js             # Local testing script
```

## Getting Started

### Prerequisites

1. **Cloudflare Account**: Sign up at [cloudflare.com](https://cloudflare.com) (free tier available)
2. **Node.js**: v16 or higher
3. **npm or yarn**: Package manager
4. **Discord Application**: Public key and bot token from [Discord Developer Portal](https://discord.com/developers/applications)

### Quick Setup (All Workers)

```bash
# Install Wrangler CLI globally
npm install -g wrangler

# Authenticate with Cloudflare
wrangler login

# Navigate to specific worker and follow its README
cd interactions/
```

## Common Commands

```bash
# Deploy a worker
cd <worker-directory>
npm run deploy

# Monitor logs in real-time
npm run tail

# Test locally
npm run dev

# List deployments
wrangler deployments list

# Rollback to previous version
wrangler rollback <deployment-id>
```

## Cost Breakdown

### Free Tier Limits

| Resource | Free Tier | Typical Bot Usage | Sufficient? |
|----------|-----------|-------------------|-------------|
| Requests/day | 100,000 | ~1,000-5,000 | ✅ Yes |
| CPU time | 10ms/request | 1-5ms/request | ✅ Yes |
| Request duration | 30 seconds | <1 second | ✅ Yes |
| Edge storage (KV) | 1 GB | <100 MB | ✅ Yes |

**Verdict**: Free tier is sufficient for most Discord bots.

### Paid Tier ($5/month)

- **10 million requests** per month
- **50ms CPU time** per request
- **Priority support**
- **Custom domains**

[Full pricing details](https://developers.cloudflare.com/workers/platform/pricing/)

## Performance Benchmarks

### Interactions Worker

| Metric | Flask Server | Cloudflare Worker | Improvement |
|--------|--------------|-------------------|-------------|
| **Response Time** | 73-357ms | 3-20ms | **10-100x faster** |
| **Availability** | 99% (estimated) | 99.99%+ | **Better SLA** |
| **Cold Start** | 1-5 seconds | None | **Instant** |
| **Global Latency** | Varies | <50ms | **Consistent** |

See [MIGRATION_COMPARISON.md](./MIGRATION_COMPARISON.md) for detailed analysis.

## Security

### Signature Verification

All interactions are verified using Ed25519 signatures before processing:

1. Discord signs each request with your application's private key
2. Worker verifies using the public key
3. Invalid signatures are rejected (401 Unauthorized)

**Never disable signature verification in production!**

### Secrets Management

Sensitive credentials are stored as encrypted secrets:

```bash
# Set a secret
wrangler secret put SECRET_NAME

# List secrets (values are hidden)
wrangler secret list

# Delete a secret
wrangler secret delete SECRET_NAME
```

Secrets are:
- ✅ Encrypted at rest
- ✅ Only accessible to the worker
- ✅ Not visible in code or logs
- ✅ Rotatable without code changes

## Monitoring

### Real-Time Logs

```bash
# View live logs
cd <worker-directory>
npm run tail

# Filter by status
wrangler tail --status ok
wrangler tail --status error

# Filter by method
wrangler tail --method POST
```

### Dashboard Analytics

View metrics at [Cloudflare Dashboard](https://dash.cloudflare.com):

1. Navigate to **Workers & Pages**
2. Select your worker
3. View:
   - Requests per second
   - Error rates
   - CPU time distribution
   - 99th percentile latency

### Alerts

Set up email/webhook alerts for:
- Error rate thresholds
- Request volume spikes
- Downtime events

## Best Practices

### Performance

1. **Keep CPU time low**: Aim for <10ms per request
2. **Use async operations**: Always `await` I/O calls
3. **Cache aggressively**: Use Workers KV for frequently accessed data
4. **Minimize external calls**: Batch requests when possible
5. **Defer heavy work**: Use deferred responses for time-consuming tasks

### Reliability

1. **Handle errors gracefully**: Always return valid Discord responses
2. **Implement timeouts**: Add timeouts to external API calls
3. **Log appropriately**: Log errors, but avoid excessive logging
4. **Test thoroughly**: Use staging environment before production
5. **Monitor continuously**: Set up alerts for anomalies

### Security

1. **Always verify signatures**: Never skip Discord signature verification
2. **Validate input**: Sanitize user input before processing
3. **Use secrets properly**: Never commit secrets to git
4. **Rate limit**: Implement rate limiting for abuse prevention
5. **Keep dependencies updated**: Update Wrangler regularly

## Development Workflow

### Local Development

```bash
# Start local dev server
npm run dev

# In another terminal, test
curl http://localhost:8787/health
```

### Testing with Discord

Since Discord can't reach localhost, use Cloudflare Tunnel:

```bash
# Terminal 1: Start worker
npm run dev

# Terminal 2: Expose via tunnel
cloudflared tunnel --url http://localhost:8787

# Use tunnel URL in Discord Developer Portal
```

### Deployment

```bash
# Deploy to production
npm run deploy

# Deploy to staging (if configured)
npm run deploy:staging

# Monitor deployment
npm run tail
```

## Troubleshooting

### Common Issues

#### "Invalid signature" errors

**Solution**: Verify `DISCORD_PUBLIC_KEY` matches Discord Developer Portal

```bash
wrangler secret put DISCORD_PUBLIC_KEY
npm run deploy
```

#### Discord verification fails

**Solution**: Check URL includes `/interactions` and worker is deployed

```bash
# Test health endpoint
curl https://your-worker.workers.dev/health

# Check logs
npm run tail
```

#### Worker not updating

**Solution**: Redeploy and clear cache

```bash
npm run deploy
# Wait 30 seconds for global propagation
```

## Migration Guides

### From Flask to Worker

See [MIGRATION_COMPARISON.md](./MIGRATION_COMPARISON.md) for:
- Feature comparison
- Performance benchmarks
- Cost analysis
- Step-by-step migration plan
- Rollback procedures

**Recommended approach**: Hybrid (Worker for edge, Flask/Python for complex logic)

## Future Workers

Potential additional workers for Catalyst Bot:

1. **Market Data Worker**: Real-time stock price updates
2. **Webhook Proxy**: Intelligent routing for Discord webhooks
3. **Chart CDN**: Serve cached charts from edge
4. **Analytics Worker**: Real-time bot analytics collection
5. **Rate Limiter**: Distributed rate limiting for API calls

## Resources

### Documentation

- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Wrangler CLI Reference](https://developers.cloudflare.com/workers/wrangler/commands/)
- [Discord Interactions API](https://discord.com/developers/docs/interactions/receiving-and-responding)
- [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)

### Tools

- [Wrangler CLI](https://github.com/cloudflare/workers-sdk)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Discord Developer Portal](https://discord.com/developers/applications)

### Community

- [Cloudflare Workers Discord](https://discord.gg/cloudflaredev)
- [Cloudflare Community Forum](https://community.cloudflare.com/c/developers/workers/)

## Contributing

When adding new workers:

1. Create a new directory in `workers/`
2. Include `README.md`, `wrangler.toml`, and `.gitignore`
3. Add documentation links to this file
4. Test thoroughly in staging
5. Update cost estimates and monitoring

## Support

For issues:

1. Check worker logs: `npm run tail`
2. Review documentation in worker directory
3. Check Cloudflare Dashboard for errors
4. Consult [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)

## License

Same license as main Catalyst Bot project.
