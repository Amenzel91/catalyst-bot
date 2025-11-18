# SEC Digester as WebSocket Microservice

**Date**: 2025-11-17
**Architecture**: Decoupled WebSocket Service
**Status**: Proposed Design

---

## Executive Summary

Converting the SEC Digester into a standalone WebSocket service is an **excellent architectural decision** that aligns perfectly with cloud-first deployment. This approach provides:

- ✅ **Clean separation** of concerns (document processing vs. trading logic)
- ✅ **Independent scaling** (SEC service in cloud, main bot anywhere)
- ✅ **Multiple consumers** (Discord bot, web dashboard, analytics)
- ✅ **Real-time streaming** (<50ms latency for alerts)
- ✅ **Reliability** (message persistence, reconnection handling)

---

## Architecture Options

### Option 1: Simple WebSocket (RECOMMENDED for MVP)

**Best for**: Single consumer (main bot), quick implementation

```
┌─────────────────────────────────────┐
│   SEC Digester Service (Cloud)      │
│   - FastAPI WebSocket Server        │
│   - Port 8765                        │
│                                      │
│   EDGAR Monitor → LLM Analysis      │
│         ↓                            │
│   WebSocket Broadcast                │
└──────────────┬──────────────────────┘
               │ ws://sec-digester:8765/filings
               ↓
┌─────────────────────────────────────┐
│   Main Catalyst Bot                  │
│   - WebSocket Client                 │
│   - Auto-reconnect                   │
│   - Message queue on disconnect      │
└──────────────────────────────────────┘
```

**Pros:**
- ✅ Simplest implementation (1-2 days)
- ✅ Low latency (<50ms)
- ✅ Built into FastAPI
- ✅ Perfect for single consumer

**Cons:**
- ❌ Message loss on disconnect
- ❌ No message persistence
- ❌ Harder to scale to multiple consumers

**When to use**: MVP, single bot consumer, can tolerate missed filings

### Option 2: WebSocket + Redis Streams (RECOMMENDED for Production)

**Best for**: Multiple consumers, guaranteed delivery, production reliability

```
┌──────────────────────────────────────────────────┐
│   SEC Digester Service (Cloud)                   │
│                                                   │
│   ┌────────────────┐                            │
│   │ EDGAR Monitor  │                            │
│   └───────┬────────┘                            │
│           ↓                                      │
│   ┌────────────────┐                            │
│   │ LLM Analysis   │                            │
│   └───────┬────────┘                            │
│           ↓                                      │
│   ┌────────────────┐     ┌──────────────────┐  │
│   │ Redis Streams  │────→│ WebSocket Server │  │
│   │ (Persistent)   │     │ (Broadcasting)   │  │
│   └────────────────┘     └─────────┬────────┘  │
└──────────────────────────────────────┼──────────┘
                                       │
                     ┌─────────────────┼─────────────────┐
                     │                 │                 │
                     ↓                 ↓                 ↓
          ┌─────────────────┐ ┌──────────────┐ ┌─────────────┐
          │ Main Bot        │ │ Dashboard    │ │ Analytics   │
          │ (Discord)       │ │ (Web)        │ │ (Research)  │
          └─────────────────┘ └──────────────┘ └─────────────┘
```

**Pros:**
- ✅ Message persistence (survive restarts)
- ✅ Multiple consumers
- ✅ Replay capability (catch up after disconnect)
- ✅ Guaranteed delivery
- ✅ Deduplication support

**Cons:**
- ❌ More complex (3-4 days)
- ❌ Requires Redis infrastructure
- ❌ Slightly higher latency (~10ms overhead)

**When to use**: Production, multiple consumers, can't miss filings

### Option 3: Hybrid REST + WebSocket (Best of Both Worlds)

**Best for**: Maximum flexibility, multiple access patterns

```
┌─────────────────────────────────────────────────┐
│   SEC Digester Service (Cloud)                  │
│                                                  │
│   ┌─────────────────────────────────────────┐  │
│   │ FastAPI Application                     │  │
│   │                                          │  │
│   │  ┌──────────────┐  ┌─────────────────┐ │  │
│   │  │ REST API     │  │ WebSocket       │ │  │
│   │  │ :8000/api    │  │ :8765/stream    │ │  │
│   │  │              │  │                 │ │  │
│   │  │ - Query      │  │ - Real-time     │ │  │
│   │  │ - Historical │  │ - Subscribe     │ │  │
│   │  │ - Search     │  │ - Push alerts   │ │  │
│   │  └──────────────┘  └─────────────────┘ │  │
│   │           ↓                ↓            │  │
│   │      ┌──────────────────────────────┐  │  │
│   │      │   Redis Streams              │  │  │
│   │      │   (Event Store)              │  │  │
│   │      └──────────────────────────────┘  │  │
│   └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**Pros:**
- ✅ Real-time WebSocket for alerts
- ✅ REST API for queries/historical data
- ✅ Flexibility for different use cases
- ✅ Easy testing (can use curl for REST)

**Cons:**
- ❌ Most complex (5-6 days)
- ❌ Two interfaces to maintain

**When to use**: Multi-purpose service, multiple teams consuming

---

## Recommended Approach: Start Simple, Evolve

### Phase 1: Simple WebSocket (Week 1)
Build basic WebSocket server for real-time streaming

### Phase 2: Add Redis Streams (Week 2-3)
Add persistence and reliability

### Phase 3: Add REST API (Week 4)
Add query interface for historical data

---

## Detailed Design: Option 2 (Production-Ready)

### Service Architecture

```python
# sec_digester_service/main.py
"""
SEC Digester WebSocket Microservice

Standalone service that:
1. Monitors EDGAR for new filings
2. Analyzes with LLM (Gemini/Claude)
3. Publishes to Redis Streams
4. Broadcasts via WebSocket to clients
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import redis.asyncio as redis
from typing import Set
import json
import logging

app = FastAPI(title="SEC Digester Service")

# CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connected WebSocket clients
active_connections: Set[WebSocket] = set()

# Redis connection for streams
redis_client = None


@app.on_event("startup")
async def startup():
    """Initialize Redis and start background tasks."""
    global redis_client
    redis_client = await redis.from_url("redis://localhost:6379")

    # Start background filing monitor
    asyncio.create_task(edgar_monitor_task())

    # Start WebSocket broadcaster
    asyncio.create_task(redis_to_websocket_broadcaster())

    logging.info("SEC Digester Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.close()


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws/filings")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time SEC filing stream.

    Clients connect here to receive filing alerts in real-time.

    Message Format:
    {
        "type": "filing_alert",
        "filing_id": "0001234567-25-000123",
        "ticker": "AAPL",
        "filing_type": "8-K",
        "item_code": "2.02",
        "timestamp": "2025-11-17T10:30:00Z",
        "analysis": {
            "sentiment": 0.75,
            "keywords": ["earnings", "beat"],
            "summary": "Apple reports Q4 earnings...",
            "priority": "high"
        },
        "url": "https://www.sec.gov/..."
    }
    """
    await websocket.accept()
    active_connections.add(websocket)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to SEC Digester",
            "server_time": datetime.utcnow().isoformat()
        })

        # Keep connection alive
        while True:
            # Receive heartbeat from client
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logging.info(f"Client disconnected. Active: {len(active_connections)}")


# ============================================================================
# Background Tasks
# ============================================================================

async def edgar_monitor_task():
    """
    Background task: Monitor EDGAR for new filings.

    Polls EDGAR RSS feed every 5 minutes, detects new filings,
    analyzes them, and publishes to Redis Streams.
    """
    from .sec_monitor import SECMonitor
    from .llm_service import LLMService

    monitor = SECMonitor()
    llm_service = LLMService()

    while True:
        try:
            # Fetch new filings
            new_filings = await monitor.fetch_recent_filings()

            for filing in new_filings:
                # Analyze with LLM
                analysis = await llm_service.analyze_filing(filing)

                # Create alert message
                alert = {
                    "type": "filing_alert",
                    "filing_id": filing.accession_number,
                    "ticker": filing.ticker,
                    "filing_type": filing.filing_type,
                    "item_code": filing.item_code,
                    "timestamp": filing.filed_at.isoformat(),
                    "analysis": {
                        "sentiment": analysis.sentiment,
                        "keywords": analysis.keywords,
                        "summary": analysis.summary,
                        "priority": analysis.priority,
                    },
                    "url": filing.url,
                }

                # Publish to Redis Stream
                await redis_client.xadd(
                    "sec:filings",
                    {"data": json.dumps(alert)},
                    maxlen=10000  # Keep last 10K filings
                )

                logging.info(f"Published filing: {filing.ticker} {filing.filing_type}")

        except Exception as e:
            logging.error(f"Error in EDGAR monitor: {e}")

        # Wait before next poll
        await asyncio.sleep(300)  # 5 minutes


async def redis_to_websocket_broadcaster():
    """
    Background task: Read from Redis Streams and broadcast to WebSocket clients.

    Reads new messages from Redis Streams and pushes them to all connected
    WebSocket clients for real-time alerts.
    """
    last_id = "0"  # Start from beginning

    while True:
        try:
            # Read new messages from stream
            messages = await redis_client.xread(
                {"sec:filings": last_id},
                count=10,
                block=1000  # Block for 1 second
            )

            if messages:
                for stream_name, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        # Update last_id for next read
                        last_id = message_id

                        # Parse message
                        alert = json.loads(message_data[b"data"])

                        # Broadcast to all connected clients
                        await broadcast_to_clients(alert)

        except Exception as e:
            logging.error(f"Error in broadcaster: {e}")
            await asyncio.sleep(1)


async def broadcast_to_clients(message: dict):
    """Broadcast message to all connected WebSocket clients."""
    disconnected = set()

    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logging.error(f"Error sending to client: {e}")
            disconnected.add(connection)

    # Remove disconnected clients
    active_connections -= disconnected


# ============================================================================
# REST API Endpoints (Optional - for queries)
# ============================================================================

@app.get("/api/filings/recent")
async def get_recent_filings(limit: int = 50):
    """
    Get recent filings from Redis Stream.

    Useful for:
    - Initial load when client connects
    - Catching up after disconnect
    - Historical queries
    """
    messages = await redis_client.xrevrange(
        "sec:filings",
        count=limit
    )

    filings = []
    for message_id, message_data in messages:
        filings.append(json.loads(message_data[b"data"]))

    return {"filings": filings, "count": len(filings)}


@app.get("/api/filings/{ticker}")
async def get_filings_by_ticker(ticker: str, limit: int = 20):
    """Get recent filings for specific ticker."""
    # In production, would use secondary index or database
    # For now, scan stream and filter

    messages = await redis_client.xrevrange("sec:filings", count=100)

    filings = []
    for message_id, message_data in messages:
        alert = json.loads(message_data[b"data"])
        if alert["ticker"].upper() == ticker.upper():
            filings.append(alert)
            if len(filings) >= limit:
                break

    return {"ticker": ticker, "filings": filings, "count": len(filings)}


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "active_connections": len(active_connections),
        "redis_connected": redis_client is not None
    }
```

### Client Implementation (Main Bot)

```python
# catalyst_bot/sec_websocket_client.py
"""
WebSocket client for consuming SEC filing alerts.

Connects to SEC Digester service and receives real-time filing alerts.
Automatically reconnects on disconnect and catches up on missed messages.
"""

import asyncio
import websockets
import json
import logging
from typing import Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SECWebSocketClient:
    """
    WebSocket client for SEC Digester service.

    Features:
    - Auto-reconnect on disconnect
    - Catch-up on missed messages
    - Heartbeat to keep connection alive
    - Message deduplication
    """

    def __init__(
        self,
        url: str = "ws://localhost:8765/ws/filings",
        on_filing: Optional[Callable] = None
    ):
        self.url = url
        self.on_filing = on_filing
        self.websocket = None
        self.running = False

        # Track processed filings to avoid duplicates
        self.processed_filings = set()
        self.max_cache_size = 1000

    async def connect(self):
        """Connect to SEC Digester service."""
        self.running = True

        while self.running:
            try:
                logger.info(f"Connecting to SEC Digester: {self.url}")

                async with websockets.connect(self.url) as websocket:
                    self.websocket = websocket
                    logger.info("Connected to SEC Digester")

                    # Catch up on recent filings
                    await self._catch_up_recent_filings()

                    # Start heartbeat
                    heartbeat_task = asyncio.create_task(self._heartbeat())

                    # Listen for messages
                    try:
                        async for message in websocket:
                            await self._handle_message(message)
                    except websockets.ConnectionClosed:
                        logger.warning("Connection closed, reconnecting...")
                        heartbeat_task.cancel()

            except Exception as e:
                logger.error(f"Connection error: {e}")

            # Wait before reconnecting
            if self.running:
                logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    async def disconnect(self):
        """Disconnect from service."""
        self.running = False
        if self.websocket:
            await self.websocket.close()

    async def _heartbeat(self):
        """Send periodic heartbeat to keep connection alive."""
        while True:
            try:
                await self.websocket.send("ping")
                await asyncio.sleep(30)  # Every 30 seconds
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break

    async def _catch_up_recent_filings(self):
        """
        Catch up on recent filings after reconnect.

        Fetches last 50 filings via REST API to ensure no missed alerts.
        """
        import aiohttp

        try:
            base_url = self.url.replace("ws://", "http://").replace("/ws/filings", "")

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/api/filings/recent?limit=50") as resp:
                    data = await resp.json()

                    logger.info(f"Catching up on {len(data['filings'])} recent filings")

                    for filing in reversed(data["filings"]):  # Process oldest first
                        await self._handle_filing(filing)

        except Exception as e:
            logger.error(f"Catch-up error: {e}")

    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            msg_type = data.get("type")

            if msg_type == "connected":
                logger.info(f"Server says: {data.get('message')}")

            elif msg_type == "filing_alert":
                await self._handle_filing(data)

            elif msg_type == "pong":
                pass  # Heartbeat response

            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            # Plain text message (like "pong")
            pass

    async def _handle_filing(self, filing: dict):
        """
        Handle incoming filing alert.

        Deduplicates and calls registered callback.
        """
        filing_id = filing.get("filing_id")

        # Deduplicate
        if filing_id in self.processed_filings:
            logger.debug(f"Skipping duplicate: {filing_id}")
            return

        # Add to cache
        self.processed_filings.add(filing_id)

        # Limit cache size
        if len(self.processed_filings) > self.max_cache_size:
            # Remove oldest (simple FIFO, could use LRU)
            self.processed_filings.pop()

        # Log
        logger.info(
            f"New filing: {filing['ticker']} {filing['filing_type']} "
            f"(sentiment: {filing['analysis']['sentiment']:.2f})"
        )

        # Call callback
        if self.on_filing:
            try:
                await self.on_filing(filing)
            except Exception as e:
                logger.error(f"Callback error: {e}")


# ============================================================================
# Usage in Main Bot
# ============================================================================

async def handle_sec_filing(filing: dict):
    """
    Callback for new SEC filings.

    This is where you generate Discord alerts, update database, etc.
    """
    # Extract data
    ticker = filing["ticker"]
    filing_type = filing["filing_type"]
    sentiment = filing["analysis"]["sentiment"]
    summary = filing["analysis"]["summary"]
    priority = filing["analysis"]["priority"]

    # Generate Discord alert
    if priority in ["high", "critical"]:
        await send_discord_alert(
            ticker=ticker,
            filing_type=filing_type,
            sentiment=sentiment,
            summary=summary,
            url=filing["url"]
        )

    # Log to database
    await log_filing_to_db(filing)

    # Update watchlist
    await update_ticker_watchlist(ticker, filing)


async def main():
    """Main bot entry point."""
    # Create SEC WebSocket client
    sec_client = SECWebSocketClient(
        url="ws://sec-digester.yourdomain.com:8765/ws/filings",
        on_filing=handle_sec_filing
    )

    # Start connection (runs forever with auto-reconnect)
    await sec_client.connect()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Message Format

### Filing Alert

```json
{
  "type": "filing_alert",
  "filing_id": "0001234567-25-000123",
  "ticker": "AAPL",
  "filing_type": "8-K",
  "item_code": "2.02",
  "timestamp": "2025-11-17T10:30:00Z",
  "analysis": {
    "sentiment": 0.75,
    "keywords": ["earnings", "beat", "guidance"],
    "summary": "Apple reports Q4 2024 earnings with revenue of $94.9B, beating estimates...",
    "priority": "high",
    "metrics": {
      "revenue": "$94.9B",
      "eps": "$1.52",
      "yoy_growth": "25%"
    }
  },
  "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000001/aapl-8k_20250115.htm"
}
```

### Connection Messages

```json
// On connect
{
  "type": "connected",
  "message": "Connected to SEC Digester",
  "server_time": "2025-11-17T10:00:00Z"
}

// Heartbeat
Client → Server: "ping"
Server → Client: "pong"
```

---

## Deployment

### Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  # SEC Digester Service
  sec-digester:
    build: ./sec_digester_service
    ports:
      - "8765:8765"  # WebSocket
      - "8000:8000"  # REST API (optional)
    environment:
      - REDIS_URL=redis://redis:6379
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - SEC_MONITOR_INTERVAL=300  # 5 minutes
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - sec-network

  # Redis for message persistence
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped
    networks:
      - sec-network

  # Main Catalyst Bot (separate service)
  catalyst-bot:
    build: ./catalyst_bot
    environment:
      - SEC_DIGESTER_URL=ws://sec-digester:8765/ws/filings
      - DISCORD_TOKEN=${DISCORD_TOKEN}
    depends_on:
      - sec-digester
    restart: unless-stopped
    networks:
      - sec-network

networks:
  sec-network:
    driver: bridge

volumes:
  redis-data:
```

### Cloud Deployment (AWS)

```bash
# Deploy SEC Digester to AWS Fargate
aws ecs create-cluster --cluster-name sec-digester-cluster

# Create task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create service
aws ecs create-service \
  --cluster sec-digester-cluster \
  --service-name sec-digester \
  --task-definition sec-digester:1 \
  --desired-count 2 \
  --launch-type FARGATE

# Main bot can run anywhere (local, cloud, etc.)
```

---

## Benefits Summary

### For Development

✅ **Independent testing** - Test SEC service without running main bot
✅ **Faster iteration** - Change LLM prompts without touching bot code
✅ **Clear boundaries** - Document processing vs. trading logic separated

### For Production

✅ **Independent scaling** - Scale SEC service separately from bot
✅ **Deployment flexibility** - SEC in cloud, bot anywhere
✅ **Multiple consumers** - Discord bot, web dashboard, analytics all consume same stream
✅ **Reliability** - Redis Streams ensure no message loss
✅ **Real-time** - <50ms latency for alerts

### For Cost

✅ **Cloud efficiency** - SEC service in cloud (close to LLM APIs, no rate limits)
✅ **Resource optimization** - Main bot doesn't need GPU or heavy processing
✅ **Horizontal scaling** - Add more SEC service instances during high volume

---

## Migration Strategy

### Week 1: Build WebSocket Service
1. Create `sec_digester_service/` directory
2. Implement FastAPI WebSocket server
3. Migrate EDGAR monitoring logic
4. Test locally with simple client

### Week 2: Add Redis Streams
1. Set up Redis infrastructure
2. Implement stream publishing
3. Add catch-up logic
4. Test reconnection scenarios

### Week 3: Update Main Bot
1. Create WebSocket client in main bot
2. Replace direct SEC calls with WebSocket consumption
3. Migrate alert generation
4. Test end-to-end

### Week 4: Production Deployment
1. Deploy SEC service to cloud
2. Deploy Redis
3. Update bot configuration
4. Monitor and optimize

---

## Monitoring & Observability

### Key Metrics

```python
# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram

# Filings processed
filings_processed = Counter(
    'sec_filings_processed_total',
    'Total SEC filings processed',
    ['ticker', 'filing_type']
)

# Active WebSocket connections
active_connections_gauge = Gauge(
    'sec_websocket_connections',
    'Number of active WebSocket connections'
)

# Processing latency
processing_latency = Histogram(
    'sec_filing_processing_seconds',
    'Time to process SEC filing',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# LLM API costs
llm_api_cost = Counter(
    'sec_llm_api_cost_usd',
    'LLM API costs in USD',
    ['provider', 'model']
)
```

### Alerts

```yaml
# Prometheus alerts
groups:
  - name: sec_digester
    rules:
      - alert: NoFilingsProcessed
        expr: rate(sec_filings_processed_total[5m]) == 0
        for: 15m
        annotations:
          summary: "No SEC filings processed in 15 minutes"

      - alert: HighProcessingLatency
        expr: sec_filing_processing_seconds > 10
        for: 5m
        annotations:
          summary: "SEC filing processing taking >10s"

      - alert: LLMCostSpike
        expr: rate(sec_llm_api_cost_usd[1h]) > 5
        annotations:
          summary: "LLM API costs >$5/hour"
```

---

## Cost Impact

### Without WebSocket Service (Current)
- Main bot handles everything
- GPU usage or API calls from bot server
- Hard to scale independently

### With WebSocket Service
- **SEC Service**: $50-100/month (small cloud instance + LLM APIs)
- **Redis**: $10-20/month (managed Redis or small instance)
- **Main Bot**: $10-30/month (lightweight, no heavy processing)
- **Total**: $70-150/month

**Savings**:
- Independent scaling = only scale what you need
- Cloud efficiency = lower API costs (no rate limits)
- Multiple consumers = shared infrastructure cost

---

## Next Steps

### Decision Point

**Should we implement SEC Digester as WebSocket service?**

**My Recommendation**: **YES** ✅

**Why:**
1. Aligns perfectly with cloud-first approach
2. Clean architecture (separation of concerns)
3. Enables multiple consumers (future web dashboard)
4. Independent deployment and scaling
5. Industry standard for real-time financial alerts

**Timeline**: Add 1-2 weeks to implementation plan for WebSocket service

### Updated Implementation Plan

**Phase 1-2: Build WebSocket SEC Service** (Week 1-3)
- Week 1: FastAPI WebSocket server
- Week 2: Redis Streams integration
- Week 3: Client implementation in main bot

**Phase 3-4: LLM Service Integration** (Week 4-5)
- Week 4: Integrate unified LLM service
- Week 5: Sentiment migration

**Phase 5: Production Deployment** (Week 6-7)
- Week 6: Cloud deployment
- Week 7: Monitoring and optimization

**Total**: 7 weeks (same timeline, restructured)

---

## Questions to Resolve

1. **WebSocket vs. gRPC?**
   - WebSocket is simpler, more standard for web
   - gRPC better for service-to-service (but overkill here)
   - **Recommendation**: WebSocket

2. **Message format?**
   - JSON (proposed) - human-readable, easy debugging
   - Protobuf - faster, smaller, but less readable
   - **Recommendation**: JSON for now

3. **Authentication?**
   - API keys for WebSocket connections?
   - OAuth2 if exposing publicly?
   - **Recommendation**: Start without auth (internal only), add later

4. **Multiple SEC services?**
   - One service per filing type?
   - One unified service?
   - **Recommendation**: Unified for now, split if needed

---

## Conclusion

Converting SEC Digester to a WebSocket microservice is an **excellent architectural decision** that:

✅ Fixes your GPU overload (SEC service in cloud)
✅ Enables clean separation of concerns
✅ Supports multiple consumers
✅ Provides real-time streaming (<50ms latency)
✅ Ensures reliable message delivery (Redis Streams)
✅ Simplifies future scaling

**Recommendation**: Proceed with **Option 2 (WebSocket + Redis Streams)** for production reliability.

Ready to implement! 🚀
