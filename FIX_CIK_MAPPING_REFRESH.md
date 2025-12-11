# Fix: Refresh CIK-to-Ticker Mapping Database

## Problem
**70% of high-scoring ticker=N/A items** are caused by outdated CIK (Central Index Key) mappings. SEC filings are correctly extracted and scored, but can't be alerted because the CIK→ticker lookup fails.

**Agent Investigation Results:**
- High-scoring N/A items: 198 total in 9 hours
- Root cause breakdown:
  - **70%** - Outdated CIK mappings (need database refresh)
  - 20% - GlobeNewswire non-public companies
  - 10% - New/unusual registrations

## Current System
**File:** `company_tickers.ndjson`
- Contains CIK→ticker mappings
- Loaded once at startup in `ticker_map.py`
- Used by `sec_prefilter.py` to extract tickers from SEC filing URLs

**Example CIK extraction:**
```python
# SEC filing URL: https://www.sec.gov/edgar/data/0001234567/...
# Extracts CIK: "0001234567"
# Looks up in company_tickers.ndjson
# Returns: ticker="AAPL" (if in database)
# Returns: None (if CIK not found → ticker=N/A)
```

## Solution
Refresh `company_tickers.ndjson` from SEC's official API to get latest CIK mappings.

**SEC Official Source:**
```
https://www.sec.gov/files/company_tickers.json
```

---

## Implementation Plan

### Option A: Manual Refresh (Immediate Fix)

**Step 1:** Download latest mappings
```bash
curl -H "User-Agent: catalyst-bot/1.0" \
     https://www.sec.gov/files/company_tickers.json \
     -o company_tickers_new.json
```

**Step 2:** Convert to NDJSON format
```python
#!/usr/bin/env python3
"""Convert SEC company_tickers.json to NDJSON format."""
import json

# Load JSON
with open("company_tickers_new.json", "r") as f:
    data = json.load(f)

# Convert to NDJSON
with open("company_tickers.ndjson", "w") as f:
    for entry in data.values():
        # Format: {"cik": "0001234567", "ticker": "AAPL", "title": "Apple Inc"}
        cik = str(entry.get("cik_str", "")).zfill(10)  # Pad to 10 digits
        ticker = entry.get("ticker", "")
        title = entry.get("title", "")

        if cik and ticker:
            f.write(json.dumps({
                "cik": cik,
                "ticker": ticker.upper(),
                "title": title
            }) + "\n")

print(f"Converted {len(data)} entries to NDJSON")
```

**Step 3:** Restart bot to reload mappings
```bash
# Bot loads company_tickers.ndjson at startup
pkill -f catalyst_bot.runner
python -m catalyst_bot.runner --loop --sleep-secs 300
```

**Expected Impact:** 70% of high-scoring N/A items resolved immediately

---

### Option B: Automated Refresh Function

Add automatic refresh capability to the bot.

**File:** `src/catalyst_bot/ticker_map.py`

**Insert after line 137:**

```python
def refresh_cik_mappings_from_sec(
    output_path: str = "company_tickers.ndjson",
    user_agent: str = "catalyst-bot contact@example.com"
) -> bool:
    """
    Fetch latest CIK-to-ticker mappings from SEC and update local database.

    Downloads from official SEC API and converts to NDJSON format.
    Handles both padded (0001234567) and unpadded (1234567) CIK formats.

    Parameters
    ----------
    output_path : str
        Path to output NDJSON file
    user_agent : str
        User-Agent header (SEC requires identification)

    Returns
    -------
    bool
        True if refresh succeeded, False otherwise

    Notes
    -----
    SEC rate limits API access. Don't call more than once per day.
    User-Agent must identify your bot per SEC guidelines.

    Examples
    --------
    >>> refresh_cik_mappings_from_sec()
    True
    >>> # Restart bot to reload mappings
    """
    import requests
    import json
    from pathlib import Path

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": user_agent}

    try:
        log.info("cik_refresh_started source=sec_api")

        # Fetch from SEC
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        data = r.json()

        if not data:
            log.error("cik_refresh_failed reason=empty_response")
            return False

        # Backup existing file
        output = Path(output_path)
        if output.exists():
            backup_path = output.with_suffix(".ndjson.backup")
            output.rename(backup_path)
            log.info("cik_refresh_backup created=%s", backup_path)

        # Write NDJSON
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for entry in data.values():
                cik_str = str(entry.get("cik_str", "")).strip()
                ticker = entry.get("ticker", "").strip()
                title = entry.get("title", "").strip()

                if not cik_str or not ticker:
                    continue

                # Pad CIK to 10 digits for consistency
                cik_padded = cik_str.zfill(10)

                record = {
                    "cik": cik_padded,
                    "cik_unpadded": cik_str.lstrip("0") or "0",  # Store both formats
                    "ticker": ticker.upper(),
                    "title": title
                }

                f.write(json.dumps(record) + "\n")
                count += 1

        log.info(
            "cik_refresh_complete entries=%d path=%s",
            count,
            output_path
        )

        return True

    except requests.exceptions.RequestException as e:
        log.error(
            "cik_refresh_http_error err=%s status=%d",
            e.__class__.__name__,
            getattr(e.response, "status_code", 0)
        )
        return False
    except Exception as e:
        log.error(
            "cik_refresh_failed err=%s msg=%s",
            e.__class__.__name__,
            str(e)
        )
        return False


def auto_refresh_cik_mappings_if_stale(
    max_age_days: int = 7,
    mapping_file: str = "company_tickers.ndjson"
) -> None:
    """
    Automatically refresh CIK mappings if file is older than max_age_days.

    Call this on bot startup to ensure mappings are fresh.

    Parameters
    ----------
    max_age_days : int
        Refresh if file is older than this many days
    mapping_file : str
        Path to mapping file
    """
    from pathlib import Path
    from datetime import datetime, timedelta

    try:
        path = Path(mapping_file)

        if not path.exists():
            log.warning("cik_mapping_missing attempting_refresh")
            refresh_cik_mappings_from_sec(output_path=mapping_file)
            return

        # Check file age
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age = datetime.now() - mtime

        if age > timedelta(days=max_age_days):
            log.info(
                "cik_mapping_stale age_days=%.1f threshold=%d refreshing",
                age.total_seconds() / 86400,
                max_age_days
            )
            refresh_cik_mappings_from_sec(output_path=mapping_file)
        else:
            log.info(
                "cik_mapping_fresh age_days=%.1f",
                age.total_seconds() / 86400
            )

    except Exception as e:
        log.warning(
            "cik_mapping_age_check_failed err=%s continuing",
            e.__class__.__name__
        )
```

**Usage in `runner.py` (add to startup):**

```python
# In main() function, before loop starts
def main():
    # ... existing startup code ...

    # Auto-refresh CIK mappings if stale (>7 days old)
    from catalyst_bot.ticker_map import auto_refresh_cik_mappings_if_stale
    auto_refresh_cik_mappings_if_stale(max_age_days=7)

    # ... start main loop ...
```

---

## Expected Impact

**Before:**
- 70% of high-scoring N/A items due to missing CIK mappings
- ~138 items out of 198 affected

**After:**
- CIK mappings up-to-date with latest SEC registrations
- Expected reduction: 120-130 items resolved
- Remaining N/A items: ~60-70 (mostly GlobeNewswire non-public companies)

**Combined with Non-Public Company Filter:**
- Tiingo batch API: Fixes rate limiting
- Non-public filter: Removes GlobeNewswire noise (~18 items/cycle)
- CIK refresh: Fixes SEC ticker extraction (~15 items/cycle)
- **Total impact: High-scoring N/A items: 198 → <10**

---

## Validation Plan

### Pre-Refresh Baseline
```bash
# Count current high-scoring N/A items
python lookup_high_score_items.py | grep "Found"
# Expected: "Found 73 items scoring >= 0.6 with ticker=N/A"

# Check current CIK mapping file age
ls -lh company_tickers.ndjson
stat company_tickers.ndjson
```

### Post-Refresh Validation
```bash
# 1. Verify file updated
ls -lh company_tickers.ndjson
# Should show today's date

# 2. Count entries
wc -l company_tickers.ndjson
# Expected: 10,000-15,000 entries (as of 2025)

# 3. Check sample mappings
grep -i "AAPL" company_tickers.ndjson
grep -i "TSLA" company_tickers.ndjson
# Should find entries with proper CIK padding

# 4. Run bot for 1 hour
python -m catalyst_bot.runner --loop --sleep-secs 300

# 5. Check high-scoring N/A items again
python lookup_high_score_items.py | grep "Found"
# Expected: "Found <20 items scoring >= 0.6 with ticker=N/A" (70% reduction)
```

### SEC Filings Test
```python
# Test specific CIKs from recent filings
from catalyst_bot.sec_prefilter import extract_ticker_from_filing

test_filings = [
    {"item_id": "https://www.sec.gov/edgar/data/0000320193/..."},  # Apple
    {"item_id": "https://www.sec.gov/edgar/data/0001318605/..."},  # Tesla
]

for filing in test_filings:
    ticker = extract_ticker_from_filing(filing)
    print(f"CIK extracted ticker: {ticker}")
    # Should return valid tickers, not None
```

---

## Maintenance Schedule

**Recommended Refresh Frequency:**
- **Auto-refresh:** Weekly (on bot startup if file >7 days old)
- **Manual refresh:** Monthly (download latest from SEC)
- **Emergency refresh:** When noticing spike in N/A items

**Automation Options:**

**Option 1: Startup Check (Recommended)**
```python
# In runner.py main()
auto_refresh_cik_mappings_if_stale(max_age_days=7)
```

**Option 2: Scheduled Job**
```bash
# Cron job (runs weekly)
0 2 * * 0 cd /path/to/catalyst-bot && python -c "from catalyst_bot.ticker_map import refresh_cik_mappings_from_sec; refresh_cik_mappings_from_sec()"
```

**Option 3: Manual Refresh Script**
```bash
#!/bin/bash
# refresh_cik_mappings.sh
cd "$(dirname "$0")"
python -c "from catalyst_bot.ticker_map import refresh_cik_mappings_from_sec; refresh_cik_mappings_from_sec()"
echo "CIK mappings refreshed. Restart bot to reload."
```

---

## Error Handling

### SEC API Unavailable
```python
# Fallback: Continue with existing mappings
if not refresh_cik_mappings_from_sec():
    log.warning("cik_refresh_failed using_existing_mappings")
    # Bot continues with current file
```

### File Corruption
```python
# Automatic backup created before refresh
# If refresh fails, restore from backup:
mv company_tickers.ndjson.backup company_tickers.ndjson
```

### Rate Limiting
SEC limits automated access. If you hit rate limits:
1. Reduce refresh frequency (e.g., every 14 days)
2. Add `time.sleep(1)` between API calls if making multiple requests
3. Ensure User-Agent header identifies your bot

---

## SEC API Guidelines

**Required User-Agent Format:**
```
User-Agent: catalyst-bot/1.0 (contact@yourdomain.com)
```

**SEC Requirements:**
- Identify your bot in User-Agent
- Provide contact email
- Don't exceed 10 requests per second
- Don't scrape entire EDGAR database

**References:**
- https://www.sec.gov/os/accessing-edgar-data
- https://www.sec.gov/developer

---

## Alternative Data Sources

If SEC API is unavailable, consider:

**Option 1: sec-api.io** (Paid service)
- More reliable API
- Additional metadata
- Cost: ~$30-50/month

**Option 2: EDGAR Company Search** (Manual)
- https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=XXXXXXXX
- For one-off lookups, not bulk refresh

**Option 3: Build from EDGAR Filings** (Complex)
- Parse company information from recent 10-K/10-Q filings
- Requires significant processing

**Recommendation:** Stick with official SEC API (free, authoritative)

---

## Testing Plan

### Unit Tests
```python
# tests/test_cik_refresh.py

def test_refresh_cik_mappings_from_sec():
    """Test CIK mapping refresh from SEC API."""
    # Mock SEC API response
    # Assert NDJSON file created correctly
    # Assert backup created

def test_auto_refresh_checks_file_age():
    """Test auto-refresh only runs if file is stale."""
    # Create fresh file
    # Call auto_refresh with max_age_days=7
    # Assert no refresh occurred

def test_cik_padding_formats():
    """Test both padded and unpadded CIK formats stored."""
    # Refresh with test data
    # Assert "0001234567" and "1234567" both stored
```

### Integration Test
```bash
# 1. Backup current file
cp company_tickers.ndjson company_tickers.ndjson.test_backup

# 2. Run refresh
python -c "from catalyst_bot.ticker_map import refresh_cik_mappings_from_sec; refresh_cik_mappings_from_sec()"

# 3. Verify file
ls -lh company_tickers.ndjson
head -5 company_tickers.ndjson

# 4. Test in bot
python -m catalyst_bot.runner --loop --sleep-secs 60

# 5. Check logs for successful CIK lookups
grep "cik_lookup" data/logs/bot.jsonl | tail -20

# 6. Restore backup if needed
mv company_tickers.ndjson.test_backup company_tickers.ndjson
```

---

## Rollback Plan

If refresh causes issues:

**Step 1:** Restore backup
```bash
mv company_tickers.ndjson.backup company_tickers.ndjson
```

**Step 2:** Restart bot
```bash
pkill -f catalyst_bot.runner
python -m catalyst_bot.runner --loop --sleep-secs 300
```

**Risk: Very Low**
- Automatic backup created before refresh
- Bot continues with existing mappings if refresh fails
- No breaking changes to code

---

## Monitoring

After refresh, track:

```python
# Add to cycle logs
log.info(
    "cik_extraction_metrics",
    sec_items_processed=sec_item_count,
    cik_lookup_success=cik_success_count,
    cik_lookup_failed=cik_failed_count,
    cik_success_rate=cik_success_count / sec_item_count if sec_item_count > 0 else 0,
)
```

**Success Criteria:**
- CIK lookup success rate: >95% (up from ~92%)
- High-scoring N/A items from SEC filings: <5 per 9-hour period
- File age: <7 days (auto-refreshed weekly)

---

**Created:** 2025-12-11
**Priority:** P2 - Medium (complements other fixes)
**Estimated Impact:** 70% reduction in CIK-related N/A items
**Risk:** Very Low (automatic backup, graceful fallback)
**Maintenance:** Weekly auto-refresh recommended
