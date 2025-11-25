# Security Remediation Plan
**Date**: November 24, 2025
**Source**: GitHub Dependabot + CodeQL Alerts

## Critical Issues (Immediate Action Required)

### 1. Exposed Secrets in Git History ⚠️ **CRITICAL**

**Status**: Detected in git history (already removed from current files)

**Affected Secrets**:
- ✗ Anthropic API Key (`sk-ant-api03-B4nXykLQxUPV6R...`)
- ✗ Discord Bot Token (`MTM5ODUyMTQ...`)
- ✗ Google API Key (`AIzaSyD5oG5EDvyGZuYDKY6FAHF...`)

**Files** (historical commits):
- `docs/operations/ENV_REVIEW_AND_RECOMMENDATIONS.md:300`
- `docs/operations/WEBHOOK_ROTATION_GUIDE.m...:145`
- `docs/operations/ENV_REVIEW_AND_RECOMMEND...:297`

**Required Actions**:
1. **IMMEDIATELY ROTATE ALL KEYS**:
   - [ ] Revoke Anthropic API key at https://console.anthropic.com
   - [ ] Revoke Discord webhook/bot token at Discord Developer Portal
   - [ ] Revoke Google API key at https://console.cloud.google.com

2. **Update .env with NEW keys**:
   ```bash
   ANTHROPIC_API_KEY=<new_key>
   DISCORD_WEBHOOK_URL=<new_webhook>
   GOOGLE_API_KEY=<new_key>
   ```

3. **Clean Git History** (choose one):

   **Option A: BFG Repo Cleaner (Recommended)**:
   ```bash
   # Download BFG: https://rtyley.github.io/bfg-repo-cleaner/
   java -jar bfg.jar --replace-text passwords.txt catalyst-bot/
   cd catalyst-bot
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   git push --force
   ```

   **Option B: git-filter-repo**:
   ```bash
   pip install git-filter-repo
   git filter-repo --invert-paths --path docs/operations/ENV_REVIEW_AND_RECOMMENDATIONS.md
   git push --force
   ```

4. **GitHub Secret Scanning**:
   - Go to GitHub repo Settings → Security → Secret scanning alerts
   - Mark each alert as "Revoked" after rotating keys

---

## High Severity Code Issues

### 2. Path Injection Vulnerabilities (CWE-22) 🔴 **HIGH**

**Location**: `src/catalyst_bot/market.py:85, 90, 107`

**Issue**: User-controlled `ticker` parameter used in file paths without sanitization

**Vulnerable Code**:
```python
def _alpha_cached_last_prev(ticker, api_key, timeout=10.0):
    key = ticker.upper()  # ← User input
    cache_file = _AV_CACHE_PATH / f"{key}.json"  # ← Path injection!
    # ...
    if cache_file.exists():  # Line 89-90
        with cache_file.open("r", encoding="utf-8") as fp:  # Line 90
    # ...
    with cache_file.open("w", encoding="utf-8") as fp:  # Line 107
```

**Attack Vector**:
```python
# Attacker input:
ticker = "../../../etc/passwd"
# Results in path:
# /path/to/cache/../../../../etc/passwd.json
```

**Fix** (Add input sanitization):
```python
import re

def _sanitize_ticker(ticker: str) -> str:
    """Sanitize ticker for safe file path usage."""
    # Allow only alphanumeric characters and common ticker symbols
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Invalid ticker")

    # Remove any path traversal characters
    sanitized = re.sub(r'[^A-Z0-9\-\.]', '', ticker.upper())

    # Ensure it's not empty after sanitization
    if not sanitized or len(sanitized) > 10:
        raise ValueError(f"Invalid ticker: {ticker}")

    return sanitized

def _alpha_cached_last_prev(ticker, api_key, timeout=10.0):
    key = _sanitize_ticker(ticker)  # ← Add sanitization
    cache_file = _AV_CACHE_PATH / f"{key}.json"
    # ... rest of code unchanged
```

**Files to Update**:
- [x] `src/catalyst_bot/market.py` - Add `_sanitize_ticker()` function
- [x] `src/catalyst_bot/market.py:85` - Use `_sanitize_ticker(ticker)`

---

### 3. Incomplete URL Sanitization (CWE-20) 🔴 **HIGH**

**Location**: `src/catalyst_bot/runner.py:1876`

**Issue**: `_mask_webhook()` function doesn't properly sanitize webhook URLs

**Current Code** (needs review):
```python
def _mask_webhook(url: str) -> str:
    # Incomplete implementation - allows partial token exposure
    pass
```

**Fix** (Proper masking):
```python
def _mask_webhook(url: str) -> str:
    """Mask sensitive parts of webhook URL for logging."""
    if not url:
        return ""

    # Discord webhook format: https://discord.com/api/webhooks/{id}/{token}
    # Mask the token part completely
    import re
    pattern = r'(https?://[^/]+/[^/]+/webhooks/)([^/]+)/(.+)'
    match = re.match(pattern, url)

    if match:
        base, webhook_id, token = match.groups()
        # Show first 8 chars of ID, mask token completely
        masked_id = webhook_id[:8] + "..." if len(webhook_id) > 8 else webhook_id
        return f"{base}{masked_id}/***REDACTED***"

    # Generic URL masking
    return url.split('?')[0] + "?***PARAMS_REDACTED***"
```

**Files to Update**:
- [ ] `src/catalyst_bot/runner.py:1876` - Replace `_mask_webhook()` implementation

---

### 4. Clear-text Storage/Logging of Sensitive Information 🔴 **HIGH**

**Issue 4a**: `jobs/earnings_pull.py:92` - API key in clear-text

**Current Code**:
```python
# Line 92
api_key = os.getenv("TIINGO_API_KEY")
# Logged in clear text somewhere
```

**Fix**:
```python
# Never log API keys, even partially
log.info("tiingo_request ticker=%s", ticker)  # ← Remove api_key from logs
```

**Issue 4b**: `tests/manual/test_tiingo_direct.py:29` - API key logged

**Current Code**:
```python
# Line 29
log.info(f"Using API key: {api_key}")  # ← NEVER DO THIS
```

**Fix**:
```python
# Mask API keys in test logs
masked_key = api_key[:8] + "..." if api_key else "NOT_SET"
log.info(f"Using API key: {masked_key}")
```

**Files to Update**:
- [ ] `jobs/earnings_pull.py:92` - Remove API key from logging
- [ ] `tests/manual/test_tiingo_direct.py:29` - Mask API key in logs

---

### 5. Information Exposure Through Exception (CWE-209) 🟡 **MEDIUM**

**Location**: `src/catalyst_bot/discord_interactions.py:479`

**Issue**: Exception messages may leak sensitive system information

**Current Code**:
```python
except Exception as e:
    log.error(f"discord_interaction_failed error={str(e)}")  # ← May leak paths, keys
    return {"error": str(e)}  # ← Never return raw exceptions to users!
```

**Fix**:
```python
except ValueError as e:
    # Log full error internally
    log.error("discord_interaction_failed error=%s", str(e), exc_info=True)
    # Return generic error to user
    return {"error": "Invalid request parameters"}

except Exception as e:
    # Log full error internally
    log.error("discord_interaction_failed error=%s", str(e), exc_info=True)
    # Return generic error to user
    return {"error": "An unexpected error occurred"}
```

**Files to Update**:
- [ ] `src/catalyst_bot/discord_interactions.py:479` - Generic error messages

---

## Medium Severity Issues

### 6. Workflow Permissions Missing (13 workflows) 🟡 **MEDIUM**

**Issue**: GitHub Actions workflows don't specify permissions (overly permissive)

**Affected Files**:
```
.github/workflows/trading-bot-ci.yml:372
.github/workflows/trading-bot-ci.yml:327
.github/workflows/trading-bot-ci.yml:301
.github/workflows/trading-bot-ci.yml:251
.github/workflows/trading-bot-ci.yml:198
.github/workflows/trading-bot-ci.yml:176
.github/workflows/trading-bot-ci.yml:130
.github/workflows/trading-bot-ci.yml:118
.github/workflows/trading-bot-ci.yml:70
.github/workflows/trading-bot-ci.yml:35
.github/workflows/trading-bot-deploy.yml:383
.github/workflows/trading-bot-deploy.yml:339
.github/workflows/trading-bot-deploy.yml:198
```

**Fix** (Add to each workflow job):
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:  # ← Add this
      contents: read
      pull-requests: read
    steps:
      # ... existing steps
```

**Files to Update**:
- [ ] `.github/workflows/trading-bot-ci.yml` - Add permissions to 10 jobs
- [ ] `.github/workflows/trading-bot-deploy.yml` - Add permissions to 3 jobs

---

### 7. esbuild Development Server Vulnerability 🟡 **MODERATE**

**Issue**: `esbuild` package allows arbitrary requests in development

**Location**: `workers/interactions/package-lock.json`

**Current Version**: Unknown (needs check)
**Required Action**: Update to latest version

**Fix**:
```bash
cd workers/interactions
npm update esbuild
npm audit fix
```

**Files to Update**:
- [ ] `workers/interactions/package-lock.json` - Update esbuild dependency

---

## Implementation Checklist

### Phase 1: Immediate (Today)
- [ ] **CRITICAL**: Rotate all 3 exposed API keys
- [ ] Update .env with new keys
- [ ] Test bot still works with new keys
- [ ] Mark GitHub secret alerts as "Revoked"

### Phase 2: High Priority (This Week)
- [ ] Fix path injection in `market.py` (add `_sanitize_ticker()`)
- [ ] Fix URL sanitization in `runner.py` (improve `_mask_webhook()`)
- [ ] Remove sensitive data from logs (`earnings_pull.py`, `test_tiingo_direct.py`)
- [ ] Fix exception exposure in `discord_interactions.py`

### Phase 3: Medium Priority (Next Week)
- [ ] Add GitHub Actions workflow permissions (13 files)
- [ ] Update esbuild dependency
- [ ] Clean git history (BFG Repo Cleaner or git-filter-repo)

### Phase 4: Verification
- [ ] Run CodeQL scan again
- [ ] Run Dependabot scan again
- [ ] Verify all alerts resolved
- [ ] Document changes in commit message

---

## Testing After Fixes

1. **API Key Rotation**:
   ```bash
   # Test bot startup
   python -m catalyst_bot.runner --once

   # Verify Discord webhook works
   # Verify Anthropic API works
   # Verify Google API works
   ```

2. **Path Injection Fix**:
   ```python
   # Test with malicious input
   from catalyst_bot import market

   # Should raise ValueError
   market._sanitize_ticker("../../../etc/passwd")
   market._sanitize_ticker("A" * 20)  # Too long
   market._sanitize_ticker("")  # Empty

   # Should work
   market._sanitize_ticker("AAPL")  # Returns "AAPL"
   market._sanitize_ticker("BRK.B")  # Returns "BRK.B"
   ```

3. **Logging Fixes**:
   ```bash
   # Check logs don't contain API keys
   grep -r "sk-ant" logs/
   grep -r "AIzaSy" logs/
   # Should return nothing
   ```

---

## Prevention (Future)

1. **Pre-commit Hooks**:
   ```bash
   # Install detect-secrets
   pip install detect-secrets
   detect-secrets scan > .secrets.baseline

   # Add to .pre-commit-config.yaml
   - repo: https://github.com/Yelp/detect-secrets
     rev: v1.4.0
     hooks:
       - id: detect-secrets
         args: ['--baseline', '.secrets.baseline']
   ```

2. **GitHub Secret Scanning**:
   - Already enabled (detected these issues)
   - Keep enabled in repo settings

3. **CodeQL Scanning**:
   - Already enabled
   - Runs on every PR

4. **Dependency Updates**:
   - Enable Dependabot auto-updates
   - Review security advisories weekly

---

## Resources

- **Secret Rotation**:
  - Anthropic: https://console.anthropic.com/settings/keys
  - Discord: https://discord.com/developers/applications
  - Google Cloud: https://console.cloud.google.com/apis/credentials

- **Git History Cleaning**:
  - BFG Repo Cleaner: https://rtyley.github.io/bfg-repo-cleaner/
  - git-filter-repo: https://github.com/newren/git-filter-repo

- **Security Best Practices**:
  - OWASP Top 10: https://owasp.org/www-project-top-ten/
  - CWE List: https://cwe.mitre.org/

---

**Priority Order**:
1. ⚠️ Rotate exposed API keys (IMMEDIATE)
2. 🔴 Fix path injection (HIGH)
3. 🔴 Fix logging of sensitive data (HIGH)
4. 🟡 Fix workflow permissions (MEDIUM)
5. 🟡 Update dependencies (MEDIUM)
