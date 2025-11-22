# Paper Trading Bot - Deployment Documentation Index

**Version:** 1.0
**Last Updated:** November 2025

---

## Overview

This directory contains comprehensive deployment and operational documentation for the Catalyst Paper Trading Bot. All guides are production-ready and include step-by-step instructions, complete configuration files, and troubleshooting sections.

---

## Documentation Structure

```
docs/deployment/
├── README.md                    # This file - Documentation index
├── production-setup.md          # Production deployment guide
├── docker-setup.md              # Docker and container deployment
├── monitoring.md                # Monitoring, metrics, and alerting
├── disaster-recovery.md         # Backup, restore, and emergency procedures
└── .github/workflows/           # CI/CD pipeline configurations
    ├── trading-bot-ci.yml       # Continuous integration (tests, quality)
    └── trading-bot-deploy.yml   # Continuous deployment (staging, production)
```

---

## Quick Start

### For First-Time Deployment

1. **Read the Implementation Plan** (if not already done)
   - `/home/user/catalyst-bot/docs/paper-trading-bot-implementation-plan.md`

2. **Choose Your Deployment Method**
   - **Traditional Server:** → [Production Setup Guide](#1-production-deployment-guide)
   - **Containerized:** → [Docker Setup Guide](#2-docker-deployment-guide)

3. **Set Up Monitoring** (Required for production)
   - [Monitoring and Alerting Guide](#3-monitoring-and-alerting-guide)

4. **Prepare for Emergencies**
   - [Disaster Recovery Guide](#4-disaster-recovery-guide)

5. **Configure CI/CD** (Recommended for teams)
   - [CI/CD Pipeline](#5-cicd-pipeline)

---

## 1. Production Deployment Guide

**File:** `production-setup.md`

**Purpose:** Deploy the paper trading bot on a traditional Ubuntu server using systemd for process management.

**Contents:**
- Server requirements (CPU, RAM, storage)
- OS setup (Ubuntu 22.04 LTS)
- Python environment configuration
- Dependency installation
- Database initialization
- Environment variable configuration
- SSL/TLS setup for webhooks
- Firewall configuration (UFW)
- systemd service creation
- Auto-restart on failure
- Log rotation with logrotate
- Automated backup strategy

**When to Use:**
- Deploying to a dedicated server (bare metal or VPS)
- Need direct control over the system
- Single-server deployment
- Non-containerized environment

**Time to Deploy:** 2-3 hours (first time), 30 minutes (subsequent)

**Prerequisites:**
- Ubuntu 22.04 LTS server
- SSH access with sudo privileges
- Alpaca paper trading account
- API keys for market data providers

---

## 2. Docker Deployment Guide

**File:** `docker-setup.md`

**Purpose:** Deploy the paper trading bot using Docker containers for isolation, portability, and easy scaling.

**Contents:**
- Dockerfile creation and optimization
- docker-compose.yml for multi-container setup
- Volume mounts for data persistence
- Environment variable management (.env files)
- Health checks configuration
- Resource limits (CPU, memory)
- Networking configuration
- Multi-app deployment (trading bot + Slack bot + Discord bot)
- Container monitoring

**When to Use:**
- Need consistent environments (dev/staging/production)
- Multi-app deployment
- Want easy rollbacks
- Kubernetes/orchestration in the future
- Development on Windows/Mac

**Time to Deploy:** 1-2 hours (first time), 15 minutes (subsequent)

**Prerequisites:**
- Docker 24.0+ installed
- Docker Compose 2.20+ installed
- Basic Docker knowledge
- API keys and credentials

**Key Features:**
- Multi-stage builds for smaller images
- Non-root user for security
- Automatic health checks
- Resource limits enforcement
- Shared volumes for multi-app setups

---

## 3. Monitoring and Alerting Guide

**File:** `monitoring.md`

**Purpose:** Set up comprehensive monitoring, metrics collection, and alerting for production operations.

**Contents:**
- Prometheus metrics export
  - Portfolio metrics (value, P&L, positions)
  - Performance metrics (Sharpe ratio, win rate, drawdown)
  - Trading activity (orders, trades, success rate)
  - System metrics (CPU, memory, disk)
- Grafana dashboard setup
  - Pre-built dashboard JSON
  - Custom panels and visualizations
- Alert rules and thresholds
  - Critical alerts (kill switch, daily loss)
  - High priority alerts (error rate, API issues)
  - Medium priority alerts (performance degradation)
- Notification channels
  - Discord webhooks
  - Email notifications
  - Slack integration
- Structured logging strategy
  - JSON logging format
  - Log levels and best practices
- Log aggregation (optional)
  - ELK stack setup
  - Loki + Promtail (lightweight alternative)

**When to Use:**
- Always! Required for production deployments
- Before running live paper trading
- For performance analysis and optimization

**Time to Set Up:** 2-3 hours

**Prerequisites:**
- Deployed trading bot
- Prometheus and Grafana (Docker or standalone)
- Discord/Email/Slack webhook URLs

**Key Metrics:**
- Portfolio value and daily P&L
- Open positions and concentration
- Order success rate and latency
- API performance and error rates
- System resource usage

---

## 4. Disaster Recovery Guide

**File:** `disaster-recovery.md`

**Purpose:** Comprehensive backup, restore, and emergency procedures for all disaster scenarios.

**Contents:**
- Backup procedures
  - Manual backup scripts
  - Automated daily/weekly backups
  - Backup verification
  - Retention policies
- Database backup automation
  - systemd timers
  - Cloud storage sync (S3, GCS)
  - Online backups (SQLite)
- Restore procedures
  - Full system restore
  - Single database restore
  - Cloud storage restore
- Kill switch activation
  - Manual emergency stop
  - Automated circuit breakers
  - Order cancellation
- Emergency position liquidation
  - Close all positions
  - Selective closures (losing, old, high exposure)
- Data corruption recovery
  - Integrity checks
  - Repair procedures
  - Rebuild from backups
- API key rotation
  - Zero-downtime rotation
  - Security best practices
- Incident response checklist
  - Critical incidents (Severity 1)
  - High priority incidents (Severity 2)
- Common disaster scenarios
  - Server hardware failure
  - Database corruption
  - Accidental file deletion
  - API outages
  - Security breaches

**When to Use:**
- Set up immediately after deployment
- Monthly DR drills
- During incidents and emergencies
- Quarterly security audits

**Recovery Targets:**
- **RTO (Recovery Time Objective):** < 1 hour
- **RPO (Recovery Point Objective):** < 24 hours

**Key Features:**
- Automated backups (no manual intervention)
- Cloud storage for off-site backups
- Tested restore procedures
- Emergency kill switch scripts
- Incident response playbooks

---

## 5. CI/CD Pipeline

**Files:**
- `.github/workflows/trading-bot-ci.yml` - Continuous Integration
- `.github/workflows/trading-bot-deploy.yml` - Continuous Deployment

**Purpose:** Automated testing, quality checks, and deployment pipeline for safe and reliable releases.

### 5.1 Continuous Integration (`trading-bot-ci.yml`)

**Triggers:**
- Pull requests to `main` or `develop`
- Pushes to `develop` branch

**Jobs:**
1. **Code Quality**
   - Black (formatting)
   - isort (import sorting)
   - Flake8 (linting)
   - MyPy (type checking)

2. **Security Checks**
   - Bandit (security linter)
   - Safety (dependency vulnerabilities)

3. **Unit Tests**
   - Multi-version testing (Python 3.9, 3.10, 3.11)
   - Coverage reporting (70% minimum)
   - Parallel execution with pytest-xdist

4. **Integration Tests**
   - Broker API tests (Alpaca)
   - RL model tests
   - Database tests

5. **Docker Build**
   - Build test image
   - Vulnerability scanning with Trivy
   - Smoke tests

6. **Performance Benchmarks**
   - pytest-benchmark
   - Regression detection

**Time:** 10-15 minutes

### 5.2 Continuous Deployment (`trading-bot-deploy.yml`)

**Triggers:**
- Pushes to `main` branch
- Manual workflow dispatch

**Stages:**

1. **Pre-Deployment Validation**
   - Run critical tests
   - Configuration validation

2. **Build and Push**
   - Build Docker image
   - Push to container registry
   - Tag with version/SHA

3. **Deploy to Staging** (Automatic)
   - Pull latest image
   - Blue-green deployment
   - Health checks
   - Smoke tests

4. **Deploy to Production** (Manual Approval Required)
   - Pre-deployment backup
   - Blue-green deployment
   - Gradual rollout
   - 10-minute monitoring
   - Automated rollback on failure

5. **Post-Deployment Monitoring**
   - 30-minute metrics monitoring
   - Error rate tracking
   - Deployment report generation

**Time:** 20-30 minutes (staging), 45-60 minutes (production)

**Security:**
- Secrets stored in GitHub Secrets
- Container image signing (optional)
- SSH key-based authentication
- Least-privilege access

---

## Deployment Workflows

### Recommended Workflow for New Deployments

```
1. Development
   ├── Implement features locally
   ├── Run tests: pytest tests/
   └── Commit and push to feature branch

2. Pull Request
   ├── Create PR to develop branch
   ├── CI runs automatically (trading-bot-ci.yml)
   ├── Code review
   └── Merge to develop

3. Staging Deployment
   ├── Merge develop to main
   ├── CD triggers automatically (trading-bot-deploy.yml)
   ├── Deploys to staging
   └── Run smoke tests

4. Production Deployment
   ├── Manual approval in GitHub
   ├── Pre-deployment backup
   ├── Blue-green deployment
   ├── Health checks
   └── 10-minute monitoring

5. Post-Deployment
   ├── Monitor for 24 hours
   ├── Review metrics in Grafana
   └── Document any issues
```

### Emergency Hotfix Workflow

```
1. Create hotfix branch from main
2. Implement fix
3. Run tests locally
4. Push and create PR
5. Emergency approval process
6. Merge to main
7. Deploy with skip_tests option (if critical)
8. Monitor closely for 1 hour
9. Backport to develop
```

---

## Common Tasks

### Deploy to Production (First Time)

```bash
# 1. Choose deployment method
# Option A: Traditional server
cd ~/catalyst-bot
./docs/deployment/production-setup.md  # Follow guide

# Option B: Docker
cd ~/catalyst-bot
docker compose up -d
```

### Set Up Monitoring

```bash
# 1. Start Prometheus and Grafana
docker compose up -d prometheus grafana

# 2. Access Grafana
open http://localhost:3001
# Login: admin / <GRAFANA_PASSWORD>

# 3. Import dashboard
# Dashboard → Import → Upload trading-bot-overview.json
```

### Create Manual Backup

```bash
cd ~/catalyst-bot
./scripts/manual-backup.sh
```

### Activate Kill Switch

```bash
cd ~/catalyst-bot
./scripts/kill-switch.sh
```

### Restore from Backup

```bash
cd ~/catalyst-bot
./scripts/restore-from-backup.sh /path/to/backup.tar.gz
```

### Check System Health

```bash
# Docker deployment
docker compose ps
docker compose logs -f trading-bot

# Traditional deployment
sudo systemctl status catalyst-trading-bot.service
sudo journalctl -u catalyst-trading-bot.service -f

# Check metrics
curl http://localhost:9090/metrics | grep catalyst_bot
```

---

## Troubleshooting

### Bot Won't Start

1. Check logs: `docker compose logs trading-bot` or `journalctl -u catalyst-trading-bot`
2. Verify environment variables: `cat .env`
3. Test Alpaca connectivity: `python -m catalyst_bot.broker.test_connection`
4. Check database integrity: `./scripts/check-database-integrity.sh`

### High Error Rate

1. Check Grafana dashboard for error details
2. Review logs: `grep ERROR data/logs/trading-bot.log`
3. Verify API keys are valid
4. Check API status pages (Alpaca, Tiingo, etc.)

### Deployment Failed

1. Check CI/CD logs in GitHub Actions
2. Verify secrets are configured correctly
3. Test SSH connectivity to server
4. Check disk space and resource limits

---

## Best Practices

### Security

- [ ] Never commit `.env` files to git
- [ ] Rotate API keys quarterly
- [ ] Use SSH keys, not passwords
- [ ] Enable 2FA on all accounts
- [ ] Restrict firewall to necessary ports only
- [ ] Run containers as non-root user
- [ ] Scan Docker images for vulnerabilities

### Reliability

- [ ] Set up automated backups (daily minimum)
- [ ] Test restore procedures monthly
- [ ] Monitor metrics continuously
- [ ] Set up alerts for critical thresholds
- [ ] Document all incidents
- [ ] Run DR drills quarterly

### Performance

- [ ] Monitor resource usage (CPU, memory, disk)
- [ ] Optimize database queries (enable WAL mode)
- [ ] Use caching for API responses
- [ ] Profile slow operations
- [ ] Set appropriate resource limits

### Compliance

- [ ] Keep audit logs for all trades
- [ ] Backup logs for 90 days minimum
- [ ] Document all configuration changes
- [ ] Track API usage and costs
- [ ] Review security annually

---

## Support and Resources

### Documentation

- [Paper Trading Bot Implementation Plan](../paper-trading-bot-implementation-plan.md)
- [Alpaca API Documentation](https://docs.alpaca.markets/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Docker Documentation](https://docs.docker.com/)

### Getting Help

- **GitHub Issues:** https://github.com/yourusername/catalyst-bot/issues
- **Discord Community:** [Your Discord Server]
- **Email Support:** [Your Support Email]

### External Resources

- [Python Best Practices](https://docs.python-guide.org/)
- [12-Factor App Methodology](https://12factor.net/)
- [systemd Documentation](https://www.freedesktop.org/software/systemd/man/)
- [Docker Compose Best Practices](https://docs.docker.com/compose/production/)

---

## Changelog

### Version 1.0 (November 2025)

- Initial release of comprehensive deployment documentation
- Production deployment guide for Ubuntu servers
- Docker deployment guide with multi-container support
- Monitoring guide with Prometheus and Grafana
- Disaster recovery procedures and scripts
- CI/CD pipeline with GitHub Actions
- Automated testing and quality checks
- Blue-green deployment strategy

---

## Contributing

If you find issues with the documentation or have suggestions for improvements:

1. Open an issue describing the problem
2. Submit a pull request with corrections
3. Update the changelog when adding new sections

---

**End of Deployment Documentation Index**
