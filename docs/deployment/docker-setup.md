# Paper Trading Bot - Docker Deployment Guide

**Version:** 1.0
**Last Updated:** November 2025
**Docker Version:** 24.0+
**Docker Compose Version:** 2.20+

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Dockerfile](#dockerfile)
4. [Docker Compose Configuration](#docker-compose-configuration)
5. [Volume Mounts](#volume-mounts)
6. [Environment Variable Management](#environment-variable-management)
7. [Health Checks](#health-checks)
8. [Resource Limits](#resource-limits)
9. [Networking Configuration](#networking-configuration)
10. [Multi-App Deployment](#multi-app-deployment)
11. [Building and Running](#building-and-running)
12. [Monitoring Containers](#monitoring-containers)
13. [Troubleshooting](#troubleshooting)

---

## Overview

This guide provides comprehensive instructions for deploying the Catalyst Paper Trading Bot using Docker and Docker Compose. Containerization offers:

- **Isolation**: Each app runs in its own environment
- **Portability**: Deploy anywhere Docker runs
- **Consistency**: Same environment dev → staging → production
- **Scalability**: Easy horizontal scaling
- **Resource Management**: CPU/memory limits per container

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│  Docker Host (Ubuntu 22.04)                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Docker Network: catalyst-network (bridge)           │  │
│  │  ┌────────────────┐  ┌────────────────┐             │  │
│  │  │ trading-bot    │  │ slack-bot      │             │  │
│  │  │ (port 9090)    │  │ (port 3000)    │             │  │
│  │  └───────┬────────┘  └───────┬────────┘             │  │
│  │          │                    │                       │  │
│  │  ┌───────┴────────────────────┴────────┐             │  │
│  │  │ Shared Volumes:                     │             │  │
│  │  │ - databases/ (SQLite)               │             │  │
│  │  │ - logs/ (application logs)          │             │  │
│  │  │ - cache/ (API cache)                │             │  │
│  │  │ - models/ (RL models)               │             │  │
│  │  └─────────────────────────────────────┘             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### 1. Install Docker

```bash
# Update package index
sudo apt update

# Install dependencies
sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### 2. Configure Docker (Non-root Access)

```bash
# Create docker group
sudo groupadd docker

# Add your user to docker group
sudo usermod -aG docker $USER

# Apply group changes (logout/login or use newgrp)
newgrp docker

# Verify non-root access
docker run hello-world
```

### 3. Docker Daemon Configuration

```bash
# Create daemon config
sudo mkdir -p /etc/docker
sudo vim /etc/docker/daemon.json
```

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  }
}
```

```bash
# Restart Docker
sudo systemctl restart docker
sudo systemctl enable docker
```

---

## Dockerfile

### Main Dockerfile (`docker/Dockerfile`)

```dockerfile
# =============================================================================
# Catalyst Paper Trading Bot - Production Dockerfile
# =============================================================================
FROM python:3.10-slim-bullseye AS base

# Metadata
LABEL maintainer="your-email@example.com"
LABEL description="Catalyst Paper Trading Bot with RL"
LABEL version="1.0"

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgomp1 \
    libta-lib0 \
    libta-lib-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Create app user (non-root)
RUN useradd -m -u 1000 -s /bin/bash catalyst && \
    mkdir -p /app /data /logs && \
    chown -R catalyst:catalyst /app /data /logs

WORKDIR /app

# =============================================================================
# Dependencies Stage
# =============================================================================
FROM base AS dependencies

# Copy requirements
COPY requirements.txt requirements-trading.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-trading.txt

# =============================================================================
# Production Stage
# =============================================================================
FROM base AS production

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=catalyst:catalyst src/ /app/src/
COPY --chown=catalyst:catalyst data/ /app/data/

# Switch to non-root user
USER catalyst

# Create necessary directories
RUN mkdir -p /data/{databases,cache,logs,models,backups} && \
    chmod -R 750 /data

# Expose ports
EXPOSE 9090
EXPOSE 5000

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=5)" || exit 1

# Default command
CMD ["python", "-m", "catalyst_bot.runner", "--mode", "paper-trading"]
```

### Trading Bot Requirements (`requirements-trading.txt`)

```txt
# Paper Trading Dependencies
alpaca-py==0.24.0
finrl==0.3.6
stable-baselines3[extra]==2.2.1
gymnasium==0.29.1
vectorbt==0.26.2
pyfolio-reloaded==0.9.5
empyrical==0.5.5

# Monitoring
prometheus-client==0.19.0
flask==3.0.0

# Performance
uvloop==0.19.0
orjson==3.9.10
```

---

## Docker Compose Configuration

### Main Docker Compose File (`docker-compose.yml`)

```yaml
version: '3.8'

services:
  # =============================================================================
  # Catalyst Paper Trading Bot
  # =============================================================================
  trading-bot:
    build:
      context: .
      dockerfile: docker/Dockerfile
      target: production
    container_name: catalyst-trading-bot
    hostname: trading-bot
    restart: unless-stopped

    # Environment
    env_file:
      - .env.production
    environment:
      - TZ=America/New_York
      - TRADING_MODE=paper
      - LOG_LEVEL=INFO

    # Volumes
    volumes:
      - ./data/databases:/data/databases:rw
      - ./data/cache:/data/cache:rw
      - ./data/logs:/data/logs:rw
      - ./data/models:/data/models:ro
      - ./data/backups:/data/backups:rw
      - /etc/localtime:/etc/localtime:ro

    # Ports
    ports:
      - "9090:9090"  # Prometheus metrics
      - "5000:5000"  # Health check endpoint

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 6G
        reservations:
          cpus: '1.0'
          memory: 2G

    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 120s

    # Logging
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

    # Networks
    networks:
      - catalyst-network

    # Dependencies
    depends_on:
      - prometheus

  # =============================================================================
  # Slack Bot (Optional - if running multi-bot setup)
  # =============================================================================
  slack-bot:
    build:
      context: .
      dockerfile: docker/Dockerfile.slack
      target: production
    container_name: catalyst-slack-bot
    hostname: slack-bot
    restart: unless-stopped

    # Environment
    env_file:
      - .env.production
    environment:
      - TZ=America/New_York
      - LOG_LEVEL=INFO

    # Volumes (shared with trading bot)
    volumes:
      - ./data/databases:/data/databases:ro  # Read-only access
      - ./data/logs:/data/logs/slack:rw
      - /etc/localtime:/etc/localtime:ro

    # Ports
    ports:
      - "3000:3000"  # Slack webhook receiver

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M

    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 60s
      timeout: 10s
      retries: 3

    # Networks
    networks:
      - catalyst-network

  # =============================================================================
  # Prometheus (Metrics Collection)
  # =============================================================================
  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: catalyst-prometheus
    restart: unless-stopped

    # Configuration
    volumes:
      - ./config/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus

    # Ports
    ports:
      - "9091:9090"  # Prometheus UI

    # Command
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=90d'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'

    # Networks
    networks:
      - catalyst-network

  # =============================================================================
  # Grafana (Monitoring Dashboard)
  # =============================================================================
  grafana:
    image: grafana/grafana:10.2.2
    container_name: catalyst-grafana
    restart: unless-stopped

    # Environment
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-changeme}
      - GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource

    # Volumes
    volumes:
      - ./config/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./config/grafana/dashboards:/var/lib/grafana/dashboards:ro
      - grafana-data:/var/lib/grafana

    # Ports
    ports:
      - "3001:3000"  # Grafana UI (avoid conflict with Slack bot)

    # Dependencies
    depends_on:
      - prometheus

    # Networks
    networks:
      - catalyst-network

# =============================================================================
# Networks
# =============================================================================
networks:
  catalyst-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.25.0.0/16

# =============================================================================
# Volumes
# =============================================================================
volumes:
  prometheus-data:
    driver: local
  grafana-data:
    driver: local
```

---

## Volume Mounts

### Volume Structure

```
./data/
├── databases/      # SQLite databases (read-write)
│   ├── positions.db
│   ├── trades.db
│   ├── portfolio.db
│   └── rl_training.db
├── cache/          # API response cache (read-write)
│   ├── float_cache.json
│   └── price_cache.json
├── logs/           # Application logs (read-write)
│   ├── trading-bot.log
│   ├── trading-bot.error.log
│   └── trades.jsonl
├── models/         # RL models (read-only for trading bot)
│   ├── ensemble.pkl
│   ├── ppo_model.pkl
│   └── sac_model.pkl
└── backups/        # Database backups (read-write)
    └── 2025-01-15/
```

### Volume Permissions

```bash
# Set correct ownership
sudo chown -R 1000:1000 ./data

# Set correct permissions
chmod 755 ./data
chmod 750 ./data/databases
chmod 750 ./data/cache
chmod 755 ./data/logs
chmod 550 ./data/models
chmod 750 ./data/backups
```

### Named Volumes vs Bind Mounts

**Use Bind Mounts (current setup) for:**
- Easy access to logs for debugging
- Manual database backups
- Direct model file updates
- Shared data between host and container

**Use Named Volumes for:**
- Better performance on Windows/Mac
- Automatic Docker management
- Production deployments with orchestration

**Example with Named Volumes:**
```yaml
volumes:
  - catalyst-databases:/data/databases
  - catalyst-cache:/data/cache
  - catalyst-logs:/data/logs

volumes:
  catalyst-databases:
    driver: local
  catalyst-cache:
    driver: local
  catalyst-logs:
    driver: local
```

---

## Environment Variable Management

### 1. Create Environment Files

```bash
# Production environment
touch .env.production

# Staging environment
touch .env.staging

# Development environment
touch .env.development
```

### 2. Production Environment File (`.env.production`)

```bash
# =============================================================================
# PRODUCTION ENVIRONMENT - PAPER TRADING
# =============================================================================

# Trading Configuration
TRADING_MODE=paper
ALPACA_PAPER=1
ALPACA_API_KEY=your_production_paper_key
ALPACA_SECRET=your_production_paper_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Discord Webhooks
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/PROD_WEBHOOK
DISCORD_ADMIN_WEBHOOK=https://discord.com/api/webhooks/PROD_ADMIN

# Risk Management
MAX_POSITION_PCT=0.20
MAX_PORTFOLIO_LEVERAGE=3.0
DAILY_LOSS_LIMIT_PCT=-0.03
MAX_TRADES_PER_DAY=40
KILL_SWITCH_ENABLED=1

# RL Configuration
RL_MODEL_PATH=/data/models/ensemble.pkl
RL_CONFIDENCE_THRESHOLD=0.6
RL_ENABLED=1

# API Keys
TIINGO_API_KEY=your_tiingo_key
FINNHUB_API_KEY=your_finnhub_key
GEMINI_API_KEY=your_gemini_key
ANTHROPIC_API_KEY=your_anthropic_key

# Monitoring
PROMETHEUS_PORT=9090
ENABLE_PERFORMANCE_TRACKING=1
LOG_LEVEL=INFO

# Database Configuration
DB_DIR=/data/databases
CACHE_DIR=/data/cache
LOG_DIR=/data/logs

# Grafana (for docker-compose)
GRAFANA_PASSWORD=secure_password_here
```

### 3. Secure Environment Files

```bash
# Restrict permissions
chmod 600 .env.production .env.staging .env.development

# Add to .gitignore
echo ".env.*" >> .gitignore

# Verify
ls -la .env.*
```

### 4. Environment Variable Precedence

Docker Compose resolves environment variables in this order (highest to lowest priority):

1. Environment variables set in `docker-compose.yml` → `environment:`
2. Variables from `env_file:` (.env.production)
3. Variables from shell environment
4. Variables from `.env` file (if exists)

---

## Health Checks

### 1. Application Health Endpoint

Create `/app/src/catalyst_bot/health.py`:

```python
from flask import Flask, jsonify
import time
import psutil
import os

app = Flask(__name__)
start_time = time.time()

@app.route('/health')
def health():
    """Health check endpoint for Docker"""
    uptime = time.time() - start_time

    # Check critical components
    checks = {
        'status': 'healthy',
        'uptime_seconds': int(uptime),
        'database': check_database(),
        'alpaca': check_alpaca(),
        'memory_usage_mb': psutil.virtual_memory().used / 1024 / 1024,
        'cpu_percent': psutil.cpu_percent(interval=0.1)
    }

    # Overall health
    if not all([checks['database'], checks['alpaca']]):
        checks['status'] = 'unhealthy'
        return jsonify(checks), 503

    return jsonify(checks), 200

def check_database():
    """Verify database connectivity"""
    try:
        import sqlite3
        db_path = os.getenv('DB_DIR', '/data/databases') + '/positions.db'
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute('SELECT 1').fetchone()
        conn.close()
        return True
    except Exception:
        return False

def check_alpaca():
    """Verify Alpaca API connectivity"""
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(
            os.getenv('ALPACA_API_KEY'),
            os.getenv('ALPACA_SECRET'),
            paper=True
        )
        client.get_account()
        return True
    except Exception:
        return False

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### 2. Docker Health Check Configuration

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
  interval: 60s       # Check every 60 seconds
  timeout: 10s        # Fail if check takes >10s
  retries: 3          # Mark unhealthy after 3 failures
  start_period: 120s  # Wait 2 minutes before first check
```

### 3. Monitor Health Status

```bash
# Check container health
docker ps

# View health check logs
docker inspect catalyst-trading-bot | jq '.[0].State.Health'

# Follow health checks in real-time
docker events --filter 'event=health_status'
```

---

## Resource Limits

### 1. CPU and Memory Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Maximum 2 CPU cores
      memory: 6G        # Maximum 6 GB RAM
    reservations:
      cpus: '1.0'      # Guaranteed 1 CPU core
      memory: 2G        # Guaranteed 2 GB RAM
```

### 2. Disk I/O Limits

```yaml
services:
  trading-bot:
    # ... other config ...
    blkio_config:
      weight: 500
      device_read_bps:
        - path: /dev/sda
          rate: '50mb'
      device_write_bps:
        - path: /dev/sda
          rate: '30mb'
```

### 3. Network Bandwidth Limits

```bash
# Using tc (traffic control) on host
sudo tc qdisc add dev eth0 root tbf rate 100mbit burst 32kbit latency 400ms

# Or use Docker network plugins
```

### 4. Monitor Resource Usage

```bash
# Real-time stats
docker stats catalyst-trading-bot

# Export to Prometheus
# Metrics available at http://localhost:9090/metrics
```

---

## Networking Configuration

### 1. Bridge Network (Default)

```yaml
networks:
  catalyst-network:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.25.0.0/16
          gateway: 172.25.0.1
```

**Benefits:**
- Containers can communicate by service name
- Isolated from host network
- Port mapping to host

### 2. Host Network (Low Latency)

```yaml
services:
  trading-bot:
    network_mode: "host"
```

**Benefits:**
- No NAT overhead
- Lower latency (critical for trading)
- Direct access to host network

**Drawbacks:**
- No network isolation
- Port conflicts with host

### 3. Service Communication

```yaml
# Trading bot can reach Prometheus by hostname
curl http://prometheus:9090/api/v1/query

# Slack bot can query trading bot
curl http://trading-bot:5000/health
```

### 4. External Access

```bash
# Access from host
curl http://localhost:9090/metrics       # Prometheus metrics
curl http://localhost:3001                # Grafana UI
curl http://localhost:5000/health         # Trading bot health

# Access from external network (configure firewall)
sudo ufw allow 9090/tcp comment 'Prometheus'
sudo ufw allow 3001/tcp comment 'Grafana'
```

---

## Multi-App Deployment

### Scenario: Trading Bot + Slack Bot + Discord Bot

```yaml
version: '3.8'

services:
  # Trading Bot (primary)
  trading-bot:
    build:
      context: .
      dockerfile: docker/Dockerfile
    # ... (see main config) ...
    networks:
      - catalyst-network

  # Slack Bot (alerts)
  slack-bot:
    build:
      context: .
      dockerfile: docker/Dockerfile.slack
    volumes:
      - ./data/databases:/data/databases:ro  # Read-only
      - ./data/logs/slack:/data/logs:rw
    ports:
      - "3000:3000"
    networks:
      - catalyst-network
    depends_on:
      - trading-bot

  # Discord Bot (admin controls)
  discord-bot:
    build:
      context: .
      dockerfile: docker/Dockerfile.discord
    volumes:
      - ./data/databases:/data/databases:ro  # Read-only
      - ./data/logs/discord:/data/logs:rw
    ports:
      - "8080:8080"
    networks:
      - catalyst-network
    depends_on:
      - trading-bot

networks:
  catalyst-network:
    driver: bridge
```

### Shared Database Access

**Problem:** Multiple containers accessing same SQLite database can cause locks.

**Solutions:**

1. **Read-Only Access for Non-Critical Apps**
   ```yaml
   volumes:
     - ./data/databases:/data/databases:ro
   ```

2. **PostgreSQL for Multi-Writer**
   ```yaml
   services:
     postgres:
       image: postgres:16-alpine
       environment:
         POSTGRES_DB: catalyst
         POSTGRES_USER: catalyst
         POSTGRES_PASSWORD: ${DB_PASSWORD}
       volumes:
         - postgres-data:/var/lib/postgresql/data
   ```

3. **SQLite WAL Mode**
   ```bash
   # Enable in .env
   SQLITE_WAL_MODE=1
   ```

---

## Building and Running

### 1. Build Images

```bash
# Build all services
docker compose build

# Build specific service
docker compose build trading-bot

# Build without cache (force rebuild)
docker compose build --no-cache

# Build with progress output
docker compose build --progress=plain
```

### 2. Start Containers

```bash
# Start all services
docker compose up -d

# Start specific service
docker compose up -d trading-bot

# Start with logs visible
docker compose up

# Start and recreate containers
docker compose up -d --force-recreate
```

### 3. Stop and Remove

```bash
# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v

# Stop specific service
docker compose stop trading-bot
```

### 4. View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f trading-bot

# Last 100 lines
docker compose logs --tail=100 trading-bot

# Since timestamp
docker compose logs --since 2025-01-15T10:00:00 trading-bot
```

### 5. Execute Commands in Container

```bash
# Open shell in trading bot
docker compose exec trading-bot /bin/bash

# Run Python script
docker compose exec trading-bot python -m catalyst_bot.scripts.validate_deployment

# View environment variables
docker compose exec trading-bot env | grep ALPACA
```

---

## Monitoring Containers

### 1. Container Status

```bash
# List running containers
docker compose ps

# Detailed status with health
docker compose ps -a

# Stats (CPU, memory, network, disk)
docker stats

# Continuous stats
watch -n 2 'docker stats --no-stream'
```

### 2. Prometheus Metrics

```bash
# Query Prometheus
curl 'http://localhost:9091/api/v1/query?query=catalyst_bot_portfolio_value'

# View all metrics
curl http://localhost:9090/metrics | grep catalyst_bot
```

### 3. Grafana Dashboards

```bash
# Access Grafana UI
open http://localhost:3001

# Default credentials
# Username: admin
# Password: (set in GRAFANA_PASSWORD env var)
```

### 4. Health Monitoring Script

```bash
#!/bin/bash
# monitor-containers.sh

while true; do
    echo "=== Container Health Status ==="
    docker compose ps

    echo ""
    echo "=== Resource Usage ==="
    docker stats --no-stream

    echo ""
    echo "=== Health Checks ==="
    docker inspect catalyst-trading-bot | jq '.[0].State.Health.Status'

    sleep 60
done
```

---

## Troubleshooting

### Issue 1: Container Won't Start

**Symptoms:**
- `docker compose up` fails
- Container in "Restarting" state

**Diagnosis:**
```bash
# Check logs
docker compose logs trading-bot

# Inspect container
docker inspect catalyst-trading-bot

# Check exit code
docker inspect catalyst-trading-bot | jq '.[0].State.ExitCode'
```

**Solutions:**
```bash
# Rebuild image
docker compose build --no-cache trading-bot

# Check environment file
cat .env.production | grep -v "^#" | grep "="

# Verify file permissions
ls -la ./data/databases/
```

---

### Issue 2: Volume Permission Denied

**Symptoms:**
- "Permission denied" errors in logs
- Cannot write to database

**Diagnosis:**
```bash
# Check volume ownership
ls -la ./data/databases/

# Check container user
docker compose exec trading-bot whoami
docker compose exec trading-bot id
```

**Solutions:**
```bash
# Fix ownership (user ID 1000 from Dockerfile)
sudo chown -R 1000:1000 ./data

# Or match your host user
sudo chown -R $USER:$USER ./data
```

---

### Issue 3: Network Connection Issues

**Symptoms:**
- Cannot reach Alpaca API
- DNS resolution fails

**Diagnosis:**
```bash
# Test network connectivity
docker compose exec trading-bot ping -c 3 8.8.8.8

# Test DNS
docker compose exec trading-bot nslookup api.alpaca.markets

# Test Alpaca API
docker compose exec trading-bot curl -v https://paper-api.alpaca.markets/v2/account
```

**Solutions:**
```bash
# Add DNS servers to daemon.json
sudo vim /etc/docker/daemon.json
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}

# Restart Docker
sudo systemctl restart docker

# Or use host network
# (change in docker-compose.yml)
network_mode: "host"
```

---

### Issue 4: Out of Memory

**Symptoms:**
- Container killed by OOMKiller
- Exit code 137

**Diagnosis:**
```bash
# Check memory usage
docker stats catalyst-trading-bot

# Check OOM kills in logs
dmesg | grep -i oom
journalctl -u docker | grep -i oom
```

**Solutions:**
```bash
# Increase memory limit
# In docker-compose.yml:
deploy:
  resources:
    limits:
      memory: 8G  # Increase from 6G

# Or reduce model complexity
# In .env.production:
RL_MODEL_SIZE=small
```

---

### Issue 5: Slow Performance

**Symptoms:**
- Container running slow
- High CPU usage

**Diagnosis:**
```bash
# Profile container
docker stats catalyst-trading-bot

# Check I/O bottlenecks
docker exec catalyst-trading-bot iostat -x 5
```

**Solutions:**
```bash
# Use tmpfs for cache
# In docker-compose.yml:
volumes:
  - type: tmpfs
    target: /data/cache
    tmpfs:
      size: 1G

# Optimize database
docker compose exec trading-bot python -m catalyst_bot.database.optimize

# Enable WAL mode
# In .env:
SQLITE_WAL_MODE=1
```

---

## Best Practices

### 1. Multi-Stage Builds
- Reduce final image size
- Separate build dependencies from runtime
- Faster deployments

### 2. Layer Caching
- Order Dockerfile instructions properly
- Copy `requirements.txt` before source code
- Minimize layer invalidation

### 3. Security
- Use non-root user
- Scan images for vulnerabilities
- Keep base images updated

```bash
# Scan image
docker scan catalyst-trading-bot

# Update base image
docker pull python:3.10-slim-bullseye
docker compose build --no-cache
```

### 4. Logging
- Use JSON structured logs
- Limit log file sizes
- Aggregate logs centrally (ELK stack)

### 5. Secrets Management
- Use Docker secrets (Swarm mode)
- Or external secret managers (HashiCorp Vault)
- Never commit .env files

---

## Next Steps

1. **Deploy to production**: `docker compose -f docker-compose.yml up -d`
2. **Set up monitoring**: Access Grafana at http://localhost:3001
3. **Configure backups**: Schedule database backup containers
4. **Implement CI/CD**: Automate builds and deployments (see ci-cd.md)
5. **Scale horizontally**: Use Docker Swarm or Kubernetes

---

**End of Docker Deployment Guide**
