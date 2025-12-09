# Nightly Scanner Suite Implementation Plan

**Version:** 1.0
**Date:** December 9, 2025
**Status:** Ready for Implementation
**Branch:** `claude/auto-volatility-stock-list-01SUsPtUnZwFCUPdN8vcTnu8`

---

## Executive Summary

This document outlines the implementation plan for a **Nightly Scanner Suite** - a collection of standalone scheduled reports that post market intelligence to Discord. The suite includes:

1. **High IV Scanner** - Stocks under $10 with highest implied volatility
2. **Short Interest Scanner** - High short interest candidates
3. **Unusual Volume Scanner** - Abnormal volume detection
4. **Earnings Preview** - Upcoming earnings for watchlist
5. **Gap Scanner** - Pre-market gap up/down candidates
6. **Float Rotation Scanner** - Low float with high volume turnover

**Key Design Principles:**
- Standalone modules (not bloating main runner)
- Phased rollout with test commands
- Data persistence for future features
- 10 PM CST schedule (Sunday-Thursday)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Agent Team Structure](#2-agent-team-structure)
3. [Phase 1: IV Scanner (MVP)](#3-phase-1-iv-scanner-mvp)
4. [Phase 2: Additional Scanners](#4-phase-2-additional-scanners)
5. [Phase 3: Rich Embeds & Cross-Scanner Features](#5-phase-3-rich-embeds)
6. [Dependencies & Wiring](#6-dependencies--wiring)
7. [Test Commands](#7-test-commands)
8. [Configuration Reference](#8-configuration-reference)
9. [Ticket Breakdown](#9-ticket-breakdown)
10. [Future Rich Embed Ideas](#10-future-rich-embed-ideas)

---

## 1. Architecture Overview

### File Structure

```
src/catalyst_bot/
├── scanners/                          # NEW: Scanner suite package
│   ├── __init__.py                    # Package exports
│   ├── base_scanner.py                # Abstract base class
│   ├── iv_scanner.py                  # High IV scanner (Phase 1)
│   ├── short_interest_scanner.py      # Short interest (Phase 2)
│   ├── volume_scanner.py              # Unusual volume (Phase 2)
│   ├── earnings_scanner.py            # Earnings preview (Phase 2)
│   ├── gap_scanner.py                 # Gap up/down (Phase 2)
│   ├── float_scanner.py               # Float rotation (Phase 2)
│   └── scheduler.py                   # Unified scheduler
│
├── data_providers/                    # NEW: External data clients
│   ├── __init__.py
│   ├── tradier_client.py              # Tradier API for options/IV
│   ├── barchart_scraper.py            # Barchart web scraper
│   └── finra_client.py                # FINRA short interest
│
├── scanner_reports.py                 # NEW: Discord report builder
├── scanner_db.py                      # NEW: SQLite persistence
│
└── runner.py                          # EXISTING: Add scheduler hook
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     NIGHTLY SCANNER SUITE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Tradier    │    │   yfinance   │    │   Barchart   │       │
│  │     API      │    │   (free)     │    │  (scraper)   │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │                │
│         └───────────────────┼───────────────────┘                │
│                             ▼                                    │
│                    ┌────────────────┐                            │
│                    │  BASE SCANNER  │                            │
│                    │   (abstract)   │                            │
│                    └────────┬───────┘                            │
│                             │                                    │
│         ┌───────────────────┼───────────────────┐                │
│         ▼                   ▼                   ▼                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │ IV Scanner  │    │Vol Scanner  │    │Gap Scanner  │  ...     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            ▼                                     │
│                   ┌────────────────┐                             │
│                   │  Scanner DB    │◄── SQLite persistence       │
│                   │ (scanner_db.py)│                             │
│                   └────────┬───────┘                             │
│                            │                                     │
│                            ▼                                     │
│                   ┌────────────────┐                             │
│                   │ Report Builder │                             │
│                   │(scanner_reports)│                            │
│                   └────────┬───────┘                             │
│                            │                                     │
│              ┌─────────────┼─────────────┐                       │
│              ▼                           ▼                       │
│     ┌────────────────┐          ┌────────────────┐              │
│     │Scanner Webhook │          │ Admin Webhook  │              │
│     │   (primary)    │          │   (backup)     │              │
│     └────────────────┘          └────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Schedule: 10 PM CST (Fixed)

```python
# 10 PM CST = 04:00 UTC (always, ignoring DST)
# CST is UTC-6, so 22:00 - (-6) = 04:00 UTC
SCANNER_UTC_HOUR = 4
SCANNER_UTC_MINUTE = 0

# Days: Sunday-Thursday (reports for Mon-Fri trading)
SCANNER_DAYS = [6, 0, 1, 2, 3]  # Sun=6, Mon=0, Tue=1, Wed=2, Thu=3
```

---

## 2. Agent Team Structure

For Claude Code CLI vibecoding implementation, deploy these specialized agents:

### Supervisor Agent (Orchestrator)

**Role:** Coordinates all sub-agents, maintains context, ensures integration

**Responsibilities:**
- Track progress across all phases
- Ensure code consistency
- Validate wiring between modules
- Final integration testing

**Prompt Template:**
```
You are the Supervisor Agent for the Nightly Scanner Suite implementation.

Current Phase: [PHASE_NUMBER]
Completed Tickets: [LIST]
Active Tickets: [LIST]
Blocked Tickets: [LIST]

Your job is to:
1. Coordinate the sub-agents below
2. Ensure context is maintained between sessions
3. Validate that new code preserves existing functionality
4. Track dependencies and wiring points

Sub-agents to coordinate:
- Data Layer Agent
- Scanner Agent
- Report Builder Agent
- Scheduler Agent
- Test Agent

Current task: [TASK_DESCRIPTION]
```

### Sub-Agent Definitions

#### 1. Data Layer Agent

**Scope:** `src/catalyst_bot/data_providers/`

**Responsibilities:**
- Implement Tradier API client
- Implement Barchart web scraper
- Handle rate limiting and caching
- Error handling for API failures

**Key Files:**
- `tradier_client.py` - Tradier sandbox API
- `barchart_scraper.py` - Web scraping with BeautifulSoup
- `finra_client.py` - Short interest data

**Prompt:**
```
You are the Data Layer Agent. Your job is to implement external data providers.

CRITICAL RULES:
1. All API keys come from environment variables
2. Implement exponential backoff for rate limits
3. Cache responses where appropriate
4. Return None on failures (don't raise exceptions to callers)
5. Log all API calls for debugging

Current ticket: [TICKET_ID]
```

#### 2. Scanner Agent

**Scope:** `src/catalyst_bot/scanners/`

**Responsibilities:**
- Implement base scanner abstract class
- Implement each specific scanner
- Define filtering and ranking logic
- Handle stock universe generation

**Key Files:**
- `base_scanner.py` - Abstract base with common methods
- `iv_scanner.py`, `volume_scanner.py`, etc.

**Prompt:**
```
You are the Scanner Agent. Your job is to implement market scanners.

CRITICAL RULES:
1. All scanners inherit from BaseScanner
2. Each scanner is standalone (can run independently)
3. Return standardized ScanResult dataclass
4. Preserve existing scanner.py functionality
5. Use data providers (don't call APIs directly)

Current ticket: [TICKET_ID]
```

#### 3. Report Builder Agent

**Scope:** `src/catalyst_bot/scanner_reports.py`

**Responsibilities:**
- Build Discord embeds for each scanner type
- Format data for readability
- Handle embed field limits (25 fields, 1024 chars)
- Color coding based on data

**Prompt:**
```
You are the Report Builder Agent. Your job is to create Discord embeds.

CRITICAL RULES:
1. Follow existing embed patterns in alerts.py
2. Respect Discord limits (25 fields, 6000 chars total)
3. Use consistent color scheme
4. Include timestamps and data freshness indicators
5. Support both simple lists and rich embeds

Current ticket: [TICKET_ID]
```

#### 4. Scheduler Agent

**Scope:** `src/catalyst_bot/scanners/scheduler.py` + runner.py integration

**Responsibilities:**
- Implement schedule checking (10 PM CST)
- Integrate with runner.py loop
- Handle test/force commands
- Prevent duplicate runs

**Prompt:**
```
You are the Scheduler Agent. Your job is to implement timing and scheduling.

CRITICAL RULES:
1. Use 04:00 UTC (10 PM CST fixed, no DST)
2. Only run Sunday-Thursday
3. Track last run in JSON file to prevent duplicates
4. Minimal changes to runner.py (single hook)
5. Support manual trigger via test command

Current ticket: [TICKET_ID]
```

#### 5. Test Agent

**Scope:** `tests/` + manual test commands

**Responsibilities:**
- Write unit tests for each scanner
- Implement `/test-scanner` command
- Create mock data for testing
- Validate Discord posting

**Prompt:**
```
You are the Test Agent. Your job is to ensure quality.

CRITICAL RULES:
1. Every scanner needs unit tests
2. Mock all external API calls in tests
3. Test command must work outside market hours
4. Validate embed formatting
5. Test database persistence

Current ticket: [TICKET_ID]
```

---

## 3. Phase 1: IV Scanner (MVP)

### Goal
Ship a working High IV Scanner that:
- Runs at 10 PM CST Sunday-Thursday
- Finds stocks under $10 with highest IV
- Posts formatted list to Discord
- Saves results to SQLite

### Tickets

#### TICKET-001: Base Scanner Infrastructure

**Priority:** P0 (Blocker)
**Agent:** Scanner Agent
**Estimated Effort:** 2 hours

**Description:**
Create the base scanner class and package structure.

**Files to Create:**
- `src/catalyst_bot/scanners/__init__.py`
- `src/catalyst_bot/scanners/base_scanner.py`

**Code Example:**

```python
# src/catalyst_bot/scanners/base_scanner.py
"""
Base scanner class for all market scanners.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..logging_utils import get_logger


@dataclass
class ScanResult:
    """Standardized result from any scanner."""

    scanner_name: str
    scan_time: datetime
    results: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and len(self.results) > 0

    @property
    def count(self) -> int:
        return len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanner_name": self.scanner_name,
            "scan_time": self.scan_time.isoformat(),
            "result_count": self.count,
            "results": self.results,
            "metadata": self.metadata,
            "error": self.error,
        }


class BaseScanner(ABC):
    """Abstract base class for all market scanners."""

    def __init__(self, name: str):
        self.name = name
        self.log = get_logger(f"scanner.{name}")
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[ScanResult] = None

    @abstractmethod
    def scan(self) -> ScanResult:
        """Execute the scan and return results."""
        pass

    @abstractmethod
    def get_feature_flag(self) -> str:
        """Return the feature flag env var name for this scanner."""
        pass

    def is_enabled(self) -> bool:
        """Check if this scanner is enabled via feature flag."""
        flag = self.get_feature_flag()
        return os.getenv(flag, "0").lower() in ("1", "true", "yes", "on")

    def run_if_enabled(self) -> Optional[ScanResult]:
        """Run scan only if feature flag is enabled."""
        if not self.is_enabled():
            self.log.debug(f"{self.name}_disabled")
            return None

        self.log.info(f"{self.name}_starting")
        result = self.scan()
        self._last_run = datetime.now(timezone.utc)
        self._last_result = result

        if result.success:
            self.log.info(f"{self.name}_complete count={result.count}")
        else:
            self.log.warning(f"{self.name}_failed error={result.error}")

        return result
```

**Acceptance Criteria:**
- [ ] Package structure created
- [ ] ScanResult dataclass defined
- [ ] BaseScanner ABC with required methods
- [ ] Feature flag support
- [ ] Logging integration

---

#### TICKET-002: Tradier API Client

**Priority:** P0 (Blocker)
**Agent:** Data Layer Agent
**Estimated Effort:** 3 hours

**Description:**
Implement Tradier sandbox API client for options/IV data.

**Files to Create:**
- `src/catalyst_bot/data_providers/__init__.py`
- `src/catalyst_bot/data_providers/tradier_client.py`

**Code Example:**

```python
# src/catalyst_bot/data_providers/tradier_client.py
"""
Tradier API client for options data with IV.

Setup:
1. Sign up at developer.tradier.com
2. Get sandbox token from dash.tradier.com/settings/api
3. Set TRADIER_SANDBOX_TOKEN env var
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

from ..logging_utils import get_logger

log = get_logger("tradier_client")

TRADIER_SANDBOX_BASE = "https://sandbox.tradier.com/v1"
TRADIER_PROD_BASE = "https://api.tradier.com/v1"


class TradierClient:
    """Client for Tradier API (sandbox or production)."""

    def __init__(self, use_sandbox: bool = True):
        self.token = os.getenv("TRADIER_SANDBOX_TOKEN") if use_sandbox else os.getenv("TRADIER_API_TOKEN")
        self.base_url = TRADIER_SANDBOX_BASE if use_sandbox else TRADIER_PROD_BASE
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        self._request_delay = 0.5  # Polite rate limiting
        self._last_request = 0.0

    def is_configured(self) -> bool:
        """Check if API token is set."""
        return bool(self.token)

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make API request with rate limiting."""
        if not self.is_configured():
            log.warning("tradier_not_configured")
            return None

        # Rate limiting
        elapsed = time.time() - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)

        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            self._last_request = time.time()

            if response.status_code == 200:
                return response.json()
            else:
                log.warning(f"tradier_request_failed status={response.status_code} url={endpoint}")
                return None

        except requests.RequestException as e:
            log.error(f"tradier_request_error endpoint={endpoint} err={e}")
            return None

    def get_option_expirations(self, symbol: str) -> List[str]:
        """Get available option expiration dates for a symbol."""
        data = self._request("/markets/options/expirations", {"symbol": symbol})

        if data and "expirations" in data:
            expirations = data["expirations"]
            if expirations and "date" in expirations:
                dates = expirations["date"]
                return dates if isinstance(dates, list) else [dates]

        return []

    def get_option_chain(self, symbol: str, expiration: str, greeks: bool = True) -> Optional[Dict]:
        """Get options chain with optional Greeks/IV data."""
        params = {
            "symbol": symbol,
            "expiration": expiration,
            "greeks": "true" if greeks else "false",
        }

        return self._request("/markets/options/chains", params)

    def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get current quote for a symbol."""
        data = self._request("/markets/quotes", {"symbols": symbol})

        if data and "quotes" in data and "quote" in data["quotes"]:
            return data["quotes"]["quote"]

        return None

    def calculate_avg_iv(self, chain_data: Dict) -> Optional[float]:
        """Calculate average IV from options chain data."""
        if not chain_data or "options" not in chain_data:
            return None

        options = chain_data.get("options", {}).get("option", [])
        if not options:
            return None

        if not isinstance(options, list):
            options = [options]

        ivs = []
        for opt in options:
            greeks = opt.get("greeks", {})
            if greeks:
                # mid_iv is the midpoint IV from ORATS
                iv = greeks.get("mid_iv")
                if iv and isinstance(iv, (int, float)) and iv > 0:
                    ivs.append(float(iv))

        if ivs:
            return sum(ivs) / len(ivs)

        return None

    def get_iv_for_symbol(self, symbol: str) -> Optional[float]:
        """Convenience method: get average IV for nearest expiration."""
        expirations = self.get_option_expirations(symbol)

        if not expirations:
            return None

        # Get nearest expiration
        chain = self.get_option_chain(symbol, expirations[0])

        if chain:
            return self.calculate_avg_iv(chain)

        return None


# Module-level singleton
_client: Optional[TradierClient] = None


def get_tradier_client(use_sandbox: bool = True) -> TradierClient:
    """Get or create Tradier client singleton."""
    global _client
    if _client is None:
        _client = TradierClient(use_sandbox=use_sandbox)
    return _client
```

**Acceptance Criteria:**
- [ ] Client connects to Tradier sandbox
- [ ] Fetches option expirations
- [ ] Fetches option chains with Greeks
- [ ] Calculates average IV
- [ ] Rate limiting implemented
- [ ] Error handling (returns None, doesn't raise)

---

#### TICKET-003: IV Scanner Implementation

**Priority:** P0 (Blocker)
**Agent:** Scanner Agent
**Estimated Effort:** 3 hours

**Dependencies:** TICKET-001, TICKET-002

**Description:**
Implement the High IV Scanner using Tradier data.

**Files to Create:**
- `src/catalyst_bot/scanners/iv_scanner.py`

**Code Example:**

```python
# src/catalyst_bot/scanners/iv_scanner.py
"""
High Implied Volatility Scanner

Finds stocks under $10 with the highest implied volatility.
Uses Tradier API for accurate IV data from ORATS.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import yfinance as yf

from ..data_providers.tradier_client import get_tradier_client
from ..logging_utils import get_logger
from .base_scanner import BaseScanner, ScanResult

log = get_logger("iv_scanner")

# Default universe of optionable stocks to scan
# This can be expanded or loaded from config
DEFAULT_UNIVERSE = [
    "SIRI", "SOFI", "NIO", "PLUG", "LCID", "F", "RIVN", "NKLA",
    "VALE", "BBD", "GNUS", "TELL", "MARA", "RIOT", "CLSK", "BTG",
    "GOLD", "AU", "PAAS", "SWN", "RIG", "CLOV", "WISH", "WKHS",
    "GOEV", "FFIE", "MULN", "SNDL", "TLRY", "CGC", "ACB", "HEXO",
    "DNA", "NVAX", "MRNA", "BNTX", "AMC", "GME", "BB", "NOK",
    "PLTR", "SNAP", "PINS", "HOOD", "COIN", "RBLX", "U", "DKNG",
]


class IVScanner(BaseScanner):
    """Scanner for high implied volatility stocks under $10."""

    def __init__(
        self,
        max_price: float = 10.0,
        min_iv: float = 0.60,
        min_volume: int = 500_000,
        max_results: int = 25,
        universe: List[str] = None,
    ):
        super().__init__("iv_scanner")
        self.max_price = max_price
        self.min_iv = min_iv
        self.min_volume = min_volume
        self.max_results = max_results
        self.universe = universe or DEFAULT_UNIVERSE
        self.tradier = get_tradier_client()

    def get_feature_flag(self) -> str:
        return "FEATURE_IV_SCANNER"

    def _get_stock_price_and_volume(self, symbol: str) -> tuple:
        """Get current price and volume using yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")

            if hist.empty:
                return None, None

            price = hist["Close"].iloc[-1]
            volume = hist["Volume"].iloc[-1]

            return float(price), int(volume)
        except Exception as e:
            log.debug(f"yfinance_error symbol={symbol} err={e}")
            return None, None

    def _filter_universe(self) -> List[Dict[str, Any]]:
        """Filter universe to stocks meeting price/volume criteria."""
        filtered = []

        for symbol in self.universe:
            price, volume = self._get_stock_price_and_volume(symbol)

            if price is None:
                continue

            if price > self.max_price:
                log.debug(f"skip_price symbol={symbol} price={price}")
                continue

            if volume is not None and volume < self.min_volume:
                log.debug(f"skip_volume symbol={symbol} volume={volume}")
                continue

            filtered.append({
                "symbol": symbol,
                "price": price,
                "volume": volume or 0,
            })

        log.info(f"universe_filtered total={len(self.universe)} passed={len(filtered)}")
        return filtered

    def scan(self) -> ScanResult:
        """Execute IV scan."""
        scan_time = datetime.now(timezone.utc)

        # Check if Tradier is configured
        if not self.tradier.is_configured():
            return ScanResult(
                scanner_name=self.name,
                scan_time=scan_time,
                results=[],
                error="Tradier API not configured. Set TRADIER_SANDBOX_TOKEN env var.",
            )

        # Filter universe by price/volume
        candidates = self._filter_universe()

        if not candidates:
            return ScanResult(
                scanner_name=self.name,
                scan_time=scan_time,
                results=[],
                error="No stocks passed price/volume filter",
            )

        # Get IV for each candidate
        results = []

        for stock in candidates:
            symbol = stock["symbol"]

            try:
                iv = self.tradier.get_iv_for_symbol(symbol)

                if iv is None:
                    log.debug(f"no_iv symbol={symbol}")
                    continue

                if iv < self.min_iv:
                    log.debug(f"low_iv symbol={symbol} iv={iv:.2%}")
                    continue

                results.append({
                    "symbol": symbol,
                    "price": stock["price"],
                    "volume": stock["volume"],
                    "iv": iv,
                    "iv_pct": f"{iv:.1%}",
                })

                log.info(f"high_iv_found symbol={symbol} iv={iv:.2%} price=${stock['price']:.2f}")

            except Exception as e:
                log.warning(f"iv_scan_error symbol={symbol} err={e}")
                continue

        # Sort by IV descending
        results.sort(key=lambda x: x["iv"], reverse=True)

        # Limit results
        results = results[:self.max_results]

        return ScanResult(
            scanner_name=self.name,
            scan_time=scan_time,
            results=results,
            metadata={
                "max_price": self.max_price,
                "min_iv": self.min_iv,
                "min_volume": self.min_volume,
                "universe_size": len(self.universe),
                "candidates_checked": len(candidates),
            },
        )


def run_iv_scan(
    max_price: float = None,
    min_iv: float = None,
    max_results: int = None,
) -> ScanResult:
    """Convenience function to run IV scan with optional overrides."""
    kwargs = {}

    if max_price is not None:
        kwargs["max_price"] = max_price
    if min_iv is not None:
        kwargs["min_iv"] = min_iv
    if max_results is not None:
        kwargs["max_results"] = max_results

    scanner = IVScanner(**kwargs)
    return scanner.scan()
```

**Acceptance Criteria:**
- [ ] Scans universe for high IV stocks
- [ ] Filters by price ($10 max) and volume
- [ ] Uses Tradier for accurate IV
- [ ] Returns sorted ScanResult
- [ ] Handles API failures gracefully

---

#### TICKET-004: Scanner Database Persistence

**Priority:** P1
**Agent:** Data Layer Agent
**Estimated Effort:** 2 hours

**Description:**
Implement SQLite persistence for scanner results.

**Files to Create:**
- `src/catalyst_bot/scanner_db.py`

**Code Example:**

```python
# src/catalyst_bot/scanner_db.py
"""
SQLite persistence for scanner results.

Stores scan history for:
- Historical analysis
- Trend tracking
- Cross-scanner features
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger
from .scanners.base_scanner import ScanResult

log = get_logger("scanner_db")

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "scanner_results.db"


class ScannerDatabase:
    """SQLite database for scanner results."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("SCANNER_DB_PATH", str(DEFAULT_DB_PATH))
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and tables if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scanner_name TEXT NOT NULL,
                    scan_time TEXT NOT NULL,
                    result_count INTEGER NOT NULL,
                    metadata TEXT,
                    error TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scan_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    data TEXT NOT NULL,
                    rank INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES scan_runs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_scan_runs_scanner
                    ON scan_runs(scanner_name, scan_time);

                CREATE INDEX IF NOT EXISTS idx_scan_results_symbol
                    ON scan_results(symbol, created_at);
            """)
            log.info(f"scanner_db_initialized path={self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_scan_result(self, result: ScanResult) -> int:
        """Save scan result to database. Returns run_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO scan_runs (scanner_name, scan_time, result_count, metadata, error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.scanner_name,
                    result.scan_time.isoformat(),
                    result.count,
                    json.dumps(result.metadata) if result.metadata else None,
                    result.error,
                ),
            )
            run_id = cursor.lastrowid

            # Save individual results
            for rank, item in enumerate(result.results, 1):
                conn.execute(
                    """
                    INSERT INTO scan_results (run_id, symbol, data, rank)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        item.get("symbol", "UNKNOWN"),
                        json.dumps(item),
                        rank,
                    ),
                )

            log.info(f"scan_saved run_id={run_id} scanner={result.scanner_name} count={result.count}")
            return run_id

    def get_latest_run(self, scanner_name: str) -> Optional[Dict[str, Any]]:
        """Get most recent run for a scanner."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM scan_runs
                WHERE scanner_name = ?
                ORDER BY scan_time DESC
                LIMIT 1
                """,
                (scanner_name,),
            ).fetchone()

            if row:
                return dict(row)
            return None

    def get_run_results(self, run_id: int) -> List[Dict[str, Any]]:
        """Get results for a specific run."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM scan_results
                WHERE run_id = ?
                ORDER BY rank
                """,
                (run_id,),
            ).fetchall()

            return [json.loads(row["data"]) for row in rows]

    def get_symbol_history(
        self,
        symbol: str,
        scanner_name: str = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get historical scan results for a symbol."""
        query = """
            SELECT sr.*, sc.scanner_name, sc.scan_time
            FROM scan_results sr
            JOIN scan_runs sc ON sr.run_id = sc.id
            WHERE sr.symbol = ?
            AND datetime(sc.scan_time) > datetime('now', ?)
        """
        params = [symbol, f"-{days} days"]

        if scanner_name:
            query += " AND sc.scanner_name = ?"
            params.append(scanner_name)

        query += " ORDER BY sc.scan_time DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]


# Module singleton
_db: Optional[ScannerDatabase] = None


def get_scanner_db() -> ScannerDatabase:
    """Get or create database singleton."""
    global _db
    if _db is None:
        _db = ScannerDatabase()
    return _db
```

**Acceptance Criteria:**
- [ ] Creates SQLite database on first run
- [ ] Saves scan runs with metadata
- [ ] Saves individual results with ranking
- [ ] Retrieves latest run
- [ ] Retrieves symbol history

---

#### TICKET-005: Discord Report Builder

**Priority:** P1
**Agent:** Report Builder Agent
**Estimated Effort:** 2 hours

**Dependencies:** TICKET-001

**Description:**
Build Discord embeds for scanner results.

**Files to Create:**
- `src/catalyst_bot/scanner_reports.py`

**Code Example:**

```python
# src/catalyst_bot/scanner_reports.py
"""
Discord embed builder for scanner reports.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from .logging_utils import get_logger
from .scanners.base_scanner import ScanResult

log = get_logger("scanner_reports")

# Colors for embeds
COLOR_SUCCESS = 0x2ECC71  # Green
COLOR_WARNING = 0xF39C12  # Orange
COLOR_ERROR = 0xE74C3C    # Red
COLOR_INFO = 0x3498DB     # Blue
COLOR_IV = 0x9B59B6       # Purple (for IV scanner)


def build_iv_scanner_embed(result: ScanResult) -> Dict[str, Any]:
    """Build Discord embed for IV scanner results."""
    if not result.success:
        return {
            "title": "High IV Scanner - Error",
            "description": f"Scan failed: {result.error}",
            "color": COLOR_ERROR,
            "timestamp": result.scan_time.isoformat(),
        }

    # Build results table
    lines = []
    for i, stock in enumerate(result.results[:25], 1):  # Discord limit
        symbol = stock["symbol"]
        price = stock["price"]
        iv = stock["iv"]

        # Format: "1. BCAB - $4.94 - 494.1%"
        lines.append(f"**{i}.** `{symbol}` — ${price:.2f} — **{iv:.1%}**")

    description = "\n".join(lines) if lines else "No high IV stocks found."

    # Metadata
    meta = result.metadata
    footer_text = (
        f"Scanned {meta.get('candidates_checked', 0)} stocks | "
        f"Min IV: {meta.get('min_iv', 0):.0%} | "
        f"Max Price: ${meta.get('max_price', 10):.0f}"
    )

    return {
        "title": f"High IV Stocks Under ${meta.get('max_price', 10):.0f}",
        "description": description,
        "color": COLOR_IV,
        "fields": [
            {
                "name": "Top Pick",
                "value": f"`{result.results[0]['symbol']}` with **{result.results[0]['iv']:.1%}** IV" if result.results else "N/A",
                "inline": True,
            },
            {
                "name": "Total Found",
                "value": str(result.count),
                "inline": True,
            },
        ],
        "footer": {"text": footer_text},
        "timestamp": result.scan_time.isoformat(),
    }


def build_scanner_embed(result: ScanResult) -> Dict[str, Any]:
    """Build embed based on scanner type."""
    if result.scanner_name == "iv_scanner":
        return build_iv_scanner_embed(result)

    # Generic embed for other scanners
    return {
        "title": f"{result.scanner_name.replace('_', ' ').title()} Results",
        "description": f"Found {result.count} results",
        "color": COLOR_INFO,
        "timestamp": result.scan_time.isoformat(),
    }


def post_scanner_report(
    result: ScanResult,
    webhook_url: str = None,
    also_post_to_admin: bool = True,
) -> bool:
    """Post scanner report to Discord."""
    webhook_url = webhook_url or os.getenv("DISCORD_SCANNER_WEBHOOK")
    admin_webhook = os.getenv("DISCORD_ADMIN_WEBHOOK")

    if not webhook_url and not admin_webhook:
        log.warning("no_webhook_configured")
        return False

    embed = build_scanner_embed(result)
    payload = {
        "username": "Catalyst Scanner",
        "embeds": [embed],
    }

    success = False

    # Post to scanner webhook
    if webhook_url:
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if response.status_code in (200, 204):
                log.info(f"scanner_report_posted scanner={result.scanner_name}")
                success = True
            else:
                log.warning(f"scanner_post_failed status={response.status_code}")
        except Exception as e:
            log.error(f"scanner_post_error err={e}")

    # Also post to admin
    if also_post_to_admin and admin_webhook and admin_webhook != webhook_url:
        try:
            requests.post(
                admin_webhook,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        except Exception:
            pass  # Admin is backup, don't fail on error

    return success
```

**Acceptance Criteria:**
- [ ] Builds formatted embed for IV scanner
- [ ] Respects Discord field limits
- [ ] Posts to scanner webhook
- [ ] Also posts to admin webhook
- [ ] Handles errors gracefully

---

#### TICKET-006: Scanner Scheduler

**Priority:** P0
**Agent:** Scheduler Agent
**Estimated Effort:** 2 hours

**Dependencies:** TICKET-003, TICKET-004, TICKET-005

**Description:**
Implement the scheduler that runs scanners at 10 PM CST.

**Files to Create:**
- `src/catalyst_bot/scanners/scheduler.py`

**Code Example:**

```python
# src/catalyst_bot/scanners/scheduler.py
"""
Scanner scheduler - runs scanners at configured times.

Schedule: 10 PM CST (04:00 UTC) Sunday-Thursday
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..logging_utils import get_logger
from ..scanner_db import get_scanner_db
from ..scanner_reports import post_scanner_report
from .iv_scanner import IVScanner

log = get_logger("scanner_scheduler")

# 10 PM CST = 04:00 UTC (CST is UTC-6, fixed regardless of DST)
SCANNER_UTC_HOUR = int(os.getenv("SCANNER_UTC_HOUR", "4"))
SCANNER_UTC_MINUTE = int(os.getenv("SCANNER_UTC_MINUTE", "0"))

# Run Sunday-Thursday (so reports are ready for Mon-Fri)
# weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
SCANNER_DAYS = [6, 0, 1, 2, 3]  # Sun, Mon, Tue, Wed, Thu

# State file to prevent duplicate runs
STATE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "scanner_state.json"


def _load_state() -> dict:
    """Load scheduler state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    """Save scheduler state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _get_today_key() -> str:
    """Get today's date key for state tracking."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def should_run_scanners(now: Optional[datetime] = None) -> bool:
    """Check if scanners should run now."""
    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure timezone aware
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Check day of week
    if now.weekday() not in SCANNER_DAYS:
        return False

    # Check time window (within 5 minutes of target)
    target = now.replace(
        hour=SCANNER_UTC_HOUR,
        minute=SCANNER_UTC_MINUTE,
        second=0,
        microsecond=0,
    )

    diff = abs((now - target).total_seconds())
    if diff > 300:  # 5 minute window
        return False

    # Check if already run today
    state = _load_state()
    today_key = _get_today_key()

    if state.get("last_run_date") == today_key:
        return False

    return True


def run_all_scanners(force: bool = False) -> dict:
    """Run all enabled scanners."""
    results = {}
    db = get_scanner_db()

    # IV Scanner
    iv_scanner = IVScanner()
    if iv_scanner.is_enabled() or force:
        log.info("running_iv_scanner")
        result = iv_scanner.scan()
        results["iv_scanner"] = result

        # Save to database
        db.save_scan_result(result)

        # Post to Discord
        post_scanner_report(result)

    # Mark as run
    state = _load_state()
    state["last_run_date"] = _get_today_key()
    state["last_run_time"] = datetime.now(timezone.utc).isoformat()
    state["last_results"] = {k: v.count for k, v in results.items()}
    _save_state(state)

    return results


def run_scanners_if_scheduled(now: Optional[datetime] = None) -> Optional[dict]:
    """Run scanners if it's the scheduled time."""
    if should_run_scanners(now):
        log.info("scanner_schedule_triggered")
        return run_all_scanners()
    return None


# Manual trigger for testing
def force_run_scanner(scanner_name: str = "iv_scanner") -> Optional[dict]:
    """Force run a specific scanner (for testing)."""
    log.info(f"force_run_scanner name={scanner_name}")

    if scanner_name == "iv_scanner":
        scanner = IVScanner()
        result = scanner.scan()

        # Save and post
        db = get_scanner_db()
        db.save_scan_result(result)
        post_scanner_report(result)

        return {"iv_scanner": result}

    return None
```

**Acceptance Criteria:**
- [ ] Runs at 04:00 UTC (10 PM CST)
- [ ] Only runs Sunday-Thursday
- [ ] Prevents duplicate runs same day
- [ ] Saves results to database
- [ ] Posts to Discord
- [ ] Supports force/manual trigger

---

#### TICKET-007: Runner Integration

**Priority:** P0
**Agent:** Scheduler Agent
**Estimated Effort:** 1 hour

**Dependencies:** TICKET-006

**Description:**
Add minimal hook in runner.py to call scanner scheduler.

**Files to Modify:**
- `src/catalyst_bot/runner.py` (minimal change)

**Code Example:**

```python
# Add near other scheduled task imports (around line 50)
from .scanners.scheduler import run_scanners_if_scheduled

# Add in main loop, after other scheduled tasks (around line 4000)
# Look for where run_scheduled_tasks() is called

# Add this single line:
run_scanners_if_scheduled(now)
```

**Wiring Point in runner.py:**

Find the section that looks like:
```python
# Run scheduled tasks
run_scheduled_tasks(now, logs, analyze_fn, report_fn)
```

Add after it:
```python
# Run scanner suite if scheduled
try:
    from .scanners.scheduler import run_scanners_if_scheduled
    run_scanners_if_scheduled(now)
except ImportError:
    pass  # Scanners not installed yet
```

**Acceptance Criteria:**
- [ ] Single import added to runner.py
- [ ] Single function call in main loop
- [ ] Wrapped in try/except for graceful degradation
- [ ] No changes to existing runner logic

---

#### TICKET-008: Test Command Implementation

**Priority:** P1
**Agent:** Test Agent
**Estimated Effort:** 2 hours

**Dependencies:** TICKET-006

**Description:**
Add test command to manually trigger scanner.

**Files to Create/Modify:**
- `src/catalyst_bot/commands/scanner_commands.py` (new)
- `src/catalyst_bot/commands/command_registry.py` (modify)

**Code Example:**

```python
# src/catalyst_bot/commands/scanner_commands.py
"""
Discord commands for scanner management.
"""
from __future__ import annotations

from typing import Any, Dict

from ..logging_utils import get_logger
from ..scanners.scheduler import force_run_scanner

log = get_logger("scanner_commands")


async def handle_test_scanner(
    interaction: Any,
    scanner_name: str = "iv_scanner",
) -> Dict[str, Any]:
    """Handle /test-scanner command."""
    log.info(f"test_scanner_command scanner={scanner_name}")

    # Run the scanner
    results = force_run_scanner(scanner_name)

    if results and scanner_name in results:
        result = results[scanner_name]
        return {
            "content": f"Scanner `{scanner_name}` completed!\n"
                      f"Found **{result.count}** results.\n"
                      f"Check the scanner channel for the full report.",
            "ephemeral": True,
        }
    else:
        return {
            "content": f"Scanner `{scanner_name}` not found or failed.",
            "ephemeral": True,
        }


# Command definition for registry
SCANNER_COMMANDS = [
    {
        "name": "test-scanner",
        "description": "Manually trigger a scanner for testing",
        "options": [
            {
                "name": "scanner",
                "description": "Scanner to run",
                "type": 3,  # STRING
                "required": False,
                "choices": [
                    {"name": "IV Scanner", "value": "iv_scanner"},
                    {"name": "Volume Scanner", "value": "volume_scanner"},
                    {"name": "Short Interest", "value": "short_scanner"},
                ],
            },
        ],
        "handler": handle_test_scanner,
    },
]
```

**Acceptance Criteria:**
- [ ] `/test-scanner` command works
- [ ] Can specify which scanner to run
- [ ] Returns confirmation message
- [ ] Posts full report to channel

---

#### TICKET-009: Unit Tests

**Priority:** P1
**Agent:** Test Agent
**Estimated Effort:** 3 hours

**Description:**
Write unit tests for scanner modules.

**Files to Create:**
- `tests/test_iv_scanner.py`
- `tests/test_scanner_db.py`
- `tests/test_tradier_client.py`

**Code Example:**

```python
# tests/test_iv_scanner.py
"""Tests for IV Scanner."""
import pytest
from unittest.mock import MagicMock, patch

from catalyst_bot.scanners.iv_scanner import IVScanner, run_iv_scan
from catalyst_bot.scanners.base_scanner import ScanResult


@pytest.fixture
def mock_tradier():
    """Mock Tradier client."""
    with patch("catalyst_bot.scanners.iv_scanner.get_tradier_client") as mock:
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_iv_for_symbol.return_value = 0.85  # 85% IV
        mock.return_value = client
        yield client


@pytest.fixture
def mock_yfinance():
    """Mock yfinance."""
    with patch("catalyst_bot.scanners.iv_scanner.yf") as mock:
        ticker = MagicMock()
        ticker.history.return_value = MagicMock(
            empty=False,
            __getitem__=lambda self, key: MagicMock(iloc=MagicMock(__getitem__=lambda s, i: 5.0 if key == "Close" else 1000000))
        )
        mock.Ticker.return_value = ticker
        yield mock


class TestIVScanner:
    """Test IV Scanner functionality."""

    def test_scanner_initialization(self):
        """Test scanner initializes with defaults."""
        scanner = IVScanner()
        assert scanner.name == "iv_scanner"
        assert scanner.max_price == 10.0
        assert scanner.min_iv == 0.60

    def test_feature_flag(self):
        """Test feature flag detection."""
        scanner = IVScanner()
        assert scanner.get_feature_flag() == "FEATURE_IV_SCANNER"

    def test_scan_returns_result(self, mock_tradier, mock_yfinance):
        """Test scan returns ScanResult."""
        scanner = IVScanner(universe=["TEST"])
        result = scanner.scan()

        assert isinstance(result, ScanResult)
        assert result.scanner_name == "iv_scanner"

    def test_scan_filters_by_iv(self, mock_tradier, mock_yfinance):
        """Test that low IV stocks are filtered."""
        mock_tradier.get_iv_for_symbol.return_value = 0.30  # Below threshold

        scanner = IVScanner(universe=["TEST"], min_iv=0.60)
        result = scanner.scan()

        assert result.count == 0

    def test_scan_includes_high_iv(self, mock_tradier, mock_yfinance):
        """Test that high IV stocks are included."""
        mock_tradier.get_iv_for_symbol.return_value = 0.85

        scanner = IVScanner(universe=["TEST"], min_iv=0.60)
        result = scanner.scan()

        assert result.count == 1
        assert result.results[0]["symbol"] == "TEST"
        assert result.results[0]["iv"] == 0.85

    def test_scan_handles_tradier_not_configured(self):
        """Test graceful handling when Tradier not configured."""
        with patch("catalyst_bot.scanners.iv_scanner.get_tradier_client") as mock:
            client = MagicMock()
            client.is_configured.return_value = False
            mock.return_value = client

            scanner = IVScanner()
            result = scanner.scan()

            assert not result.success
            assert "not configured" in result.error


class TestRunIVScan:
    """Test convenience function."""

    def test_run_iv_scan_with_defaults(self, mock_tradier, mock_yfinance):
        """Test run_iv_scan function."""
        result = run_iv_scan()
        assert isinstance(result, ScanResult)

    def test_run_iv_scan_with_overrides(self, mock_tradier, mock_yfinance):
        """Test run_iv_scan with custom parameters."""
        result = run_iv_scan(max_price=5.0, min_iv=0.80)
        assert isinstance(result, ScanResult)
```

**Acceptance Criteria:**
- [ ] Tests for IVScanner class
- [ ] Tests for ScannerDatabase
- [ ] Tests for TradierClient
- [ ] All external calls mocked
- [ ] Tests pass in CI

---

#### TICKET-010: Configuration & Environment

**Priority:** P1
**Agent:** Scheduler Agent
**Estimated Effort:** 1 hour

**Description:**
Document and add configuration to .env.example.

**Files to Modify:**
- `.env.example`
- `src/catalyst_bot/config.py` (add new settings)

**Environment Variables to Add:**

```ini
# =============================================================================
# SCANNER SUITE CONFIGURATION
# =============================================================================

# Feature Flags
FEATURE_IV_SCANNER=1                    # Enable IV Scanner
FEATURE_VOLUME_SCANNER=0                # Enable Volume Scanner (Phase 2)
FEATURE_SHORT_SCANNER=0                 # Enable Short Interest Scanner (Phase 2)
FEATURE_EARNINGS_SCANNER=0              # Enable Earnings Scanner (Phase 2)
FEATURE_GAP_SCANNER=0                   # Enable Gap Scanner (Phase 2)
FEATURE_FLOAT_SCANNER=0                 # Enable Float Scanner (Phase 2)

# Schedule (10 PM CST = 04:00 UTC)
SCANNER_UTC_HOUR=4
SCANNER_UTC_MINUTE=0

# Discord Webhooks
DISCORD_SCANNER_WEBHOOK=               # Primary scanner reports channel
# DISCORD_ADMIN_WEBHOOK already exists  # Backup channel

# Tradier API (sign up at developer.tradier.com)
TRADIER_SANDBOX_TOKEN=                 # Get from dash.tradier.com/settings/api

# IV Scanner Settings
IV_SCANNER_MAX_PRICE=10.0              # Maximum stock price
IV_SCANNER_MIN_IV=0.60                 # Minimum IV threshold (60%)
IV_SCANNER_MIN_VOLUME=500000           # Minimum daily volume
IV_SCANNER_MAX_RESULTS=25              # Max results to return

# Database
SCANNER_DB_PATH=data/scanner_results.db
```

**Acceptance Criteria:**
- [ ] All env vars documented in .env.example
- [ ] Config.py has new settings
- [ ] Defaults are sensible
- [ ] Comments explain each setting

---

## 4. Phase 2: Additional Scanners

After Phase 1 is stable, add these scanners following the same pattern:

### TICKET-011: Short Interest Scanner
- Data source: FINRA, Finviz
- Finds high short interest stocks
- Reports short % of float

### TICKET-012: Unusual Volume Scanner
- Data source: yfinance, Finviz
- Finds stocks with abnormal volume
- Reports relative volume (RVOL)

### TICKET-013: Earnings Preview Scanner
- Data source: Existing earnings.py
- Weekly report of upcoming earnings
- Filters for watchlist stocks

### TICKET-014: Gap Scanner
- Data source: yfinance pre-market
- Finds pre-market gap up/down
- Morning report before market open

### TICKET-015: Float Rotation Scanner
- Data source: float_data.py + volume
- Finds low float stocks with high turnover
- Reports float rotation percentage

---

## 5. Phase 3: Rich Embeds

### Future Rich Embed Ideas

**IV Scanner Enhanced Embed:**
```
┌─────────────────────────────────────────────┐
│  HIGH IV STOCKS UNDER $10                   │
│  ════════════════════════════════════════   │
│                                             │
│  📊 BCAB - BioAtla                         │
│  ├─ Price: $4.94                           │
│  ├─ IV: 494.1% (🔴 Extreme)                │
│  ├─ IV Rank: 95th percentile               │
│  └─ [Mini sparkline chart]                 │
│                                             │
│  📊 VTGN - Vistagen                        │
│  ├─ Price: $3.21                           │
│  ├─ IV: 441.5% (🔴 Extreme)                │
│  ├─ IV Rank: 92nd percentile               │
│  └─ [Mini sparkline chart]                 │
│                                             │
│  ... (top 10)                              │
│                                             │
│  ────────────────────────────────────────   │
│  📈 Sector Breakdown:                      │
│  Biotech: 45% | Cannabis: 20% | EV: 15%    │
│                                             │
│  🔗 Full List | 📊 Charts | ⚙️ Settings     │
└─────────────────────────────────────────────┘
```

**Mini Charts:**
- Use QuickChart.io API (already integrated)
- Sparkline showing 5-day IV trend
- Color coded: green (rising), red (falling)

**Interactive Buttons:**
- "Full List" - Link to web dashboard
- "Charts" - Generate detailed chart
- "Settings" - Link to config docs

---

## 6. Dependencies & Wiring

### New Dependencies (requirements.txt)

```
# Already present:
requests>=2.28.0
pandas>=1.5.0
yfinance>=0.2.0
beautifulsoup4>=4.11.0

# No new dependencies needed!
```

### Wiring Points

| File | Location | Change |
|------|----------|--------|
| `runner.py` | Line ~4000 (main loop) | Add `run_scanners_if_scheduled(now)` |
| `config.py` | Settings dataclass | Add scanner settings |
| `.env.example` | End of file | Add scanner env vars |
| `command_registry.py` | Command list | Add `/test-scanner` |

### Import Chain

```
runner.py
└── scanners/scheduler.py
    ├── scanners/iv_scanner.py
    │   ├── scanners/base_scanner.py
    │   └── data_providers/tradier_client.py
    ├── scanner_db.py
    └── scanner_reports.py
```

---

## 7. Test Commands

### Manual Testing

```bash
# Test IV Scanner directly
python -c "
from catalyst_bot.scanners.iv_scanner import run_iv_scan
result = run_iv_scan()
print(f'Found {result.count} stocks')
for r in result.results[:5]:
    print(f'  {r[\"symbol\"]}: {r[\"iv\"]:.1%}')
"

# Force run scheduler
python -c "
from catalyst_bot.scanners.scheduler import force_run_scanner
results = force_run_scanner('iv_scanner')
print(results)
"

# Test Discord posting
python -c "
from catalyst_bot.scanners.scheduler import force_run_scanner
force_run_scanner('iv_scanner')
print('Check Discord for report!')
"
```

### Discord Command

```
/test-scanner scanner:iv_scanner
```

---

## 8. Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_IV_SCANNER` | `0` | Enable IV Scanner |
| `SCANNER_UTC_HOUR` | `4` | Hour to run (UTC) |
| `SCANNER_UTC_MINUTE` | `0` | Minute to run (UTC) |
| `DISCORD_SCANNER_WEBHOOK` | - | Scanner reports webhook |
| `TRADIER_SANDBOX_TOKEN` | - | Tradier API token |
| `IV_SCANNER_MAX_PRICE` | `10.0` | Max stock price |
| `IV_SCANNER_MIN_IV` | `0.60` | Min IV threshold |
| `IV_SCANNER_MIN_VOLUME` | `500000` | Min daily volume |
| `IV_SCANNER_MAX_RESULTS` | `25` | Max results |
| `SCANNER_DB_PATH` | `data/scanner_results.db` | Database path |

---

## 9. Ticket Breakdown

### Phase 1 Tickets (MVP)

| ID | Title | Priority | Agent | Est. Hours | Dependencies |
|----|-------|----------|-------|------------|--------------|
| 001 | Base Scanner Infrastructure | P0 | Scanner | 2h | - |
| 002 | Tradier API Client | P0 | Data | 3h | - |
| 003 | IV Scanner Implementation | P0 | Scanner | 3h | 001, 002 |
| 004 | Scanner Database | P1 | Data | 2h | 001 |
| 005 | Discord Report Builder | P1 | Report | 2h | 001 |
| 006 | Scanner Scheduler | P0 | Scheduler | 2h | 003, 004, 005 |
| 007 | Runner Integration | P0 | Scheduler | 1h | 006 |
| 008 | Test Command | P1 | Test | 2h | 006 |
| 009 | Unit Tests | P1 | Test | 3h | 003, 004 |
| 010 | Configuration | P1 | Scheduler | 1h | - |

**Total Phase 1:** ~21 hours

### Phase 2 Tickets

| ID | Title | Priority | Est. Hours |
|----|-------|----------|------------|
| 011 | Short Interest Scanner | P2 | 3h |
| 012 | Unusual Volume Scanner | P2 | 3h |
| 013 | Earnings Preview Scanner | P2 | 3h |
| 014 | Gap Scanner | P2 | 3h |
| 015 | Float Rotation Scanner | P2 | 3h |

**Total Phase 2:** ~15 hours

### Phase 3 Tickets

| ID | Title | Priority | Est. Hours |
|----|-------|----------|------------|
| 016 | Rich Embeds with Mini Charts | P3 | 4h |
| 017 | Interactive Buttons | P3 | 3h |
| 018 | Cross-Scanner Analytics | P3 | 4h |
| 019 | Web Dashboard | P3 | 8h |

---

## 10. Future Rich Embed Ideas

### Mini Chart Data
- IV trend (5-day sparkline)
- Price trend (5-day)
- Volume bars
- Uses existing QuickChart.io integration

### Color Coding
- 🟢 Green: IV > 100%
- 🟡 Yellow: IV 60-100%
- 🔴 Red: IV < 60%

### Sector Breakdown
- Group results by sector
- Show % distribution
- Highlight sector trends

### Comparison Metrics
- IV vs. 30-day average
- IV percentile rank
- Historical IV chart

### Interactive Features
- Button: "📊 Full Chart" - generates detailed chart
- Button: "📋 Export CSV" - downloads results
- Select: Filter by sector
- Select: Sort by metric

---

## Appendix A: Research Reference

See `/docs/research/FREE_OPTIONS_IV_DATA_SOURCES_RESEARCH.md` for:
- Detailed data source analysis
- API comparison table
- Complete code examples
- Tradier setup instructions

---

## Appendix B: Preserving Existing Code

### Rules for Agents

1. **Never modify existing scanner.py** - Create new module
2. **Minimal runner.py changes** - Single try/except block
3. **Use existing patterns** - Follow weekly_performance.py style
4. **Feature flags** - Everything disabled by default
5. **Graceful degradation** - ImportError handling

### Code Review Checklist

- [ ] No changes to existing feed processing
- [ ] No changes to existing alerts
- [ ] No changes to existing scoring
- [ ] Feature flag controls all new code
- [ ] All external calls have timeouts
- [ ] All errors logged, not raised

---

**Document Status:** Ready for Implementation
**Next Step:** Deploy Data Layer Agent on TICKET-001 and TICKET-002
