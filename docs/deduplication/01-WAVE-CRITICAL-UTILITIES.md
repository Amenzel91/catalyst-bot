# WAVE 1: CRITICAL UTILITY DUPLICATES

**Documentation Date:** 2025-12-14
**Status:** Analysis Complete - Ready for Implementation
**Priority:** HIGH - Foundation for all subsequent waves

---

## Executive Summary

This document provides comprehensive documentation for Wave 1 of the codebase deduplication project, focusing on **4 critical utility duplicate groups** affecting 17 files across the catalyst-bot codebase.

### Impact Metrics
- **Total Files Affected:** 17 source files + 3 test files
- **Total Duplicate Functions:** 17 (4 groups)
- **Estimated LOC Reduction:** ~450 lines
- **Risk Level:** Medium (core utilities, well-tested)
- **Consolidation Target:** `src/catalyst_bot/utils/` (new module)

### Duplicate Groups
1. **GPU Memory Cleanup** - 4 implementations (llm_async.py, gpu_profiler.py, llm_client.py, ml/gpu_memory.py)
2. **Token Estimation** - 2 implementations (prompt_compression.py, llm_usage_monitor.py)
3. **Webhook Masking** - 2 implementations (alerts.py, runner.py)
4. **Repo Root Resolution** - 9 implementations (admin_controls.py, config_updater.py, weekly_performance.py, moa_historical_analyzer.py, false_positive_analyzer.py, analyzer.py, ticker_map.py, moa_analyzer.py, false_positive_tracker.py)

---

## 1. GPU Memory Cleanup (4 Implementations)

### 1.1 Current State Analysis

#### Implementation 1: `/home/user/catalyst-bot/src/catalyst_bot/llm_client.py`
- **Lines:** 88-141
- **Function:** `cleanup_gpu_memory(force: bool = False) -> None`
- **Features:**
  - Rate limiting with `_cleanup_interval` (300s default)
  - Tracks `_last_cleanup_time` globally
  - Full cleanup sequence: gc.collect() → torch.cuda.synchronize() → torch.cuda.empty_cache() → reset_peak_memory_stats()
  - Debug logging with memory stats (allocated_gb, reserved_gb)
  - Environment variable: `GPU_CLEANUP_INTERVAL_SEC`
- **Completeness:** 95% - **MOST COMPREHENSIVE**
- **Notes:** Critical sequence ordering documented in docstring

#### Implementation 2: `/home/user/catalyst-bot/src/catalyst_bot/ml/gpu_memory.py`
- **Lines:** 201-249
- **Function:** `cleanup_gpu_memory(force: bool = False) -> Dict[str, float]`
- **Features:**
  - Rate limiting with `_CLEANUP_INTERVAL_SEC` (60s default)
  - Returns cleanup stats dict: `{before_mb, after_mb, freed_mb}`
  - gc.collect() → torch.cuda.empty_cache() → torch.cuda.synchronize()
  - Info logging for freed memory
- **Completeness:** 85%
- **Unique Feature:** Returns dict with cleanup metrics (useful for monitoring)

#### Implementation 3: `/home/user/catalyst-bot/src/catalyst_bot/gpu_profiler.py`
- **Lines:** 105-114
- **Function:** `cleanup_gpu_memory() -> None`
- **Features:**
  - No rate limiting (always executes)
  - Simple sequence: torch.cuda.empty_cache() → gc.collect()
  - No logging
- **Completeness:** 40% - **MINIMAL IMPLEMENTATION**
- **Use Case:** Profiling scenarios where unconditional cleanup needed

#### Implementation 4: `/home/user/catalyst-bot/src/catalyst_bot/llm_async.py`
- **Lines:** 325-336
- **Function:** `cleanup_gpu_memory(force: bool = False) -> None`
- **Features:**
  - Wrapper/delegation pattern
  - Delegates to `llm_client.cleanup_gpu_memory`
  - Logs debug message if unavailable
- **Completeness:** 10% - **COMPATIBILITY WRAPPER**
- **Purpose:** Re-export for backward compatibility

### 1.2 Dependency Mapping

#### Direct Callers (12 files total)

**Internal Python Imports:**
1. `/home/user/catalyst-bot/src/catalyst_bot/llm_async.py` (lines 210, 250, 332)
   - Imports from `llm_client.cleanup_gpu_memory`
   - Called on persistent failures and periodic cleanup
2. `/home/user/catalyst-bot/src/catalyst_bot/gpu_profiler.py`
   - Self-contained (lines 146, 271, 311, 395)
   - Called before/after profiling runs
3. `/home/user/catalyst-bot/src/catalyst_bot/ml/gpu_memory.py`
   - Self-contained
   - Called via `with_gpu_cleanup` decorator and `GPUMemoryContext` context manager
4. `/home/user/catalyst-bot/tests/test_llm_gpu_warmup.py`
   - Test file (imports from `llm_client`)

**Documentation References:**
5. `/home/user/catalyst-bot/docs/setup/DEPLOYMENT_READY.md` (lines 122, 325)
   - Test command: `python -c "from catalyst_bot.llm_client import cleanup_gpu_memory; cleanup_gpu_memory(force=True)"`
6. `/home/user/catalyst-bot/docs/planning/LLM_STABILITY_COMPREHENSIVE_PLAN.md` (line 478)
7. `/home/user/catalyst-bot/docs/enhancements/WAVE_0.2_IMPLEMENTATION_REPORT.md`
8. `/home/user/catalyst-bot/docs/MASTER_IMPLEMENTATION_PLAN.md`
9. `/home/user/catalyst-bot/docs/tutorials/Optimizing High-Volume LLM Sentiment Analysis for Python Trading Bots.md`
10. `/home/user/catalyst-bot/docs/waves/WAVE_2_IMPLEMENTATION.md`
11. `/home/user/catalyst-bot/docs/waves/WAVE_2.2_IMPLEMENTATION_SUMMARY.md`

#### Exports
- **NOT exported** in any `__init__.py` files
- Used via direct imports only

### 1.3 Consolidation Plan

#### Canonical Implementation
**Keep:** `/home/user/catalyst-bot/src/catalyst_bot/llm_client.py` implementation (lines 88-141)

**Rationale:**
1. Most complete feature set (rate limiting, logging, error handling)
2. Already documented critical sequence ordering
3. Most actively used (llm_async.py already delegates to it)
4. Proper environment variable support
5. Production-tested AMD RX 6800 compatibility

#### Enhanced Version
**Move to:** `/home/user/catalyst-bot/src/catalyst_bot/utils/gpu_utils.py` (NEW FILE)

**Enhancements to incorporate:**
1. Add return value from `ml/gpu_memory.py` (cleanup stats dict)
2. Keep both 60s and 300s interval options (make configurable)
3. Add profiling mode flag (disable rate limiting like gpu_profiler.py)

#### Files to Modify
1. **DELETE** `ml/gpu_memory.py:cleanup_gpu_memory()` (lines 201-249)
   - Keep other functions in ml/gpu_memory.py (get_model, etc.)
2. **DELETE** `gpu_profiler.py:cleanup_gpu_memory()` (lines 105-114)
3. **UPDATE** `llm_async.py:cleanup_gpu_memory()` (lines 325-336)
   - Change import to new location
4. **UPDATE** `llm_client.py`
   - Move function to utils/gpu_utils.py
   - Add import/re-export for backward compatibility

### 1.4 Migration Guide

#### Before (Current Usage)
```python
# Option 1: From llm_client
from catalyst_bot.llm_client import cleanup_gpu_memory
cleanup_gpu_memory(force=True)

# Option 2: From ml/gpu_memory
from catalyst_bot.ml.gpu_memory import cleanup_gpu_memory
stats = cleanup_gpu_memory(force=True)  # Returns dict

# Option 3: From gpu_profiler
from catalyst_bot.gpu_profiler import cleanup_gpu_memory
cleanup_gpu_memory()  # No args, always runs

# Option 4: From llm_async (wrapper)
from catalyst_bot.llm_async import cleanup_gpu_memory
cleanup_gpu_memory(force=False)
```

#### After (Unified Interface)
```python
# Primary import (new canonical location)
from catalyst_bot.utils.gpu_utils import cleanup_gpu_memory

# Basic usage (same as before)
cleanup_gpu_memory(force=True)

# Get cleanup stats (new optional return)
stats = cleanup_gpu_memory(force=True, return_stats=True)
# Returns: {'before_mb': 1024.5, 'after_mb': 512.2, 'freed_mb': 512.3}

# Profiling mode (disable rate limiting)
cleanup_gpu_memory(force=True, profiling_mode=True)

# Backward compatibility imports (deprecated but supported)
from catalyst_bot.llm_client import cleanup_gpu_memory  # Still works
from catalyst_bot.llm_async import cleanup_gpu_memory   # Still works
```

#### New Enhanced Signature
```python
def cleanup_gpu_memory(
    force: bool = False,
    return_stats: bool = False,
    profiling_mode: bool = False,
) -> Optional[Dict[str, float]]:
    """
    GPU memory cleanup for PyTorch/CUDA workloads.

    Critical cleanup sequence:
    1. Python garbage collection
    2. CUDA/ROCm synchronization
    3. Empty CUDA cache
    4. Reset peak memory stats

    Args:
        force: If True, cleanup regardless of interval timer
        return_stats: If True, return dict with cleanup metrics
        profiling_mode: If True, disable rate limiting (for profiling)

    Returns:
        Dict with cleanup stats if return_stats=True, else None
        Dict keys: before_mb, after_mb, freed_mb

    Environment Variables:
        GPU_CLEANUP_INTERVAL_SEC: Seconds between cleanups (default: 300)
    """
```

#### Migration Steps for Each File

**1. llm_async.py (lines 210, 250, 332)**
```python
# OLD:
from .llm_client import cleanup_gpu_memory

# NEW:
from .utils.gpu_utils import cleanup_gpu_memory
```

**2. gpu_profiler.py (lines 146, 271, 311, 395)**
```python
# OLD:
cleanup_gpu_memory()

# NEW:
from catalyst_bot.utils.gpu_utils import cleanup_gpu_memory
cleanup_gpu_memory(force=True, profiling_mode=True)
```

**3. ml/gpu_memory.py (update context manager and decorator)**
```python
# OLD:
def cleanup_gpu_memory(force: bool = False) -> Dict[str, float]:
    # ... implementation ...

# NEW:
from catalyst_bot.utils.gpu_utils import cleanup_gpu_memory

# Update calls to request stats:
cleanup_stats = cleanup_gpu_memory(force=True, return_stats=True)
```

### 1.5 Verification Checklist

#### Unit Tests
- [ ] Create `tests/utils/test_gpu_utils.py`
  - [ ] Test basic cleanup (force=True)
  - [ ] Test rate limiting (force=False)
  - [ ] Test return_stats=True
  - [ ] Test profiling_mode=True
  - [ ] Test with CUDA unavailable (graceful degradation)
  - [ ] Test interval timing
  - [ ] Test environment variable override

#### Integration Tests
- [ ] Run existing `tests/test_llm_gpu_warmup.py`
- [ ] Verify backward compatibility imports
- [ ] Test llm_async.py integration
- [ ] Test gpu_profiler.py profiling runs
- [ ] Test ml/gpu_memory.py context manager

#### Manual Testing
```bash
# 1. Test basic import and execution
python -c "from catalyst_bot.utils.gpu_utils import cleanup_gpu_memory; cleanup_gpu_memory(force=True); print('✅ Basic cleanup works')"

# 2. Test stats return
python -c "from catalyst_bot.utils.gpu_utils import cleanup_gpu_memory; stats = cleanup_gpu_memory(force=True, return_stats=True); print(f'✅ Stats: {stats}')"

# 3. Test backward compatibility
python -c "from catalyst_bot.llm_client import cleanup_gpu_memory; cleanup_gpu_memory(force=True); print('✅ Backward compat works')"

# 4. Test profiling scenario
python -m catalyst_bot.gpu_profiler --mode full

# 5. Test LLM async integration
python -c "from catalyst_bot.llm_async import query_llm_async; import asyncio; asyncio.run(query_llm_async('test'))"
```

#### Regression Prevention
- [ ] All existing tests pass: `pytest tests/test_llm_gpu_warmup.py -v`
- [ ] GPU profiler still works: `python -m catalyst_bot.gpu_profiler --mode sentiment`
- [ ] LLM client still functional: Test actual LLM queries
- [ ] Memory cleanup logs appear in production logs
- [ ] No import errors in any module

---

## 2. Token Estimation (2 Implementations)

### 2.1 Current State Analysis

#### Implementation 1: `/home/user/catalyst-bot/src/catalyst_bot/prompt_compression.py`
- **Lines:** 29-53
- **Function:** `estimate_tokens(text: str) -> int`
- **Algorithm:**
  - Characters / 4.0 * 1.05 (5% safety margin)
  - Returns max(1, estimated)
  - Handles empty strings → returns 0
- **Completeness:** 100%
- **Context:** Used for SEC filing compression
- **Docstring:** Comprehensive with parameters and examples

#### Implementation 2: `/home/user/catalyst-bot/src/catalyst_bot/llm_usage_monitor.py`
- **Lines:** 620-633
- **Function:** `estimate_tokens(text: str) -> int`
- **Algorithm:**
  - len(text) / 4 * 1.05 (identical logic)
  - No max() wrapper
  - Handles empty strings implicitly (len("") = 0)
- **Completeness:** 90%
- **Context:** Used for LLM usage tracking and cost calculation
- **Docstring:** Brief comment style

### 2.2 Dependency Mapping

#### Callers of prompt_compression.estimate_tokens
1. `/home/user/catalyst-bot/src/catalyst_bot/prompt_compression.py`
   - Internal calls (lines 262, 360, 393)
   - Used in `prioritize_sections()`, `compress_sec_filing()`, `should_compress()`
2. `/home/user/catalyst-bot/tests/test_prompt_compression.py`
   - Test coverage
3. `/home/user/catalyst-bot/scripts/demo_compression.py`
   - Demo script

#### Callers of llm_usage_monitor.estimate_tokens
1. `/home/user/catalyst-bot/src/catalyst_bot/llm_hybrid.py` (lines 771, 889, 905)
   - Used for token counting before API calls
   - Import: `from .llm_usage_monitor import estimate_tokens, get_monitor`

#### Documentation References
1. `/home/user/catalyst-bot/docs/llm/COMPRESSION_SUMMARY.txt`
2. `/home/user/catalyst-bot/docs/llm/PROMPT_COMPRESSION_REPORT.md`
3. `/home/user/catalyst-bot/docs/llm/LLM_USAGE_MONITORING.md`
4. `/home/user/catalyst-bot/docs/llm/LLM_SEC_CENTRALIZATION_PLAN.md`

### 2.3 Consolidation Plan

#### Canonical Implementation
**Keep:** `/home/user/catalyst-bot/src/catalyst_bot/prompt_compression.py` implementation

**Rationale:**
1. Better documentation (full docstring)
2. More defensive (max(1, estimated) prevents zero tokens)
3. Explicit empty string handling
4. Already well-tested

#### Target Location
**Move to:** `/home/user/catalyst-bot/src/catalyst_bot/utils/text_utils.py` (NEW FILE)

**Enhancements:**
- Add optional `model` parameter for model-specific token counting
- Add support for tiktoken if available (actual tokenization)
- Keep backward-compatible default (chars/4 heuristic)

#### Files to Modify
1. **DELETE** `llm_usage_monitor.py:estimate_tokens()` (lines 620-633)
2. **UPDATE** `llm_usage_monitor.py` - Import from utils.text_utils
3. **UPDATE** `prompt_compression.py` - Import from utils.text_utils (or keep for backward compat)
4. **UPDATE** `llm_hybrid.py` - Update import path

### 2.4 Migration Guide

#### Before (Current Usage)
```python
# Option 1: From prompt_compression
from catalyst_bot.prompt_compression import estimate_tokens
tokens = estimate_tokens("Hello world")  # Returns: 3

# Option 2: From llm_usage_monitor
from catalyst_bot.llm_usage_monitor import estimate_tokens
tokens = estimate_tokens("Hello world")  # Returns: 2
```

#### After (Unified Interface)
```python
# Primary import
from catalyst_bot.utils.text_utils import estimate_tokens

# Basic usage (backward compatible)
tokens = estimate_tokens("Hello world")  # Returns: 3 (chars/4 * 1.05)

# Enhanced usage (if tiktoken available)
tokens = estimate_tokens("Hello world", model="gpt-4")  # Actual tokenization

# Backward compatibility imports (deprecated but supported)
from catalyst_bot.prompt_compression import estimate_tokens  # Still works
from catalyst_bot.llm_usage_monitor import estimate_tokens   # Still works
```

#### New Enhanced Signature
```python
def estimate_tokens(
    text: str,
    model: Optional[str] = None,
    use_tiktoken: bool = True,
) -> int:
    """
    Estimate token count for text.

    Uses tiktoken for accurate tokenization if available and model specified.
    Falls back to heuristic: ~4 chars per token + 5% safety margin.

    Args:
        text: Input text to tokenize
        model: Model name for tiktoken (e.g., "gpt-4", "gpt-3.5-turbo")
               If None, uses heuristic
        use_tiktoken: If True, attempt to use tiktoken library

    Returns:
        Estimated token count (minimum 1 for non-empty strings)

    Examples:
        >>> estimate_tokens("Hello world")
        3
        >>> estimate_tokens("Hello world", model="gpt-4")
        2  # Actual tokenization
    """
```

#### Migration Steps

**1. prompt_compression.py (lines 262, 360, 393)**
```python
# OLD:
def estimate_tokens(text: str) -> int:
    # ... implementation ...

# NEW:
from .utils.text_utils import estimate_tokens
# Remove local implementation
```

**2. llm_usage_monitor.py (line 620)**
```python
# OLD:
def estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return int(len(text) / 4 * 1.05)

# NEW:
from .utils.text_utils import estimate_tokens
# Remove local implementation
```

**3. llm_hybrid.py (lines 771, 889, 905)**
```python
# OLD:
from .llm_usage_monitor import estimate_tokens

# NEW:
from .utils.text_utils import estimate_tokens
```

### 2.5 Verification Checklist

#### Unit Tests
- [ ] Create `tests/utils/test_text_utils.py`
  - [ ] Test basic estimation (heuristic)
  - [ ] Test empty string → 0
  - [ ] Test tiktoken integration (if available)
  - [ ] Test model-specific tokenization
  - [ ] Test graceful fallback (tiktoken unavailable)
  - [ ] Test safety margin (1.05x multiplier)

#### Integration Tests
- [ ] Run `tests/test_prompt_compression.py` (verify no regression)
- [ ] Test LLM usage monitoring still accurate
- [ ] Test prompt compression ratios unchanged
- [ ] Test llm_hybrid.py token counting

#### Manual Testing
```bash
# 1. Test basic estimation
python -c "from catalyst_bot.utils.text_utils import estimate_tokens; print(estimate_tokens('Hello world'))"

# 2. Test backward compatibility
python -c "from catalyst_bot.prompt_compression import estimate_tokens; print(estimate_tokens('Test'))"

# 3. Test in compression context
python -m scripts.demo_compression

# 4. Test in LLM monitoring
python -c "from catalyst_bot.llm_usage_monitor import get_monitor; m = get_monitor(); print(m.get_daily_stats())"
```

#### Regression Prevention
- [ ] Compression ratios remain consistent
- [ ] LLM cost calculations unchanged
- [ ] All token counts within 1% of previous values
- [ ] No import errors

---

## 3. Webhook Masking (2 Implementations)

### 3.1 Current State Analysis

#### Implementation 1: `/home/user/catalyst-bot/src/catalyst_bot/alerts.py`
- **Lines:** 117-125
- **Function:** `_mask_webhook(url: str | None) -> str`
- **Algorithm:**
  - Extracts last 8 characters of final URL segment
  - Returns `"...{tail[-8:]}"`
  - Handles None → `"<unset>"`
  - Handles errors → `"<masked>"`
- **Completeness:** 70%
- **Security:** Shows last 8 chars of token (moderate security)
- **Type Hints:** Modern (uses `str | None`)

#### Implementation 2: `/home/user/catalyst-bot/src/catalyst_bot/runner.py`
- **Lines:** 361-386
- **Function:** `_mask_webhook(url: str) -> str`
- **Algorithm:**
  - Parses Discord webhook format: `https://discord.com/api/webhooks/{id}/{token}`
  - Shows last 4 digits of webhook ID
  - Completely redacts token: `"***REDACTED***"`
  - Returns format: `"id=...{wid_tail} token=***REDACTED***"`
  - Handles empty → `"empty"`
  - Handles errors → `"unparsable"`
- **Completeness:** 100% - **MOST SECURE**
- **Security:** Never shows token, minimal ID exposure
- **Documentation:** Comprehensive docstring with security notes

### 3.2 Dependency Mapping

#### Callers of alerts._mask_webhook
1. `/home/user/catalyst-bot/src/catalyst_bot/alerts.py`
   - Used internally for webhook validation logging
   - Not called from other modules

#### Callers of runner._mask_webhook
1. `/home/user/catalyst-bot/src/catalyst_bot/runner.py`
   - Used internally for runner logging
   - Not called from other modules

#### Documentation References
1. `/home/user/catalyst-bot/docs/project/CODE_REVIEW_REPORT.md`
2. `/home/user/catalyst-bot/docs/security/SECURITY_REMEDIATION_PLAN.md`
   - Security audit explicitly recommends webhook masking

### 3.3 Consolidation Plan

#### Canonical Implementation
**Keep:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py` implementation

**Rationale:**
1. Superior security (never exposes token)
2. Better error handling (distinguishes empty vs unparsable)
3. More informative output (shows ID and token status separately)
4. Comprehensive documentation
5. Follows security best practices

#### Target Location
**Move to:** `/home/user/catalyst-bot/src/catalyst_bot/utils/security_utils.py` (NEW FILE)

**Rename to:** `mask_webhook_url()` (make public, remove underscore)

#### Files to Modify
1. **DELETE** `alerts.py:_mask_webhook()` (lines 117-125)
2. **UPDATE** `alerts.py` - Import from utils.security_utils
3. **UPDATE** `runner.py` - Import from utils.security_utils

### 3.4 Migration Guide

#### Before (Current Usage)
```python
# Option 1: From alerts (less secure)
from catalyst_bot.alerts import _mask_webhook
masked = _mask_webhook("https://discord.com/api/webhooks/123456/secret_token")
# Returns: "...ret_token" (last 8 chars, exposes part of token!)

# Option 2: From runner (more secure)
from catalyst_bot.runner import _mask_webhook
masked = _mask_webhook("https://discord.com/api/webhooks/123456/secret_token")
# Returns: "id=...3456 token=***REDACTED***"
```

#### After (Unified Interface)
```python
# Primary import (new public API)
from catalyst_bot.utils.security_utils import mask_webhook_url

# Secure masking (token never exposed)
masked = mask_webhook_url("https://discord.com/api/webhooks/123456/secret_token")
# Returns: "id=...3456 token=***REDACTED***"

# Handle edge cases
mask_webhook_url(None)   # Returns: "empty"
mask_webhook_url("")     # Returns: "empty"
mask_webhook_url("bad")  # Returns: "unparsable"

# Backward compatibility (deprecated, private API)
from catalyst_bot.alerts import _mask_webhook  # Still works (delegates)
from catalyst_bot.runner import _mask_webhook  # Still works (delegates)
```

#### New Enhanced Signature
```python
def mask_webhook_url(url: Optional[str]) -> str:
    """
    Securely mask a Discord webhook URL for logging.

    Discord webhook format: https://discord.com/api/webhooks/{id}/{token}

    Security Policy:
    - Webhook token is NEVER exposed (fully redacted)
    - Only last 4 digits of webhook ID shown (for identification)
    - Prevents accidental token leakage in logs

    Args:
        url: Discord webhook URL to mask (or None)

    Returns:
        Masked representation safe for logging
        Format: "id=...{last4} token=***REDACTED***"
        Special cases: "empty", "unparsable"

    Examples:
        >>> mask_webhook_url("https://discord.com/api/webhooks/123456789/abc123token")
        "id=...6789 token=***REDACTED***"

        >>> mask_webhook_url(None)
        "empty"

    Security:
        This function is specifically designed to prevent webhook token
        leakage in application logs, which could lead to unauthorized
        Discord channel access.
    """
```

#### Migration Steps

**1. alerts.py (replace internal function)**
```python
# OLD:
def _mask_webhook(url: str | None) -> str:
    """Return a scrubbed identifier for a Discord webhook (avoid leaking secrets)."""
    if not url:
        return "<unset>"
    try:
        tail = str(url).rsplit("/", 1)[-1]
        return f"...{tail[-8:]}"
    except Exception:
        return "<masked>"

# NEW:
from .utils.security_utils import mask_webhook_url as _mask_webhook
# Remove local implementation, use import alias for backward compat
```

**2. runner.py (replace internal function)**
```python
# OLD:
def _mask_webhook(url: str) -> str:
    """
    Return a masked fingerprint for a Discord webhook URL...
    """
    # ... implementation ...

# NEW:
from .utils.security_utils import mask_webhook_url as _mask_webhook
# Remove local implementation, use import alias for backward compat
```

### 3.5 Verification Checklist

#### Unit Tests
- [ ] Create `tests/utils/test_security_utils.py`
  - [ ] Test valid Discord webhook URL
  - [ ] Test None input → "empty"
  - [ ] Test empty string → "empty"
  - [ ] Test malformed URL → "unparsable"
  - [ ] Test token never exposed (regex check output)
  - [ ] Test webhook ID last 4 digits shown
  - [ ] Test various URL formats

#### Security Tests
- [ ] Verify token NEVER appears in masked output
- [ ] Test against known webhook URLs (sanitized test data)
- [ ] Verify no regex-based token extraction possible
- [ ] Audit all log statements using this function

#### Integration Tests
- [ ] Run alerts.py webhook validation flow
- [ ] Run runner.py startup logging
- [ ] Verify log files contain masked webhooks only
- [ ] Test actual Discord webhook posts still work

#### Manual Testing
```bash
# 1. Test basic masking
python -c "from catalyst_bot.utils.security_utils import mask_webhook_url; print(mask_webhook_url('https://discord.com/api/webhooks/123456789/secret_token_here'))"
# Expected: "id=...6789 token=***REDACTED***"

# 2. Test security (token should NEVER appear)
python -c "from catalyst_bot.utils.security_utils import mask_webhook_url; result = mask_webhook_url('https://discord.com/api/webhooks/123/MY_SECRET'); assert 'MY_SECRET' not in result; print('✅ Token not leaked')"

# 3. Test backward compatibility
python -c "from catalyst_bot.alerts import _mask_webhook; print(_mask_webhook('https://discord.com/api/webhooks/123/token'))"

# 4. Test in production context
python -c "from catalyst_bot.runner import get_webhook_url; from catalyst_bot.utils.security_utils import mask_webhook_url; url = get_webhook_url(); print(f'Webhook: {mask_webhook_url(url)}')"
```

#### Regression Prevention
- [ ] Alert system still posts to Discord
- [ ] Runner startup logs show masked webhooks
- [ ] No webhook URLs visible in plaintext logs
- [ ] Webhook validation still functional

---

## 4. Repo Root Resolution (9 Implementations)

### 4.1 Current State Analysis

#### Implementation Pattern
**All 9 implementations use identical logic:**
```python
def _repo_root() -> Path:  # or _get_repo_root() or get_project_root()
    """Get repository root directory."""
    return Path(__file__).resolve().parents[N]
```

Where `N` varies based on file depth:
- `N=2` for files in `src/catalyst_bot/`
- `N=3` for files in deeper directories

#### All Implementations

1. **`/home/user/catalyst-bot/src/catalyst_bot/deployment.py:40`**
   - Function: `get_project_root() -> Path`
   - Level: `parents[2]`
   - Public API (no underscore)

2. **`/home/user/catalyst-bot/src/catalyst_bot/analyzer.py:38`**
   - Function: `_repo_root() -> Path`
   - Level: `parents[2]`
   - Private (underscore prefix)

3. **`/home/user/catalyst-bot/src/catalyst_bot/ticker_map.py:26`**
   - Function: `_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Return the repository root based on this file's location."

4. **`/home/user/catalyst-bot/src/catalyst_bot/false_positive_tracker.py:44`**
   - Function: `_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Get repository root directory."

5. **`/home/user/catalyst-bot/src/catalyst_bot/weekly_performance.py:28`**
   - Function: `_get_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Get repository root directory."

6. **`/home/user/catalyst-bot/src/catalyst_bot/moa_historical_analyzer.py:56`**
   - Function: `_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Get repository root directory."

7. **`/home/user/catalyst-bot/src/catalyst_bot/admin_controls.py:77`**
   - Function: `_get_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Get repository root directory."

8. **`/home/user/catalyst-bot/src/catalyst_bot/config_updater.py:40`**
   - Function: `_get_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Get repository root directory."

9. **`/home/user/catalyst-bot/src/catalyst_bot/moa_analyzer.py:96`**
   - Function: `_repo_root() -> Path`
   - Level: `parents[2]`
   - Docstring: "Get repository root directory."

10. **`/home/user/catalyst-bot/src/catalyst_bot/false_positive_analyzer.py:34`**
    - Function: `_repo_root() -> Path`
    - Level: `parents[2]`
    - Docstring: "Get repository root directory."

### 4.2 Dependency Mapping

#### Usage Patterns

**Each function is used ONLY within its own module** (internal helper):
- `analyzer.py`: Used in `_paths()` to get data directories
- `ticker_map.py`: Used in `_ndjson_path()` to locate ticker data
- `false_positive_tracker.py`: Used in `_ensure_fp_dirs()` for log paths
- `weekly_performance.py`: Used to locate backtest results
- `moa_historical_analyzer.py`: Used in `_ensure_moa_dirs()`
- `admin_controls.py`: Used to locate `.env` file
- `config_updater.py`: Used in `_get_env_path()`
- `moa_analyzer.py`: Used in `_ensure_moa_dirs()`
- `false_positive_analyzer.py`: Used in `_ensure_fp_dirs()`
- `deployment.py`: Public API, used in deployment scripts

#### External Callers
1. `/home/user/catalyst-bot/scripts/validate_deployment.py`
   - Imports `get_project_root` from `deployment.py`
2. `/home/user/catalyst-bot/tests/manual/test_admin_workflow.py`
   - Likely uses admin_controls functions indirectly
3. `/home/user/catalyst-bot/tests/test_admin_controls.py`
   - Tests admin_controls module
4. `/home/user/catalyst-bot/tests/test_moa_keyword_discovery.py`
   - Tests MOA modules

### 4.3 Consolidation Plan

#### Canonical Implementation
**Keep:** `/home/user/catalyst-bot/src/catalyst_bot/deployment.py:get_project_root()`

**Rationale:**
1. Public API (no underscore) - intentionally designed for external use
2. Best name (`get_project_root` is clearer than `_repo_root`)
3. Already has external callers (validate_deployment.py)
4. Located in deployment.py (appropriate for infrastructure utilities)

#### Target Location
**Move to:** `/home/user/catalyst-bot/src/catalyst_bot/utils/path_utils.py` (NEW FILE)

**Rename to:** `get_project_root()` (keep public name)

**Enhanced Implementation:**
```python
from pathlib import Path
from typing import Optional

# Cache to avoid repeated filesystem operations
_PROJECT_ROOT_CACHE: Optional[Path] = None

def get_project_root(anchor_file: Optional[Path] = None) -> Path:
    """
    Get the catalyst-bot project root directory.

    Finds the repository root by walking up from this file until
    finding the directory containing 'src/catalyst_bot/'.

    Result is cached for performance (single filesystem traversal).

    Args:
        anchor_file: Optional file path to use as anchor (for testing)
                     If None, uses this file's location

    Returns:
        Path to project root directory

    Raises:
        RuntimeError: If project root cannot be determined

    Examples:
        >>> root = get_project_root()
        >>> assert (root / "src" / "catalyst_bot").exists()
    """
    global _PROJECT_ROOT_CACHE

    if _PROJECT_ROOT_CACHE is not None:
        return _PROJECT_ROOT_CACHE

    # Use anchor file or this file
    start = anchor_file or Path(__file__)
    current = start.resolve()

    # Walk up directory tree looking for project markers
    for parent in [current] + list(current.parents):
        # Check for src/catalyst_bot/ (project marker)
        if (parent / "src" / "catalyst_bot").exists():
            _PROJECT_ROOT_CACHE = parent
            return parent

        # Also check for .git directory (fallback)
        if (parent / ".git").exists():
            _PROJECT_ROOT_CACHE = parent
            return parent

    # Fallback to two parents up (original behavior)
    fallback = Path(__file__).resolve().parents[2]
    _PROJECT_ROOT_CACHE = fallback
    return fallback

def clear_project_root_cache() -> None:
    """Clear cached project root (for testing)."""
    global _PROJECT_ROOT_CACHE
    _PROJECT_ROOT_CACHE = None
```

#### Files to Modify (All 10)
1. **DELETE** local `_repo_root()` / `_get_repo_root()` from each file
2. **ADD** import: `from .utils.path_utils import get_project_root`
3. **REPLACE** calls: `_repo_root()` → `get_project_root()`

### 4.4 Migration Guide

#### Before (Current Usage - 9 different functions)
```python
# analyzer.py
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
root = _repo_root()

# admin_controls.py
def _get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
root = _get_repo_root()

# deployment.py (public API)
def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]
root = get_project_root()

# ... 7 more identical implementations
```

#### After (Unified Interface)
```python
# All modules use single import
from catalyst_bot.utils.path_utils import get_project_root

# Get project root (cached after first call)
root = get_project_root()

# Use for paths
data_dir = get_project_root() / "data"
config_file = get_project_root() / ".env"
```

#### Migration Steps for Each File

**1. analyzer.py (line 38)**
```python
# OLD:
def _repo_root() -> Path:
    # .../catalyst-bot/src/catalyst_bot/analyzer.py -> repo root
    return Path(__file__).resolve().parents[2]

def _paths() -> Tuple[Path, Path, Path]:
    root = _repo_root()
    # ...

# NEW:
from .utils.path_utils import get_project_root

def _paths() -> Tuple[Path, Path, Path]:
    root = get_project_root()
    # ...
```

**2. ticker_map.py (line 26)**
```python
# OLD:
def _repo_root() -> Path:
    """Return the repository root based on this file's location."""
    return Path(__file__).resolve().parents[2]

def _ndjson_path() -> Path:
    return _repo_root() / "data" / "tickers.ndjson"

# NEW:
from .utils.path_utils import get_project_root

def _ndjson_path() -> Path:
    return get_project_root() / "data" / "tickers.ndjson"
```

**3. false_positive_tracker.py (line 44)**
```python
# OLD:
def _repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]

def _ensure_fp_dirs() -> Tuple[Path, Path]:
    root = _repo_root()
    # ...

# NEW:
from .utils.path_utils import get_project_root

def _ensure_fp_dirs() -> Tuple[Path, Path]:
    root = get_project_root()
    # ...
```

**4. weekly_performance.py (line 28)**
```python
# OLD:
def _get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]

def analyze_weekly_performance(lookback_days: int = 7) -> Dict[str, Any]:
    repo_root = _get_repo_root()
    # ...

# NEW:
from .utils.path_utils import get_project_root

def analyze_weekly_performance(lookback_days: int = 7) -> Dict[str, Any]:
    repo_root = get_project_root()
    # ...
```

**5-9. Similar pattern for remaining files:**
- `moa_historical_analyzer.py:56`
- `admin_controls.py:77`
- `config_updater.py:40`
- `moa_analyzer.py:96`
- `false_positive_analyzer.py:34`

**10. deployment.py (line 40) - Move implementation**
```python
# OLD (entire implementation):
def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parents[2]

# NEW (re-export for backward compatibility):
from .utils.path_utils import get_project_root

__all__ = ["get_project_root", ...]
```

### 4.5 Verification Checklist

#### Unit Tests
- [ ] Create `tests/utils/test_path_utils.py`
  - [ ] Test `get_project_root()` returns correct path
  - [ ] Test caching (same object returned)
  - [ ] Test `clear_project_root_cache()`
  - [ ] Test from different file depths
  - [ ] Test project markers (src/catalyst_bot/, .git/)
  - [ ] Test fallback behavior

#### Integration Tests
- [ ] Test analyzer.py paths (`_paths()` function)
- [ ] Test ticker_map.py data loading
- [ ] Test false_positive_tracker.py directory creation
- [ ] Test weekly_performance.py backtest access
- [ ] Test MOA analyzer directory creation
- [ ] Test admin_controls.py .env file access
- [ ] Test config_updater.py updates
- [ ] Test deployment.py validation

#### Manual Testing
```bash
# 1. Test basic path resolution
python -c "from catalyst_bot.utils.path_utils import get_project_root; root = get_project_root(); print(f'Project root: {root}'); assert root.name == 'catalyst-bot'; print('✅')"

# 2. Test caching
python -c "from catalyst_bot.utils.path_utils import get_project_root; r1 = get_project_root(); r2 = get_project_root(); assert r1 is r2; print('✅ Caching works')"

# 3. Test from each module
python -c "from catalyst_bot.analyzer import _paths; print(_paths())"
python -c "from catalyst_bot.ticker_map import _ndjson_path; print(_ndjson_path())"
python -c "from catalyst_bot.admin_controls import _get_current_parameters; print('✅ admin_controls works')"

# 4. Test deployment script (external caller)
python scripts/validate_deployment.py

# 5. Test data file access
python -c "from catalyst_bot.utils.path_utils import get_project_root; assert (get_project_root() / 'data').exists(); print('✅ Data directory accessible')"

# 6. Test all modules that use repo root
pytest tests/test_admin_controls.py -v
pytest tests/test_moa_keyword_discovery.py -v
```

#### Regression Prevention
- [ ] All path-dependent operations still work
- [ ] Data files still accessible (ticker_map, backtest data)
- [ ] Log directories still created correctly
- [ ] .env file still found by admin_controls
- [ ] MOA and false positive tracking directories functional
- [ ] Deployment validation script passes
- [ ] No import errors in any module

---

## 5. Implementation Roadmap

### Phase 1: Foundation (Week 1)
**Goal:** Create utility modules and tests

**Tasks:**
1. Create `src/catalyst_bot/utils/` directory
2. Create `src/catalyst_bot/utils/__init__.py`
3. Implement `utils/gpu_utils.py` (GPU cleanup consolidation)
4. Implement `utils/text_utils.py` (token estimation)
5. Implement `utils/security_utils.py` (webhook masking)
6. Implement `utils/path_utils.py` (repo root resolution)
7. Create comprehensive tests:
   - `tests/utils/test_gpu_utils.py`
   - `tests/utils/test_text_utils.py`
   - `tests/utils/test_security_utils.py`
   - `tests/utils/test_path_utils.py`

**Success Criteria:**
- [ ] All new utility modules pass tests
- [ ] 100% test coverage for new code
- [ ] No external dependencies broken

### Phase 2: Migration (Week 2)
**Goal:** Update all calling code

**Tasks:**
1. **GPU Memory Cleanup** (4 files)
   - Update `llm_async.py` imports
   - Update `gpu_profiler.py` calls
   - Update `ml/gpu_memory.py` context manager
   - Remove duplicate implementations

2. **Token Estimation** (3 files)
   - Update `llm_hybrid.py` import
   - Update `prompt_compression.py`
   - Update `llm_usage_monitor.py`
   - Remove duplicates

3. **Webhook Masking** (2 files)
   - Update `alerts.py` internal calls
   - Update `runner.py` internal calls
   - Remove duplicates

4. **Repo Root Resolution** (10 files)
   - Update all 9 modules with local implementations
   - Update `deployment.py` to re-export
   - Remove all duplicates

**Success Criteria:**
- [ ] All imports updated
- [ ] All duplicate code removed
- [ ] All tests passing (including existing tests)
- [ ] No functionality regressions

### Phase 3: Verification (Week 3)
**Goal:** Comprehensive testing and validation

**Tasks:**
1. Run full test suite: `pytest tests/ -v --cov=src/catalyst_bot/utils`
2. Manual integration testing (see checklists above)
3. Code review for each change
4. Update documentation references
5. Security audit (webhook masking)
6. Performance validation (GPU cleanup, token estimation)

**Success Criteria:**
- [ ] All automated tests pass
- [ ] Manual testing complete
- [ ] Code review approved
- [ ] Documentation updated
- [ ] No security regressions
- [ ] Performance metrics stable

### Phase 4: Deployment (Week 4)
**Goal:** Production rollout

**Tasks:**
1. Create deployment checklist
2. Backup current production state
3. Deploy to staging environment
4. Run smoke tests
5. Monitor for 24 hours
6. Deploy to production
7. Monitor logs for issues

**Success Criteria:**
- [ ] Staging deployment successful
- [ ] No errors in staging logs
- [ ] Production deployment successful
- [ ] All systems operational
- [ ] No increase in error rates

---

## 6. Risk Assessment

### High Risk Items
1. **GPU Memory Cleanup** - Critical for LLM stability
   - **Mitigation:** Extensive testing on AMD RX 6800
   - **Rollback Plan:** Keep llm_client.py backup for 2 weeks

2. **Repo Root Resolution** - Affects 10 modules
   - **Mitigation:** Comprehensive path tests across all modules
   - **Rollback Plan:** Git branch for easy revert

### Medium Risk Items
1. **Token Estimation** - Affects cost calculations
   - **Mitigation:** Validate costs match previous calculations
   - **Rollback Plan:** Comparison tests before/after

2. **Webhook Masking** - Security implications
   - **Mitigation:** Security audit, never expose tokens
   - **Rollback Plan:** Quick rollback if token leakage detected

### Low Risk Items
- All utility code is well-isolated
- No database schema changes
- No external API changes
- Backward compatibility maintained

---

## 7. Success Metrics

### Code Quality Metrics
- **LOC Reduction:** ~450 lines (target)
- **Duplicate Elimination:** 17 → 4 implementations (76% reduction)
- **Test Coverage:** 100% for new utility modules
- **Documentation:** Complete for all new APIs

### Performance Metrics
- **GPU Cleanup Time:** No regression (should remain < 100ms)
- **Token Estimation Accuracy:** Within 1% of current values
- **Repo Root Resolution:** Cached (near-zero overhead)

### Reliability Metrics
- **Zero Regressions:** All existing tests pass
- **Zero Security Issues:** Webhook tokens never exposed
- **Zero Import Errors:** All modules still functional

---

## 8. Appendix

### A. Complete File Change Summary

#### Files to Create (5)
1. `src/catalyst_bot/utils/__init__.py`
2. `src/catalyst_bot/utils/gpu_utils.py`
3. `src/catalyst_bot/utils/text_utils.py`
4. `src/catalyst_bot/utils/security_utils.py`
5. `src/catalyst_bot/utils/path_utils.py`

#### Files to Modify (17)
1. `src/catalyst_bot/llm_async.py` (GPU cleanup import)
2. `src/catalyst_bot/llm_client.py` (move GPU cleanup, add re-export)
3. `src/catalyst_bot/gpu_profiler.py` (remove cleanup, add import)
4. `src/catalyst_bot/ml/gpu_memory.py` (remove cleanup, add import)
5. `src/catalyst_bot/prompt_compression.py` (remove estimate_tokens, add import)
6. `src/catalyst_bot/llm_usage_monitor.py` (remove estimate_tokens, add import)
7. `src/catalyst_bot/llm_hybrid.py` (update import path)
8. `src/catalyst_bot/alerts.py` (remove _mask_webhook, add import)
9. `src/catalyst_bot/runner.py` (remove _mask_webhook, add import)
10. `src/catalyst_bot/analyzer.py` (remove _repo_root, add import)
11. `src/catalyst_bot/ticker_map.py` (remove _repo_root, add import)
12. `src/catalyst_bot/false_positive_tracker.py` (remove _repo_root, add import)
13. `src/catalyst_bot/weekly_performance.py` (remove _get_repo_root, add import)
14. `src/catalyst_bot/moa_historical_analyzer.py` (remove _repo_root, add import)
15. `src/catalyst_bot/admin_controls.py` (remove _get_repo_root, add import)
16. `src/catalyst_bot/config_updater.py` (remove _get_repo_root, add import)
17. `src/catalyst_bot/moa_analyzer.py` (remove _repo_root, add import)
18. `src/catalyst_bot/false_positive_analyzer.py` (remove _repo_root, add import)
19. `src/catalyst_bot/deployment.py` (move get_project_root, add re-export)

#### Tests to Create (4)
1. `tests/utils/test_gpu_utils.py`
2. `tests/utils/test_text_utils.py`
3. `tests/utils/test_security_utils.py`
4. `tests/utils/test_path_utils.py`

### B. Import Aliases for Backward Compatibility

To minimize breaking changes, use import aliases:

```python
# In llm_client.py (after moving cleanup to utils)
from .utils.gpu_utils import cleanup_gpu_memory

# In alerts.py (after moving mask to utils)
from .utils.security_utils import mask_webhook_url as _mask_webhook

# In deployment.py (after moving to utils)
from .utils.path_utils import get_project_root
```

This allows external code to continue using old import paths during transition period.

### C. Deprecation Timeline

**Immediate (Wave 1 Implementation):**
- Create new utility modules
- Update internal imports
- Maintain backward compatibility

**1 Month Post-Deployment:**
- Add deprecation warnings to old import paths
- Update documentation to recommend new paths

**3 Months Post-Deployment:**
- Remove backward compatibility aliases
- Require all code use new import paths

### D. Related Documentation

- **Security:** `/home/user/catalyst-bot/docs/security/SECURITY_REMEDIATION_PLAN.md`
- **LLM Stability:** `/home/user/catalyst-bot/docs/planning/LLM_STABILITY_COMPREHENSIVE_PLAN.md`
- **Deployment:** `/home/user/catalyst-bot/docs/setup/DEPLOYMENT_READY.md`
- **Code Review:** `/home/user/catalyst-bot/docs/project/CODE_REVIEW_REPORT.md`

---

## 9. Contact & Support

**Implementation Lead:** To be assigned
**Review Required:** Senior Engineer
**Estimated Effort:** 3-4 weeks (1 engineer)
**Dependencies:** None (foundational work)

**Questions or Issues:**
- Create GitHub issue with label `deduplication-wave1`
- Tag in PR reviews
- Escalate blockers to tech lead

---

**Document Version:** 1.0
**Last Updated:** 2025-12-14
**Next Review:** After Wave 1 implementation complete
