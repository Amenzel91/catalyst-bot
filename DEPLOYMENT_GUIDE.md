# Catalyst-Bot 24/7 Deployment Guide

This guide covers setting up Catalyst-Bot to run continuously on Windows with automatic restart on failure.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Option 1: Windows Service (NSSM)](#option-1-windows-service-nssm-recommended)
3. [Option 2: Task Scheduler](#option-2-task-scheduler)
4. [Monitoring & Health Checks](#monitoring--health-checks)
5. [Remote Access Setup](#remote-access-setup)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before deploying, ensure:

✅ Bot is tested and working with `python -m catalyst_bot.runner --once`
✅ `.env` file is configured with all required API keys
✅ Virtual environment is set up (`.venv/`)
✅ Health endpoint is enabled: `FEATURE_HEALTH_ENDPOINT=1`
✅ You have Administrator privileges on Windows

---

## Option 1: Windows Service (NSSM) ⭐ RECOMMENDED

**Pros:**
- True Windows service (starts before login)
- Automatic log rotation
- Easy management via Services console
- Graceful shutdown handling

**Cons:**
- Requires downloading NSSM (one-time setup)

### Step 1: Download NSSM

1. Download NSSM from: https://nssm.cc/download
2. Extract `nssm.exe` to a permanent location (e.g., `C:\Tools\nssm\`)
3. Add to PATH or note the full path

### Step 2: Install Service

Open PowerShell **as Administrator** and run:

```powershell
cd "C:\Path\To\catalyst-bot"

# Install service (if NSSM is in PATH)
.\install-service.ps1 -Action install

# OR specify NSSM path explicitly
.\install-service.ps1 -Action install -NssmPath "C:\Tools\nssm\nssm.exe"
```

### Step 3: Start Service

```powershell
.\install-service.ps1 -Action start
```

### Step 4: Verify

```powershell
# Check status
.\install-service.ps1 -Action status

# View logs
Get-Content data\logs\service.log -Tail 50
```

### Management Commands

```powershell
# Start service
.\install-service.ps1 -Action start

# Stop service
.\install-service.ps1 -Action stop

# Restart service
.\install-service.ps1 -Action restart

# Check status
.\install-service.ps1 -Action status

# Remove service
.\install-service.ps1 -Action remove
```

### Service Configuration

The service is configured with:

- **Startup**: Automatic (starts on boot)
- **Recovery**: Auto-restart after 60 seconds on failure
- **Logs**: Rotated daily, 10MB max, keep 7 days
- **Working Directory**: Repository root
- **User**: Local System account

To modify settings, use NSSM directly:

```powershell
nssm edit CatalystBot
```

---

## Option 2: Task Scheduler

**Pros:**
- Built into Windows (no extra downloads)
- Runs as your user account (easier for testing)

**Cons:**
- Requires user to be logged in (unless configured for "Run whether user is logged on or not")
- More visible (console window)

### Step 1: Install Task

Open PowerShell **as Administrator**:

```powershell
cd "C:\Path\To\catalyst-bot"

.\install-task.ps1 -Action install
```

### Step 2: Start Task

```powershell
# Start immediately
.\install-task.ps1 -Action start

# OR restart computer (task runs at startup)
Restart-Computer
```

### Step 3: Verify

```powershell
# Check task status
.\install-task.ps1 -Action status

# View in Task Scheduler GUI
taskschd.msc
```

### Management Commands

```powershell
# Start task
.\install-task.ps1 -Action start

# Stop task
.\install-task.ps1 -Action stop

# Check status
.\install-task.ps1 -Action status

# Remove task
.\install-task.ps1 -Action remove
```

### Task Configuration

The task is configured with:

- **Trigger**: At system startup
- **Recovery**: Restart every 1 minute on failure
- **Execution Time Limit**: None (runs indefinitely)
- **Network**: Only run if network is available
- **Power**: Run on battery, don't stop if going on batteries

---

## Monitoring & Health Checks

### Built-in Health Endpoint

The bot includes a health check endpoint at `http://localhost:8080/health`

**Enable in `.env`:**
```ini
FEATURE_HEALTH_ENDPOINT=1
HEALTH_ENDPOINT_PORT=8080
```

**Response format:**
```json
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "last_cycle_time": "2025-10-04T12:00:00Z",
  "cycles_completed": 1440,
  "gpu_available": true
}
```

### External Monitoring (Recommended)

Use **UptimeRobot** (free) or similar:

1. Create account at https://uptimerobot.com
2. Add HTTP(S) monitor:
   - **URL**: `http://your-ip:8080/health`
   - **Interval**: 5 minutes
   - **Alert**: Email/Discord on failure

### Discord Heartbeat

The bot sends periodic "I'm alive" messages to Discord.

**Enable in `.env`:**
```ini
FEATURE_HEARTBEAT=1
HEARTBEAT_INTERVAL_MINUTES=60
```

Heartbeats include:
- Uptime
- Alerts sent (this cycle / total)
- GPU status
- Last cycle duration

---

## Remote Access Setup

### Option A: Windows Remote Desktop (RDP)

**Built into Windows Pro/Enterprise:**

1. Enable RDP:
   ```
   Settings → System → Remote Desktop → Enable
   ```

2. Configure firewall (if needed):
   ```powershell
   Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
   ```

3. Connect from another PC:
   ```
   mstsc /v:your-pc-ip
   ```

**Port forwarding (if accessing from outside network):**
- Forward port 3389 on your router to the dev rig
- Use dynamic DNS (e.g., No-IP) for consistent access

### Option B: TeamViewer

**Free for personal use:**

1. Download: https://www.teamviewer.com/
2. Install on dev rig
3. Note your TeamViewer ID
4. Set unattended access password
5. Connect from anywhere using ID + password

### Option C: AnyDesk

**Alternative to TeamViewer:**

1. Download: https://anydesk.com/
2. Install and configure
3. Connect using AnyDesk address

### Security Best Practices

- **Strong passwords**: 16+ characters for RDP/remote tools
- **VPN**: Use Tailscale or Wireguard for secure access
- **IP whitelist**: Limit RDP to known IPs if possible
- **Two-factor**: Enable 2FA on router admin panel
- **Auto-update**: Keep Windows and remote tools updated

---

## Troubleshooting

### Service won't start

**Check logs:**
```powershell
Get-Content data\logs\service.log -Tail 100
```

**Common issues:**
- Virtual environment not found → Check `.venv\Scripts\python.exe` exists
- Missing .env file → Copy `.env.example` to `.env` and configure
- API keys not set → Check Discord webhook, API keys in `.env`

### High CPU/GPU usage

**Monitor resource usage:**
```powershell
# Check GPU
nvidia-smi

# Check CPU
Get-Process python | Select-Object CPU, WorkingSet
```

**Optimizations:**
- Reduce `MAX_ALERTS_PER_CYCLE` in `.env`
- Enable ML skip for earnings: `SKIP_ML_FOR_EARNINGS=1`
- Increase cycle interval: `SLEEP_SECONDS=90`

### Bot keeps restarting

**Check for crash patterns:**
```powershell
# Count restart frequency
Get-Content data\logs\service.log | Select-String "Starting Catalyst Bot"
```

**Common causes:**
- API rate limits → Add retry delays, reduce frequency
- Out of memory → Increase virtual memory / upgrade RAM
- GPU driver crash → Update Nvidia drivers
- Network issues → Check firewall, VPN settings

### Logs not showing recent data

**Force flush logs:**
```python
# Add to runner.py if needed
import logging
logging.getLogger().handlers[0].flush()
```

**Check log rotation:**
- NSSM rotates at 10MB
- Task Scheduler: logs to console only (redirect to file manually)

### Can't access health endpoint remotely

**Test locally first:**
```powershell
Invoke-WebRequest http://localhost:8080/health
```

**If working locally but not remotely:**
- Open firewall port 8080:
  ```powershell
  New-NetFirewallRule -DisplayName "Catalyst Health Check" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
  ```
- Change bind address in code if needed (default: `0.0.0.0` = all interfaces)

### Service starts but bot doesn't run

**Verify working directory:**
```powershell
# Check NSSM config
nssm get CatalystBot AppDirectory
```

**Should be:** Repository root (e.g., `C:\Users\...\catalyst-bot`)

**Fix if wrong:**
```powershell
nssm set CatalystBot AppDirectory "C:\Path\To\catalyst-bot"
nssm restart CatalystBot
```

---

## Rollback / Emergency Stop

### Immediate Stop

```powershell
# If using NSSM
.\install-service.ps1 -Action stop

# If using Task Scheduler
.\install-task.ps1 -Action stop

# OR kill process manually
Get-Process python | Where-Object {$_.Path -like "*catalyst-bot*"} | Stop-Process -Force
```

### Complete Removal

```powershell
# Remove service/task
.\install-service.ps1 -Action remove
# OR
.\install-task.ps1 -Action remove

# Clean up processes
Get-Process python | Stop-Process -Force
```

### Restore from Git

```powershell
# Stash local changes
git stash

# Reset to last known good commit
git reset --hard <commit-hash>

# Restart service
.\install-service.ps1 -Action start
```

---

## Post-Deployment Checklist

- [ ] Service/task starts automatically on reboot
- [ ] Health endpoint responds at `http://localhost:8080/health`
- [ ] Discord alerts are being posted
- [ ] Logs are being written and rotated
- [ ] UptimeRobot (or similar) is monitoring health endpoint
- [ ] Remote access is working (RDP/TeamViewer)
- [ ] Firewall rules allow necessary ports (8080, 3389 if RDP)
- [ ] `.env` secrets are backed up securely (encrypted)
- [ ] Git repository is up to date with latest changes
- [ ] You have tested a manual restart: `.\install-service.ps1 -Action restart`

---

## Support & Resources

- **Logs**: `data/logs/service.log` (NSSM) or console output (Task Scheduler)
- **Health Check**: `http://localhost:8080/health`
- **Discord Webhooks**: Test with `curl` or Postman
- **NSSM Docs**: https://nssm.cc/usage
- **Task Scheduler**: `taskschd.msc` (Windows GUI)

**Need help?** Check existing logs first, then search for error messages in bot code or GitHub issues.

---

## Advanced: Docker Deployment (Future)

For Linux or cloud deployment, consider containerization:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "-m", "catalyst_bot.runner", "--loop"]
```

*(Not yet tested - Windows native deployment is current focus)*

---

**Last Updated**: October 4, 2025
**Version**: 1.0
