# Catalyst-Bot Deployment Checklist

This comprehensive checklist ensures safe and reliable deployments of Catalyst-Bot to production.

**WAVE 2.3: 24/7 Deployment Infrastructure**

---

## Pre-Deployment Verification

### Code Quality
- [ ] All tests passing (`pytest`)
- [ ] No failing pre-commit hooks
- [ ] Code review completed (if applicable)
- [ ] No critical TODOs or FIXMEs in new code
- [ ] Documentation updated for new features

### Configuration
- [ ] `.env` file exists and is properly configured
- [ ] All required API keys are set and valid:
  - [ ] `DISCORD_WEBHOOK_URL` - Alerts webhook
  - [ ] `DISCORD_ADMIN_WEBHOOK` - Admin notifications
  - [ ] `DISCORD_BOT_TOKEN` - For interactive components
  - [ ] `TIINGO_API_KEY` - Market data (if enabled)
  - [ ] `FINNHUB_API_KEY` - News data (if enabled)
  - [ ] `FINVIZ_AUTH_TOKEN` - Elite features (if enabled)
- [ ] `FEATURE_*` flags set correctly for production
- [ ] `PRICE_CEILING` appropriate for production
- [ ] `MIN_SCORE` tuned to reduce noise
- [ ] Log level set appropriately (`LOG_LEVEL=INFO` recommended)

### Infrastructure
- [ ] Cloudflare tunnel configured and tested
- [ ] Health endpoint accessible at `/health/ping`
- [ ] QuickChart service running (if `FEATURE_QUICKCHART=1`)
- [ ] Ollama service running (if `FEATURE_OLLAMA=1`)
- [ ] GPU drivers updated (if using GPU features)
- [ ] Sufficient disk space (>10GB free recommended)

### Dependencies
- [ ] Virtual environment exists (`.venv`)
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] No dependency conflicts (`pip check`)
- [ ] Database migrations applied (if any)

---

## Deployment Steps

### 1. Backup Current State

- [ ] Create timestamped backup directory:
  ```bash
  mkdir backups\%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
  ```

- [ ] Backup configuration:
  ```bash
  copy .env .env.backup
  ```

- [ ] Backup database (if using SQLite):
  ```bash
  copy data\catalyst.db backups\catalyst_%date%.db
  ```

- [ ] Note current git commit:
  ```bash
  git rev-parse HEAD > backups\last_commit.txt
  ```

- [ ] Tag release (if major deployment):
  ```bash
  git tag -a v1.x.x -m "Production release v1.x.x"
  git push origin v1.x.x
  ```

### 2. Stop Current Instance

**If running as a service:**
```bash
net stop CatalystBot
```

**If running manually:**
- Press `Ctrl+C` in the terminal
- Wait for graceful shutdown (up to 30 seconds)

- [ ] Service/process stopped
- [ ] Verify no orphaned Python processes:
  ```bash
  tasklist | findstr python
  ```

### 3. Update Code

- [ ] Pull latest changes:
  ```bash
  git fetch origin
  git pull origin main
  ```

- [ ] Verify on correct branch/tag:
  ```bash
  git status
  git log --oneline -5
  ```

### 4. Update Dependencies

- [ ] Activate virtual environment:
  ```bash
  .venv\Scripts\activate
  ```

- [ ] Install/update dependencies:
  ```bash
  pip install -r requirements.txt --upgrade
  ```

- [ ] Verify no errors in installation

### 5. Apply Migrations

- [ ] Check for pending migrations:
  ```bash
  # If using Alembic or similar
  # alembic current
  # alembic upgrade head
  ```

- [ ] Run any custom migration scripts (if applicable)

### 6. Configuration Updates

- [ ] Review `.env` changes in git diff
- [ ] Update `.env` with any new required settings
- [ ] Verify critical settings unchanged (unless intentional)
- [ ] Document any config changes in deployment notes

### 7. Pre-Start Validation

- [ ] Test health endpoint (if running separately):
  ```bash
  curl http://localhost:8080/health/ping
  ```

- [ ] Verify file permissions (logs, data directories)
- [ ] Check disk space again
- [ ] Review recent logs for any pre-existing issues

### 8. Start Bot

**If running as a service:**
```bash
net start CatalystBot
```

**If running manually:**
```bash
.venv\Scripts\python -m catalyst_bot.runner --loop
```

- [ ] Bot started successfully
- [ ] No immediate errors in console/logs

### 9. Verify Bot Health

Wait 2-5 minutes, then check:

- [ ] Health endpoint responds:
  ```bash
  curl http://localhost:8080/health/ping
  # Expected: ok
  ```

- [ ] Detailed health shows "healthy":
  ```bash
  curl http://localhost:8080/health/detailed
  # Check "status": "healthy"
  ```

- [ ] Discord connection established (check logs for "bot_start")

- [ ] First cycle completes successfully:
  ```bash
  # Check logs for "CYCLE_DONE"
  tail -n 50 data\logs\bot.jsonl
  ```

- [ ] No errors in service logs:
  ```bash
  # If using service
  type data\logs\service_stderr.log
  ```

### 10. Monitor Initial Cycles

Monitor for 5-10 minutes:

- [ ] Multiple cycles complete successfully
- [ ] Alerts posting to Discord (if any triggered)
- [ ] No unusual error spikes in logs
- [ ] Health endpoint stays healthy
- [ ] GPU usage normal (if applicable)
- [ ] Memory usage stable

### 11. External Monitoring

- [ ] UptimeRobot shows "Up" status
- [ ] Cloudflare tunnel accessible from external network
- [ ] Test alert via admin webhook received

---

## Post-Deployment Validation

### Functionality Tests

- [ ] Manual test: Trigger an alert (if safe in production)
- [ ] Verify rich alerts formatting (charts, indicators)
- [ ] Test admin commands (if interactive mode enabled)
- [ ] Check watchlist cascade updates (if enabled)
- [ ] Verify feedback loop tracking (if enabled)

### Performance Checks

- [ ] Review cycle times (should be <30s typically)
- [ ] Check GPU utilization (if using GPU features)
- [ ] Monitor memory usage trend
- [ ] Review disk I/O (should be minimal)
- [ ] Check database performance (query times)

### Log Review

- [ ] No ERROR level messages
- [ ] WARNING messages are expected/understood
- [ ] API rate limits not being hit
- [ ] No repeated failures on same tickers/sources

### Monitoring Setup

- [ ] UptimeRobot configured and alerting
- [ ] Watchdog enabled (if desired)
- [ ] Admin webhook notifications working
- [ ] Log rotation configured
- [ ] Cloudflare tunnel stable

---

## Deployment Sign-Off

- [ ] Deployment completed successfully
- [ ] All health checks passed
- [ ] Team notified of deployment
- [ ] Deployment notes documented
- [ ] Rollback procedure reviewed and ready

**Deployed by:** `_______________________`
**Date/Time:** `_______________________`
**Version/Commit:** `_______________________`
**Notes:**

```
_______________________________________________________
_______________________________________________________
_______________________________________________________
```

---

## Rollback Procedure

If issues are detected post-deployment:

### Option 1: Quick Config Rollback

If only configuration changed:

1. [ ] Stop the bot:
   ```bash
   net stop CatalystBot
   ```

2. [ ] Restore previous config:
   ```bash
   copy .env.backup .env
   ```

3. [ ] Restart bot:
   ```bash
   net start CatalystBot
   ```

4. [ ] Verify health restored

### Option 2: Full Code Rollback

If code changes are problematic:

1. [ ] Stop the bot:
   ```bash
   net stop CatalystBot
   ```

2. [ ] Revert to previous commit/tag:
   ```bash
   git log --oneline -10
   git checkout <previous-commit-hash>
   # Or: git checkout v1.x.x
   ```

3. [ ] Restore config (if needed):
   ```bash
   copy .env.backup .env
   ```

4. [ ] Reinstall dependencies (if requirements changed):
   ```bash
   pip install -r requirements.txt
   ```

5. [ ] Restart bot:
   ```bash
   net start CatalystBot
   ```

6. [ ] Verify health restored

### Option 3: Use Rollback Script

```bash
rollback.bat
# Follow prompts to enter git tag/commit
```

### Post-Rollback

- [ ] Verify bot is healthy
- [ ] Document what went wrong
- [ ] Create GitHub issue for the problem
- [ ] Plan fix and re-deployment
- [ ] Notify team of rollback

---

## Emergency Contacts

**If deployment fails and you need help:**

- **Primary Contact:** `_______________________`
- **Secondary Contact:** `_______________________`
- **Discord Server:** `_______________________`
- **GitHub Issues:** `https://github.com/Amenzel91/catalyst-bot/issues`

---

## Common Issues and Solutions

### Issue: Bot won't start

**Symptoms:** Service fails to start, immediate exit

**Check:**
- Virtual environment activated
- Dependencies installed
- `.env` file present and valid
- No syntax errors in Python files
- Port 8080 not already in use

**Fix:**
```bash
# Check service logs
type data\logs\service_stderr.log

# Run manually to see error
.venv\Scripts\python -m catalyst_bot.runner --once
```

### Issue: Health endpoint not responding

**Symptoms:** `curl` fails, UptimeRobot shows down

**Check:**
- Bot process running
- `FEATURE_HEALTH_ENDPOINT=1` in `.env`
- Correct port in `HEALTH_CHECK_PORT`
- Firewall not blocking port 8080
- Cloudflare tunnel running

**Fix:**
```bash
# Test locally first
curl http://localhost:8080/health/ping

# Check if port is listening
netstat -an | findstr :8080

# Restart bot
net stop CatalystBot
net start CatalystBot
```

### Issue: Alerts not posting

**Symptoms:** Bot running, but no Discord alerts

**Check:**
- `DISCORD_WEBHOOK_URL` is set correctly
- Webhook URL still valid (not deleted in Discord)
- `FEATURE_RECORD_ONLY=0` (alerts enabled)
- Market hours (may not be alerting outside hours)
- `MIN_SCORE` not set too high

**Fix:**
```bash
# Test webhook manually
curl -X POST -H "Content-Type: application/json" -d "{\"content\":\"Test\"}" DISCORD_WEBHOOK_URL

# Check bot logs for errors
tail -n 100 data\logs\bot.jsonl | findstr ERROR
```

### Issue: High memory/CPU usage

**Symptoms:** Bot sluggish, high resource usage

**Check:**
- GPU features enabled but no GPU present
- Large watchlist with many active features
- QuickChart generating too many charts
- Memory leak in long-running instance

**Fix:**
```bash
# Restart to clear memory
net stop CatalystBot
net start CatalystBot

# Disable resource-heavy features temporarily
# Edit .env: FEATURE_QUICKCHART=0, FEATURE_INDICATORS=0
```

### Issue: Database locked errors

**Symptoms:** SQLite errors in logs

**Check:**
- Multiple instances running
- Stale lock files
- Disk I/O issues

**Fix:**
```bash
# Ensure only one instance
tasklist | findstr python
taskkill /F /PID <pid>

# Remove lock file if exists
del data\catalyst.db-wal
del data\catalyst.db-shm
```

---

## Maintenance Schedule

**Daily:**
- Monitor health endpoint
- Check error logs
- Verify alerts posting

**Weekly:**
- Review deployment notes
- Check disk space
- Update dependencies (patch versions)
- Review UptimeRobot metrics

**Monthly:**
- Full backup of database and config
- Review and tune configuration
- Update dependencies (minor versions)
- Security updates

**Quarterly:**
- Major version upgrades
- Performance optimization
- Infrastructure review
- Disaster recovery test

---

## Version History

| Version | Date | Changes | Deployed By |
|---------|------|---------|-------------|
| v1.0.0  | YYYY-MM-DD | Initial deployment | Name |
| v1.1.0  | YYYY-MM-DD | Added feature X | Name |
|         |            |                    |      |

---

**End of Deployment Checklist**
**WAVE 2.3: 24/7 Deployment Infrastructure**
