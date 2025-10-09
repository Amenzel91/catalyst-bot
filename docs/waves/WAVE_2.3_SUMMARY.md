# WAVE 2.3: 24/7 Deployment Infrastructure - Implementation Summary

This document summarizes the implementation of WAVE 2.3 deployment infrastructure for Catalyst-Bot.

## Overview

WAVE 2.3 introduces production-ready deployment capabilities including:
- Windows service integration with auto-restart
- Enhanced health monitoring with detailed metrics
- Watchdog process for automatic recovery
- External monitoring integration (UptimeRobot)
- Safe deployment and rollback procedures
- Enhanced logging with rotation

## Files Created

### 1. Service Management (Windows)

#### `install_service.bat`
- Installs Catalyst-Bot as a Windows service using NSSM
- Checks for NSSM installation, installs via Chocolatey if missing
- Configures auto-restart on failure
- Sets up logging to `data/logs/service_*.log`
- Configures service to start on boot
- **Usage:** Right-click → Run as Administrator

#### `uninstall_service.bat`
- Stops and removes the CatalystBot service
- Preserves data and logs
- **Usage:** Right-click → Run as Administrator

#### `restart_service.bat`
- Restarts the CatalystBot service gracefully
- 3-second delay for clean shutdown
- **Usage:** Right-click → Run as Administrator

### 2. Health Monitoring

#### `src/catalyst_bot/health_monitor.py` (NEW)
Enhanced health monitoring module with comprehensive metrics:

**Functions:**
- `init_health_monitor()` - Initialize at startup
- `record_cycle()` - Track successful cycles
- `record_alert()` - Track alert counts (daily/weekly)
- `record_error()` - Track error counts (hourly)
- `get_uptime()` - Bot uptime in seconds
- `get_last_cycle_time()` - Time since last cycle
- `get_error_count()` - Errors in last hour
- `get_alert_stats()` - Alert counts
- `get_gpu_stats()` - GPU utilization and VRAM
- `get_disk_stats()` - Disk space information
- `get_feature_status()` - Feature flags status
- `check_api_service()` - API service health checks
- `is_healthy()` - Simple boolean health check
- `get_health_status()` - Comprehensive health dict

**Health Status Response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "last_cycle_seconds_ago": 45,
  "cycles_today": 1200,
  "alerts_today": 23,
  "alerts_week": 145,
  "errors_last_hour": 0,
  "gpu_utilization": 35.2,
  "vram_used_mb": 384,
  "disk_free_gb": 125.3,
  "features": {
    "quickchart": true,
    "ollama": true,
    "feedback_loop": true
  },
  "services": {
    "discord": "healthy",
    "tiingo": "healthy",
    "finnhub": "healthy"
  }
}
```

#### `src/catalyst_bot/health_endpoint.py` (ENHANCED)
Enhanced with new endpoints:

**Endpoints:**
- `GET /` - Server info and endpoint list
- `GET /health/ping` - Simple "ok" response (UptimeRobot compatible)
- `GET /health` - Basic health status (backward compatible)
- `GET /health/detailed` - Comprehensive metrics from health_monitor

### 3. Watchdog Process

#### `src/catalyst_bot/watchdog.py` (NEW)
Monitors the bot and restarts if frozen or crashed:

**Features:**
- Pings health endpoint at configured intervals
- Detects frozen/unresponsive bot
- Automatic restart via Windows service
- Discord webhook alerts for admin
- Configurable thresholds and limits
- Prevents restart loops (max 3/hour)

**Configuration:**
```ini
WATCHDOG_ENABLED=0
WATCHDOG_CHECK_INTERVAL=60
WATCHDOG_RESTART_ON_FREEZE=1
WATCHDOG_FREEZE_THRESHOLD=300
WATCHDOG_MAX_RESTARTS=3
```

**Functions:**
- `check_bot_alive()` - Ping health endpoint
- `check_service_running()` - Check Windows service status
- `restart_bot()` - Restart via service or process
- `send_alert_to_admin()` - Discord webhook alerts
- `run_watchdog()` - Main monitoring loop

#### `run_watchdog.bat`
Continuously runs the watchdog process:
```cmd
run_watchdog.bat
```

### 4. Deployment & Rollback

#### `src/catalyst_bot/deployment.py` (NEW)
Safe deployment utilities:

**Functions:**
- `backup_config()` - Backup .env with timestamp
- `restore_config()` - Restore .env from backup
- `get_current_commit()` - Get current git commit
- `create_deployment_tag()` - Tag releases for tracking
- `list_deployment_tags()` - Show recent tags
- `rollback_to_tag()` - Rollback to specific tag
- `rollback_to_commit()` - Rollback to specific commit
- `get_deployment_info()` - Current deployment status

**CLI Usage:**
```bash
# Backup configuration
python -m catalyst_bot.deployment backup

# Create deployment tag
python -m catalyst_bot.deployment tag v1.2.3 --push

# List tags
python -m catalyst_bot.deployment list-tags

# Rollback
python -m catalyst_bot.deployment rollback v1.2.2

# Show current deployment
python -m catalyst_bot.deployment info
```

#### `rollback.bat`
Interactive rollback wizard:
- Lists available tags
- Shows deployment info
- Stops service
- Rolls back code
- Restores config
- Restarts service
- **Usage:** Run as Administrator

### 5. Logging Enhancements

#### `src/catalyst_bot/logging_utils.py` (ENHANCED)
Enhanced logging with rotation and separate files:

**Log Files:**
- `data/logs/bot.jsonl` - All log levels (main log)
- `data/logs/errors.log` - WARNING and above only
- `data/logs/health.log` - Health monitor specific logs
- `data/logs/service_stdout.log` - Service stdout (if using NSSM)
- `data/logs/service_stderr.log` - Service stderr (if using NSSM)

**Rotation Settings:**
- Max file size: 10MB per file
- Backup count: Configurable via `LOG_ROTATION_DAYS` (default: 7)
- Format: JSON for machine parsing, optional plain text for console

**Configuration:**
```ini
LOG_ROTATION_DAYS=7
LOG_LEVEL=INFO
LOG_PLAIN=1
```

### 6. Documentation

#### `DEPLOYMENT_CHECKLIST.md` (NEW)
Comprehensive deployment checklist covering:
- Pre-deployment verification (tests, config, dependencies)
- Step-by-step deployment procedure
- Post-deployment validation
- Rollback procedures
- Common issues and solutions
- Maintenance schedule

**Sections:**
- Pre-Deployment Verification
- Deployment Steps (1-11)
- Post-Deployment Validation
- Deployment Sign-Off
- Rollback Procedure (3 options)
- Emergency Contacts
- Common Issues and Solutions
- Version History

#### `UPTIMEROBOT_SETUP.md` (NEW)
Complete guide for external monitoring:
- What is UptimeRobot
- Step-by-step account setup
- Monitor configuration
- Discord webhook alerts
- Public status pages
- Troubleshooting
- Integration with watchdog

**Configuration Template:**
```
Monitor Name: Catalyst-Bot Health Check
Monitor Type: HTTP(s)
URL: https://your-tunnel.trycloudflare.com/health/ping
Monitoring Interval: 5 minutes
Keyword: ok
Alert Contacts: [Email, Discord webhook]
```

#### `NSSM_INSTALLATION.md` (NEW)
Complete NSSM installation guide:
- What is NSSM and why use it
- Installation via Chocolatey (recommended)
- Manual installation steps
- NSSM commands reference
- Configuration best practices
- Troubleshooting
- Alternatives to NSSM

### 7. Configuration

#### `.env` (UPDATED)
Added WAVE 2.3 settings:

```ini
# --- WAVE 2.3: 24/7 Deployment Infrastructure ---
# Health check endpoint configuration
HEALTH_CHECK_ENABLED=1
HEALTH_CHECK_PORT=8080
FEATURE_HEALTH_ENDPOINT=1

# Watchdog process monitoring
WATCHDOG_ENABLED=0
WATCHDOG_CHECK_INTERVAL=60
WATCHDOG_RESTART_ON_FREEZE=1
WATCHDOG_FREEZE_THRESHOLD=300
WATCHDOG_MAX_RESTARTS=3

# Deployment environment identifier
DEPLOYMENT_ENV=production

# Log rotation (days to keep old logs)
LOG_ROTATION_DAYS=7

# Admin alert webhook for critical notifications
ADMIN_ALERT_WEBHOOK=
```

## Installation Instructions

### 1. Install NSSM

**Option A: Via Chocolatey (Recommended)**
```powershell
# Install Chocolatey first (if needed)
# See NSSM_INSTALLATION.md for details

# Install NSSM
choco install nssm -y
```

**Option B: Manual Installation**
1. Download from https://nssm.cc/download
2. Extract and copy `nssm.exe` to `C:\Windows\System32\`

### 2. Install Bot as Service

```cmd
# Right-click and "Run as Administrator"
install_service.bat
```

This will:
- Check for NSSM
- Configure the service with auto-restart
- Set up logging
- Prompt to start immediately

### 3. Configure UptimeRobot (Optional but Recommended)

1. Follow `UPTIMEROBOT_SETUP.md`
2. Create free account at https://uptimerobot.com
3. Add monitor for `/health/ping` endpoint
4. Configure Discord webhook alerts

### 4. Enable Watchdog (Optional)

Edit `.env`:
```ini
WATCHDOG_ENABLED=1
```

Run watchdog:
```cmd
run_watchdog.bat
```

Or install as a second service (advanced).

## Usage Guide

### Starting/Stopping the Bot

**As a Service:**
```cmd
net start CatalystBot
net stop CatalystBot
restart_service.bat
```

**Check Service Status:**
```cmd
nssm status CatalystBot
```

### Health Checks

**Local Health Check:**
```bash
curl http://localhost:8080/health/ping
# Expected: ok

curl http://localhost:8080/health/detailed
# Returns comprehensive JSON metrics
```

**Remote Health Check (via Cloudflare tunnel):**
```bash
curl https://your-tunnel.trycloudflare.com/health/ping
```

### Deployment Workflow

**Before Deploying:**
```cmd
# 1. Backup configuration
python -m catalyst_bot.deployment backup

# 2. Create deployment tag
python -m catalyst_bot.deployment tag v1.2.3 --push

# 3. Review DEPLOYMENT_CHECKLIST.md
```

**Deploy:**
```cmd
# 1. Stop service
net stop CatalystBot

# 2. Pull changes
git pull origin main

# 3. Install dependencies
.venv\Scripts\activate
pip install -r requirements.txt

# 4. Start service
net start CatalystBot

# 5. Verify health
curl http://localhost:8080/health/ping
```

**If Issues Occur:**
```cmd
# Quick rollback
rollback.bat

# Or manual
python -m catalyst_bot.deployment rollback v1.2.2
```

### Viewing Logs

```cmd
# All logs
type data\logs\bot.jsonl | findstr ERROR

# Errors only
type data\logs\errors.log

# Health monitoring
type data\logs\health.log

# Service logs (if using NSSM)
type data\logs\service_stderr.log
```

### Monitoring

**Check Health Status:**
```bash
curl http://localhost:8080/health/detailed | python -m json.tool
```

**Check UptimeRobot:**
- Visit your UptimeRobot dashboard
- View public status page (if created)
- Check alert history

**Check Deployment Info:**
```bash
python -m catalyst_bot.deployment info
```

## Architecture

### Auto-Restart Flow

```
Bot Crashes/Exits
       ↓
Windows Service (NSSM) detects exit
       ↓
Waits 10 seconds (AppRestartDelay)
       ↓
Restarts bot process
       ↓
Bot initializes and resumes
```

### Watchdog Flow (Optional)

```
Watchdog pings /health/ping every 60s
       ↓
No response for 5 minutes (300s)
       ↓
Watchdog sends alert to Discord
       ↓
Watchdog restarts service via NSSM
       ↓
Waits 30s for bot to start
       ↓
Resumes monitoring
```

### Health Check Flow

```
UptimeRobot pings /health/ping every 5 min
       ↓
       ├─ "ok" response → All good
       │
       └─ No response or error
              ↓
          Wait for 2nd failed check (10 min total)
              ↓
          Send alerts via configured channels:
              - Email
              - SMS
              - Discord webhook
```

### Deployment Flow

```
1. Backup config → .env.backup
2. Create git tag → v1.x.x
3. Stop service → net stop CatalystBot
4. Pull changes → git pull
5. Update deps → pip install -r requirements.txt
6. Start service → net start CatalystBot
7. Verify health → curl /health/ping
8. Monitor for 5-10 minutes
```

## Configuration Reference

### Minimal Production Config

```ini
# Health endpoint
HEALTH_CHECK_ENABLED=1
HEALTH_CHECK_PORT=8080

# Logging
LOG_ROTATION_DAYS=7
LOG_LEVEL=INFO

# Watchdog (optional)
WATCHDOG_ENABLED=0
```

### Full Production Config

```ini
# Health monitoring
HEALTH_CHECK_ENABLED=1
HEALTH_CHECK_PORT=8080
FEATURE_HEALTH_ENDPOINT=1

# Watchdog
WATCHDOG_ENABLED=1
WATCHDOG_CHECK_INTERVAL=60
WATCHDOG_RESTART_ON_FREEZE=1
WATCHDOG_FREEZE_THRESHOLD=300
WATCHDOG_MAX_RESTARTS=3

# Deployment
DEPLOYMENT_ENV=production
LOG_ROTATION_DAYS=7

# Admin alerts
ADMIN_ALERT_WEBHOOK=https://discord.com/api/webhooks/YOUR_WEBHOOK
```

## Troubleshooting

### Service Won't Start

**Check:**
1. Virtual environment exists at `.venv`
2. `.env` file exists
3. Python path is correct: `nssm get CatalystBot Application`
4. Working directory is correct: `nssm get CatalystBot AppDirectory`

**View errors:**
```cmd
type data\logs\service_stderr.log
```

### Health Endpoint Not Responding

**Check:**
1. Service is running: `nssm status CatalystBot`
2. Port 8080 not in use: `netstat -an | findstr :8080`
3. Firewall not blocking port
4. `FEATURE_HEALTH_ENDPOINT=1` in `.env`

**Test locally:**
```bash
curl http://localhost:8080/health/ping
```

### Watchdog Not Restarting Bot

**Check:**
1. `WATCHDOG_ENABLED=1` in `.env`
2. Watchdog process is running
3. Service exists: `nssm status CatalystBot`
4. Check watchdog logs for errors

### UptimeRobot Shows "Down"

**Check:**
1. Cloudflare tunnel is running
2. Health endpoint responds locally
3. Correct URL in UptimeRobot (including `/health/ping`)
4. Keyword is set to "ok"

**Test from external network:**
```bash
curl https://your-tunnel.trycloudflare.com/health/ping
```

## Performance Impact

### Resource Usage

**Health Endpoint:**
- CPU: Negligible (<1%)
- Memory: ~2MB additional
- Network: Minimal (small HTTP responses)

**Watchdog:**
- CPU: Negligible (<1%)
- Memory: ~5MB additional
- Network: Minimal (1 HTTP request per minute)

**Logging:**
- Disk: ~10-50MB per day (depends on activity)
- I/O: Minimal (buffered writes)
- CPU: Negligible

### Recommendations

- **Production:** Enable health endpoint + UptimeRobot
- **Development:** Health endpoint only
- **High availability:** Health + Watchdog + UptimeRobot
- **Resource constrained:** Health endpoint only

## Security Considerations

### Health Endpoint

- Exposes system metrics (uptime, GPU usage, disk space)
- Consider firewall rules if internet-facing
- No authentication required (by design for monitoring)
- Safe to expose via Cloudflare tunnel

### Watchdog

- Can restart service (requires admin on Windows)
- Discord webhook alerts contain system info
- Runs with same privileges as bot

### Deployment

- `.env.backup` contains sensitive keys
- Git tags are public if pushed to public repo
- Service logs may contain sensitive data

**Best Practices:**
- Add `.env.backup` to `.gitignore`
- Use `.env` encryption for sensitive keys
- Restrict access to `data/logs/` directory
- Use private git repository

## Future Enhancements

Possible improvements for future waves:

1. **Docker Support**
   - Containerized deployment
   - Better isolation
   - Cross-platform

2. **Prometheus Metrics**
   - `/metrics` endpoint
   - Time-series data collection
   - Grafana dashboards

3. **Automated Backups**
   - Database backups
   - S3/cloud storage
   - Rotation policies

4. **Blue-Green Deployments**
   - Zero-downtime updates
   - Quick rollback
   - A/B testing

5. **Multi-Instance Support**
   - Load balancing
   - High availability
   - Failover

## Support

### Documentation

- `DEPLOYMENT_CHECKLIST.md` - Complete deployment guide
- `UPTIMEROBOT_SETUP.md` - External monitoring setup
- `NSSM_INSTALLATION.md` - Service installation

### Logs

- `data/logs/bot.jsonl` - Main application log
- `data/logs/errors.log` - Error log
- `data/logs/health.log` - Health monitoring log
- `data/logs/service_stderr.log` - Service errors

### Commands

```bash
# Health check
curl http://localhost:8080/health/detailed

# Deployment info
python -m catalyst_bot.deployment info

# Service status
nssm status CatalystBot

# View logs
type data\logs\bot.jsonl | findstr ERROR
```

## Summary

WAVE 2.3 provides enterprise-grade deployment infrastructure for Catalyst-Bot:

✅ **Auto-restart** - Service recovers automatically from crashes
✅ **Health monitoring** - Comprehensive metrics via HTTP endpoints
✅ **External monitoring** - UptimeRobot integration for 24/7 oversight
✅ **Safe deployments** - Backup, tag, and rollback procedures
✅ **Enhanced logging** - Separate logs with rotation
✅ **Watchdog** - Optional process monitor with auto-recovery
✅ **Production-ready** - Tested on Windows with NSSM

The bot can now run reliably 24/7 with minimal manual intervention.

---

**WAVE 2.3: 24/7 Deployment Infrastructure - Complete**
**Implementation Date:** 2025-10-05
