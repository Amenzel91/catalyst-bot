# Paper Trading Bot - Production Deployment Guide

**Version:** 1.0
**Last Updated:** November 2025
**Target Environment:** Ubuntu 22.04 LTS
**Deployment Type:** Production (Paper Trading)

---

## Table of Contents

1. [Overview](#overview)
2. [Server Requirements](#server-requirements)
3. [Operating System Setup](#operating-system-setup)
4. [Python Environment Setup](#python-environment-setup)
5. [Dependency Installation](#dependency-installation)
6. [Database Initialization](#database-initialization)
7. [Environment Configuration](#environment-configuration)
8. [SSL/TLS Setup](#ssltls-setup)
9. [Firewall Configuration](#firewall-configuration)
10. [Process Management with systemd](#process-management-with-systemd)
11. [Log Rotation](#log-rotation)
12. [Backup Strategy](#backup-strategy)
13. [Validation & Testing](#validation--testing)
14. [Troubleshooting](#troubleshooting)

---

## Overview

This guide provides step-by-step instructions for deploying the Catalyst Bot Paper Trading system in a production environment. The deployment uses systemd for process management, ensuring automatic restarts on failure and system boot.

**Architecture:**
```
┌─────────────────────────────────────────┐
│  Ubuntu 22.04 LTS Server                │
│  ├── Python 3.10+ Environment           │
│  ├── systemd Service Manager            │
│  ├── UFW Firewall                       │
│  ├── Nginx (optional, for webhooks)     │
│  └── Logrotate                          │
└─────────────────────────────────────────┘
         │
         ├──→ Alpaca Paper Trading API
         ├──→ Discord Webhooks
         ├──→ Market Data APIs (Tiingo, etc.)
         └──→ LLM APIs (Gemini, Claude)
```

---

## Server Requirements

### Minimum Specifications

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **CPU** | 2 cores | 4 cores | Higher for ML training |
| **RAM** | 4 GB | 8 GB | 16 GB for RL training |
| **Storage** | 25 GB | 50 GB | SSD strongly recommended |
| **Network** | 10 Mbps | 100 Mbps | Low latency critical |
| **OS** | Ubuntu 20.04+ | Ubuntu 22.04 LTS | Long-term support |

### Storage Breakdown

```
/home/catalyst-bot/
├── src/              ~500 MB  (source code)
├── data/
│   ├── databases/    ~2 GB    (SQLite DBs)
│   ├── cache/        ~1 GB    (API cache)
│   ├── logs/         ~5 GB    (rotating logs)
│   └── models/       ~10 GB   (RL models)
├── venv/             ~3 GB    (Python packages)
└── backups/          ~10 GB   (database backups)
```

### Network Requirements

**Outbound Ports:**
- 443 (HTTPS) - APIs, webhooks, market data
- 80 (HTTP) - Package downloads (during setup)

**Inbound Ports (Optional):**
- 443 (HTTPS) - Discord interactive webhooks (if using)
- 22 (SSH) - Remote management

---

## Operating System Setup

### 1. Initial Server Setup

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install essential build tools
sudo apt install -y \
    build-essential \
    git \
    curl \
    wget \
    vim \
    htop \
    tmux \
    ca-certificates \
    software-properties-common

# Set timezone (important for market hours)
sudo timedatectl set-timezone America/New_York

# Verify timezone
timedatectl
# Should show: Time zone: America/New_York (EST, -0500)
```

### 2. Create Dedicated User

```bash
# Create catalyst-bot user (no password, system user)
sudo useradd -r -m -s /bin/bash catalyst-bot

# Add to sudo group (optional, for deployment automation)
sudo usermod -aG sudo catalyst-bot

# Switch to catalyst-bot user
sudo su - catalyst-bot
cd ~
```

### 3. Create Directory Structure

```bash
# Create project directories
mkdir -p ~/catalyst-bot/{data/{databases,cache,logs,models,backups},config,scripts}

# Set permissions
chmod 750 ~/catalyst-bot
chmod 700 ~/catalyst-bot/data
chmod 755 ~/catalyst-bot/config
```

---

## Python Environment Setup

### 1. Install Python 3.10+

```bash
# Add deadsnakes PPA for latest Python
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Install Python 3.10
sudo apt install -y \
    python3.10 \
    python3.10-venv \
    python3.10-dev \
    python3-pip

# Verify installation
python3.10 --version
# Should show: Python 3.10.x
```

### 2. Create Virtual Environment

```bash
cd ~/catalyst-bot

# Create virtual environment
python3.10 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip, setuptools, wheel
pip install --upgrade pip setuptools wheel

# Verify
which python
# Should show: /home/catalyst-bot/catalyst-bot/venv/bin/python
```

### 3. Clone Repository

```bash
# Clone the project (replace with your repo URL)
git clone https://github.com/yourusername/catalyst-bot.git src
cd src

# Checkout production branch
git checkout main  # or your production branch

# Verify
git status
git log --oneline -5
```

---

## Dependency Installation

### 1. Install Python Dependencies

```bash
# Ensure virtual environment is activated
source ~/catalyst-bot/venv/bin/activate

# Install base dependencies
pip install -r requirements.txt

# Install paper trading dependencies
pip install \
    alpaca-py==0.24.0 \
    finrl==0.3.6 \
    stable-baselines3[extra]==2.2.1 \
    gymnasium==0.29.1 \
    vectorbt==0.26.2 \
    pyfolio-reloaded==0.9.5 \
    empyrical==0.5.5 \
    prometheus-client==0.19.0

# Install monitoring dependencies
pip install \
    streamlit==1.29.0 \
    watchdog==3.0.0

# Verify installation
pip list | grep -E "alpaca|finrl|stable-baselines"
```

### 2. Verify Critical Imports

```bash
# Test imports
python -c "
import alpaca
import finrl
from stable_baselines3 import PPO
import vectorbt as vbt
print('✓ All critical packages imported successfully')
"
```

### 3. Install System Dependencies (for RL training)

```bash
# Install TA-Lib (technical analysis library)
sudo apt install -y libta-lib0 libta-lib-dev
pip install ta-lib

# Install OpenGL for rendering (optional, for backtesting charts)
sudo apt install -y libgl1-mesa-glx

# Verify TA-Lib
python -c "import talib; print('✓ TA-Lib installed')"
```

---

## Database Initialization

### 1. Create Database Files

```bash
cd ~/catalyst-bot/data/databases

# The application will create these on first run, but we can pre-create them
touch positions.db trades.db portfolio.db rl_training.db

# Set permissions
chmod 600 *.db
```

### 2. Initialize Database Schema

```bash
# Run database initialization script
cd ~/catalyst-bot/src
python -m catalyst_bot.database.init_schema

# Verify tables were created
sqlite3 ../data/databases/positions.db ".tables"
# Should show: positions, closed_positions, position_history
```

### 3. Database Configuration

Create `~/catalyst-bot/data/databases/README.md`:

```markdown
# Database Files

- positions.db: Active and closed positions
- trades.db: Trade history and execution logs
- portfolio.db: Portfolio metrics and performance tracking
- rl_training.db: RL agent training history and metrics
- sec_llm_cache.db: SEC filing analysis cache
- seen_store.db: Deduplication store for alerts

## Backup Schedule

Automated backups run daily at 2 AM (see backup-databases.timer)
```

---

## Environment Configuration

### 1. Create Production .env File

```bash
cd ~/catalyst-bot/src

# Copy example file
cp .env.example .env

# Edit with production values
vim .env
```

### 2. Critical Environment Variables

```bash
# =============================================================================
# PRODUCTION PAPER TRADING CONFIGURATION
# =============================================================================

# -----------------------------------------------------------------------------
# Trading Mode
# -----------------------------------------------------------------------------
TRADING_MODE=paper  # paper, live, or backtest
ALPACA_PAPER=1      # Use Alpaca paper trading API

# -----------------------------------------------------------------------------
# Alpaca Credentials (Paper Trading)
# -----------------------------------------------------------------------------
# Get from: https://app.alpaca.markets/paper/dashboard/overview
ALPACA_API_KEY=your_paper_api_key_here
ALPACA_SECRET=your_paper_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# -----------------------------------------------------------------------------
# Discord Notifications
# -----------------------------------------------------------------------------
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK
DISCORD_ADMIN_WEBHOOK=https://discord.com/api/webhooks/YOUR_ADMIN_WEBHOOK

# -----------------------------------------------------------------------------
# Risk Management
# -----------------------------------------------------------------------------
# Position sizing
MAX_POSITION_PCT=0.20           # Max 20% per position
MAX_PORTFOLIO_LEVERAGE=3.0      # Max 3x leverage
DAILY_LOSS_LIMIT_PCT=-0.03      # -3% max daily loss
MAX_DRAWDOWN_PCT=-0.10          # -10% max drawdown

# Trading limits
MAX_TRADES_PER_DAY=40           # Prevent overtrading
MAX_OPEN_POSITIONS=5            # Max concurrent positions
MIN_TRADE_SIZE_USD=100          # Minimum $100 per trade

# Stop-loss configuration
ATR_STOP_MULTIPLIER=6.0         # ATR × 6 for stop distance
TRAILING_STOP_TRIGGER_PCT=0.05  # Activate at 5% profit
TRAILING_STOP_DISTANCE_PCT=0.03 # Trail by 3%

# Circuit breakers
KILL_SWITCH_ENABLED=1
CIRCUIT_BREAKER_CONSECUTIVE_LOSSES=3
CIRCUIT_BREAKER_API_ERROR_THRESHOLD=5

# -----------------------------------------------------------------------------
# RL Agent Configuration
# -----------------------------------------------------------------------------
RL_MODEL_PATH=/home/catalyst-bot/catalyst-bot/data/models/ensemble.pkl
RL_CONFIDENCE_THRESHOLD=0.6     # Minimum confidence for trades
RL_ENABLED=1                    # Enable RL-based trading

# -----------------------------------------------------------------------------
# Market Data APIs
# -----------------------------------------------------------------------------
TIINGO_API_KEY=your_tiingo_key
FINNHUB_API_KEY=your_finnhub_key
ALPHAVANTAGE_API_KEY=your_alphavantage_key

# -----------------------------------------------------------------------------
# LLM APIs
# -----------------------------------------------------------------------------
GEMINI_API_KEY=your_gemini_key
ANTHROPIC_API_KEY=your_anthropic_key

# -----------------------------------------------------------------------------
# Monitoring
# -----------------------------------------------------------------------------
PROMETHEUS_PORT=9090
ENABLE_PERFORMANCE_TRACKING=1
LOG_LEVEL=INFO                  # DEBUG for development, INFO for production

# -----------------------------------------------------------------------------
# Database Paths
# -----------------------------------------------------------------------------
DB_DIR=/home/catalyst-bot/catalyst-bot/data/databases
CACHE_DIR=/home/catalyst-bot/catalyst-bot/data/cache
LOG_DIR=/home/catalyst-bot/catalyst-bot/data/logs
```

### 3. Secure Environment File

```bash
# Restrict permissions
chmod 600 .env

# Verify no one else can read it
ls -la .env
# Should show: -rw------- 1 catalyst-bot catalyst-bot
```

### 4. Validate Configuration

```bash
# Run configuration validator
python -m catalyst_bot.scripts.validate_deployment

# Expected output:
# ✓ Environment variables loaded
# ✓ Alpaca credentials valid
# ✓ Discord webhooks accessible
# ✓ Database files exist
# ✓ RL model found
# ✓ All dependencies installed
```

---

## SSL/TLS Setup

### 1. Install Nginx (Optional - for Discord Interactions)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

# Configure Nginx for webhook receiver
sudo vim /etc/nginx/sites-available/catalyst-bot
```

### 2. Nginx Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Discord interaction endpoint
    location /discord/interactions {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:5000;
    }
}
```

### 3. Obtain SSL Certificate

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/catalyst-bot /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Verify auto-renewal
sudo certbot renew --dry-run
```

---

## Firewall Configuration

### 1. Install and Configure UFW

```bash
# Install UFW
sudo apt install -y ufw

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (critical - don't lock yourself out!)
sudo ufw allow 22/tcp comment 'SSH'

# Allow HTTPS (if using Discord interactions)
sudo ufw allow 443/tcp comment 'HTTPS'

# Allow Prometheus (if monitoring externally)
# sudo ufw allow from 10.0.0.0/8 to any port 9090 proto tcp comment 'Prometheus'

# Enable firewall
sudo ufw enable

# Verify status
sudo ufw status verbose
```

### 2. Firewall Rules Summary

```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
22/tcp (v6)                ALLOW       Anywhere (v6)
443/tcp (v6)               ALLOW       Anywhere (v6)
```

---

## Process Management with systemd

### 1. Create systemd Service File

```bash
sudo vim /etc/systemd/system/catalyst-trading-bot.service
```

### 2. Service Configuration

```ini
[Unit]
Description=Catalyst Paper Trading Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=catalyst-bot
Group=catalyst-bot
WorkingDirectory=/home/catalyst-bot/catalyst-bot/src
Environment="PATH=/home/catalyst-bot/catalyst-bot/venv/bin"
EnvironmentFile=/home/catalyst-bot/catalyst-bot/src/.env

# Main process
ExecStart=/home/catalyst-bot/catalyst-bot/venv/bin/python -m catalyst_bot.runner --mode paper-trading

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=5

# Resource limits
MemoryMax=6G
CPUQuota=200%

# Logging
StandardOutput=append:/home/catalyst-bot/catalyst-bot/data/logs/trading-bot.log
StandardError=append:/home/catalyst-bot/catalyst-bot/data/logs/trading-bot.error.log
SyslogIdentifier=catalyst-trading-bot

# Security
NoNewPrivileges=true
PrivateTmp=true

# Kill switch support
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### 3. Enable and Start Service

```bash
# Reload systemd daemon
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable catalyst-trading-bot.service

# Start service
sudo systemctl start catalyst-trading-bot.service

# Check status
sudo systemctl status catalyst-trading-bot.service

# View logs
sudo journalctl -u catalyst-trading-bot.service -f
```

### 4. Service Management Commands

```bash
# Stop service
sudo systemctl stop catalyst-trading-bot.service

# Restart service
sudo systemctl restart catalyst-trading-bot.service

# Disable service (no auto-start on boot)
sudo systemctl disable catalyst-trading-bot.service

# View recent logs
sudo journalctl -u catalyst-trading-bot.service -n 100

# View logs since boot
sudo journalctl -u catalyst-trading-bot.service -b

# Follow logs in real-time
sudo journalctl -u catalyst-trading-bot.service -f
```

---

## Log Rotation

### 1. Configure Logrotate

```bash
sudo vim /etc/logrotate.d/catalyst-trading-bot
```

### 2. Logrotate Configuration

```
/home/catalyst-bot/catalyst-bot/data/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 catalyst-bot catalyst-bot
    sharedscripts
    postrotate
        systemctl reload catalyst-trading-bot.service > /dev/null 2>&1 || true
    endscript
}

/home/catalyst-bot/catalyst-bot/data/logs/*.jsonl {
    daily
    rotate 90
    compress
    delaycompress
    missingok
    notifempty
    create 0640 catalyst-bot catalyst-bot
    size 100M
}
```

### 3. Test Logrotate

```bash
# Test configuration
sudo logrotate -d /etc/logrotate.d/catalyst-trading-bot

# Force rotation (for testing)
sudo logrotate -f /etc/logrotate.d/catalyst-trading-bot

# Verify rotated files
ls -lh /home/catalyst-bot/catalyst-bot/data/logs/
```

---

## Backup Strategy

### 1. Create Backup Script

```bash
vim ~/catalyst-bot/scripts/backup-databases.sh
```

```bash
#!/bin/bash
#
# Catalyst Bot Database Backup Script
# Backs up all SQLite databases to timestamped archives
#

set -e

# Configuration
BACKUP_DIR="/home/catalyst-bot/catalyst-bot/data/backups"
DB_DIR="/home/catalyst-bot/catalyst-bot/data/databases"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup each database
for db in "$DB_DIR"/*.db; do
    db_name=$(basename "$db" .db)
    backup_file="$BACKUP_DIR/${db_name}_${DATE}.db"

    echo "Backing up $db_name..."

    # SQLite online backup
    sqlite3 "$db" ".backup '$backup_file'"

    # Compress backup
    gzip "$backup_file"

    echo "✓ Backed up to ${backup_file}.gz"
done

# Remove old backups
find "$BACKUP_DIR" -name "*.db.gz" -mtime +$RETENTION_DAYS -delete

echo "✓ Backup complete. Cleaned up backups older than $RETENTION_DAYS days."
```

### 2. Make Script Executable

```bash
chmod +x ~/catalyst-bot/scripts/backup-databases.sh

# Test backup
~/catalyst-bot/scripts/backup-databases.sh
```

### 3. Schedule with systemd Timer

```bash
# Create service file
sudo vim /etc/systemd/system/backup-databases.service
```

```ini
[Unit]
Description=Backup Catalyst Bot Databases
After=network.target

[Service]
Type=oneshot
User=catalyst-bot
ExecStart=/home/catalyst-bot/catalyst-bot/scripts/backup-databases.sh
```

```bash
# Create timer file
sudo vim /etc/systemd/system/backup-databases.timer
```

```ini
[Unit]
Description=Daily Database Backup Timer
Requires=backup-databases.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Enable and start timer
sudo systemctl daemon-reload
sudo systemctl enable backup-databases.timer
sudo systemctl start backup-databases.timer

# Verify timer
sudo systemctl list-timers --all
```

### 4. Backup to Remote Storage (Optional)

```bash
# Install rclone for cloud backups
sudo apt install -y rclone

# Configure rclone (one-time setup)
rclone config

# Add to backup script
rclone sync "$BACKUP_DIR" remote:catalyst-bot-backups/databases
```

---

## Validation & Testing

### 1. Pre-Launch Checklist

```bash
#!/bin/bash
# Run comprehensive validation

echo "=== Catalyst Bot Production Validation ==="

# Check 1: Environment variables
echo "Checking environment variables..."
if [ -f ~/catalyst-bot/src/.env ]; then
    echo "✓ .env file exists"
else
    echo "✗ .env file missing"
    exit 1
fi

# Check 2: Database files
echo "Checking databases..."
for db in positions trades portfolio; do
    if [ -f ~/catalyst-bot/data/databases/${db}.db ]; then
        echo "✓ ${db}.db exists"
    else
        echo "✗ ${db}.db missing"
    fi
done

# Check 3: Python dependencies
echo "Checking Python packages..."
source ~/catalyst-bot/venv/bin/activate
python -c "import alpaca; import finrl; from stable_baselines3 import PPO" && echo "✓ Critical packages installed" || echo "✗ Missing packages"

# Check 4: Alpaca connectivity
echo "Testing Alpaca API..."
python -m catalyst_bot.broker.test_connection && echo "✓ Alpaca connected" || echo "✗ Alpaca connection failed"

# Check 5: Discord webhooks
echo "Testing Discord webhooks..."
curl -X POST "$DISCORD_WEBHOOK_URL" -H "Content-Type: application/json" -d '{"content":"Production deployment test"}' && echo "✓ Discord webhook OK" || echo "✗ Discord webhook failed"

# Check 6: systemd service
echo "Checking systemd service..."
systemctl is-enabled catalyst-trading-bot.service && echo "✓ Service enabled" || echo "✗ Service not enabled"

echo ""
echo "=== Validation Complete ==="
```

### 2. Run Dry Run Test

```bash
# Start bot in dry-run mode (logs trades without execution)
python -m catalyst_bot.runner --mode paper-trading --dry-run

# Monitor for 30 minutes, verify:
# - Signals are generated
# - Risk checks pass
# - No exceptions
# - Logs are structured
```

### 3. Verify Monitoring Endpoints

```bash
# Check Prometheus metrics
curl http://localhost:9090/metrics | grep catalyst_bot

# Expected metrics:
# catalyst_bot_portfolio_value
# catalyst_bot_open_positions
# catalyst_bot_daily_pnl
# catalyst_bot_order_success_rate
```

---

## Troubleshooting

### Issue 1: Service Won't Start

**Symptoms:**
- `systemctl start catalyst-trading-bot.service` fails
- `systemctl status` shows "failed" state

**Diagnosis:**
```bash
# Check service logs
sudo journalctl -u catalyst-trading-bot.service -n 50

# Check for permission errors
ls -la /home/catalyst-bot/catalyst-bot/src/.env

# Verify Python path
/home/catalyst-bot/catalyst-bot/venv/bin/python --version
```

**Solution:**
```bash
# Fix permissions
sudo chown -R catalyst-bot:catalyst-bot /home/catalyst-bot/catalyst-bot
chmod 600 /home/catalyst-bot/catalyst-bot/src/.env

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart catalyst-trading-bot.service
```

---

### Issue 2: Alpaca API Errors

**Symptoms:**
- Orders fail with 401 Unauthorized
- "Invalid API key" errors

**Diagnosis:**
```bash
# Test Alpaca credentials manually
python -c "
from alpaca.trading.client import TradingClient
import os
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET'), paper=True)
print(client.get_account())
"
```

**Solution:**
```bash
# Regenerate API keys at https://app.alpaca.markets/paper/dashboard
# Update .env file
vim ~/catalyst-bot/src/.env

# Restart service
sudo systemctl restart catalyst-trading-bot.service
```

---

### Issue 3: High Memory Usage

**Symptoms:**
- OOM (Out of Memory) errors
- Service killed by systemd

**Diagnosis:**
```bash
# Check memory usage
sudo systemctl status catalyst-trading-bot.service | grep Memory

# View memory trends
journalctl -u catalyst-trading-bot.service | grep -i memory
```

**Solution:**
```bash
# Increase memory limit in service file
sudo vim /etc/systemd/system/catalyst-trading-bot.service
# Change: MemoryMax=6G → MemoryMax=8G

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart catalyst-trading-bot.service

# Or reduce RL model complexity
# Set in .env: RL_MODEL_SIZE=small
```

---

### Issue 4: Database Locked Errors

**Symptoms:**
- SQLite "database is locked" errors
- Timeout errors on database writes

**Diagnosis:**
```bash
# Check for long-running transactions
sqlite3 /home/catalyst-bot/catalyst-bot/data/databases/positions.db "PRAGMA busy_timeout;"

# Check for multiple processes
ps aux | grep catalyst_bot
```

**Solution:**
```bash
# Enable WAL mode in .env
echo "SQLITE_WAL_MODE=1" >> ~/catalyst-bot/src/.env

# Or manually enable for each database
for db in ~/catalyst-bot/data/databases/*.db; do
    sqlite3 "$db" "PRAGMA journal_mode=WAL;"
done

# Restart service
sudo systemctl restart catalyst-trading-bot.service
```

---

### Issue 5: Logs Not Rotating

**Symptoms:**
- Log files exceed 10 GB
- Disk space running out

**Diagnosis:**
```bash
# Check log sizes
du -sh /home/catalyst-bot/catalyst-bot/data/logs/*

# Test logrotate configuration
sudo logrotate -d /etc/logrotate.d/catalyst-trading-bot
```

**Solution:**
```bash
# Force rotation
sudo logrotate -f /etc/logrotate.d/catalyst-trading-bot

# Manually compress old logs
gzip /home/catalyst-bot/catalyst-bot/data/logs/*.log.1

# Verify logrotate cron job
sudo systemctl status cron
```

---

## Next Steps

After successful deployment:

1. **Monitor for 24 hours** - Watch logs, verify no errors
2. **Review first trades** - Analyze execution quality, slippage
3. **Tune risk parameters** - Adjust based on initial performance
4. **Enable monitoring dashboard** - Set up Grafana (see monitoring.md)
5. **Schedule model retraining** - Weekly or monthly (see training guide)

---

## Security Best Practices

### 1. Credential Management

```bash
# Never commit .env to git
echo ".env" >> .gitignore

# Use environment-specific files
.env.production   # Production credentials
.env.staging      # Staging credentials
.env.development  # Development credentials (mock keys)
```

### 2. API Key Rotation

```bash
# Rotate API keys quarterly
# 1. Generate new keys
# 2. Update .env
# 3. Restart service
# 4. Revoke old keys after 24h grace period
```

### 3. Database Encryption (Optional)

```bash
# Install SQLCipher for encrypted databases
sudo apt install -y sqlcipher

# Create encrypted database
sqlcipher positions.db
> PRAGMA key = 'your-encryption-key';
> .databases
```

---

## Support & Resources

**Documentation:**
- Deployment Guide: `docs/deployment/production-setup.md` (this file)
- Docker Guide: `docs/deployment/docker-setup.md`
- Monitoring Guide: `docs/deployment/monitoring.md`
- Disaster Recovery: `docs/deployment/disaster-recovery.md`

**External Resources:**
- Alpaca API Docs: https://docs.alpaca.markets/
- systemd Documentation: https://www.freedesktop.org/software/systemd/man/
- Ubuntu Server Guide: https://ubuntu.com/server/docs

**Getting Help:**
- GitHub Issues: https://github.com/yourusername/catalyst-bot/issues
- Discord Community: [Your Discord Server]

---

**End of Production Deployment Guide**
