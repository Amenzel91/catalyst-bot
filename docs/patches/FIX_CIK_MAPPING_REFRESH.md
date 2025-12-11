# Fix: Refresh CIK-to-Ticker Mapping Database

> **Claude Code CLI Implementation Guide**
> Priority: P2 - Medium | Risk: Very Low | Estimated Impact: 70% CIK lookup improvement

---

## Problem Summary

| Metric | Current | After Fix |
|--------|---------|-----------|
| CIK mappings in file | 2 entries | 10,000+ |
| CIK lookup success | 0% (broken) | >95% |
| High-scoring N/A from CIK | 70% of N/A items | <5% |
| SEC filing ticker resolution | Failing | Working |

**Root Cause:** The `company_tickers.ndjson` file has TWO critical issues:
1. **Only 2 entries** (Apple, Microsoft) instead of 10,000+
2. **Wrong field name** - file uses `"cik_str"` but code expects `"cik"`

---

## CRITICAL: Field Name Mismatch

```
┌─────────────────────────────────────────────────────────────────┐
│                    FIELD NAME ISSUE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Current NDJSON file contains:                                   │
│    {"cik_str": 320193, "ticker": "AAPL", ...}                    │
│                  ↑                                               │
│                  Wrong field name!                               │
│                                                                  │
│  Code at ticker_map.py:79 expects:                               │
│    cik = str(obj.get("cik") or "").strip()                       │
│                       ↑                                          │
│                       Expects "cik"                              │
│                                                                  │
│  Result: obj.get("cik") returns None → cik="" → 0 rows loaded   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Tickets

### TICKET-0: Populate NDJSON File (LOCAL CLI - REQUIRED FIRST)

> **⚠️ This must be done on your local machine with internet access to SEC.gov**

**File to Create/Update:** `company_tickers.ndjson` (repo root)

**Step 1: Fetch SEC Data**
```bash
# Run this on your local machine
curl -H "User-Agent: catalyst-bot/1.0 (your-email@example.com)" \
     https://www.sec.gov/files/company_tickers.json \
     -o company_tickers_raw.json

# Verify download (should be ~1.5MB)
ls -lh company_tickers_raw.json
```

**Step 2: Convert to NDJSON with Correct Field Name**

Create a conversion script `convert_sec_tickers.py`:
```python
#!/usr/bin/env python3
"""
Convert SEC company_tickers.json to NDJSON format.

CRITICAL: Uses "cik" field (not "cik_str") to match ticker_map.py:79
"""
import json

def convert():
    # Load SEC JSON
    with open("company_tickers_raw.json", "r") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} entries from SEC")

    # Convert to NDJSON with CORRECT field name
    count = 0
    with open("company_tickers.ndjson", "w", encoding="utf-8") as f:
        for entry in data.values():
            cik_str = str(entry.get("cik_str", "")).strip()
            ticker = entry.get("ticker", "").strip()
            title = entry.get("title", "").strip()

            if not cik_str or not ticker:
                continue

            # Pad CIK to 10 digits
            cik_padded = cik_str.zfill(10)

            # CRITICAL: Use "cik" field (not "cik_str")
            # This matches ticker_map.py line 79: obj.get("cik")
            record = {
                "cik": cik_padded,
                "ticker": ticker.upper(),
                "title": title
            }

            f.write(json.dumps(record) + "\n")
            count += 1

    print(f"Wrote {count} entries to company_tickers.ndjson")
    print(f"Field format: {{\"cik\": \"0000320193\", \"ticker\": \"AAPL\", ...}}")

if __name__ == "__main__":
    convert()
```

**Step 3: Run Conversion**
```bash
python3 convert_sec_tickers.py

# Expected output:
# Loaded 10847 entries from SEC
# Wrote 10847 entries to company_tickers.ndjson
# Field format: {"cik": "0000320193", "ticker": "AAPL", ...}
```

**Step 4: Verify Output**
```bash
# Check first 3 lines
head -3 company_tickers.ndjson

# Expected format (note: "cik" not "cik_str"):
# {"cik": "0000320193", "ticker": "AAPL", "title": "Apple Inc."}
# {"cik": "0000789019", "ticker": "MSFT", "title": "MICROSOFT CORP"}
# {"cik": "0001018724", "ticker": "AMZN", "title": "AMAZON COM INC"}

# Count entries
wc -l company_tickers.ndjson
# Expected: 10000+ entries

# Verify no BOM (file should start with '{')
od -c company_tickers.ndjson | head -1
# Should show: 0000000   {   "   c   i   k   "   :  ...
# NOT: 0000000 357 273 277 (UTF-8 BOM)
```

**Step 5: Commit and Push**
```bash
git add company_tickers.ndjson
git commit -m "fix: populate CIK mappings with 10k+ entries (correct field name)"
git push
```

**Step 6: Delete SQLite Cache (Forces Rebuild)**
```bash
# On the server/deployment
rm -f data/tickers.db

# Next bot run will rebuild from fresh NDJSON
```

---

### TICKET-1: Add Auto-Refresh Function

**File:** `src/catalyst_bot/ticker_map.py`
**Insert Location:** After line 137 (after `load_cik_to_ticker()` function, before `cik_from_text()`)

**Context:**
```
Line 137: return mapping  (end of load_cik_to_ticker)
Line 138: [BLANK - INSERT HERE]
Line 139: [BLANK - INSERT HERE]
Line 140: def cik_from_text(text: str | None) -> str | None:
```

**Code to Insert:**

```python
def refresh_cik_mappings_from_sec(
    output_path: str = None,
    user_agent: str = "catalyst-bot/1.0 contact@example.com"
) -> bool:
    """
    Fetch latest CIK-to-ticker mappings from SEC and update local NDJSON.

    Downloads from official SEC API and converts to NDJSON format.
    CRITICAL: Uses "cik" field name to match _bootstrap_if_needed() at line 79.

    Parameters
    ----------
    output_path : str, optional
        Path to output NDJSON file. Defaults to repo root company_tickers.ndjson
    user_agent : str
        User-Agent header (SEC requires identification)

    Returns
    -------
    bool
        True if refresh succeeded, False otherwise

    Notes
    -----
    SEC rate limits API access. Don't call more than once per day.
    Bot must be restarted OR tickers.db deleted to reload mappings.
    """
    import requests
    from pathlib import Path

    if output_path is None:
        output_path = str(_ndjson_path())

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": user_agent}

    try:
        log.info("cik_refresh_started source=sec_api")

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

        # Write NDJSON with CORRECT field name
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for entry in data.values():
                cik_str = str(entry.get("cik_str", "")).strip()
                ticker = entry.get("ticker", "").strip()
                title = entry.get("title", "").strip()

                if not cik_str or not ticker:
                    continue

                cik_padded = cik_str.zfill(10)

                # CRITICAL: Use "cik" field to match line 79
                record = {
                    "cik": cik_padded,
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
            "cik_refresh_http_error err=%s status=%s",
            e.__class__.__name__,
            getattr(getattr(e, "response", None), "status_code", "N/A")
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
    mapping_file: str = None
) -> None:
    """
    Automatically refresh CIK mappings if NDJSON file is older than max_age_days.

    Call this on bot startup to ensure mappings are fresh.

    Parameters
    ----------
    max_age_days : int
        Refresh if file is older than this many days
    mapping_file : str, optional
        Path to NDJSON file. Defaults to repo root.
    """
    from datetime import datetime, timedelta

    if mapping_file is None:
        mapping_file = str(_ndjson_path())

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

---

### TICKET-2: Add Startup Auto-Refresh (Optional)

**File:** `src/catalyst_bot/runner.py`
**Function:** `runner_main()` (starts at line 3963)
**Insert Location:** Around line 4090 (after signal handlers, before main loop)

**Code to Insert:**

```python
    # Auto-refresh CIK mappings if stale (>7 days old)
    try:
        from catalyst_bot.ticker_map import auto_refresh_cik_mappings_if_stale
        auto_refresh_cik_mappings_if_stale(max_age_days=7)
    except Exception as e:
        log.warning("cik_auto_refresh_failed err=%s", e.__class__.__name__)
```

---

## Wiring Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       ticker_map.py                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Lines 1-8: Imports (json, os, re, sqlite3, pathlib, typing)     │
│                                                                  │
│  Line 31-33: _ndjson_path() → returns company_tickers.ndjson     │
│                                                                  │
│  Lines 55-92: _bootstrap_if_needed()                             │
│      └─ Line 72: Opens NDJSON file                               │
│      └─ Line 79: cik = obj.get("cik")  ← EXPECTS "cik" FIELD     │
│      └─ Line 80: ticker = obj.get("ticker")                      │
│      └─ Line 81: if cik and ticker: (insert into DB)             │
│                                                                  │
│  Lines 98-137: load_cik_to_ticker()                              │
│      └─ Line 114: Calls _bootstrap_if_needed()                   │
│      └─ Line 115: SELECT cik, ticker FROM tickers                │
│      └─ Lines 134-136: Returns dict with padded CIK keys         │
│                                                                  │
│  Lines 138-139: [INSERT] refresh_cik_mappings_from_sec()         │
│                 [INSERT] auto_refresh_cik_mappings_if_stale()    │
│                                                                  │
│  Lines 140-149: cik_from_text()                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      sec_prefilter.py                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Line 39: _CIK_MAP: Dict[str, str] = {}                          │
│                                                                  │
│  Lines 43-57: init_prefilter()                                   │
│      └─ Line 52: _CIK_MAP = load_cik_to_ticker()                 │
│                                                                  │
│  Lines 60-106: extract_ticker_from_filing()                      │
│      └─ Line 85: ticker = _CIK_MAP.get(cik)                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        runner.py                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Line 1442: _CIK_MAP = None                                      │
│                                                                  │
│  Lines 1445-1451: ensure_cik_map()                               │
│      └─ Line 1449: _CIK_MAP = load_cik_to_ticker()               │
│                                                                  │
│  Lines 3963+: runner_main()                                      │
│      └─ Line ~4090: [INSERT] auto_refresh_cik_mappings_if_stale  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   company_tickers.ndjson                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  BEFORE (broken):                                                │
│    {"cik_str": 320193, "ticker": "AAPL", ...}  ← WRONG FIELD     │
│    (only 2 entries)                                              │
│                                                                  │
│  AFTER (fixed):                                                  │
│    {"cik": "0000320193", "ticker": "AAPL", ...}  ← CORRECT       │
│    (10,000+ entries)                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
                SEC Filing URL
        /edgar/data/0001018724/...
                    │
                    ▼
        ┌───────────────────────┐
        │  cik_from_text()      │ ← Extracts CIK: "0001018724"
        │  (ticker_map.py:140)  │
        └───────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  _CIK_MAP.get(cik)    │ ← Looks up ticker
        │  (sec_prefilter.py:85)│
        └───────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
   CIK Found              CIK Not Found
   ticker="AMZN"          ticker=None
        │                       │
        ▼                       ▼
   Alert Generated        ticker="N/A"
                          (wasted processing)
```

---

## CLI Implementation Steps

### Step 1: Fix NDJSON File (Local Machine)

```bash
# On your LOCAL machine with internet access:

# 1. Fetch SEC data
curl -H "User-Agent: catalyst-bot/1.0 (you@email.com)" \
     https://www.sec.gov/files/company_tickers.json \
     -o company_tickers_raw.json

# 2. Create conversion script (see TICKET-0)
# 3. Run conversion
python3 convert_sec_tickers.py

# 4. Verify (should show "cik" not "cik_str")
head -1 company_tickers.ndjson

# 5. Commit
git add company_tickers.ndjson
git commit -m "fix: populate CIK mappings (10k+ entries, correct field name)"
git push
```

### Step 2: Add Refresh Functions (Claude Code)

```bash
# Claude Code will:
# 1. Read src/catalyst_bot/ticker_map.py
# 2. Find line 138 (after load_cik_to_ticker)
# 3. Insert refresh_cik_mappings_from_sec()
# 4. Insert auto_refresh_cik_mappings_if_stale()
```

### Step 3: Add Startup Hook (Optional)

```bash
# Claude Code will:
# 1. Read src/catalyst_bot/runner.py
# 2. Find runner_main() at line 3963
# 3. Insert auto-refresh call around line 4090
```

### Step 4: Clear Cache and Test

```bash
# Delete SQLite cache to force rebuild
rm -f data/tickers.db

# Run bot once
python -m catalyst_bot.runner --once

# Check logs for successful bootstrap
grep "ticker_bootstrap_done" data/logs/bot.jsonl | tail -1
# Expected: ticker_bootstrap_done rows=10847

# Check CIK lookup success
grep "ticker_from_cik" data/logs/bot.jsonl | tail -5
```

---

## Testing Plan

### Unit Test (create tests/test_cik_refresh.py)

```python
import pytest
from pathlib import Path
import tempfile

def test_cik_field_name_in_ndjson():
    """Verify NDJSON uses 'cik' field (not 'cik_str')."""
    import json

    ndjson_path = Path("company_tickers.ndjson")
    if not ndjson_path.exists():
        pytest.skip("NDJSON file not found")

    with open(ndjson_path) as f:
        first_line = f.readline()
        record = json.loads(first_line)

    # CRITICAL: Must have "cik" field, not "cik_str"
    assert "cik" in record, "NDJSON must use 'cik' field"
    assert "cik_str" not in record, "NDJSON must NOT use 'cik_str' field"
    assert "ticker" in record

def test_cik_map_has_entries():
    """Verify CIK map loads with 5000+ entries."""
    from src.catalyst_bot.ticker_map import load_cik_to_ticker

    cik_map = load_cik_to_ticker()
    assert len(cik_map) > 5000, f"CIK map should have 5000+ entries, got {len(cik_map)}"

def test_known_cik_mappings():
    """Verify known CIK→ticker mappings."""
    from src.catalyst_bot.ticker_map import load_cik_to_ticker

    cik_map = load_cik_to_ticker()

    # Test both padded and unpadded formats
    assert cik_map.get("320193") == "AAPL" or cik_map.get("0000320193") == "AAPL"
    assert cik_map.get("789019") == "MSFT" or cik_map.get("0000789019") == "MSFT"
    assert cik_map.get("1018724") == "AMZN" or cik_map.get("0001018724") == "AMZN"
```

### Integration Test

```bash
# Test SEC filing ticker extraction
python -c "
from src.catalyst_bot.sec_prefilter import init_prefilter, extract_ticker_from_filing

init_prefilter()

filing = {
    'item_id': '/edgar/data/0001018724/0001018724-24-001234.txt',
    'title': '8-K - Amazon.com Inc.'
}

ticker = extract_ticker_from_filing(filing)
print(f'Extracted ticker: {ticker}')
assert ticker == 'AMZN', f'Expected AMZN, got {ticker}'
print('SUCCESS: CIK lookup working!')
"
```

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| CIK entries | 2 | 10,000+ |
| CIK lookup success | 0% | >95% |
| SEC filing N/A rate | ~70% | <5% |
| High-scoring N/A items | 138 (70% of 198) | <10 |

---

## Maintenance Schedule

| Frequency | Action | Method |
|-----------|--------|--------|
| Weekly | Auto-refresh if stale | `auto_refresh_cik_mappings_if_stale()` on startup |
| Monthly | Manual verification | Check entry count and known mappings |
| Emergency | Manual refresh | Run `refresh_cik_mappings_from_sec()` |

---

## Rollback Plan

**If refresh causes issues:**

```bash
# 1. Restore backup
mv company_tickers.ndjson.backup company_tickers.ndjson

# 2. Delete SQLite cache
rm -f data/tickers.db

# 3. Restart bot
pkill -f catalyst_bot.runner
python -m catalyst_bot.runner --loop
```

**Risk: VERY LOW**
- Automatic backup created before refresh
- Bot continues with existing mappings if refresh fails
- No breaking changes to code

---

## Definition Reference

| Term | Definition |
|------|------------|
| `company_tickers.ndjson` | NDJSON file with CIK→ticker mappings (repo root) |
| `data/tickers.db` | SQLite cache built from NDJSON on first load |
| `_bootstrap_if_needed()` | Function at line 55 that loads NDJSON → SQLite |
| `load_cik_to_ticker()` | Public API at line 98 that returns CIK→ticker dict |
| `cik_from_text()` | Function at line 140 that extracts CIK from EDGAR URLs |
| `refresh_cik_mappings_from_sec()` | NEW function to fetch fresh data from SEC |
| `auto_refresh_cik_mappings_if_stale()` | NEW function for automatic weekly refresh |
| CIK | Central Index Key - SEC's unique company identifier |

---

**Created:** 2025-12-11
**Updated:** 2025-12-11 (added field name fix, local CLI instructions)
**Validated:** Cross-referenced with actual codebase
**Critical Fix:** NDJSON must use "cik" field, not "cik_str"
