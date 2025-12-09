# Event Sourcing Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** LOW (Deferred to Wave 4)
**Impact:** HIGH | **Effort:** HIGH | **ROI:** MEDIUM-HIGH
**Estimated Implementation Time:** 8-12 hours (phased approach)
**Target Files:** `src/catalyst_bot/events/` (new package), multiple integration points

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Implementation Strategy](#implementation-strategy)
4. [Phase A: Event Infrastructure](#phase-a-event-infrastructure)
5. [Phase B: Trading Event Capture](#phase-b-trading-event-capture)
6. [Phase C: Alert Event Capture](#phase-c-alert-event-capture)
7. [Phase D: State Reconstruction](#phase-d-state-reconstruction)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

The Catalyst-Bot currently operates with **direct state mutations** without capturing the reasoning, timing, or sequence of changes. This creates significant gaps:

| Gap | Impact |
|-----|--------|
| No pre-execution intent logged | Can't audit WHY a trade was attempted |
| Position updates overwrite state | Can't reconstruct P&L history |
| Stop-loss triggers not persisted | Can't analyze trigger accuracy |
| Order rejections not captured | Can't improve order routing |
| Alert decisions not logged | Can't audit filtering logic |

### What is Event Sourcing?

```
Traditional Approach:
┌─────────────┐    UPDATE    ┌─────────────┐
│ Position    │ ──────────── │ Position    │
│ price: $100 │              │ price: $105 │
└─────────────┘              └─────────────┘
         ↓
   Previous state LOST

Event Sourcing Approach:
┌──────────────────────────────────────────────────────────┐
│ Event Log (Immutable)                                     │
├──────────────────────────────────────────────────────────┤
│ 1. POSITION_OPENED   { price: $100, signal_id: xyz }     │
│ 2. PRICE_UPDATED     { old: $100, new: $102 }            │
│ 3. PRICE_UPDATED     { old: $102, new: $105 }            │
│ 4. STOP_LOSS_CHECKED { current: $105, trigger: $95 }     │
└──────────────────────────────────────────────────────────┘
         ↓
   Full history PRESERVED, state can be reconstructed
```

### Key Benefits

- **Audit Trail** - Complete record of every decision and state change
- **Debug Capability** - Replay events to understand what happened
- **Recovery** - Reconstruct state from event log after corruption
- **Analytics** - Rich historical data for backtesting and optimization
- **Compliance** - Required for regulated trading environments

---

## Current State Analysis

### 1. Position Management - No Event Trail

**File:** `src/catalyst_bot/portfolio/position_manager.py`

**Lines 514-578 (Position Open):**
```python
# Current: Direct INSERT without capturing decision context
cursor.execute("""
    INSERT OR REPLACE INTO positions (
        position_id, ticker, side, quantity, ...
    ) VALUES (?, ?, ?, ?, ...)
""", values)
# LOST: Why was this position opened? What signal triggered it?
```

**Lines 665-723 (Price Update):**
```python
# Current: Overwrites previous price state
cursor.execute("""
    UPDATE positions SET
        current_price = ?,
        unrealized_pnl = ?,
        market_value = ?
    WHERE position_id = ?
""", ...)
# LOST: Price history, P&L trajectory over time
```

**Lines 580-663 (Position Close):**
```python
# Current: Moves to closed_positions, deletes from positions
cursor.execute("INSERT INTO closed_positions ...")
cursor.execute("DELETE FROM positions WHERE position_id = ?", ...)
# LOST: Intermediate states, close reasoning details
```

### 2. Order Execution - Partial Event Tracking

**File:** `src/catalyst_bot/execution/order_executor.py`

**Lines 439-542 (Signal Execution):**
```python
# Current: No pre-execution event captured
async def execute_signal(self, signal: TradingSignal) -> Optional[str]:
    # Decision made but not logged
    order = self.broker.place_order(...)
    # Only success is logged, not intent or failures
```

**Lines 728-769 (Order Monitoring):**
```python
# Current: Status changes overwrite, not logged as events
cursor.execute("""
    UPDATE executed_orders SET status = ?, ...
""")
# LOST: Status transition history, timing of each change
```

### 3. Alert Processing - No Decision Trail

**File:** `src/catalyst_bot/alerts.py`

**Lines 1-300+ (Alert Flow):**
```python
# Multiple decision points without event capture:
# 1. Rate limiting check - decision not logged
# 2. Classification scoring - score not persisted with reasoning
# 3. Trade decision - why trade vs skip not captured
# 4. Execution result - partial logging only
```

### 4. Existing Event-Like Patterns

The codebase has **partial event patterns** that can be extended:

| Pattern | Location | What It Does | Gap |
|---------|----------|--------------|-----|
| `fills` table | Migration 002:136-153 | Logs individual fills | Only captures fills, not intent |
| `alert_performance` | feedback/database.py:128-180 | Tracks alert outcomes | Missing decision reasoning |
| `portfolio_snapshots` | Migration 002:178-209 | Daily snapshots | Can't reconstruct between snapshots |

---

## Implementation Strategy

### Phased Approach

```
Phase A: Event Infrastructure (Foundation)
   ↓
Phase B: Trading Events (Order + Position lifecycle)
   ↓
Phase C: Alert Events (Classification + Decision flow)
   ↓
Phase D: State Reconstruction (Replay capability)
```

### New Package Structure

```
src/catalyst_bot/
  └── events/
      ├── __init__.py
      ├── event_store.py      # SQLite event persistence
      ├── event_types.py      # Event type definitions
      ├── event_schemas.py    # Pydantic models for events
      ├── event_emitter.py    # Centralized event emission
      └── state_rebuilder.py  # Reconstruct state from events
```

### Event Categories

| Category | Events | Priority |
|----------|--------|----------|
| **Trading** | SIGNAL_GENERATED, ORDER_SUBMITTED, ORDER_FILLED, ORDER_REJECTED, ORDER_CANCELLED | P1 |
| **Position** | POSITION_OPENED, POSITION_PRICE_UPDATED, POSITION_CLOSED, STOP_LOSS_TRIGGERED | P1 |
| **Alert** | ALERT_RECEIVED, ALERT_CLASSIFIED, ALERT_DECISION_MADE, ALERT_EXECUTED | P2 |
| **Risk** | RISK_CHECK_PASSED, RISK_LIMIT_EXCEEDED, CIRCUIT_BREAKER_TRIGGERED | P2 |
| **Portfolio** | PORTFOLIO_SNAPSHOT_CREATED, DAILY_PNL_CALCULATED | P3 |

---

## Phase A: Event Infrastructure

### A.1 Event Store Database

**New Migration:** `src/catalyst_bot/migrations/004_create_event_log_tables.py`

```python
"""
Migration 004: Create event sourcing infrastructure
"""

def upgrade(cursor):
    # Main event log - append-only, never modified
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,  -- 'position', 'order', 'alert'
            aggregate_id TEXT NOT NULL,    -- The entity this event relates to
            payload TEXT NOT NULL,         -- JSON event data
            metadata TEXT,                 -- JSON: source, user, correlation_id
            created_at INTEGER NOT NULL,   -- Unix timestamp (ms precision)
            sequence_number INTEGER,       -- For ordering within aggregate

            -- Indexes for common queries
            UNIQUE(aggregate_type, aggregate_id, sequence_number)
        )
    """)

    # Index for time-based queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_log_created_at
        ON event_log(created_at)
    """)

    # Index for aggregate lookup
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_log_aggregate
        ON event_log(aggregate_type, aggregate_id)
    """)

    # Index for event type filtering
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_log_type
        ON event_log(event_type)
    """)

    # Snapshots for faster state reconstruction
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            state TEXT NOT NULL,           -- JSON: full state at snapshot time
            last_event_id TEXT NOT NULL,   -- Last event included in snapshot
            last_sequence_number INTEGER NOT NULL,
            created_at INTEGER NOT NULL,

            UNIQUE(aggregate_type, aggregate_id)
        )
    """)

def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS event_snapshots")
    cursor.execute("DROP TABLE IF EXISTS event_log")
```

### A.2 Event Type Definitions

**New File:** `src/catalyst_bot/events/event_types.py`

```python
"""
Event type constants and categories for the event sourcing system.
"""
from enum import Enum

class EventCategory(str, Enum):
    TRADING = "trading"
    POSITION = "position"
    ALERT = "alert"
    RISK = "risk"
    PORTFOLIO = "portfolio"

class TradingEventType(str, Enum):
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_EXPIRED = "ORDER_EXPIRED"

class PositionEventType(str, Enum):
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_PRICE_UPDATED = "POSITION_PRICE_UPDATED"
    POSITION_STOP_LOSS_MODIFIED = "POSITION_STOP_LOSS_MODIFIED"
    POSITION_TAKE_PROFIT_MODIFIED = "POSITION_TAKE_PROFIT_MODIFIED"
    STOP_LOSS_TRIGGERED = "STOP_LOSS_TRIGGERED"
    TAKE_PROFIT_TRIGGERED = "TAKE_PROFIT_TRIGGERED"
    POSITION_CLOSED = "POSITION_CLOSED"

class AlertEventType(str, Enum):
    ALERT_RECEIVED = "ALERT_RECEIVED"
    ALERT_RATE_LIMITED = "ALERT_RATE_LIMITED"
    ALERT_CLASSIFIED = "ALERT_CLASSIFIED"
    ALERT_SCORED = "ALERT_SCORED"
    ALERT_DECISION_MADE = "ALERT_DECISION_MADE"
    ALERT_SENT_DISCORD = "ALERT_SENT_DISCORD"
    ALERT_TRADE_EXECUTED = "ALERT_TRADE_EXECUTED"
    ALERT_SKIPPED = "ALERT_SKIPPED"

class RiskEventType(str, Enum):
    RISK_CHECK_PASSED = "RISK_CHECK_PASSED"
    RISK_CHECK_FAILED = "RISK_CHECK_FAILED"
    POSITION_LIMIT_WARNING = "POSITION_LIMIT_WARNING"
    POSITION_LIMIT_EXCEEDED = "POSITION_LIMIT_EXCEEDED"
    DAILY_LOSS_LIMIT_WARNING = "DAILY_LOSS_LIMIT_WARNING"
    DAILY_LOSS_LIMIT_EXCEEDED = "DAILY_LOSS_LIMIT_EXCEEDED"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    CIRCUIT_BREAKER_RESET = "CIRCUIT_BREAKER_RESET"
```

### A.3 Event Schemas (Pydantic Models)

**New File:** `src/catalyst_bot/events/event_schemas.py`

```python
"""
Pydantic models for event validation and serialization.
"""
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
import uuid

class EventMetadata(BaseModel):
    """Metadata attached to every event."""
    source: str  # Which component emitted the event
    correlation_id: Optional[str] = None  # Link related events
    causation_id: Optional[str] = None  # Event that caused this event
    user_id: Optional[str] = None  # If user-initiated
    version: str = "1.0"

class BaseEvent(BaseModel):
    """Base class for all events."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    aggregate_type: str
    aggregate_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: EventMetadata
    payload: Dict[str, Any]

# Trading Events
class SignalGeneratedEvent(BaseEvent):
    event_type: Literal["SIGNAL_GENERATED"] = "SIGNAL_GENERATED"
    aggregate_type: Literal["signal"] = "signal"
    # payload: signal_id, ticker, action, confidence, reasoning, timeframe, source_alert_id

class OrderSubmittedEvent(BaseEvent):
    event_type: Literal["ORDER_SUBMITTED"] = "ORDER_SUBMITTED"
    aggregate_type: Literal["order"] = "order"
    # payload: order_id, signal_id, ticker, side, quantity, order_type, limit_price, stop_price

class OrderFilledEvent(BaseEvent):
    event_type: Literal["ORDER_FILLED"] = "ORDER_FILLED"
    aggregate_type: Literal["order"] = "order"
    # payload: order_id, filled_quantity, filled_price, fill_time, slippage, liquidity

class OrderRejectedEvent(BaseEvent):
    event_type: Literal["ORDER_REJECTED"] = "ORDER_REJECTED"
    aggregate_type: Literal["order"] = "order"
    # payload: order_id, reject_reason, broker_message, rejected_at

# Position Events
class PositionOpenedEvent(BaseEvent):
    event_type: Literal["POSITION_OPENED"] = "POSITION_OPENED"
    aggregate_type: Literal["position"] = "position"
    # payload: position_id, ticker, side, quantity, entry_price, signal_id, stop_loss, take_profit

class PositionPriceUpdatedEvent(BaseEvent):
    event_type: Literal["POSITION_PRICE_UPDATED"] = "POSITION_PRICE_UPDATED"
    aggregate_type: Literal["position"] = "position"
    # payload: position_id, old_price, new_price, new_unrealized_pnl, price_source

class PositionClosedEvent(BaseEvent):
    event_type: Literal["POSITION_CLOSED"] = "POSITION_CLOSED"
    aggregate_type: Literal["position"] = "position"
    # payload: position_id, exit_reason, exit_price, realized_pnl, hold_duration_seconds

# Alert Events
class AlertClassifiedEvent(BaseEvent):
    event_type: Literal["ALERT_CLASSIFIED"] = "ALERT_CLASSIFIED"
    aggregate_type: Literal["alert"] = "alert"
    # payload: alert_id, catalyst_type, score, keywords_matched, confidence, sentiment_sources

class AlertDecisionMadeEvent(BaseEvent):
    event_type: Literal["ALERT_DECISION_MADE"] = "ALERT_DECISION_MADE"
    aggregate_type: Literal["alert"] = "alert"
    # payload: alert_id, decision (trade/skip/wait), reasoning, override_flags, signal_id
```

### A.4 Event Store Implementation

**New File:** `src/catalyst_bot/events/event_store.py`

```python
"""
SQLite-based event store for persisting and querying events.
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from .event_schemas import BaseEvent, EventMetadata

class EventStore:
    """Thread-safe event store using SQLite."""

    _instance: Optional["EventStore"] = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[Path] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: Optional[Path] = None):
        if self._initialized:
            return

        self.db_path = db_path or Path("data/events.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._initialized = True

        # Initialize schema
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    def _init_schema(self):
        """Initialize event log tables."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                metadata TEXT,
                created_at INTEGER NOT NULL,
                sequence_number INTEGER
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_log_aggregate
            ON event_log(aggregate_type, aggregate_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_log_type
            ON event_log(event_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_log_created_at
            ON event_log(created_at)
        """)

        conn.commit()

    def append(self, event: BaseEvent) -> str:
        """
        Append an event to the event log.
        Returns the event_id.
        """
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get next sequence number for this aggregate
            cursor.execute("""
                SELECT COALESCE(MAX(sequence_number), 0) + 1
                FROM event_log
                WHERE aggregate_type = ? AND aggregate_id = ?
            """, (event.aggregate_type, event.aggregate_id))

            sequence_number = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO event_log (
                    event_id, event_type, aggregate_type, aggregate_id,
                    payload, metadata, created_at, sequence_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.event_type,
                event.aggregate_type,
                event.aggregate_id,
                json.dumps(event.payload),
                json.dumps(event.metadata.model_dump()) if event.metadata else None,
                int(event.timestamp.timestamp() * 1000),
                sequence_number
            ))

            conn.commit()
            return event.event_id

    def get_events_for_aggregate(
        self,
        aggregate_type: str,
        aggregate_id: str,
        since_sequence: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all events for a specific aggregate, optionally since a sequence number."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT event_id, event_type, aggregate_type, aggregate_id,
                   payload, metadata, created_at, sequence_number
            FROM event_log
            WHERE aggregate_type = ? AND aggregate_id = ? AND sequence_number > ?
            ORDER BY sequence_number ASC
        """, (aggregate_type, aggregate_id, since_sequence))

        events = []
        for row in cursor.fetchall():
            events.append({
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "aggregate_type": row["aggregate_type"],
                "aggregate_id": row["aggregate_id"],
                "payload": json.loads(row["payload"]),
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "created_at": datetime.fromtimestamp(row["created_at"] / 1000),
                "sequence_number": row["sequence_number"]
            })

        return events

    def get_events_by_type(
        self,
        event_type: str,
        since_timestamp: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get events of a specific type."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if since_timestamp:
            cursor.execute("""
                SELECT * FROM event_log
                WHERE event_type = ? AND created_at > ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (event_type, int(since_timestamp.timestamp() * 1000), limit))
        else:
            cursor.execute("""
                SELECT * FROM event_log
                WHERE event_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (event_type, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_events_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
        event_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get all events in a time range, optionally filtered by type."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        if event_types:
            placeholders = ",".join("?" * len(event_types))
            cursor.execute(f"""
                SELECT * FROM event_log
                WHERE created_at BETWEEN ? AND ?
                AND event_type IN ({placeholders})
                ORDER BY created_at ASC
            """, (start_ms, end_ms, *event_types))
        else:
            cursor.execute("""
                SELECT * FROM event_log
                WHERE created_at BETWEEN ? AND ?
                ORDER BY created_at ASC
            """, (start_ms, end_ms))

        return [dict(row) for row in cursor.fetchall()]
```

### A.5 Event Emitter

**New File:** `src/catalyst_bot/events/event_emitter.py`

```python
"""
Centralized event emission with optional async handlers.
"""
import logging
from typing import Callable, Dict, List, Optional
from .event_store import EventStore
from .event_schemas import BaseEvent, EventMetadata

logger = logging.getLogger(__name__)

class EventEmitter:
    """
    Central hub for emitting events.
    - Persists events to EventStore
    - Notifies registered listeners (for real-time processing)
    """

    _instance: Optional["EventEmitter"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.store = EventStore()
        self._listeners: Dict[str, List[Callable]] = {}
        self._global_listeners: List[Callable] = []
        self._initialized = True

    def emit(
        self,
        event: BaseEvent,
        source: str = "unknown"
    ) -> str:
        """
        Emit an event: persist to store and notify listeners.
        Returns the event_id.
        """
        # Ensure metadata has source
        if not event.metadata:
            event.metadata = EventMetadata(source=source)
        elif not event.metadata.source:
            event.metadata.source = source

        # Persist
        event_id = self.store.append(event)

        # Log
        logger.debug(
            f"Event emitted: {event.event_type} "
            f"[{event.aggregate_type}:{event.aggregate_id}]"
        )

        # Notify type-specific listeners
        if event.event_type in self._listeners:
            for listener in self._listeners[event.event_type]:
                try:
                    listener(event)
                except Exception as e:
                    logger.error(f"Event listener error: {e}")

        # Notify global listeners
        for listener in self._global_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Global event listener error: {e}")

        return event_id

    def on(self, event_type: str, listener: Callable):
        """Register a listener for a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def on_all(self, listener: Callable):
        """Register a listener for all events."""
        self._global_listeners.append(listener)

    def off(self, event_type: str, listener: Callable):
        """Remove a listener."""
        if event_type in self._listeners:
            self._listeners[event_type].remove(listener)


# Convenience function for emitting events
def emit_event(event: BaseEvent, source: str = "unknown") -> str:
    """Emit an event through the global emitter."""
    return EventEmitter().emit(event, source)
```

---

## Phase B: Trading Event Capture

### B.1 Order Executor Integration

**File:** `src/catalyst_bot/execution/order_executor.py`

**Add imports at top:**
```python
from catalyst_bot.events.event_emitter import emit_event
from catalyst_bot.events.event_schemas import (
    OrderSubmittedEvent, OrderFilledEvent, OrderRejectedEvent, EventMetadata
)
```

**After line 542 (signal execution start):**
```python
# Emit ORDER_SUBMITTED event before placing order
emit_event(
    OrderSubmittedEvent(
        aggregate_id=order_id,
        metadata=EventMetadata(
            source="order_executor",
            correlation_id=signal.signal_id
        ),
        payload={
            "order_id": order_id,
            "signal_id": signal.signal_id,
            "ticker": signal.ticker,
            "side": signal.action,
            "quantity": quantity,
            "order_type": order_type,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "extended_hours": extended_hours
        }
    ),
    source="order_executor.execute_signal"
)
```

**After successful fill (around line 590):**
```python
# Emit ORDER_FILLED event
emit_event(
    OrderFilledEvent(
        aggregate_id=order_id,
        metadata=EventMetadata(
            source="order_executor",
            correlation_id=signal.signal_id
        ),
        payload={
            "order_id": order_id,
            "filled_quantity": filled_qty,
            "filled_price": filled_price,
            "fill_time": fill_timestamp,
            "slippage": round(filled_price - expected_price, 4),
            "liquidity": liquidity_type  # maker/taker if available
        }
    ),
    source="order_executor.execute_signal"
)
```

**In error handlers (around line 603-625):**
```python
# Emit ORDER_REJECTED event
emit_event(
    OrderRejectedEvent(
        aggregate_id=order_id,
        metadata=EventMetadata(
            source="order_executor",
            correlation_id=signal.signal_id if signal else None
        ),
        payload={
            "order_id": order_id,
            "reject_reason": rejection_category,
            "broker_message": str(error),
            "rejected_at": datetime.utcnow().isoformat()
        }
    ),
    source="order_executor.execute_signal"
)
```

### B.2 Position Manager Integration

**File:** `src/catalyst_bot/portfolio/position_manager.py`

**Add imports at top:**
```python
from catalyst_bot.events.event_emitter import emit_event
from catalyst_bot.events.event_schemas import (
    PositionOpenedEvent, PositionPriceUpdatedEvent,
    PositionClosedEvent, EventMetadata
)
```

**After line 578 (position opened successfully):**
```python
# Emit POSITION_OPENED event
emit_event(
    PositionOpenedEvent(
        aggregate_id=position_id,
        metadata=EventMetadata(
            source="position_manager",
            correlation_id=signal_id
        ),
        payload={
            "position_id": position_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "signal_id": signal_id,
            "stop_loss_price": stop_loss,
            "take_profit_price": take_profit,
            "cost_basis": cost_basis
        }
    ),
    source="position_manager.open_position"
)
```

**After line 723 (price update):**
```python
# Emit POSITION_PRICE_UPDATED event (batch for efficiency)
# Consider throttling to every N updates or significant changes only
if abs(new_price - old_price) / old_price > 0.001:  # >0.1% change
    emit_event(
        PositionPriceUpdatedEvent(
            aggregate_id=position_id,
            metadata=EventMetadata(source="position_manager"),
            payload={
                "position_id": position_id,
                "old_price": old_price,
                "new_price": new_price,
                "old_unrealized_pnl": old_pnl,
                "new_unrealized_pnl": new_pnl,
                "price_source": price_source
            }
        ),
        source="position_manager.update_position_prices"
    )
```

**After line 663 (position closed):**
```python
# Emit POSITION_CLOSED event
emit_event(
    PositionClosedEvent(
        aggregate_id=position_id,
        metadata=EventMetadata(
            source="position_manager",
            correlation_id=exit_order_id
        ),
        payload={
            "position_id": position_id,
            "ticker": ticker,
            "side": side,
            "exit_reason": exit_reason,  # stop_loss, take_profit, manual, timeout
            "exit_price": exit_price,
            "entry_price": entry_price,
            "quantity": quantity,
            "realized_pnl": realized_pnl,
            "hold_duration_seconds": hold_duration,
            "return_pct": return_pct
        }
    ),
    source="position_manager.close_position"
)
```

---

## Phase C: Alert Event Capture

### C.1 Alert Classification Events

**File:** `src/catalyst_bot/alerts.py`

**Add imports at top:**
```python
from catalyst_bot.events.event_emitter import emit_event
from catalyst_bot.events.event_schemas import (
    AlertClassifiedEvent, AlertDecisionMadeEvent, EventMetadata
)
```

**After classification scoring:**
```python
# Emit ALERT_CLASSIFIED event
emit_event(
    AlertClassifiedEvent(
        aggregate_id=alert_id,
        metadata=EventMetadata(source="alerts"),
        payload={
            "alert_id": alert_id,
            "ticker": ticker,
            "catalyst_type": catalyst_type,
            "score": score,
            "keywords_matched": keywords_matched,
            "confidence": confidence,
            "sentiment_sources": sentiment_sources,
            "classification_version": "1.0"
        }
    ),
    source="alerts.classify"
)
```

**Before trade decision:**
```python
# Emit ALERT_DECISION_MADE event
emit_event(
    AlertDecisionMadeEvent(
        aggregate_id=alert_id,
        metadata=EventMetadata(
            source="alerts",
            correlation_id=signal_id if should_trade else None
        ),
        payload={
            "alert_id": alert_id,
            "decision": "trade" if should_trade else "skip",
            "reasoning": decision_reasoning,
            "score": score,
            "min_score_threshold": min_score,
            "override_flags": override_flags,
            "signal_id": signal_id if should_trade else None
        }
    ),
    source="alerts.decision"
)
```

---

## Phase D: State Reconstruction

### D.1 State Rebuilder

**New File:** `src/catalyst_bot/events/state_rebuilder.py`

```python
"""
Reconstruct aggregate state from event history.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from .event_store import EventStore

class StateRebuilder:
    """Rebuild aggregate state by replaying events."""

    def __init__(self):
        self.store = EventStore()

    def rebuild_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        """
        Rebuild a position's current state from its events.
        """
        events = self.store.get_events_for_aggregate("position", position_id)

        if not events:
            return None

        state = {
            "position_id": position_id,
            "status": "unknown",
            "price_history": [],
            "pnl_history": []
        }

        for event in events:
            event_type = event["event_type"]
            payload = event["payload"]

            if event_type == "POSITION_OPENED":
                state.update({
                    "ticker": payload["ticker"],
                    "side": payload["side"],
                    "quantity": payload["quantity"],
                    "entry_price": payload["entry_price"],
                    "current_price": payload["entry_price"],
                    "stop_loss": payload.get("stop_loss_price"),
                    "take_profit": payload.get("take_profit_price"),
                    "status": "open",
                    "opened_at": event["created_at"]
                })

            elif event_type == "POSITION_PRICE_UPDATED":
                state["current_price"] = payload["new_price"]
                state["unrealized_pnl"] = payload["new_unrealized_pnl"]
                state["price_history"].append({
                    "price": payload["new_price"],
                    "pnl": payload["new_unrealized_pnl"],
                    "timestamp": event["created_at"]
                })

            elif event_type == "POSITION_CLOSED":
                state.update({
                    "status": "closed",
                    "exit_price": payload["exit_price"],
                    "exit_reason": payload["exit_reason"],
                    "realized_pnl": payload["realized_pnl"],
                    "hold_duration_seconds": payload["hold_duration_seconds"],
                    "closed_at": event["created_at"]
                })

        return state

    def rebuild_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Rebuild an order's state from its events.
        """
        events = self.store.get_events_for_aggregate("order", order_id)

        if not events:
            return None

        state = {
            "order_id": order_id,
            "status": "unknown",
            "fills": [],
            "status_history": []
        }

        for event in events:
            event_type = event["event_type"]
            payload = event["payload"]

            state["status_history"].append({
                "status": event_type,
                "timestamp": event["created_at"]
            })

            if event_type == "ORDER_SUBMITTED":
                state.update({
                    "ticker": payload["ticker"],
                    "side": payload["side"],
                    "quantity": payload["quantity"],
                    "order_type": payload["order_type"],
                    "limit_price": payload.get("limit_price"),
                    "status": "submitted",
                    "submitted_at": event["created_at"]
                })

            elif event_type == "ORDER_FILLED":
                state["status"] = "filled"
                state["filled_price"] = payload["filled_price"]
                state["filled_quantity"] = payload["filled_quantity"]
                state["slippage"] = payload.get("slippage", 0)
                state["filled_at"] = event["created_at"]
                state["fills"].append(payload)

            elif event_type == "ORDER_REJECTED":
                state["status"] = "rejected"
                state["reject_reason"] = payload["reject_reason"]
                state["rejected_at"] = event["created_at"]

            elif event_type == "ORDER_CANCELLED":
                state["status"] = "cancelled"
                state["cancelled_at"] = event["created_at"]

        return state

    def get_position_pnl_timeline(
        self,
        position_id: str
    ) -> list[Dict[str, Any]]:
        """Get P&L timeline for a position."""
        events = self.store.get_events_for_aggregate("position", position_id)

        timeline = []
        for event in events:
            if event["event_type"] == "POSITION_PRICE_UPDATED":
                timeline.append({
                    "timestamp": event["created_at"],
                    "price": event["payload"]["new_price"],
                    "unrealized_pnl": event["payload"]["new_unrealized_pnl"]
                })

        return timeline
```

---

## Coding Tickets

### Ticket ES-001: Create Event Infrastructure
**Priority:** P0 (Foundation)
**Effort:** 2-3 hours

- [ ] Create `src/catalyst_bot/events/` package
- [ ] Implement `event_types.py` with all event type enums
- [ ] Implement `event_schemas.py` with Pydantic models
- [ ] Implement `event_store.py` with SQLite persistence
- [ ] Implement `event_emitter.py` with listener support
- [ ] Create migration `004_create_event_log_tables.py`
- [ ] Add unit tests for EventStore CRUD operations

### Ticket ES-002: Trading Event Integration
**Priority:** P1
**Effort:** 2-3 hours
**Depends on:** ES-001

- [ ] Add ORDER_SUBMITTED event in `order_executor.py:542`
- [ ] Add ORDER_FILLED event in `order_executor.py:590`
- [ ] Add ORDER_REJECTED event in `order_executor.py:603-625`
- [ ] Add ORDER_CANCELLED event in monitoring loop
- [ ] Test order lifecycle events with mock broker

### Ticket ES-003: Position Event Integration
**Priority:** P1
**Effort:** 2-3 hours
**Depends on:** ES-001

- [ ] Add POSITION_OPENED event in `position_manager.py:578`
- [ ] Add POSITION_PRICE_UPDATED event in `position_manager.py:723`
- [ ] Add POSITION_CLOSED event in `position_manager.py:663`
- [ ] Add STOP_LOSS_TRIGGERED event in `position_manager.py:770`
- [ ] Add throttling for price update events (>0.1% change)
- [ ] Test position lifecycle events

### Ticket ES-004: Alert Event Integration
**Priority:** P2
**Effort:** 1-2 hours
**Depends on:** ES-001

- [ ] Add ALERT_CLASSIFIED event after scoring
- [ ] Add ALERT_DECISION_MADE event before trade
- [ ] Add ALERT_SKIPPED event when filtered
- [ ] Test alert flow events

### Ticket ES-005: State Reconstruction
**Priority:** P2
**Effort:** 2 hours
**Depends on:** ES-002, ES-003

- [ ] Implement `state_rebuilder.py`
- [ ] Add `rebuild_position()` method
- [ ] Add `rebuild_order()` method
- [ ] Add `get_position_pnl_timeline()` for analytics
- [ ] Test state reconstruction accuracy

### Ticket ES-006: Event Analytics Dashboard
**Priority:** P3
**Effort:** 2-3 hours
**Depends on:** ES-001 to ES-005

- [ ] Add event count metrics to health endpoint
- [ ] Create event query CLI commands
- [ ] Add event replay debugging tools
- [ ] Document event schema for external consumers

---

## Testing & Verification

### Unit Tests

```python
# tests/events/test_event_store.py
import pytest
from datetime import datetime
from catalyst_bot.events.event_store import EventStore
from catalyst_bot.events.event_schemas import PositionOpenedEvent, EventMetadata

def test_event_append_and_retrieve():
    store = EventStore(db_path=":memory:")

    event = PositionOpenedEvent(
        aggregate_id="pos_123",
        metadata=EventMetadata(source="test"),
        payload={
            "position_id": "pos_123",
            "ticker": "AAPL",
            "side": "long",
            "quantity": 100,
            "entry_price": 150.00
        }
    )

    event_id = store.append(event)

    events = store.get_events_for_aggregate("position", "pos_123")
    assert len(events) == 1
    assert events[0]["payload"]["ticker"] == "AAPL"
    assert events[0]["sequence_number"] == 1

def test_event_sequence_ordering():
    store = EventStore(db_path=":memory:")

    # Append multiple events for same aggregate
    for i in range(5):
        event = PositionPriceUpdatedEvent(
            aggregate_id="pos_123",
            metadata=EventMetadata(source="test"),
            payload={"new_price": 150.0 + i}
        )
        store.append(event)

    events = store.get_events_for_aggregate("position", "pos_123")
    assert len(events) == 5
    assert events[0]["sequence_number"] == 1
    assert events[4]["sequence_number"] == 5
```

### Integration Tests

```python
# tests/events/test_trading_events.py
import pytest
from unittest.mock import patch, MagicMock
from catalyst_bot.execution.order_executor import OrderExecutor
from catalyst_bot.events.event_store import EventStore

@pytest.fixture
def event_store():
    return EventStore(db_path=":memory:")

def test_order_execution_emits_events(event_store):
    """Verify order execution emits ORDER_SUBMITTED and ORDER_FILLED events."""
    executor = OrderExecutor(broker=MagicMock())

    # Execute a signal
    signal = MagicMock(
        signal_id="sig_123",
        ticker="AAPL",
        action="buy",
        quantity=100
    )

    with patch("catalyst_bot.events.event_emitter.EventStore", return_value=event_store):
        executor.execute_signal(signal)

    events = event_store.get_events_by_type("ORDER_SUBMITTED")
    assert len(events) >= 1
    assert events[0]["payload"]["ticker"] == "AAPL"
```

### Verification Checklist

- [ ] Events are immutable (no UPDATE on event_log table)
- [ ] Sequence numbers increment correctly per aggregate
- [ ] State can be fully reconstructed from events
- [ ] Event emission doesn't block main execution path
- [ ] Events are queryable by type, aggregate, and time range
- [ ] Price update events are throttled appropriately
- [ ] Correlation IDs link related events across aggregates

---

## Appendix: Event Flow Diagrams

### Order Lifecycle Events

```
Signal Generated
      │
      ▼
┌─────────────────────────────────────────────┐
│ ORDER_SUBMITTED                              │
│ {order_id, ticker, side, qty, limit_price}  │
└─────────────────────────────────────────────┘
      │
      ├──────────────────────────────┐
      ▼                              ▼
┌─────────────────┐         ┌─────────────────┐
│ ORDER_FILLED    │         │ ORDER_REJECTED  │
│ {filled_price,  │         │ {reject_reason, │
│  slippage}      │         │  broker_msg}    │
└─────────────────┘         └─────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│ POSITION_OPENED                              │
│ {position_id, entry_price, stop_loss, ...}  │
└─────────────────────────────────────────────┘
```

### Position Lifecycle Events

```
POSITION_OPENED
      │
      ▼
┌─────────────────────────────────────────────┐
│ POSITION_PRICE_UPDATED (repeated)           │
│ {old_price, new_price, unrealized_pnl}      │
└─────────────────────────────────────────────┘
      │
      ├──────────────────────┬──────────────────────┐
      ▼                      ▼                      ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ STOP_LOSS_     │  │ TAKE_PROFIT_   │  │ POSITION_      │
│ TRIGGERED      │  │ TRIGGERED      │  │ CLOSED         │
│ {trigger_price}│  │ {trigger_price}│  │ {exit_reason:  │
└────────────────┘  └────────────────┘  │  manual}       │
      │                   │              └────────────────┘
      └─────────┬─────────┘                      │
                ▼                                │
┌─────────────────────────────────────────────┐ │
│ POSITION_CLOSED                              │◄┘
│ {realized_pnl, hold_duration, return_pct}   │
└─────────────────────────────────────────────┘
```

---

## Dependencies

| Dependency | Purpose | Required |
|------------|---------|----------|
| `pydantic>=2.0` | Event schema validation | Yes |
| None additional | Uses existing SQLite | - |

## Notes

- **Wave 4 Priority**: This is marked as "future/defer" because it requires significant refactoring and the immediate ROI is lower than Waves 1-3
- **Incremental Adoption**: Start with ORDER and POSITION events (Phase B), then expand
- **Performance**: Event emission should be async/non-blocking in production
- **Storage Growth**: Event log grows indefinitely; plan for archival strategy
- **Replay Safety**: Ensure event handlers are idempotent for safe replay
