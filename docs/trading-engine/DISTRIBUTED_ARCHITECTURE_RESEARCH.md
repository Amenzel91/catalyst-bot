# Distributed Trading System Architecture Research

**Date:** December 12, 2025
**Purpose:** Architecture research for deploying Catalyst-Bot as a distributed WebSocket/API service
**Use Case:** Central signal server with local execution clients for multiple users

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Event-Driven Architecture](#event-driven-architecture)
3. [API & WebSocket Design](#api--websocket-design)
4. [Distributed System Patterns](#distributed-system-patterns)
5. [Data Pipeline Architecture](#data-pipeline-architecture)
6. [Deployment Options](#deployment-options)
7. [Reliability Patterns](#reliability-patterns)
8. [Configuration Management](#configuration-management)
9. [Recommended Architecture](#recommended-architecture)
10. [Implementation Roadmap](#implementation-roadmap)
11. [Technology Stack Recommendations](#technology-stack-recommendations)
12. [Security Considerations](#security-considerations)

---

## Executive Summary

### Current State
Catalyst-Bot is an event-driven trading system that:
- Monitors SEC filings, press releases, and news feeds in real-time
- Uses LLM-based classification to identify high-probability catalysts
- Provides comprehensive backtesting and analysis
- Already uses async patterns (asyncio, aiohttp) for HTTP operations
- Has existing EventLoopManager for bridging sync/async code

### Target State
A distributed architecture where:
- **Central Signal Server**: Runs Catalyst-Bot classification pipeline, generates trading signals
- **WebSocket API**: Pushes real-time signals to authenticated clients
- **Local Execution Clients**: Friends run local instances connected to their portfolios
- **Configuration**: User-specific risk parameters, position sizing, portfolio settings
- **Reliability**: Circuit breakers, retry logic, graceful degradation

### Key Findings
1. **Event Sourcing** is critical for financial systems - provides complete audit trail
2. **Sequenced Stream Architecture** enables perfect state synchronization across nodes
3. **Hybrid Redis + InfluxDB** approach achieves sub-millisecond latency for hot path
4. **WebSocket rate limiting** is essential (750 connections/sec, 8 msg/sec per client)
5. **Docker + AWS ECS** offers best balance of scalability and cost optimization
6. **Circuit breaker + retry patterns** are mandatory for distributed system resilience

---

## Event-Driven Architecture

### Core Concepts

#### Event Sourcing Pattern
Event sourcing stores all state changes as an immutable sequence of events rather than updating database records.

**Benefits for Trading Systems:**
- **Audit Trail**: Every decision tracked for compliance and debugging
- **Time Travel**: Reconstruct system state at any point in time
- **Backtesting**: Replay events to validate strategy changes
- **Debugging**: Understand exactly what happened and when

**Key Insight from Research:**
> "Event Sourcing is a pattern where state changes are stored as an immutable sequence of events. For financial systems, this provides complete audit trail for reconstructing account balances and tracking every change for compliance." - Confluent

**Implementation for Catalyst-Bot:**
```python
# Event types
class SignalGenerated(Event):
    timestamp: datetime
    ticker: str
    signal_type: str  # "BUY" | "SELL" | "WATCH"
    confidence: float
    catalyst_type: str
    source: str
    metadata: dict

class SignalDelivered(Event):
    timestamp: datetime
    signal_id: str
    client_id: str
    delivery_method: str  # "websocket" | "rest"
    acknowledged: bool

class TradeExecuted(Event):
    timestamp: datetime
    signal_id: str
    client_id: str
    ticker: str
    action: str
    quantity: int
    price: float
    portfolio_id: str
```

**Storage:**
```
data/events/
├── signals/
│   ├── 2025-12-12.jsonl      # Append-only event log
│   └── 2025-12-13.jsonl
├── deliveries/
│   └── 2025-12-12.jsonl
└── trades/
    └── 2025-12-12.jsonl
```

#### Message Queue Architecture

**Industry Best Practices:**
> "It's common to use Kafka or RabbitMQ to feed real-time data into the pipeline and to separate the data ingestion service from the strategy engine for scalability." - Edwin Salguero, Medium

**Message Queue Comparison:**

| Feature | Redis Pub/Sub | RabbitMQ | Apache Kafka | ZeroMQ |
|---------|--------------|----------|--------------|--------|
| **Latency** | Sub-ms | 1-5ms | 2-10ms | Sub-ms |
| **Persistence** | Optional (Streams) | Yes | Yes | No |
| **Ordering** | Per-channel | Per-queue | Per-partition | No |
| **Scalability** | Good | Good | Excellent | Good |
| **Complexity** | Low | Medium | High | Low |
| **Best For** | Real-time signals | Task queues | Event streaming | Inter-process |

**Recommendation for Catalyst-Bot:**
- **Phase 1**: Redis Pub/Sub (already using Redis for caching)
- **Phase 2**: Redis Streams (persistent pub/sub with consumer groups)
- **Phase 3**: Kafka (if scaling beyond 1000+ users)

#### Sequenced Stream Architecture

**Critical Pattern from Research:**
> "Every input into the system is assigned a globally unique monotonic sequence number and timestamp by a central component known as a sequencer. This sequenced stream of events is disseminated to nodes, which only operate on these sequenced inputs. Every node receives an identical stream in identical order." - ACM Queue

**Benefits:**
- Perfect state synchronization across unlimited clients
- No reconciliation needed
- Deterministic replay for debugging
- Natural audit trail

**Implementation:**
```python
class SignalSequencer:
    """Central sequencer for signal generation."""

    def __init__(self):
        self._sequence = 0
        self._lock = threading.Lock()

    def sequence_signal(self, signal: dict) -> dict:
        """Assign monotonic sequence number to signal."""
        with self._lock:
            self._sequence += 1
            signal['sequence_id'] = self._sequence
            signal['sequenced_at'] = datetime.now(timezone.utc).isoformat()
            return signal
```

### Async Python Patterns

#### Current Implementation
Catalyst-Bot already uses:
- `asyncio` event loop via EventLoopManager
- `aiohttp` for async HTTP (7x speedup vs requests)
- `discord.py` for async Discord integration

#### Event-Driven Trading Patterns

**From AAT (Async Algo Trading) Framework:**
> "Methods of the form `onNoun` are used to handle market data events, while methods of the form `onVerb` are used to handle order entry events. Everything is event-driven." - AsyncAlgoTrading/aat

**From Alpaca Scalping Example:**
> "Since it is important to take action as quickly as the signal triggers, we subscribe to real-time bar updates from Polygon websockets and order event websockets. Everything is event-driven. All events are dispatched to event handlers in Python's asyncio loop." - Alpaca Markets

**Pattern for Catalyst-Bot:**
```python
class SignalEngine:
    """Event-driven signal generation engine."""

    async def on_feed_item(self, item: FeedItem) -> None:
        """Handle incoming feed item."""
        # Classify
        signal = await self._classify(item)

        # Sequence
        signal = self.sequencer.sequence_signal(signal)

        # Store event
        await self._store_event(SignalGenerated(**signal))

        # Publish to subscribers
        await self.publisher.publish_signal(signal)

    async def on_client_subscribe(self, client_id: str, filters: dict) -> None:
        """Handle client subscription."""
        # Store subscription
        await self._store_subscription(client_id, filters)

        # Start streaming matching signals
        async for signal in self._signal_stream():
            if self._matches_filters(signal, filters):
                await self._send_to_client(client_id, signal)
```

---

## API & WebSocket Design

### WebSocket Best Practices

#### Authentication
**Industry Standard from Research:**
> "You need to authenticate using your credentials via headers or session authentication. Only one API key can be authenticated per WebSocket connection." - Binance

**Implementation:**
```python
import secrets
import hashlib
from datetime import datetime, timedelta

class WebSocketAuthenticator:
    """JWT-based WebSocket authentication."""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.active_tokens = {}  # token -> client_id

    def generate_token(self, client_id: str, expiry_hours: int = 24) -> str:
        """Generate JWT token for client."""
        payload = {
            'client_id': client_id,
            'issued_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(hours=expiry_hours)).isoformat()
        }
        # Use proper JWT library (PyJWT) in production
        token = secrets.token_urlsafe(32)
        self.active_tokens[token] = client_id
        return token

    async def authenticate_websocket(self, websocket, token: str) -> Optional[str]:
        """Authenticate WebSocket connection."""
        client_id = self.active_tokens.get(token)
        if not client_id:
            await websocket.send_json({'error': 'Invalid token'})
            await websocket.close(code=4001, reason='Unauthorized')
            return None
        return client_id
```

#### Rate Limiting
**Industry Standards from Research:**
- **Coinbase**: 750 connections/sec per IP, 8 messages/sec per IP
- **Binance**: 300 connection attempts per 5 min per IP, 5 messages/sec

**Implementation:**
```python
from collections import defaultdict
from datetime import datetime, timedelta

class WebSocketRateLimiter:
    """Rate limiter for WebSocket connections."""

    def __init__(self):
        # Track connections per IP
        self.connections_per_ip = defaultdict(list)
        # Track messages per client
        self.messages_per_client = defaultdict(list)

    def check_connection_limit(self, ip: str, limit: int = 300,
                              window_sec: int = 300) -> bool:
        """Check if IP can create new connection (300/5min)."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_sec)

        # Remove old connections
        self.connections_per_ip[ip] = [
            ts for ts in self.connections_per_ip[ip] if ts > cutoff
        ]

        # Check limit
        if len(self.connections_per_ip[ip]) >= limit:
            return False

        # Record connection
        self.connections_per_ip[ip].append(now)
        return True

    def check_message_limit(self, client_id: str, limit: int = 8,
                           window_sec: int = 1) -> bool:
        """Check if client can send message (8/sec)."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_sec)

        # Remove old messages
        self.messages_per_client[client_id] = [
            ts for ts in self.messages_per_client[client_id] if ts > cutoff
        ]

        # Check limit
        if len(self.messages_per_client[client_id]) >= limit:
            return False

        # Record message
        self.messages_per_client[client_id].append(now)
        return True
```

#### Connection Management
**Ping/Pong Protocol from Research:**
> "The server sends a Ping frame every three minutes to confirm the connection. Users must respond with a Pong frame containing the same payload. Failure to respond within 10 minutes results in connection termination." - Binance

**Implementation:**
```python
import asyncio
from typing import Dict
import websockets

class WebSocketConnectionManager:
    """Manages WebSocket connections with health monitoring."""

    def __init__(self):
        self.connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.last_pong: Dict[str, datetime] = {}

    async def handle_connection(self, websocket, path: str):
        """Handle new WebSocket connection."""
        # Authenticate
        token = await self._receive_auth(websocket)
        client_id = await self.authenticator.authenticate_websocket(websocket, token)
        if not client_id:
            return

        # Register connection
        self.connections[client_id] = websocket
        self.last_pong[client_id] = datetime.utcnow()

        try:
            # Start ping task
            ping_task = asyncio.create_task(self._ping_loop(client_id, websocket))

            # Handle messages
            async for message in websocket:
                await self._handle_message(client_id, message)

        finally:
            # Cleanup
            ping_task.cancel()
            del self.connections[client_id]
            del self.last_pong[client_id]

    async def _ping_loop(self, client_id: str, websocket):
        """Send ping every 3 minutes, disconnect if no pong after 10 min."""
        while True:
            await asyncio.sleep(180)  # 3 minutes

            # Send ping
            await websocket.ping()

            # Check last pong
            if (datetime.utcnow() - self.last_pong[client_id]).seconds > 600:
                # No pong for 10 minutes - disconnect
                await websocket.close(code=4000, reason='No pong received')
                break

    async def broadcast_signal(self, signal: dict):
        """Broadcast signal to all connected clients."""
        disconnected = []

        for client_id, ws in self.connections.items():
            try:
                await ws.send_json(signal)
            except websockets.ConnectionClosed:
                disconnected.append(client_id)

        # Cleanup disconnected clients
        for client_id in disconnected:
            del self.connections[client_id]
```

### REST API Design

#### Signal API Endpoints
```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI(title="Catalyst Signal API", version="1.0.0")
security = HTTPBearer()

# GET /api/v1/signals - List recent signals
@app.get("/api/v1/signals")
async def get_signals(
    limit: int = 50,
    since: Optional[str] = None,
    ticker: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recent trading signals."""
    client_id = await authenticate(credentials.credentials)

    signals = await signal_store.get_signals(
        client_id=client_id,
        limit=limit,
        since=since,
        ticker=ticker
    )

    return {
        'signals': signals,
        'count': len(signals),
        'next': None  # pagination cursor
    }

# GET /api/v1/signals/{signal_id} - Get specific signal
@app.get("/api/v1/signals/{signal_id}")
async def get_signal(
    signal_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get specific signal by ID."""
    client_id = await authenticate(credentials.credentials)

    signal = await signal_store.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    return signal

# POST /api/v1/subscriptions - Update subscription filters
@app.post("/api/v1/subscriptions")
async def update_subscription(
    filters: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update client subscription filters."""
    client_id = await authenticate(credentials.credentials)

    await subscription_manager.update_filters(client_id, filters)

    return {'status': 'updated', 'filters': filters}

# POST /api/v1/feedback - Submit trade outcome
@app.post("/api/v1/feedback")
async def submit_feedback(
    feedback: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Submit trade execution outcome for signal improvement."""
    client_id = await authenticate(credentials.credentials)

    await feedback_processor.process(client_id, feedback)

    return {'status': 'received'}
```

#### API Versioning
```python
# Version in URL path
/api/v1/signals
/api/v2/signals

# Or version in headers
@app.get("/api/signals")
async def get_signals(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    api_version = request.headers.get('X-API-Version', 'v1')

    if api_version == 'v1':
        return await get_signals_v1(...)
    elif api_version == 'v2':
        return await get_signals_v2(...)
    else:
        raise HTTPException(400, "Unsupported API version")
```

---

## Distributed System Patterns

### Central Signal Server + Local Execution Clients

#### Architecture Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                    CENTRAL SIGNAL SERVER                     │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Feed         │      │ Classification│                    │
│  │ Aggregator   │─────▶│ Pipeline      │                    │
│  │              │      │ (LLM + Score) │                    │
│  └──────────────┘      └───────┬──────┘                    │
│                                 │                            │
│                        ┌────────▼─────────┐                 │
│                        │ Signal Sequencer │                 │
│                        │ (Monotonic IDs)  │                 │
│                        └────────┬─────────┘                 │
│                                 │                            │
│                    ┌────────────▼──────────────┐            │
│                    │ Event Store (PostgreSQL)  │            │
│                    │ - signals (append-only)   │            │
│                    │ - deliveries              │            │
│                    │ - subscriptions           │            │
│                    └────────────┬──────────────┘            │
│                                 │                            │
│                    ┌────────────▼──────────────┐            │
│                    │ Redis Pub/Sub             │            │
│                    │ - signal broadcast        │            │
│                    │ - client subscriptions    │            │
│                    └────────────┬──────────────┘            │
│                                 │                            │
│                    ┌────────────▼──────────────┐            │
│                    │ WebSocket Server          │            │
│                    │ - authentication          │            │
│                    │ - rate limiting           │            │
│                    │ - connection management   │            │
│                    └───────────────────────────┘            │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket
                ┌──────────────┼──────────────┐
                │              │              │
        ┌───────▼──────┐ ┌────▼──────┐ ┌────▼──────┐
        │ LOCAL CLIENT │ │LOCAL CLIENT│ │LOCAL CLIENT│
        │              │ │            │ │            │
        │ ┌──────────┐ │ │┌──────────┐│ │┌──────────┐│
        │ │ Signal   │ │ ││ Signal   ││ ││ Signal   ││
        │ │ Receiver │ │ ││ Receiver ││ ││ Receiver ││
        │ └────┬─────┘ │ │└────┬─────┘│ │└────┬─────┘│
        │      │       │ │     │      │ │     │      │
        │ ┌────▼─────┐ │ │┌────▼─────┐│ │┌────▼─────┐│
        │ │ Risk     │ │ ││ Risk     ││ ││ Risk     ││
        │ │ Manager  │ │ ││ Manager  ││ ││ Manager  ││
        │ └────┬─────┘ │ │└────┬─────┘│ │└────┬─────┘│
        │      │       │ │     │      │ │     │      │
        │ ┌────▼─────┐ │ │┌────▼─────┐│ │┌────▼─────┐│
        │ │ Execution│ │ ││Execution ││ ││Execution ││
        │ │ Engine   │ │ ││Engine    ││ ││Engine    ││
        │ │ (Alpaca) │ │ ││(Alpaca)  ││ ││(Alpaca)  ││
        │ └────┬─────┘ │ │└────┬─────┘│ │└────┬─────┘│
        │      │       │ │     │      │ │     │      │
        │ ┌────▼─────┐ │ │┌────▼─────┐│ │┌────▼─────┐│
        │ │ Feedback │ │ ││ Feedback ││ ││ Feedback ││
        │ │ Reporter │ │ ││ Reporter ││ ││ Reporter ││
        │ └──────────┘ │ │└──────────┘│ │└──────────┘│
        │  Friend #1   │ │ Friend #2  │ │ Friend #3  │
        └──────────────┘ └────────────┘ └────────────┘
```

#### State Synchronization

**Pattern from Research:**
> "If nodes are written to be completely deterministic and not rely on external inputs, it is possible to achieve perfect synchronization (consensus) among unlimited number of nodes. The different applications are never out of sync and never need reconciliation." - ACM Queue

**Implementation:**
```python
class StateSync:
    """Synchronize client state with server via event replay."""

    async def sync_client(self, client_id: str, last_sequence: int) -> List[dict]:
        """Get all events since client's last sequence number."""
        events = await self.event_store.get_events_since(last_sequence)
        return events

    async def replay_events(self, events: List[dict]) -> None:
        """Replay events to rebuild state."""
        for event in events:
            if event['type'] == 'SignalGenerated':
                await self._process_signal(event)
            elif event['type'] == 'SubscriptionUpdated':
                await self._update_subscription(event)
```

#### Heartbeat & Health Monitoring

**Implementation:**
```python
class HealthMonitor:
    """Monitor health of distributed system components."""

    def __init__(self):
        self.component_status = {}
        self.last_heartbeat = {}

    async def heartbeat_loop(self):
        """Send heartbeats from server."""
        while True:
            await asyncio.sleep(30)  # Every 30 seconds

            status = {
                'timestamp': datetime.utcnow().isoformat(),
                'server_status': 'healthy',
                'components': {
                    'feed_aggregator': await self._check_feed_aggregator(),
                    'classifier': await self._check_classifier(),
                    'event_store': await self._check_event_store(),
                    'redis': await self._check_redis(),
                }
            }

            await self.broadcast_heartbeat(status)

    async def check_client_health(self, client_id: str) -> dict:
        """Check if client is healthy based on last heartbeat."""
        last = self.last_heartbeat.get(client_id)

        if not last:
            return {'status': 'unknown', 'message': 'No heartbeat received'}

        age = (datetime.utcnow() - last).seconds

        if age > 120:  # 2 minutes
            return {'status': 'unhealthy', 'message': f'Last heartbeat {age}s ago'}
        elif age > 60:  # 1 minute
            return {'status': 'warning', 'message': f'Last heartbeat {age}s ago'}
        else:
            return {'status': 'healthy', 'message': f'Last heartbeat {age}s ago'}
```

---

## Data Pipeline Architecture

### Real-Time Data Ingestion

**Current Catalyst-Bot Flow:**
```
RSS Feeds → Feed Aggregator → Deduplication → Classification → Alert
```

**Distributed Flow:**
```
RSS Feeds → Feed Aggregator → Redis Stream → Classification Workers →
Signal Sequencer → Event Store → Redis Pub/Sub → WebSocket Clients
```

#### Redis Streams for Data Pipeline

**From Research:**
> "A hybrid approach leveraging Redis and InfluxDB uses: WebSocket Server → Tick Consumer → Redis Stream (Primary) → Bar Aggregator, with Redis handling the hot path (real-time trading) and InfluxDB handling the cold path (historical analysis)." - Medium

**Implementation:**
```python
import redis.asyncio as redis
from typing import AsyncIterator

class RedisStreamPipeline:
    """Real-time data pipeline using Redis Streams."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.feed_stream = "catalyst:feeds"
        self.signal_stream = "catalyst:signals"

    async def publish_feed_item(self, item: dict) -> str:
        """Publish feed item to stream."""
        item_id = await self.redis.xadd(
            self.feed_stream,
            {'data': json.dumps(item)},
            maxlen=10000  # Keep last 10k items
        )
        return item_id

    async def consume_feed_items(self, consumer_group: str,
                                 consumer_name: str) -> AsyncIterator[dict]:
        """Consume feed items from stream."""
        # Create consumer group if not exists
        try:
            await self.redis.xgroup_create(
                self.feed_stream,
                consumer_group,
                id='0',
                mkstream=True
            )
        except redis.ResponseError:
            pass  # Group already exists

        while True:
            # Read from stream
            items = await self.redis.xreadgroup(
                consumer_group,
                consumer_name,
                {self.feed_stream: '>'},
                count=10,
                block=1000  # 1 second timeout
            )

            for stream, messages in items:
                for message_id, data in messages:
                    item = json.loads(data[b'data'])
                    yield item

                    # Acknowledge message
                    await self.redis.xack(self.feed_stream, consumer_group, message_id)
```

### Time-Series Database Options

#### Redis Time Series
**From Research:**
> "Stock trading requires millisecond response times. It's necessary to keep a lot of data points within a very short period of time. Redis Time Series can handle millions of operations per second with sub-millisecond latency (P50=2.1ms, P95=2.8ms)." - Redis

**Use Case for Catalyst-Bot:**
- Real-time signal metrics
- Client connection metrics
- Feed ingestion rate tracking

**Implementation:**
```python
import redis
from redis.commands.timeseries import TimeSeries

class MetricsCollector:
    """Collect real-time metrics using Redis Time Series."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.ts = self.redis.ts()

    async def record_signal_generated(self, ticker: str, confidence: float):
        """Record signal generation event."""
        # Create time series if not exists
        try:
            self.ts.create(
                f"signals:{ticker}:count",
                retention_msecs=86400000,  # 24 hours
                labels={'metric': 'signal_count', 'ticker': ticker}
            )
            self.ts.create(
                f"signals:{ticker}:confidence",
                retention_msecs=86400000,
                labels={'metric': 'confidence', 'ticker': ticker}
            )
        except redis.ResponseError:
            pass

        # Record data points
        timestamp = int(time.time() * 1000)
        self.ts.add(f"signals:{ticker}:count", timestamp, 1)
        self.ts.add(f"signals:{ticker}:confidence", timestamp, confidence)

    async def get_signal_rate(self, ticker: str, window_sec: int = 3600) -> float:
        """Get signal generation rate for ticker."""
        now = int(time.time() * 1000)
        start = now - (window_sec * 1000)

        data = self.ts.range(f"signals:{ticker}:count", start, now)
        return len(data) / (window_sec / 60)  # signals per minute
```

#### InfluxDB for Historical Analysis
**Use Case:**
- Long-term signal performance tracking
- Backtesting data storage
- Client portfolio performance

**Schema:**
```
measurement: signals
tags:
  - ticker
  - signal_type (BUY/SELL/WATCH)
  - catalyst_type (FDA/M&A/EARNINGS)
  - source (SEC_8K/GLOBENEWSWIRE)
  - client_id
fields:
  - confidence (float)
  - prescale_score (float)
  - llm_score (float)
  - rvol (float)
  - market_cap (float)
timestamp: signal generated time

measurement: executions
tags:
  - ticker
  - client_id
  - signal_id
fields:
  - entry_price (float)
  - exit_price (float)
  - quantity (int)
  - pnl (float)
  - hold_duration_sec (int)
timestamp: trade execution time
```

### Caching Strategies

**Multi-Level Cache (Current):**
```
Memory Cache → Disk Cache (Parquet) → API Call
```

**Distributed Cache:**
```
Memory Cache → Redis Cache → PostgreSQL → API Call
```

**Implementation:**
```python
class DistributedCache:
    """Multi-level distributed cache."""

    def __init__(self, redis_url: str, postgres_url: str):
        self.memory_cache = {}  # Local in-memory
        self.redis = redis.from_url(redis_url)
        self.db = create_engine(postgres_url)

    async def get(self, key: str) -> Optional[dict]:
        """Get from cache (memory → Redis → DB)."""
        # L1: Memory
        if key in self.memory_cache:
            return self.memory_cache[key]

        # L2: Redis
        value = await self.redis.get(key)
        if value:
            data = json.loads(value)
            self.memory_cache[key] = data  # Populate L1
            return data

        # L3: Database
        result = await self.db.execute(
            "SELECT data FROM cache WHERE key = %s", (key,)
        )
        if result:
            data = result['data']
            # Populate L2 and L1
            await self.redis.setex(key, 3600, json.dumps(data))
            self.memory_cache[key] = data
            return data

        return None

    async def set(self, key: str, value: dict, ttl_sec: int = 3600):
        """Set in all cache levels."""
        # L1: Memory
        self.memory_cache[key] = value

        # L2: Redis
        await self.redis.setex(key, ttl_sec, json.dumps(value))

        # L3: Database (async write)
        asyncio.create_task(
            self.db.execute(
                "INSERT INTO cache (key, data, expires_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO UPDATE SET data = %s, expires_at = %s",
                (key, value, datetime.utcnow() + timedelta(seconds=ttl_sec),
                 value, datetime.utcnow() + timedelta(seconds=ttl_sec))
            )
        )
```

---

## Deployment Options

### Docker Containerization

#### Multi-Container Architecture

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  # Central Signal Server
  signal-server:
    build:
      context: .
      dockerfile: Dockerfile.server
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://postgres:5432/catalyst
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - FINNHUB_API_KEY=${FINNHUB_API_KEY}
    depends_on:
      - redis
      - postgres
    ports:
      - "8000:8000"  # REST API
      - "8001:8001"  # WebSocket
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  # Feed Ingestion Worker
  feed-worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - REDIS_URL=redis://redis:6379
      - WORKER_TYPE=feed_ingestion
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M

  # Classification Worker (with GPU)
  classifier-worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - REDIS_URL=redis://redis:6379
      - WORKER_TYPE=classification
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - redis
      - ollama
    restart: unless-stopped
    deploy:
      replicas: 1
      resources:
        limits:
          memory: 4G
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  # Redis
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    restart: unless-stopped

  # PostgreSQL
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=catalyst
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped

  # Ollama (Local LLM)
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-data:/root/.ollama
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  redis-data:
  postgres-data:
  ollama-data:
```

**Dockerfile.server:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY data/ ./data/

# Expose ports
EXPOSE 8000 8001

# Run server
CMD ["python", "-m", "catalyst_bot.server"]
```

### Cloud Deployment (AWS)

#### AWS ECS with Fargate

**Benefits from Research:**
- No server management
- Pay per second for vCPU and memory
- Auto-scaling
- Seamless CI/CD integration

**Cost Optimization Strategies from Research:**

1. **Region Selection**: Ohio/Virginia/Oregon cheapest ($0.04048/vCPU-hr vs $0.0696 São Paulo)
2. **Savings Plans**: 50% discount with 3-year commitment
3. **Right-Sizing**: Use AWS Compute Optimizer
4. **Spot Instances**: 70% discount for non-critical workloads
5. **Log Management**: Set retention policies, use log rotation

**Task Definition (ECS):**
```json
{
  "family": "catalyst-signal-server",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "signal-server",
      "image": "your-registry/catalyst-signal-server:latest",
      "portMappings": [
        {"containerPort": 8000, "protocol": "tcp"},
        {"containerPort": 8001, "protocol": "tcp"}
      ],
      "environment": [
        {"name": "REDIS_URL", "value": "redis://redis.your-domain.com:6379"},
        {"name": "POSTGRES_URL", "value": "postgresql://..."}
      ],
      "secrets": [
        {"name": "GEMINI_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/catalyst-signal-server",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

**Terraform Infrastructure:**
```hcl
# ECS Cluster
resource "aws_ecs_cluster" "catalyst" {
  name = "catalyst-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Application Load Balancer
resource "aws_lb" "catalyst" {
  name               = "catalyst-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

# Target Groups
resource "aws_lb_target_group" "rest_api" {
  name     = "catalyst-rest-api"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }
}

resource "aws_lb_target_group" "websocket" {
  name     = "catalyst-websocket"
  port     = 8001
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/ws/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

# ECS Service with Auto-Scaling
resource "aws_ecs_service" "signal_server" {
  name            = "signal-server"
  cluster         = aws_ecs_cluster.catalyst.id
  task_definition = aws_ecs_task_definition.signal_server.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.rest_api.arn
    container_name   = "signal-server"
    container_port   = 8000
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.websocket.arn
    container_name   = "signal-server"
    container_port   = 8001
  }
}

# Auto-Scaling
resource "aws_appautoscaling_target" "ecs_target" {
  max_capacity       = 10
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.catalyst.name}/${aws_ecs_service.signal_server.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu_scaling" {
  name               = "cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}
```

#### Cost Estimates

**Small Deployment (10-20 users):**
- ECS Fargate (2 tasks, 1vCPU, 2GB): $50/month
- ElastiCache Redis (cache.t3.micro): $15/month
- RDS PostgreSQL (db.t3.micro): $15/month
- ALB: $20/month
- Data transfer: $10/month
- **Total: ~$110/month**

**Medium Deployment (50-100 users):**
- ECS Fargate (4 tasks, 2vCPU, 4GB): $200/month
- ElastiCache Redis (cache.t3.small): $30/month
- RDS PostgreSQL (db.t3.small): $30/month
- ALB: $20/month
- Data transfer: $30/month
- **Total: ~$310/month**

**With Savings Plans (3-year commitment):**
- 50% discount on Fargate costs
- **Small: $85/month**
- **Medium: $210/month**

### Self-Hosted Options

**DigitalOcean Droplets (cheaper alternative):**
- 4vCPU, 8GB RAM, 160GB SSD: $48/month
- Managed Redis: $15/month
- Managed PostgreSQL: $15/month
- Load Balancer: $12/month
- **Total: ~$90/month**

**Hetzner (EU, cheapest):**
- CCX33 (8vCPU, 32GB RAM): €27/month (~$30)
- Cloud Load Balancer: €6/month (~$7)
- Self-managed Redis/Postgres on same instance
- **Total: ~$40/month**

---

## Reliability Patterns

### Circuit Breaker Pattern

**From Research:**
> "The Circuit Breaker pattern prevents an application from performing an operation that's likely to fail. It has three states: Closed (requests flow normally), Open (blocks all requests), and Half-Open (tests if service recovered)." - Microsoft Azure

**Implementation:**
```python
from enum import Enum
from datetime import datetime, timedelta
import asyncio

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit breaker for external service calls."""

    def __init__(self, failure_threshold: int = 5,
                 timeout_sec: int = 60,
                 half_open_max_calls: int = 3):
        self.failure_threshold = failure_threshold
        self.timeout_sec = timeout_sec
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    async def call(self, func, *args, **kwargs):
        """Execute function through circuit breaker."""
        if self.state == CircuitState.OPEN:
            # Check if timeout expired
            if (datetime.utcnow() - self.last_failure_time).seconds >= self.timeout_sec:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                _logger.info("circuit_breaker_half_open")
            else:
                raise Exception("Circuit breaker is OPEN")

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise Exception("Circuit breaker is HALF_OPEN (max calls reached)")
            self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)

            # Success - reset or close circuit
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                _logger.info("circuit_breaker_closed")

            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                _logger.error("circuit_breaker_open failures=%d", self.failure_count)

            raise e

# Usage
llm_circuit_breaker = CircuitBreaker(failure_threshold=3, timeout_sec=60)

async def classify_with_llm(item: dict) -> dict:
    """Classify item with circuit breaker protection."""
    try:
        result = await llm_circuit_breaker.call(
            llm_client.classify_async, item
        )
        return result
    except Exception as e:
        _logger.warning("llm_circuit_breaker_triggered err=%s", str(e))
        # Fallback to keyword-only classification
        return keyword_classifier.classify(item)
```

### Retry Logic with Exponential Backoff

**From Research:**
> "Systems implement exponential backoff, where retry intervals gradually increase. This helps prevent overwhelming the failing service with repeated requests, giving it time to recover." - DEV Community

**Implementation:**
```python
import asyncio
from typing import TypeVar, Callable
import random

T = TypeVar('T')

class RetryStrategy:
    """Retry with exponential backoff and jitter."""

    def __init__(self, max_retries: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        if self.jitter:
            # Add random jitter (±25%)
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    async def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)

            except Exception as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    _logger.warning(
                        "retry_attempt attempt=%d/%d delay=%.2fs err=%s",
                        attempt + 1, self.max_retries, delay, str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    _logger.error(
                        "retry_failed attempts=%d err=%s",
                        self.max_retries + 1, str(e)
                    )

        raise last_exception

# Usage
retry_strategy = RetryStrategy(max_retries=3, base_delay=1.0)

async def fetch_price_data(ticker: str) -> dict:
    """Fetch price data with retry."""
    return await retry_strategy.execute(
        tiingo_client.get_price_data, ticker
    )
```

### Graceful Degradation

**Implementation:**
```python
class GracefulDegradation:
    """Graceful degradation for multi-source data."""

    async def get_price_data(self, ticker: str) -> dict:
        """Get price data with fallback chain."""
        # Try primary source (Tiingo)
        try:
            return await self.tiingo_client.get_price_data(ticker)
        except Exception as e:
            _logger.warning("tiingo_failed err=%s", str(e))

        # Try backup source (Alpha Vantage)
        try:
            return await self.alpha_vantage_client.get_price_data(ticker)
        except Exception as e:
            _logger.warning("alpha_vantage_failed err=%s", str(e))

        # Try fallback source (yfinance)
        try:
            return await self.yfinance_client.get_price_data(ticker)
        except Exception as e:
            _logger.warning("yfinance_failed err=%s", str(e))

        # All sources failed - return degraded data
        _logger.error("all_price_sources_failed ticker=%s", ticker)
        return {
            'ticker': ticker,
            'price': None,
            'error': 'All price sources unavailable',
            'degraded': True
        }

    async def classify_item(self, item: dict) -> dict:
        """Classify with LLM fallback."""
        # Try LLM classification
        if self.llm_available:
            try:
                return await self.llm_classifier.classify(item)
            except Exception as e:
                _logger.warning("llm_classification_failed err=%s", str(e))
                self.llm_available = False

        # Fallback to keyword-only classification
        _logger.info("using_keyword_only_classification")
        return self.keyword_classifier.classify(item)
```

### Error Recovery

**Implementation:**
```python
class ErrorRecovery:
    """Automatic error recovery mechanisms."""

    async def recover_websocket_connections(self):
        """Reconnect dropped WebSocket clients."""
        disconnected = []

        for client_id, ws in self.connections.items():
            if ws.closed:
                disconnected.append(client_id)

        for client_id in disconnected:
            _logger.info("recovering_websocket client_id=%s", client_id)

            # Remove old connection
            del self.connections[client_id]

            # Notify client to reconnect
            await self.send_reconnect_notification(client_id)

    async def recover_event_stream(self):
        """Recover from Redis stream failure."""
        try:
            # Test Redis connection
            await self.redis.ping()
        except Exception as e:
            _logger.error("redis_connection_failed err=%s", str(e))

            # Try to reconnect
            for attempt in range(3):
                try:
                    await asyncio.sleep(2 ** attempt)
                    self.redis = redis.from_url(self.redis_url)
                    await self.redis.ping()
                    _logger.info("redis_reconnected")
                    break
                except Exception as retry_error:
                    _logger.warning("redis_reconnect_failed attempt=%d", attempt + 1)
            else:
                # All retries failed - switch to degraded mode
                _logger.error("redis_unavailable_switching_to_degraded_mode")
                self.degraded_mode = True
```

---

## Configuration Management

### User-Specific Settings

**Configuration Schema:**
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class RiskParameters(BaseModel):
    """User risk management settings."""
    max_position_size_usd: float = Field(1000, ge=100, le=100000)
    max_daily_loss_usd: float = Field(500, ge=50, le=50000)
    max_positions: int = Field(5, ge=1, le=20)
    stop_loss_pct: float = Field(5.0, ge=1.0, le=20.0)
    take_profit_pct: float = Field(10.0, ge=2.0, le=50.0)

class SignalFilters(BaseModel):
    """User signal filtering preferences."""
    min_confidence: float = Field(0.7, ge=0.5, le=1.0)
    min_market_cap: Optional[float] = Field(100_000_000, ge=0)
    max_price: Optional[float] = Field(20.0, ge=0)
    min_rvol: Optional[float] = Field(1.5, ge=0)
    catalyst_types: List[str] = Field(
        default=["FDA", "M&A", "EARNINGS", "INSIDER_BUY"]
    )
    sectors: Optional[List[str]] = None  # None = all sectors

class ExecutionSettings(BaseModel):
    """User execution preferences."""
    auto_execute: bool = False
    execution_delay_sec: int = Field(0, ge=0, le=300)
    order_type: str = Field("market", pattern="^(market|limit)$")
    time_in_force: str = Field("day", pattern="^(day|gtc|ioc)$")

class UserConfig(BaseModel):
    """Complete user configuration."""
    user_id: str
    broker_type: str = "alpaca"
    broker_api_key: str
    broker_api_secret: str
    risk: RiskParameters = RiskParameters()
    filters: SignalFilters = SignalFilters()
    execution: ExecutionSettings = ExecutionSettings()
    notification_channels: List[str] = ["websocket"]

# Storage in PostgreSQL
CREATE TABLE user_configs (
    user_id VARCHAR(64) PRIMARY KEY,
    config JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_user_configs_updated ON user_configs(updated_at);
```

### Feature Flags

**Implementation:**
```python
from typing import Dict, Any
import json

class FeatureFlagManager:
    """Manage feature flags for gradual rollout."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.cache = {}
        self.cache_ttl = 60  # 1 minute cache

    async def is_enabled(self, flag_name: str, user_id: Optional[str] = None) -> bool:
        """Check if feature flag is enabled for user."""
        # Check cache
        cache_key = f"{flag_name}:{user_id or 'global'}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Get from Redis
        flag_config = await self.redis.get(f"feature_flags:{flag_name}")
        if not flag_config:
            return False

        config = json.loads(flag_config)

        # Global enable/disable
        if not config.get('enabled', False):
            self.cache[cache_key] = False
            return False

        # Percentage rollout
        if 'rollout_pct' in config and user_id:
            user_hash = hash(user_id) % 100
            enabled = user_hash < config['rollout_pct']
            self.cache[cache_key] = enabled
            return enabled

        # Whitelist
        if 'whitelist' in config and user_id:
            enabled = user_id in config['whitelist']
            self.cache[cache_key] = enabled
            return enabled

        # Default to enabled
        self.cache[cache_key] = True
        return True

    async def set_flag(self, flag_name: str, config: dict):
        """Set feature flag configuration."""
        await self.redis.set(
            f"feature_flags:{flag_name}",
            json.dumps(config)
        )
        # Clear cache
        self.cache.clear()

# Usage
feature_flags = FeatureFlagManager(redis_client)

# Enable for 10% of users
await feature_flags.set_flag('auto_execution', {
    'enabled': True,
    'rollout_pct': 10,
    'description': 'Automatic trade execution'
})

# Check if enabled for user
if await feature_flags.is_enabled('auto_execution', user_id):
    await execute_trade_automatically(signal)
else:
    await send_manual_alert(signal)
```

### Hot Reloading Configuration

**Implementation:**
```python
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigWatcher(FileSystemEventHandler):
    """Watch configuration files for changes."""

    def __init__(self, reload_callback):
        self.reload_callback = reload_callback

    def on_modified(self, event):
        if event.src_path.endswith('.json') or event.src_path.endswith('.yaml'):
            asyncio.create_task(self.reload_callback(event.src_path))

class HotReloadConfig:
    """Hot reload configuration without restart."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = {}
        self.observers = []

    async def start_watching(self):
        """Start watching config files."""
        observer = Observer()
        handler = ConfigWatcher(self.reload_config)
        observer.schedule(handler, path=self.config_path, recursive=True)
        observer.start()
        self.observers.append(observer)
        _logger.info("config_watcher_started path=%s", self.config_path)

    async def reload_config(self, file_path: str):
        """Reload configuration from file."""
        try:
            with open(file_path, 'r') as f:
                new_config = json.load(f)

            # Validate config
            validated = self._validate_config(new_config)

            # Update config
            self.config.update(validated)

            _logger.info("config_reloaded file=%s", file_path)

            # Notify subscribers
            await self._notify_config_change()

        except Exception as e:
            _logger.error("config_reload_failed file=%s err=%s", file_path, str(e))

    async def _notify_config_change(self):
        """Notify all connected clients of config change."""
        await self.connection_manager.broadcast_message({
            'type': 'config_updated',
            'timestamp': datetime.utcnow().isoformat()
        })
```

---

## Recommended Architecture

### Phase 1: MVP (1-2 weeks)

**Goal**: Deploy working signal distribution to 3-5 friends

**Architecture:**
```
┌──────────────────────────────────────┐
│  AWS EC2 (t3.medium)                 │
│                                      │
│  ┌────────────────────────────────┐ │
│  │ Catalyst Bot (existing code)   │ │
│  │ - Feed aggregation             │ │
│  │ - Classification               │ │
│  └────────┬───────────────────────┘ │
│           │                          │
│  ┌────────▼───────────────────────┐ │
│  │ FastAPI Server                 │ │
│  │ - REST API (port 8000)         │ │
│  │ - WebSocket (port 8001)        │ │
│  │ - Simple auth (API keys)       │ │
│  └────────┬───────────────────────┘ │
│           │                          │
│  ┌────────▼───────────────────────┐ │
│  │ SQLite                         │ │
│  │ - Signals (last 7 days)        │ │
│  │ - User configs                 │ │
│  └────────────────────────────────┘ │
└──────────────────────────────────────┘

┌──────────────┐  ┌──────────────┐
│ Client #1    │  │ Client #2    │
│ - Python     │  │ - Python     │
│ - WebSocket  │  │ - WebSocket  │
│ - Alpaca API │  │ - Alpaca API │
└──────────────┘  └──────────────┘
```

**Stack:**
- FastAPI for REST + WebSocket
- SQLite for simple storage
- Existing Catalyst-Bot code
- nginx reverse proxy
- Systemd for process management

**Estimated Cost**: $30/month (EC2 t3.medium)

### Phase 2: Production (2-4 weeks)

**Goal**: Scale to 20-50 users, add reliability

**Architecture:**
```
┌─────────────────────────────────────────────────┐
│  AWS ECS Cluster                                │
│                                                 │
│  ┌───────────────────┐  ┌───────────────────┐ │
│  │ Signal Generator  │  │ API Server        │ │
│  │ (2 tasks)         │  │ (2 tasks)         │ │
│  └────────┬──────────┘  └────────┬──────────┘ │
│           │                       │             │
│           └───────┬───────────────┘             │
│                   │                             │
└───────────────────┼─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│  ElastiCache Redis                              │
│  - Pub/Sub (signals)                            │
│  - Cache (market data)                          │
│  - Rate limiting                                │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│  RDS PostgreSQL                                 │
│  - Event store                                  │
│  - User configs                                 │
│  - Signal history                               │
└─────────────────────────────────────────────────┘

┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Client #1    │  │ Client #2    │  │ Client #N    │
└──────────────┘  └──────────────┘  └──────────────┘
```

**Stack:**
- ECS Fargate (serverless containers)
- ElastiCache Redis (managed)
- RDS PostgreSQL (managed)
- Application Load Balancer
- CloudWatch for monitoring

**Estimated Cost**: $210/month (with savings plan)

### Phase 3: Scale (4-8 weeks)

**Goal**: 100+ users, high availability

**Architecture:**
```
┌─────────────────────────────────────────────────┐
│  Multi-AZ Deployment                            │
│                                                 │
│  ┌───────────────┐  ┌───────────────────────┐ │
│  │ Feed Workers  │  │ Classification Workers│ │
│  │ (auto-scale)  │  │ (GPU, auto-scale)     │ │
│  └───────┬───────┘  └───────┬───────────────┘ │
│          │                   │                  │
│          └────────┬──────────┘                  │
│                   │                             │
│  ┌────────────────▼──────────────────────────┐ │
│  │ Redis Cluster (3 nodes)                   │ │
│  │ - Streams (persistent pub/sub)            │ │
│  │ - Consumer groups (scaling)               │ │
│  └────────────────┬──────────────────────────┘ │
│                   │                             │
│  ┌────────────────▼──────────────────────────┐ │
│  │ RDS Multi-AZ (PostgreSQL)                 │ │
│  │ - Primary (writes)                        │ │
│  │ - Read replicas (2)                       │ │
│  └────────────────┬──────────────────────────┘ │
│                   │                             │
│  ┌────────────────▼──────────────────────────┐ │
│  │ InfluxDB                                  │ │
│  │ - Long-term metrics                       │ │
│  │ - Performance analytics                   │ │
│  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Monitoring & Observability                     │
│  - CloudWatch (metrics, logs)                   │
│  - Datadog / Grafana (dashboards)               │
│  - Sentry (error tracking)                      │
│  - PagerDuty (alerting)                         │
└─────────────────────────────────────────────────┘
```

**Estimated Cost**: $500-800/month

---

## Implementation Roadmap

### Week 1-2: MVP Foundation

**Tasks:**
1. Create FastAPI server wrapper around existing Catalyst-Bot
2. Implement WebSocket server with basic authentication
3. Create signal broadcasting mechanism
4. Build simple Python client for testing
5. Deploy to single EC2 instance
6. Test with 2-3 users

**Deliverables:**
- Working WebSocket signal distribution
- Python client library
- Basic monitoring
- Deployment documentation

### Week 3-4: Client Features

**Tasks:**
1. Implement user configuration storage (SQLite)
2. Add signal filtering (client-side preferences)
3. Create risk management module
4. Build Alpaca integration for execution
5. Add feedback loop (trade outcomes → server)

**Deliverables:**
- Configurable signal filtering
- Automated execution (optional)
- Outcome tracking

### Week 5-6: Reliability

**Tasks:**
1. Implement circuit breakers for all external APIs
2. Add retry logic with exponential backoff
3. Create health monitoring system
4. Add graceful degradation
5. Implement comprehensive logging

**Deliverables:**
- Resilient external API calls
- Health dashboard
- Alert system for failures

### Week 7-8: Production Deployment

**Tasks:**
1. Migrate to AWS ECS
2. Set up managed Redis and PostgreSQL
3. Implement proper authentication (JWT)
4. Add rate limiting
5. Create monitoring dashboards
6. Write operational runbooks

**Deliverables:**
- Production-ready infrastructure
- Monitoring and alerting
- Documentation

### Week 9-12: Scale & Optimize

**Tasks:**
1. Implement event sourcing
2. Add InfluxDB for metrics
3. Create admin dashboard
4. Build user management portal
5. Add billing/usage tracking (if needed)
6. Performance optimization

**Deliverables:**
- Scalable architecture
- Admin tools
- Performance benchmarks

---

## Technology Stack Recommendations

### Core Stack

**Backend:**
- **FastAPI**: Modern, async-first Python web framework
- **WebSockets** (via FastAPI): Real-time bidirectional communication
- **Pydantic**: Data validation and settings management
- **asyncio**: Async Python (already using)
- **aiohttp**: Async HTTP client (already using)

**Message Queue:**
- **Phase 1**: Redis Pub/Sub (simple, already using Redis)
- **Phase 2**: Redis Streams (persistent, consumer groups)
- **Phase 3**: Apache Kafka (if scaling beyond 1000 users)

**Database:**
- **Primary**: PostgreSQL (event store, user configs, signals)
- **Cache**: Redis (hot data, rate limiting, sessions)
- **Time-Series**: InfluxDB (metrics, performance tracking)
- **Development**: SQLite (MVP phase)

**Deployment:**
- **Phase 1**: Single EC2 instance + systemd
- **Phase 2**: AWS ECS Fargate + managed services
- **Phase 3**: Multi-AZ ECS + auto-scaling

**Monitoring:**
- **Logs**: CloudWatch Logs or Datadog
- **Metrics**: CloudWatch Metrics + InfluxDB
- **Errors**: Sentry
- **Dashboards**: Grafana
- **Alerts**: PagerDuty or AWS SNS

### Client Library

**Python Client:**
```python
import asyncio
import websockets
import json
from typing import Callable, Optional

class CatalystClient:
    """Client library for connecting to Catalyst signal server."""

    def __init__(self, api_key: str, ws_url: str = "wss://api.catalyst.example.com/ws"):
        self.api_key = api_key
        self.ws_url = ws_url
        self.ws = None
        self.signal_handler = None

    async def connect(self):
        """Connect to WebSocket server."""
        self.ws = await websockets.connect(
            self.ws_url,
            extra_headers={'Authorization': f'Bearer {self.api_key}'}
        )
        print(f"Connected to {self.ws_url}")

    async def subscribe(self, signal_handler: Callable):
        """Subscribe to signals."""
        self.signal_handler = signal_handler

        async for message in self.ws:
            data = json.loads(message)

            if data['type'] == 'signal':
                await self.signal_handler(data['signal'])
            elif data['type'] == 'heartbeat':
                await self.ws.send(json.dumps({'type': 'pong'}))

    async def update_filters(self, filters: dict):
        """Update signal filters."""
        await self.ws.send(json.dumps({
            'type': 'update_filters',
            'filters': filters
        }))

    async def send_feedback(self, signal_id: str, outcome: dict):
        """Send trade outcome feedback."""
        await self.ws.send(json.dumps({
            'type': 'feedback',
            'signal_id': signal_id,
            'outcome': outcome
        }))

# Usage
async def handle_signal(signal: dict):
    """Handle incoming trading signal."""
    print(f"Received signal: {signal['ticker']} - {signal['signal_type']}")

    # Your trading logic here
    if signal['confidence'] >= 0.8:
        # Execute trade
        pass

client = CatalystClient(api_key="your_key")
await client.connect()
await client.update_filters({
    'min_confidence': 0.7,
    'catalyst_types': ['FDA', 'M&A']
})
await client.subscribe(handle_signal)
```

---

## Security Considerations

### Authentication & Authorization

**Multi-Layer Security from Research:**

1. **API Key Authentication** (Phase 1)
```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key."""
    user = await db.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user
```

2. **JWT Token Authentication** (Phase 2)
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt
from datetime import datetime, timedelta

security = HTTPBearer()

def create_access_token(user_id: str) -> str:
    """Create JWT access token."""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

async def verify_token(credentials = Depends(security)):
    """Verify JWT token."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=['HS256']
        )
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

3. **IP Whitelisting** (Phase 3)
```python
from fastapi import Request, HTTPException

async def verify_ip_whitelist(request: Request, user_id: str):
    """Verify client IP is whitelisted."""
    client_ip = request.client.host
    allowed_ips = await db.get_user_ip_whitelist(user_id)

    if allowed_ips and client_ip not in allowed_ips:
        raise HTTPException(
            status_code=403,
            detail=f"IP {client_ip} not whitelisted"
        )
```

### Data Encryption

**Encryption in Transit:**
- TLS 1.3 for all connections
- WebSocket Secure (WSS)
- Certificate from Let's Encrypt

**Encryption at Rest:**
- RDS encryption enabled
- Encrypted EBS volumes
- Encrypted S3 buckets (for logs)

**Implementation:**
```python
# Force HTTPS
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)

# Secure headers
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.catalyst.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### Secrets Management

**AWS Secrets Manager:**
```python
import boto3
import json

class SecretsManager:
    """Manage secrets via AWS Secrets Manager."""

    def __init__(self, region: str = "us-east-1"):
        self.client = boto3.client('secretsmanager', region_name=region)
        self.cache = {}

    def get_secret(self, secret_name: str) -> dict:
        """Get secret from AWS Secrets Manager."""
        if secret_name in self.cache:
            return self.cache[secret_name]

        response = self.client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])

        self.cache[secret_name] = secret
        return secret

secrets = SecretsManager()

# Get API keys from Secrets Manager
gemini_key = secrets.get_secret('catalyst/gemini_api_key')
database_creds = secrets.get_secret('catalyst/database')
```

### Audit Logging

**Implementation:**
```python
class AuditLogger:
    """Audit logging for compliance."""

    async def log_event(self, event_type: str, user_id: str,
                       details: dict, ip_address: str):
        """Log audit event."""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'ip_address': ip_address,
            'details': details
        }

        # Write to database
        await db.insert_audit_log(event)

        # Write to CloudWatch Logs
        logger.info(
            "audit_event",
            extra={
                'event_type': event_type,
                'user_id': user_id,
                'ip': ip_address
            }
        )

# Usage
await audit_logger.log_event(
    event_type='SIGNAL_DELIVERED',
    user_id=user_id,
    details={'signal_id': signal_id, 'ticker': ticker},
    ip_address=request.client.host
)
```

### Rate Limiting (Security)

**Prevent Abuse:**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/v1/signals")
@limiter.limit("100/minute")  # 100 requests per minute per IP
async def get_signals(request: Request):
    """Get signals with rate limiting."""
    pass
```

---

## Sources

### Event-Driven Architecture
- [Event Driven Architecture Done Right: How to Scale Systems with Quality in 2025 - Growin](https://www.growin.com/blog/event-driven-architecture-scale-systems-2025/)
- [Event-Driven Architecture (EDA): A Complete Introduction - Confluent](https://www.confluent.io/learn/event-driven-architecture/)
- [Event-Driven Architecture with CQRS & Event Sourcing - Medium](https://medium.com/techartifact-technology-learning/event-driven-architecture-with-cqrs-event-sourcing-bdded2f3c595)
- [Event Sourcing pattern - Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)

### Distributed Trading Systems
- [Evolution and Practice: Low-latency Distributed Applications in Finance - ACM Queue](https://queue.acm.org/detail.cfm?id=2770868)
- [Data Pipeline Design in an Algorithmic Trading System - Medium](https://medium.com/@edwinsalguero/data-pipeline-design-in-an-algorithmic-trading-system-ac0d8109c4b9)
- [Proof Engineering: The Algorithmic Trading Platform - Medium](https://medium.com/prooftrading/proof-engineering-the-algorithmic-trading-platform-b9c2f195433d)
- [Building a Stock Trading System: High-Frequency Trading Architecture - DEV Community](https://dev.to/sgchris/building-a-stock-trading-system-high-frequency-trading-architecture-e2f)

### WebSocket & API Design
- [Real-Time Data API (WebSockets) - EODHD](https://eodhd.com/financial-apis/new-real-time-data-api-websockets)
- [Advanced Trade WebSocket Rate Limits - Coinbase](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-rate-limits)
- [What Are Binance WebSocket Limits? - Binance Academy](https://academy.binance.com/en/articles/what-are-binance-websocket-limits)
- [WebSocket Stream - Alpaca API Docs](https://docs.alpaca.markets/docs/streaming-market-data)

### Async Python & Trading Bots
- [AsyncAlgoTrading/aat - GitHub](https://github.com/AsyncAlgoTrading/aat)
- [Concurrent Scalping Algo Using Async Python - Alpaca Markets](https://alpaca.markets/learn/concurrent-scalping-algo-async-python)
- [Python in High-Frequency Trading: Low-Latency Techniques - PyQuant News](https://www.pyquantnews.com/free-python-resources/python-in-high-frequency-trading-low-latency-techniques)
- [Replicating orderbooks from Websocket stream with Python and Asyncio - MMquant](https://mmquant.net/replicating-orderbooks-from-websocket-stream-with-python-and-asyncio/)

### Data Pipeline & Time-Series
- [Building a Real-Time Trading Platform with Redis - Redis](https://redis.io/blog/real-time-trading-platform-with-redis-enterprise/)
- [Using Redis as a Time Series Database: Why and How - InfoQ](https://www.infoq.com/articles/redis-time-series/)
- [Building a High-Frequency Trading System With Hybrid Strategy (Redis & InfluxDB) - Medium](https://vardhmanandroid2015.medium.com/building-a-high-frequency-trading-system-with-hybrid-strategy-redis-influxdb-from-10ms-to-85716febefcb)

### Cloud Deployment
- [Live Algo Trading on the Cloud - Microsoft Azure - AlgoTrading101](https://algotrading101.com/learn/algo-trading-deployment-microsoft-azure/)
- [AWS Elastic Container Service: Strategies for Cost Optimization - Astuto AI](https://www.astuto.ai/blogs/aws-elastic-container-service-strategies-for-cost-optimization)
- [Deploying freqtrade on a Cloud Server or Docker Environment - Sling Academy](https://www.slingacademy.com/article/deploying-freqtrade-on-a-cloud-server-or-docker-environment/)

### Reliability Patterns
- [Circuit Breaker Pattern - Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [Circuit Breaker & Retry Logic - Software System Design](https://softwaresystemdesign.com/high-level-design/circuit-breaker-retry-logic/)
- [Downstream Resiliency: The Timeout, Retry, and Circuit-Breaker Patterns - DEV Community](https://dev.to/rafaeljcamara/downstream-resiliency-the-timeout-retry-and-circuit-breaker-patterns-2bej)
- [Error handling in distributed systems - Temporal](https://temporal.io/blog/error-handling-in-distributed-systems)

### Security
- [Trading Platform Security: Essential Tips to Protect Your Trades - TradeFundrr](https://tradefundrr.com/trading-platform-security/)
- [Essential Security Measures for Trading Platform Software - Technivorz](https://technivorz.com/essential-security-measures-for-trading-platform-software-development/)
- [What Are the Key Considerations for Building a Secure Investment Platform? - DEV Community](https://dev.to/it-influencer/what-are-the-key-considerations-for-building-a-secure-investment-platform-1b7o)
- [Safeguarding Your Online Trading Platform: 7 Strategies to Defend Against Cyber Attacks - CyberDB](https://www.cyberdb.co/safeguarding-your-online-trading-platform-7-strategies-to-defend-against-cyber-attacks/)

---

**Next Steps:**
1. Review this architecture research
2. Choose deployment phase (MVP, Production, or Scale)
3. Begin implementation following the roadmap
4. Set up development environment
5. Create first FastAPI endpoint for signal distribution
