# WAVE 3: CONFIGURATION CLEANUP

**Status:** Analysis Complete
**Priority:** HIGH - Runtime conflicts and import confusion
**Impact:** Configuration inconsistencies causing unpredictable behavior
**Created:** 2025-12-14

---

## Executive Summary

WAVE 3 addresses critical configuration duplication and conflicts across the catalyst-bot codebase. The system currently has:

- **5 duplicate feature flags** defined in BOTH `config.py` AND `config_extras.py`
- **3 conflicting defaults** for `ANALYZER_UTC_HOUR/MINUTE` across 3 files
- **7+ duplicate env helper functions** with inconsistent behavior
- **Multiple hardcoded values** (300000, 1.5, 0.6, 0.8) repeated across files
- **Inconsistent QuickChart URL** definitions in 2+ places

This creates import confusion, runtime conflicts, and maintenance burden.

---

## 1. DUPLICATE FEATURE FLAGS

### 1.1 Current State Analysis

Five feature flags are defined in **BOTH** config modules:

#### **FEATURE_SECTOR_INFO**
- **Location 1:** `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:36`
  ```python
  FEATURE_SECTOR_INFO: bool = os.getenv("FEATURE_SECTOR_INFO", "0") == "1"
  ```
- **Location 2:** `/home/user/catalyst-bot/src/catalyst_bot/config.py:755`
  ```python
  feature_sector_info: bool = _b("FEATURE_SECTOR_INFO", False)
  ```
- **Conflict:** Different defaults (`"0" == "1"` vs `False` are equivalent, but parsing differs)
- **Impact:** Import source determines behavior

#### **FEATURE_MARKET_TIME**
- **Location 1:** `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:37`
  ```python
  FEATURE_MARKET_TIME: bool = os.getenv("FEATURE_MARKET_TIME", "0") == "1"
  ```
- **Location 2:** `/home/user/catalyst-bot/src/catalyst_bot/config.py:756`
  ```python
  feature_market_time: bool = _b("FEATURE_MARKET_TIME", False)
  ```
- **Conflict:** Same as FEATURE_SECTOR_INFO
- **Impact:** Module import determines feature availability

#### **FEATURE_AUTO_ANALYZER**
- **Location 1:** `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:44`
  ```python
  FEATURE_AUTO_ANALYZER: bool = os.getenv("FEATURE_AUTO_ANALYZER", "0") == "1"
  ```
- **Location 2:** `/home/user/catalyst-bot/src/catalyst_bot/config.py:764`
  ```python
  feature_auto_analyzer: bool = _b("FEATURE_AUTO_ANALYZER", False)
  ```
- **Conflict:** Consistent defaults, but duplication causes import confusion
- **Impact:** Multiple import paths for same config

#### **FEATURE_LOG_REPORTER**
- **Location 1:** `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:45`
  ```python
  FEATURE_LOG_REPORTER: bool = os.getenv("FEATURE_LOG_REPORTER", "0") == "1"
  ```
- **Location 2:** `/home/user/catalyst-bot/src/catalyst_bot/config.py:787`
  ```python
  feature_log_reporter: bool = _b("FEATURE_LOG_REPORTER", False)
  ```
- **Conflict:** Same as FEATURE_AUTO_ANALYZER
- **Impact:** Import ambiguity

#### **FEATURE_SECTOR_RELAX**
- **Location 1:** `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:38`
  ```python
  FEATURE_SECTOR_RELAX: bool = os.getenv("FEATURE_SECTOR_RELAX", "0") == "1"
  ```
- **Location 2:** `/home/user/catalyst-bot/src/catalyst_bot/config.py:757`
  ```python
  feature_sector_relax: bool = _b("FEATURE_SECTOR_RELAX", False)
  ```
- **Conflict:** Consistent logic, but duplicated
- **Impact:** Maintenance burden

### 1.2 Dependency Mapping

**Modules importing from config_extras.py:**
- `/home/user/catalyst-bot/src/catalyst_bot/auto_analyzer.py:34`
  ```python
  from .config_extras import FEATURE_AUTO_ANALYZER
  ```
- `/home/user/catalyst-bot/src/catalyst_bot/log_reporter.py:53-64`
  ```python
  from .config_extras import (
      ADMIN_LOG_DESTINATION,
      ADMIN_LOG_FILE_PATH,
      ANALYZER_SCHEDULES,
      ANALYZER_UTC_HOUR,
      ANALYZER_UTC_MINUTE,
      FEATURE_LOG_REPORTER,
      LOG_REPORT_CATEGORIES,
      LOG_RETENTION_DAYS,
      REPORT_DAYS,
      REPORT_TIMEZONE,
  )
  ```
- `/home/user/catalyst-bot/src/catalyst_bot/alerts.py` (imports config_extras)
- `/home/user/catalyst-bot/src/catalyst_bot/runner.py` (imports config_extras)

**Modules importing from config.py:**
- Most modules import via `from .config import get_settings`
- `settings.feature_sector_info` used in sector-related modules
- `settings.feature_auto_analyzer` used in runner loop

**RUNTIME CONFLICT:**
If `auto_analyzer.py` imports `FEATURE_AUTO_ANALYZER` from `config_extras` but `runner.py` checks `settings.feature_auto_analyzer` from `config`, **they could have different values** if environment changes between module loads!

### 1.3 Consolidation Plan

**Canonical Source:** `/home/user/catalyst-bot/src/catalyst_bot/config.py` (Settings dataclass)

**Rationale:**
1. `config.py` uses the Settings dataclass pattern (modern, typed)
2. `config.py` is the primary configuration module (imported by 100+ files)
3. `config_extras.py` was meant as a temporary patch file
4. `get_settings()` provides a singleton pattern

**Migration Strategy:**

1. **Keep only in config.py:**
   - All 5 feature flags remain in Settings dataclass
   - Remove from config_extras.py

2. **Update config_extras.py imports:**
   ```python
   # config_extras.py - NEW APPROACH
   from .config import get_settings

   # Re-export for backward compatibility
   _settings = get_settings()
   FEATURE_SECTOR_INFO = _settings.feature_sector_info
   FEATURE_MARKET_TIME = _settings.feature_market_time
   FEATURE_AUTO_ANALYZER = _settings.feature_auto_analyzer
   FEATURE_LOG_REPORTER = _settings.feature_log_reporter
   FEATURE_SECTOR_RELAX = _settings.feature_sector_relax
   ```

3. **Update all imports:**
   - `auto_analyzer.py`: Change to `from .config import get_settings`
   - `log_reporter.py`: Change to `from .config import get_settings`
   - Other modules: Use `settings = get_settings()` pattern

### 1.4 Migration Guide

**Phase 1: Add backward compatibility layer (Week 1)**

File: `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py`

```python
# Add at top after imports
from .config import get_settings

# Replace standalone definitions with re-exports
_settings = get_settings()
FEATURE_SECTOR_INFO: bool = _settings.feature_sector_info
FEATURE_MARKET_TIME: bool = _settings.feature_market_time
FEATURE_AUTO_ANALYZER: bool = _settings.feature_auto_analyzer
FEATURE_LOG_REPORTER: bool = _settings.feature_log_reporter
FEATURE_SECTOR_RELAX: bool = _settings.feature_sector_relax
```

**Phase 2: Update dependent modules (Week 1-2)**

File: `/home/user/catalyst-bot/src/catalyst_bot/auto_analyzer.py`

```python
# OLD
from .config_extras import FEATURE_AUTO_ANALYZER

# NEW
from .config import get_settings
settings = get_settings()
# Use settings.feature_auto_analyzer
```

File: `/home/user/catalyst-bot/src/catalyst_bot/log_reporter.py`

```python
# OLD
from .config_extras import (
    FEATURE_LOG_REPORTER,
    ANALYZER_UTC_HOUR,
    ANALYZER_UTC_MINUTE,
    # ... other imports
)

# NEW
from .config import get_settings
settings = get_settings()
# Use settings.feature_log_reporter, etc.
```

**Phase 3: Deprecation warnings (Week 2)**

Add to config_extras.py:

```python
import warnings

def __getattr__(name):
    if name in ['FEATURE_SECTOR_INFO', 'FEATURE_MARKET_TIME',
                'FEATURE_AUTO_ANALYZER', 'FEATURE_LOG_REPORTER',
                'FEATURE_SECTOR_RELAX']:
        warnings.warn(
            f"config_extras.{name} is deprecated, use "
            f"get_settings().{name.lower()} instead",
            DeprecationWarning,
            stacklevel=2
        )
        return getattr(get_settings(), name.lower())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Phase 4: Remove duplicates (Week 3)**

Once all modules updated and tested:
1. Remove backward compatibility layer from config_extras.py
2. Remove duplicate definitions
3. Update tests

### 1.5 Verification Checklist

- [ ] All imports updated to use `get_settings()`
- [ ] No direct imports from config_extras for these flags
- [ ] Test with FEATURE_AUTO_ANALYZER=1 that analyzer runs
- [ ] Test with FEATURE_LOG_REPORTER=1 that reports emit
- [ ] Test with FEATURE_SECTOR_INFO=1 that sector data loads
- [ ] Run full test suite
- [ ] Check logs for deprecation warnings
- [ ] Verify no runtime AttributeErrors

---

## 2. CONFLICTING ANALYZER DEFAULTS

### 2.1 Current State Analysis

`ANALYZER_UTC_HOUR` and `ANALYZER_UTC_MINUTE` have **THREE DIFFERENT DEFAULTS**:

#### **Location 1: config.py (PRIMARY)**
File: `/home/user/catalyst-bot/src/catalyst_bot/config.py:687-688`
```python
analyzer_utc_hour: int = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
analyzer_utc_minute: int = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))
```
**Default:** 21:30 UTC (3:30 PM CST / 4:30 PM EST)

#### **Location 2: config_extras.py (ALTERNATE)**
File: `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:47-48`
```python
ANALYZER_UTC_HOUR: int = int(os.getenv("ANALYZER_UTC_HOUR", "23"))
ANALYZER_UTC_MINUTE: int = int(os.getenv("ANALYZER_UTC_MINUTE", "55"))
```
**Default:** 23:55 UTC (5:55 PM CST / 6:55 PM EST)

#### **Location 3: analyzer.py (FALLBACK)**
File: `/home/user/catalyst-bot/src/catalyst_bot/analyzer.py:615-617`
```python
if hour is None:
    hour = int(os.getenv("ANALYZER_UTC_HOUR", "1"))
if minute is None:
    minute = int(os.getenv("ANALYZER_UTC_MINUTE", "0"))
```
**Default:** 1:00 UTC (7:00 PM CST previous day / 8:00 PM EST previous day)

### 2.2 Dependency Mapping

**Usage in runner.py (Line 3790-3792):**
```python
now.hour == getattr(s, "analyzer_utc_hour", 21)
and now.minute >= getattr(s, "analyzer_utc_minute", 30)
and now.minute < getattr(s, "analyzer_utc_minute", 30) + 5
```
**Impact:** Uses config.py default (21:30)

**Usage in admin_reporter.py (Line 202-203):**
```python
target_hour = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
target_minute = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))
```
**Impact:** Uses config.py default (21:30)

**Usage in log_reporter.py (Line 57-58, 132):**
```python
from .config_extras import (
    ANALYZER_UTC_HOUR,
    ANALYZER_UTC_MINUTE,
)
# ...
return now_utc.hour == ANALYZER_UTC_HOUR and now_utc.minute == ANALYZER_UTC_MINUTE
```
**Impact:** Uses config_extras.py default (23:55) ⚠️ **CONFLICT!**

**Usage in analyzer.py (Line 615-617):**
```python
hour = int(os.getenv("ANALYZER_UTC_HOUR", "1"))
minute = int(os.getenv("ANALYZER_UTC_MINUTE", "0"))
```
**Impact:** Uses fallback default (1:00) ⚠️ **CONFLICT!**

### 2.3 Conflict Analysis

**CRITICAL ISSUE:**
If environment variable `ANALYZER_UTC_HOUR` is NOT set:
- `runner.py` checks at **21:30 UTC** (from Settings)
- `log_reporter.py` checks at **23:55 UTC** (from config_extras)
- `analyzer.py` runs at **1:00 UTC** (fallback)

**Result:** Analyzer may never run, or run 3 times at different hours!

**Example Scenario:**
1. User expects analyzer at 21:30 (config.py default)
2. Runner triggers at 21:30, calls analyzer
3. Analyzer checks settings, sees hour=None, uses fallback 1:00
4. Analyzer skips run because "not scheduled time"
5. Log reporter runs at 23:55 (config_extras default)
6. **NO ANALYZER RUN OCCURS!**

### 2.4 Consolidation Plan

**Canonical Values:** 21:30 UTC (most common, documented in env.example.ini)

**Strategy:**

1. **Single source of truth:** Settings dataclass in config.py
2. **Remove from config_extras.py** (re-export from Settings instead)
3. **Remove fallback from analyzer.py** (always use Settings)

**Recommended Default Rationale:**
- **21:30 UTC** = 3:30 PM CST / 4:30 PM EST
- After market close (4:00 PM EST / 3:00 PM CST)
- Allows market data to settle
- Before typical end-of-day (midnight UTC)
- Documented in env.example.ini:419-421

### 2.5 Migration Guide

**Phase 1: Unify defaults in config.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/config.py:687-688`

```python
# NO CHANGE - already correct default
analyzer_utc_hour: int = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
analyzer_utc_minute: int = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))
```

**Phase 2: Update config_extras.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:47-48`

```python
# OLD (REMOVE)
# ANALYZER_UTC_HOUR: int = int(os.getenv("ANALYZER_UTC_HOUR", "23"))
# ANALYZER_UTC_MINUTE: int = int(os.getenv("ANALYZER_UTC_MINUTE", "55"))

# NEW (ADD)
from .config import get_settings
_settings = get_settings()
ANALYZER_UTC_HOUR: int = _settings.analyzer_utc_hour
ANALYZER_UTC_MINUTE: int = _settings.analyzer_utc_minute
```

**Phase 3: Update analyzer.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/analyzer.py:610-620`

```python
# OLD
def run_analyzer_once_if_scheduled(settings) -> bool:
    from datetime import datetime, timezone

    # Allow both config properties and env fallbacks
    hour = getattr(settings, "analyzer_run_utc_hour", None)
    minute = getattr(settings, "analyzer_run_utc_minute", None)

    try:
        if hour is None:
            hour = int(os.getenv("ANALYZER_UTC_HOUR", "1"))  # ❌ Wrong default
        if minute is None:
            minute = int(os.getenv("ANALYZER_UTC_MINUTE", "0"))  # ❌ Wrong default
    except Exception:
        hour, minute = 1, 0  # ❌ Wrong fallback

# NEW
def run_analyzer_once_if_scheduled(settings) -> bool:
    from datetime import datetime, timezone

    # Use settings directly, no fallback needed
    hour = getattr(settings, "analyzer_utc_hour", 21)  # ✅ Match config.py
    minute = getattr(settings, "analyzer_utc_minute", 30)  # ✅ Match config.py
```

**Phase 4: Update log_reporter.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/log_reporter.py:53-64`

```python
# OLD
from .config_extras import (
    ADMIN_LOG_DESTINATION,
    ADMIN_LOG_FILE_PATH,
    ANALYZER_SCHEDULES,
    ANALYZER_UTC_HOUR,  # ❌ Wrong default (23)
    ANALYZER_UTC_MINUTE,  # ❌ Wrong default (55)
    FEATURE_LOG_REPORTER,
    # ...
)

# NEW
from .config import get_settings
from .config_extras import (  # Keep other imports
    ADMIN_LOG_DESTINATION,
    ADMIN_LOG_FILE_PATH,
    ANALYZER_SCHEDULES,
    FEATURE_LOG_REPORTER,
    # ...
)

_settings = get_settings()
ANALYZER_UTC_HOUR = _settings.analyzer_utc_hour  # ✅ 21
ANALYZER_UTC_MINUTE = _settings.analyzer_utc_minute  # ✅ 30
```

### 2.6 Verification Checklist

- [ ] config.py has 21:30 default
- [ ] config_extras.py re-exports from Settings
- [ ] analyzer.py uses Settings, no fallback
- [ ] log_reporter.py uses Settings values
- [ ] runner.py uses Settings values
- [ ] admin_reporter.py uses Settings values
- [ ] Set ANALYZER_UTC_HOUR=14 and verify all modules see 14
- [ ] Unset ANALYZER_UTC_HOUR and verify all modules see 21
- [ ] Analyzer runs at expected time
- [ ] Log reporter runs at same time as analyzer

---

## 3. DUPLICATE ENV HELPER FUNCTIONS

### 3.1 Current State Analysis

Seven environment parsing functions with similar/identical behavior:

#### **Function 1: _b() in config.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/config.py:23-30`
```python
def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
```
**Behavior:** Accepts {"1", "true", "yes", "y", "on"}
**Used by:** 100+ config flags in Settings

#### **Function 2: _env_bool() in config_extras.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:70-76`
```python
def _env_bool(var: str, default: bool = False) -> bool:
    import os

    val = os.getenv(var)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}
```
**Behavior:** Accepts {"1", "true", "yes", "on"} (missing "y")
**Used by:** ExtraSettings dataclass

#### **Function 3: _env_bool() in feeds.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/feeds.py:2529`
```python
def _env_bool(name: str, default: bool) -> bool:
    # Implementation similar to config_extras
```
**Behavior:** Local helper for breakout scanner
**Used by:** 1 location (can be removed)

#### **Function 4: _env_flag() in seen_store.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/seen_store.py:51`
```python
def _env_flag(name: str, default: str) -> bool:
    # Custom implementation
```
**Behavior:** Similar boolean parsing
**Used by:** Seen store configuration

#### **Function 5: _env_float() in config_extras.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py:79-85`
```python
def _env_float(var: str, default: float) -> float:
    import os

    try:
        return float(os.getenv(var, "")) if os.getenv(var) else default
    except Exception:
        return default
```
**Behavior:** Parse float with fallback
**Used by:** ExtraSettings

#### **Function 6: _env_float_opt() in config.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/config.py:7-20`
```python
def _env_float_opt(name: str) -> Optional[float]:
    """
    Read an optional float from env. Returns None if unset, blank, or non-numeric.
    """
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "" or raw.lower() in {"none", "null"} or raw.startswith("#"):
        return None
    try:
        return float(raw)
    except Exception:
        return None
```
**Behavior:** Returns None for empty/invalid (different from _env_float!)
**Used by:** Optional float settings like PRICE_CEILING

#### **Function 7: _env_int() in feeds.py**
File: `/home/user/catalyst-bot/src/catalyst_bot/feeds.py:485`
```python
def _env_int(name: str, default: int) -> int:
    # Parse integer with fallback
```
**Behavior:** Parse int with fallback
**Used by:** Feed configuration

### 3.2 Dependency Mapping

**Files using _b():**
- `/home/user/catalyst-bot/src/catalyst_bot/config.py` (100+ calls)

**Files using _env_bool():**
- `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py` (ExtraSettings)
- `/home/user/catalyst-bot/src/catalyst_bot/feeds.py` (1 location)

**Files using _env_flag():**
- `/home/user/catalyst-bot/src/catalyst_bot/seen_store.py` (1 location)

**Files using _env_float():**
- `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py` (ExtraSettings)

**Files using _env_float_opt():**
- `/home/user/catalyst-bot/src/catalyst_bot/config.py` (PRICE_CEILING, etc.)

**Files using _env_int():**
- `/home/user/catalyst-bot/src/catalyst_bot/feeds.py` (feed config)

### 3.3 Consolidation Plan

**Create unified env_utils module:**

File: `/home/user/catalyst-bot/src/catalyst_bot/env_utils.py` (NEW)

```python
"""Unified environment variable parsing utilities.

Provides consistent, typed helpers for parsing environment variables
with proper defaults, validation, and None-handling.
"""
import os
from typing import Optional


def env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean from environment variable.

    Accepts: "1", "true", "yes", "y", "on" (case-insensitive)

    Args:
        name: Environment variable name
        default: Default value if unset or invalid

    Returns:
        Boolean value

    Examples:
        >>> os.environ["FEATURE_X"] = "1"
        >>> env_bool("FEATURE_X")
        True
        >>> env_bool("FEATURE_Y", False)
        False
    """
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int = 0) -> int:
    """Parse integer from environment variable.

    Args:
        name: Environment variable name
        default: Default value if unset or invalid

    Returns:
        Integer value
    """
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def env_float(name: str, default: float = 0.0) -> float:
    """Parse float from environment variable.

    Args:
        name: Environment variable name
        default: Default value if unset or invalid

    Returns:
        Float value
    """
    try:
        val = os.getenv(name)
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def env_float_opt(name: str) -> Optional[float]:
    """Parse optional float from environment variable.

    Returns None if unset, blank, "none", "null", or starts with "#".

    Args:
        name: Environment variable name

    Returns:
        Float value or None

    Examples:
        >>> os.environ["PRICE_CEILING"] = "50.0"
        >>> env_float_opt("PRICE_CEILING")
        50.0
        >>> env_float_opt("UNSET_VAR")
        None
    """
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "" or raw.lower() in {"none", "null"} or raw.startswith("#"):
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def env_str(name: str, default: str = "") -> str:
    """Get string from environment variable.

    Args:
        name: Environment variable name
        default: Default value if unset

    Returns:
        String value
    """
    return os.getenv(name, default)


# Backward compatibility aliases
_b = env_bool  # For config.py
_env_bool = env_bool  # For config_extras.py
_env_int = env_int  # For feeds.py
_env_float = env_float  # For config_extras.py
_env_float_opt = env_float_opt  # For config.py
```

### 3.4 Migration Guide

**Phase 1: Create env_utils.py**

Create new file with consolidated functions (see above).

**Phase 2: Update config.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/config.py`

```python
# OLD (TOP OF FILE)
def _env_float_opt(name: str) -> Optional[float]:
    # ... 14 lines ...

def _b(name: str, default: bool) -> bool:
    # ... 8 lines ...

# NEW (TOP OF FILE)
from .env_utils import env_bool as _b, env_float_opt as _env_float_opt
# All existing code continues to work
```

**Phase 3: Update config_extras.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py`

```python
# OLD
def _env_bool(var: str, default: bool = False) -> bool:
    # ... implementation ...

def _env_float(var: str, default: float) -> float:
    # ... implementation ...

# NEW
from .env_utils import env_bool as _env_bool, env_float as _env_float
# Remove function definitions
```

**Phase 4: Update feeds.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`

```python
# OLD
def _env_int(name: str, default: int) -> int:
    # ... implementation ...

def _env_bool(name: str, default: bool) -> bool:
    # ... implementation ...

# NEW
from .env_utils import env_int as _env_int, env_bool as _env_bool
# Remove function definitions
```

**Phase 5: Update seen_store.py**

File: `/home/user/catalyst-bot/src/catalyst_bot/seen_store.py`

```python
# OLD
def _env_flag(name: str, default: str) -> bool:
    # ... custom implementation ...

# NEW
from .env_utils import env_bool
# Replace _env_flag calls with env_bool
```

### 3.5 Verification Checklist

- [ ] env_utils.py created with all functions
- [ ] config.py imports from env_utils
- [ ] config_extras.py imports from env_utils
- [ ] feeds.py imports from env_utils
- [ ] seen_store.py imports from env_utils
- [ ] All tests pass
- [ ] Boolean parsing consistent across all modules
- [ ] Float parsing handles None correctly
- [ ] Integer parsing handles invalid values

---

## 4. HARDCODED VALUES

### 4.1 Volume Threshold: 300000

#### **Current State**

The value `300000` (300k shares) appears in multiple locations:

**config.py (Line 527-528):**
```python
breakout_min_avg_vol: float = float(
    os.getenv("BREAKOUT_MIN_AVG_VOL", "300000").strip() or 300000
)
```

**config.py (Line 568):**
```python
low_min_avg_vol: float = float(os.getenv("LOW_MIN_AVG_VOL", "300000") or "300000")
```

**feeds.py (Line 1773):**
```python
bv = getattr(settings, "breakout_min_avg_vol", 300000.0)
```

**runner.py (Line 1987):**
```python
min_avg_vol=getattr(settings, "low_min_avg_vol", 300000.0),
```

**admin_controls.py (Line 115):**
```python
"BREAKOUT_MIN_AVG_VOL": int(os.getenv("BREAKOUT_MIN_AVG_VOL", "300000")),
```

**finviz_elite.py (Line 267):**
```python
min_avg_vol: int = 300_000, min_relvol: float = 1.5
```

#### **Consolidation Plan**

**Add to config.py:**
```python
# Volume thresholds (centralized constants)
DEFAULT_MIN_AVG_VOLUME: int = 300_000  # 300k shares

# Use in settings:
breakout_min_avg_vol: float = float(
    os.getenv("BREAKOUT_MIN_AVG_VOL", str(DEFAULT_MIN_AVG_VOLUME))
)
low_min_avg_vol: float = float(
    os.getenv("LOW_MIN_AVG_VOL", str(DEFAULT_MIN_AVG_VOLUME))
)
```

**Update other files:**
- feeds.py: Use `settings.breakout_min_avg_vol` (no fallback)
- runner.py: Use `settings.low_min_avg_vol` (no fallback)
- admin_controls.py: Use `settings.breakout_min_avg_vol`
- finviz_elite.py: Import `DEFAULT_MIN_AVG_VOLUME` from config

### 4.2 Score Threshold: 1.5

#### **Current State**

The value `1.5` appears in multiple contexts:

**config.py (Line 165):**
```python
signal_min_score: float = float(os.getenv("SIGNAL_MIN_SCORE", "1.5") or "1.5")
```

**config.py (Line 533):**
```python
breakout_min_relvol: float = float(
    os.getenv("BREAKOUT_MIN_RELVOL", "1.5").strip() or 1.5
)
```

**config.py (Line 1193):**
```python
sub5_override_threshold: float = float(
    os.getenv("SUB5_OVERRIDE_THRESHOLD", "1.5") or "1.5"
)
```

**source_credibility.py (Line 42, 49, 55, 61, 67):**
```python
"weight": 1.5,  # Tier 1 credibility
```

**classifier.py (Line 16):**
```python
"uplisting": 1.5,
```

**finviz_elite.py (Line 267):**
```python
min_relvol: float = 1.5
```

**Multiple files:** Chart panel ratios, multipliers, etc.

#### **Analysis**

These are **DIFFERENT** values with **DIFFERENT** meanings:
- Signal scoring threshold
- Relative volume threshold
- Price override threshold
- Source credibility weight
- Category weight
- Chart layout ratios

#### **Consolidation Plan**

**NO CONSOLIDATION NEEDED** - These are semantically different constants.

**Add clarity with named constants:**

File: `/home/user/catalyst-bot/src/catalyst_bot/config.py`

```python
# Trading signal thresholds
DEFAULT_SIGNAL_MIN_SCORE: float = 1.5
DEFAULT_SUB5_OVERRIDE_THRESHOLD: float = 1.5

# Volume analysis thresholds
DEFAULT_BREAKOUT_MIN_RELVOL: float = 1.5

# Source credibility weights
TIER_1_CREDIBILITY_WEIGHT: float = 1.5

# Category scoring weights
UPLISTING_KEYWORD_WEIGHT: float = 1.5
```

Then use named constants instead of magic numbers.

### 4.3 Confidence Thresholds: 0.6 and 0.8

#### **Current State**

**0.6 (60% confidence) appears in:**

**config.py (Line 163):**
```python
signal_min_confidence: float = float(
    os.getenv("SIGNAL_MIN_CONFIDENCE", "0.6") or "0.6"
)
```

**config_extras.py (Line 129):**
```python
confidence_moderate: float = field(
    default_factory=lambda: _env_float("CONFIDENCE_MODERATE", 0.6)
)
```

**Multiple analysis files:**
- short_interest_sentiment.py:63
- keyword_review.py:63
- moa_historical_analyzer.py:1293
- llm_hybrid.py:236
- And 20+ more locations

**0.8 (80% confidence) appears in:**

**config_extras.py (Line 126):**
```python
confidence_high: float = field(
    default_factory=lambda: _env_float("CONFIDENCE_HIGH", 0.8)
)
```

**Multiple analysis files:**
- dynamic_source_scorer.py:193, 205, 455
- short_interest_sentiment.py
- And 15+ more locations

#### **Consolidation Plan**

**Add to config.py:**

```python
# Confidence thresholds (ML/trading signals)
CONFIDENCE_LOW: float = 0.4       # Below this: low confidence
CONFIDENCE_MODERATE: float = 0.6  # Moderate confidence threshold
CONFIDENCE_HIGH: float = 0.8      # High confidence threshold
CONFIDENCE_VERY_HIGH: float = 0.9 # Very high confidence threshold

# Make configurable
confidence_moderate: float = float(
    os.getenv("CONFIDENCE_MODERATE", str(CONFIDENCE_MODERATE))
)
confidence_high: float = float(
    os.getenv("CONFIDENCE_HIGH", str(CONFIDENCE_HIGH))
)
```

**Update all files:**
- Replace hardcoded `0.6` with `settings.confidence_moderate`
- Replace hardcoded `0.8` with `settings.confidence_high`
- Or import constants: `from .config import CONFIDENCE_MODERATE, CONFIDENCE_HIGH`

### 4.4 QuickChart URL Variations

#### **Current State**

QuickChart URL defined in multiple places:

**config.py (Line 336-338):**
```python
quickchart_base_url: str = os.getenv(
    "QUICKCHART_BASE_URL", "https://quickchart.io/chart"
)
```

**config.py (Line 917):**
```python
quickchart_url: str = os.getenv("QUICKCHART_URL", "http://localhost:3400")
```

**charts.py (Line 1694, 1713, 2106, 2186):**
```python
os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io")
```

**charts_quickchart.py (Line 367-368):**
```python
or os.getenv("QUICKCHART_URL")
or os.getenv("QUICKCHART_BASE_URL")
```

**backtesting/reports.py (Line 392, 456):**
```python
url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_json)}"
```

#### **Conflict Analysis**

1. **Two environment variables:**
   - `QUICKCHART_BASE_URL` (used by config.py, charts.py)
   - `QUICKCHART_URL` (used by config.py, charts_quickchart.py)

2. **Three different defaults:**
   - `https://quickchart.io/chart` (config.py line 336)
   - `http://localhost:3400` (config.py line 917)
   - `https://quickchart.io` (charts.py)

3. **Inconsistent path handling:**
   - Some include `/chart` path
   - Some don't include path

#### **Consolidation Plan**

**Single environment variable:** `QUICKCHART_BASE_URL`

**Update config.py:**

```python
# QuickChart Configuration
# Base URL for QuickChart API. Can point to self-hosted instance
# (e.g. http://localhost:3400) or public API (https://quickchart.io).
# The /chart path is appended automatically when needed.
quickchart_base_url: str = os.getenv(
    "QUICKCHART_BASE_URL",
    os.getenv("QUICKCHART_URL", "https://quickchart.io")  # Fallback for old var
)

# Ensure no trailing slash
if quickchart_base_url.endswith("/"):
    quickchart_base_url = quickchart_base_url.rstrip("/")

# Deprecated: QUICKCHART_URL (use QUICKCHART_BASE_URL instead)
quickchart_url: str = quickchart_base_url  # Backward compatibility alias
```

**Update all usage:**
- charts.py: Use `settings.quickchart_base_url`
- charts_quickchart.py: Use `settings.quickchart_base_url`
- backtesting/reports.py: Use `settings.quickchart_base_url`
- Add `/chart` path consistently when building URLs

### 4.5 Migration Guide for Hardcoded Values

**Phase 1: Add named constants (Week 1)**

Update `/home/user/catalyst-bot/src/catalyst_bot/config.py`:

```python
# Add at top of Settings class (after imports)
@dataclass
class Settings:
    # ==================== NAMED CONSTANTS ====================
    # Volume thresholds
    DEFAULT_MIN_AVG_VOLUME: int = 300_000

    # Confidence thresholds
    CONFIDENCE_LOW: float = 0.4
    CONFIDENCE_MODERATE: float = 0.6
    CONFIDENCE_HIGH: float = 0.8
    CONFIDENCE_VERY_HIGH: float = 0.9

    # Signal thresholds
    DEFAULT_SIGNAL_MIN_SCORE: float = 1.5
    DEFAULT_BREAKOUT_MIN_RELVOL: float = 1.5

    # Source credibility
    TIER_1_CREDIBILITY_WEIGHT: float = 1.5
    TIER_2_CREDIBILITY_WEIGHT: float = 1.0
    TIER_3_CREDIBILITY_WEIGHT: float = 0.5

    # ==================== CONFIGURABLE SETTINGS ====================
    # (existing settings fields...)
```

**Phase 2: Update references (Week 1-2)**

Use search/replace to update hardcoded values:
- `300000` → `settings.DEFAULT_MIN_AVG_VOLUME`
- `0.6` (confidence) → `settings.CONFIDENCE_MODERATE`
- `0.8` (confidence) → `settings.CONFIDENCE_HIGH`
- QuickChart URLs → `settings.quickchart_base_url`

**Phase 3: Add deprecation warnings (Week 2)**

For QuickChart URL:
```python
@property
def quickchart_url(self) -> str:
    warnings.warn(
        "quickchart_url is deprecated, use quickchart_base_url instead",
        DeprecationWarning
    )
    return self.quickchart_base_url
```

### 4.6 Verification Checklist

- [ ] Named constants defined in config.py
- [ ] All 300000 occurrences updated
- [ ] All 0.6/0.8 confidence values updated
- [ ] QuickChart URL unified
- [ ] QUICKCHART_URL env var still works (backward compat)
- [ ] Charts render correctly
- [ ] Trading signals use correct thresholds
- [ ] No magic numbers in code (use named constants)

---

## 5. IMPLEMENTATION TIMELINE

### Week 1: Prepare Consolidation
- [ ] Create `/home/user/catalyst-bot/src/catalyst_bot/env_utils.py`
- [ ] Add named constants to `config.py`
- [ ] Add backward compatibility layer to `config_extras.py`
- [ ] Write migration tests

### Week 2: Update Imports
- [ ] Update `auto_analyzer.py` to use `get_settings()`
- [ ] Update `log_reporter.py` to use `get_settings()`
- [ ] Update `alerts.py` imports
- [ ] Update `runner.py` imports
- [ ] Update all env helper function imports

### Week 3: Replace Hardcoded Values
- [ ] Replace 300000 with named constant
- [ ] Replace 0.6/0.8 with confidence constants
- [ ] Unify QuickChart URLs
- [ ] Update 1.5 references with named constants

### Week 4: Testing & Cleanup
- [ ] Full test suite passes
- [ ] Integration testing
- [ ] Remove duplicate definitions
- [ ] Remove backward compatibility layer (if safe)
- [ ] Update documentation

---

## 6. RISK ANALYSIS

### High Risk Areas

1. **ANALYZER_UTC_HOUR conflicts**
   - **Risk:** Analyzer may not run if modules use different defaults
   - **Mitigation:** Test with unset environment variable
   - **Rollback:** Keep config_extras re-exports until proven stable

2. **QuickChart URL changes**
   - **Risk:** Charts may break if URL format wrong
   - **Mitigation:** Test both self-hosted and public API
   - **Rollback:** Keep QUICKCHART_URL fallback for 1 release

3. **Feature flag import changes**
   - **Risk:** Features may disable unexpectedly
   - **Mitigation:** Add deprecation warnings first
   - **Rollback:** Restore config_extras definitions

### Medium Risk Areas

1. **Env helper function consolidation**
   - **Risk:** Boolean parsing may behave differently
   - **Mitigation:** Comprehensive test coverage
   - **Rollback:** Keep old functions as deprecated

2. **Hardcoded value replacements**
   - **Risk:** Logic may break if constants wrong
   - **Mitigation:** Use exact same values initially
   - **Rollback:** Simple string replacement back

### Low Risk Areas

1. **Named constants addition**
   - **Risk:** Minimal - only adds clarity
   - **Mitigation:** None needed
   - **Rollback:** Remove constants

---

## 7. SUCCESS METRICS

### Configuration Consistency
- [ ] All feature flags have single source of truth
- [ ] All modules import from same location
- [ ] No conflicting defaults across modules

### Code Quality
- [ ] Zero duplicate env helper functions
- [ ] Named constants replace all magic numbers
- [ ] Deprecation warnings for old imports

### Runtime Stability
- [ ] Analyzer runs at expected time (100% of tests)
- [ ] Feature flags consistent across all modules
- [ ] No AttributeErrors in production logs

### Developer Experience
- [ ] Configuration changes require editing only 1 file
- [ ] Clear error messages for misconfiguration
- [ ] IDE autocomplete works for all settings

---

## 8. APPENDICES

### A. Complete File Inventory

**Files with duplicate definitions:**
- `/home/user/catalyst-bot/src/catalyst_bot/config.py`
- `/home/user/catalyst-bot/src/catalyst_bot/config_extras.py`
- `/home/user/catalyst-bot/src/catalyst_bot/analyzer.py`
- `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`
- `/home/user/catalyst-bot/src/catalyst_bot/seen_store.py`

**Files importing duplicated config:**
- `/home/user/catalyst-bot/src/catalyst_bot/auto_analyzer.py`
- `/home/user/catalyst-bot/src/catalyst_bot/log_reporter.py`
- `/home/user/catalyst-bot/src/catalyst_bot/alerts.py`
- `/home/user/catalyst-bot/src/catalyst_bot/runner.py`
- `/home/user/catalyst-bot/src/catalyst_bot/admin_reporter.py`
- `/home/user/catalyst-bot/src/catalyst_bot/sector_info.py`

**Files with hardcoded values:**
- Volume (300000): config.py, feeds.py, runner.py, admin_controls.py, finviz_elite.py
- Confidence (0.6, 0.8): 35+ files across src/catalyst_bot/
- QuickChart URL: config.py, charts.py, charts_quickchart.py, backtesting/reports.py

### B. Environment Variable Reference

**Current duplicates:**
- `FEATURE_SECTOR_INFO` (config.py + config_extras.py)
- `FEATURE_MARKET_TIME` (config.py + config_extras.py)
- `FEATURE_AUTO_ANALYZER` (config.py + config_extras.py)
- `FEATURE_LOG_REPORTER` (config.py + config_extras.py)
- `FEATURE_SECTOR_RELAX` (config.py + config_extras.py)
- `ANALYZER_UTC_HOUR` (3 different defaults!)
- `ANALYZER_UTC_MINUTE` (3 different defaults!)
- `QUICKCHART_BASE_URL` vs `QUICKCHART_URL` (2 vars for same thing)

**Post-consolidation (recommended):**
- `FEATURE_SECTOR_INFO` (config.py only)
- `FEATURE_MARKET_TIME` (config.py only)
- `FEATURE_AUTO_ANALYZER` (config.py only)
- `FEATURE_LOG_REPORTER` (config.py only)
- `FEATURE_SECTOR_RELAX` (config.py only)
- `ANALYZER_UTC_HOUR=21` (config.py only, single default)
- `ANALYZER_UTC_MINUTE=30` (config.py only, single default)
- `QUICKCHART_BASE_URL` (config.py only, QUICKCHART_URL deprecated)
- `CONFIDENCE_MODERATE=0.6` (new, replaces hardcoded 0.6)
- `CONFIDENCE_HIGH=0.8` (new, replaces hardcoded 0.8)

### C. Testing Checklist

**Unit tests:**
- [ ] env_utils.py boolean parsing
- [ ] env_utils.py float/int parsing
- [ ] env_utils.py None handling
- [ ] Config flag re-exports work

**Integration tests:**
- [ ] Analyzer runs at configured time
- [ ] Log reporter runs at same time as analyzer
- [ ] Feature flags consistent across modules
- [ ] QuickChart URLs generate correctly

**Regression tests:**
- [ ] Set all env vars, verify override works
- [ ] Unset all env vars, verify defaults correct
- [ ] Mix of set/unset vars
- [ ] Invalid values handled gracefully

---

## CONCLUSION

WAVE 3 eliminates critical configuration duplication that currently causes:
- Runtime conflicts (analyzer scheduled 3 different times)
- Import confusion (5 flags defined twice)
- Maintenance burden (7 duplicate env helpers)
- Magic numbers throughout codebase

**Priority Actions:**
1. Fix `ANALYZER_UTC_HOUR` conflicts (CRITICAL - analyzer may not run)
2. Consolidate feature flags (HIGH - import confusion)
3. Create env_utils.py (MEDIUM - code quality)
4. Add named constants (LOW - maintainability)

**Expected Outcome:**
- Single source of truth for all configuration
- Consistent behavior across all modules
- Reduced maintenance burden
- Improved code clarity

**Estimated Effort:** 3-4 weeks for full migration + testing

---

**Document Version:** 1.0
**Last Updated:** 2025-12-14
**Status:** Ready for Review
