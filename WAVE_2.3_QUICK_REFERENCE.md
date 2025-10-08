# WAVE 2.3: Quick Reference Card

Quick reference for common deployment and monitoring tasks.

## Installation (One-Time Setup)

```cmd
# 1. Install NSSM (as Administrator)
choco install nssm -y

# 2. Install bot as service (as Administrator)
install_service.bat

# 3. Start service
net start CatalystBot
```

## Daily Operations

### Service Management

```cmd
# Start
net start CatalystBot

# Stop
net stop CatalystBot

# Restart
restart_service.bat

# Check status
nssm status CatalystBot
```

### Health Checks

```bash
# Quick ping
curl http://localhost:8080/health/ping

# Detailed status
curl http://localhost:8080/health/detailed

# External check (via tunnel)
curl https://your-tunnel.trycloudflare.com/health/ping
```

### View Logs

```cmd
# All logs (last 50 lines)
powershell "Get-Content data\logs\bot.jsonl -Tail 50"

# Errors only
type data\logs\errors.log

# Health logs
type data\logs\health.log

# Service logs
type data\logs\service_stderr.log
```

## Deployment

### Before Deploying

```bash
# 1. Backup config
python -m catalyst_bot.deployment backup

# 2. Tag release
python -m catalyst_bot.deployment tag v1.2.3
```

### Deploy Steps

```cmd
# 1. Stop
net stop CatalystBot

# 2. Update code
git pull origin main

# 3. Update dependencies
.venv\Scripts\activate
pip install -r requirements.txt

# 4. Start
net start CatalystBot

# 5. Verify
curl http://localhost:8080/health/ping
```

### Rollback

```cmd
# Interactive rollback
rollback.bat

# Or direct
python -m catalyst_bot.deployment rollback v1.2.2
```

## Monitoring

### Local Monitoring

```bash
# Service status
nssm status CatalystBot

# Deployment info
python -m catalyst_bot.deployment info

# Recent tags
python -m catalyst_bot.deployment list-tags
```

### External Monitoring

- **UptimeRobot Dashboard:** https://uptimerobot.com/dashboard
- **Public Status Page:** https://stats.uptimerobot.com/your-slug
- **Health Endpoint:** https://your-tunnel.trycloudflare.com/health/ping

## Troubleshooting

### Service Won't Start

```cmd
# Check configuration
nssm get CatalystBot Application
nssm get CatalystBot AppDirectory

# View errors
type data\logs\service_stderr.log

# Test manually
.venv\Scripts\python -m catalyst_bot.runner --once
```

### Health Endpoint Down

```cmd
# Check if service running
nssm status CatalystBot

# Check port
netstat -an | findstr :8080

# Restart service
net stop CatalystBot
net start CatalystBot
```

### Bot Frozen

```cmd
# Restart
restart_service.bat

# Or if watchdog enabled
# It will auto-restart
```

## Configuration Files

### `.env` Settings

```ini
# Health monitoring
HEALTH_CHECK_ENABLED=1
HEALTH_CHECK_PORT=8080

# Watchdog (optional)
WATCHDOG_ENABLED=0

# Logging
LOG_ROTATION_DAYS=7
```

### Key Directories

```
data/
  logs/              # All log files
    bot.jsonl        # Main log
    errors.log       # Errors only
    health.log       # Health monitoring
    service_*.log    # Service logs
  backups/           # Config backups
out/
  approvals/         # Deployment approvals
```

## Emergency Procedures

### Bot Crashed

1. Check logs: `type data\logs\service_stderr.log`
2. Service restarts automatically (wait 10 seconds)
3. If still down: `net start CatalystBot`
4. If persistent: `rollback.bat`

### Bad Deployment

1. Stop: `net stop CatalystBot`
2. Rollback: `rollback.bat`
3. Restore config: `copy .env.backup .env`
4. Start: `net start CatalystBot`

### Lost Configuration

1. Check backup: `dir backups\env_backup_*.env /OD`
2. Restore: `copy backups\env_backup_YYYYMMDD_HHMMSS.env .env`
3. Restart: `restart_service.bat`

## Useful Commands

```cmd
# Service management
nssm status CatalystBot              # Check status
nssm restart CatalystBot             # Restart via NSSM
nssm get CatalystBot *               # View all settings

# Deployment
python -m catalyst_bot.deployment backup              # Backup config
python -m catalyst_bot.deployment tag v1.2.3         # Tag release
python -m catalyst_bot.deployment list-tags          # List tags
python -m catalyst_bot.deployment rollback v1.2.2    # Rollback
python -m catalyst_bot.deployment info               # Current info

# Watchdog (if enabled)
python -m catalyst_bot.watchdog      # Run watchdog manually
run_watchdog.bat                     # Run with auto-restart

# Logs
type data\logs\bot.jsonl | findstr ERROR                    # Find errors
powershell "Get-Content data\logs\bot.jsonl -Tail 100"     # Last 100 lines
```

## Health Status Codes

- `200 OK` - Bot is healthy
- `503 Service Unavailable` - Bot is degraded/down
- `Connection refused` - Bot is not running

## Common Issues

| Issue | Quick Fix |
|-------|-----------|
| Service won't start | Check `service_stderr.log`, verify `.env` exists |
| Health endpoint timeout | Restart service, check port 8080 |
| UptimeRobot shows down | Restart Cloudflare tunnel, verify health locally |
| High memory usage | Restart service: `restart_service.bat` |
| Bot frozen | Service auto-restarts, or enable watchdog |

## Documentation

- **Full Guide:** `WAVE_2.3_SUMMARY.md`
- **Deployment:** `DEPLOYMENT_CHECKLIST.md`
- **UptimeRobot:** `UPTIMEROBOT_SETUP.md`
- **NSSM Setup:** `NSSM_INSTALLATION.md`

## Support

- **Logs:** `data/logs/`
- **Health:** `http://localhost:8080/health/detailed`
- **Status:** `https://your-tunnel.trycloudflare.com/health/ping`

---

**Print this for quick access during operations!**
