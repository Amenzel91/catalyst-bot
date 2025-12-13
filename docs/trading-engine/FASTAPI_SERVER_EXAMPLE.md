# FastAPI Signal Server - Implementation Example

This document provides a complete, production-ready FastAPI server implementation for distributing Catalyst-Bot signals via WebSocket and REST API.

## Table of Contents

1. [Server Structure](#server-structure)
2. [Core Server Implementation](#core-server-implementation)
3. [WebSocket Manager](#websocket-manager)
4. [Authentication](#authentication)
5. [Rate Limiting](#rate-limiting)
6. [Signal Publisher](#signal-publisher)
7. [Client Example](#client-example)
8. [Deployment](#deployment)

---

## Server Structure

```
src/catalyst_bot/
├── server/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── websocket_manager.py    # WebSocket connection management
│   ├── signal_publisher.py     # Signal distribution
│   ├── auth.py                 # Authentication
│   ├── rate_limiter.py         # Rate limiting
│   ├── models.py               # Pydantic models
│   └── config.py               # Server configuration
├── runner.py                   # Existing Catalyst runner
└── ...
```

---

## Core Server Implementation

**src/catalyst_bot/server/main.py:**

```python
"""
FastAPI server for Catalyst signal distribution.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, List
import asyncio
import logging
from datetime import datetime

from .websocket_manager import WebSocketManager
from .signal_publisher import SignalPublisher
from .auth import verify_token, verify_api_key
from .rate_limiter import RateLimiter
from .models import Signal, UserConfig, SignalFilter, TradeOutcome
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize FastAPI app
app = FastAPI(
    title="Catalyst Signal API",
    version="1.0.0",
    description="Real-time trading signal distribution via WebSocket and REST"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize managers
ws_manager = WebSocketManager()
signal_publisher = SignalPublisher(ws_manager)
rate_limiter = RateLimiter()


# =============================================================================
# WebSocket Endpoints
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None
):
    """
    WebSocket endpoint for real-time signal streaming.

    Query params:
        token: JWT authentication token

    Messages from client:
        - {"type": "auth", "token": "..."}
        - {"type": "subscribe", "filters": {...}}
        - {"type": "pong"}

    Messages to client:
        - {"type": "signal", "data": {...}}
        - {"type": "heartbeat"}
        - {"type": "error", "message": "..."}
    """
    client_id = None

    try:
        # Accept connection
        await websocket.accept()
        logger.info("websocket_connection_accepted")

        # Authenticate
        if not token:
            # Wait for auth message
            auth_msg = await websocket.receive_json()
            if auth_msg.get('type') != 'auth':
                await websocket.send_json({'type': 'error', 'message': 'Authentication required'})
                await websocket.close(code=4001)
                return
            token = auth_msg.get('token')

        # Verify token
        client_id = await verify_token(token)
        if not client_id:
            await websocket.send_json({'type': 'error', 'message': 'Invalid token'})
            await websocket.close(code=4001)
            return

        # Check rate limit
        if not rate_limiter.check_connection_limit(websocket.client.host):
            await websocket.send_json({'type': 'error', 'message': 'Rate limit exceeded'})
            await websocket.close(code=4029)
            return

        # Register connection
        await ws_manager.connect(client_id, websocket)
        logger.info("websocket_authenticated client_id=%s", client_id)

        # Send welcome message
        await websocket.send_json({
            'type': 'welcome',
            'client_id': client_id,
            'timestamp': datetime.utcnow().isoformat()
        })

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(
            ws_manager.heartbeat_loop(client_id, websocket)
        )

        # Handle incoming messages
        while True:
            message = await websocket.receive_json()
            msg_type = message.get('type')

            # Check message rate limit
            if not rate_limiter.check_message_limit(client_id):
                await websocket.send_json({
                    'type': 'error',
                    'message': 'Message rate limit exceeded (8/sec)'
                })
                continue

            if msg_type == 'subscribe':
                # Update signal filters
                filters = message.get('filters', {})
                await ws_manager.update_filters(client_id, filters)
                await websocket.send_json({
                    'type': 'subscribed',
                    'filters': filters
                })
                logger.info("subscription_updated client_id=%s filters=%s", client_id, filters)

            elif msg_type == 'pong':
                # Update last pong time
                await ws_manager.update_pong(client_id)

            elif msg_type == 'feedback':
                # Handle trade outcome feedback
                await signal_publisher.process_feedback(
                    client_id,
                    message.get('signal_id'),
                    message.get('outcome')
                )

            else:
                await websocket.send_json({
                    'type': 'error',
                    'message': f'Unknown message type: {msg_type}'
                })

    except WebSocketDisconnect:
        logger.info("websocket_disconnected client_id=%s", client_id)
    except Exception as e:
        logger.error("websocket_error client_id=%s err=%s", client_id, str(e), exc_info=True)
    finally:
        # Cleanup
        if client_id:
            heartbeat_task.cancel()
            await ws_manager.disconnect(client_id)


# =============================================================================
# REST API Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'connected_clients': ws_manager.get_connection_count()
    }


@app.get("/api/v1/signals", response_model=List[Signal])
async def get_signals(
    limit: int = 50,
    since: Optional[str] = None,
    ticker: Optional[str] = None,
    user_id: str = Depends(verify_api_key)
):
    """
    Get recent signals.

    Query params:
        - limit: Maximum number of signals to return (default: 50, max: 100)
        - since: ISO timestamp to get signals after
        - ticker: Filter by ticker symbol

    Returns:
        List of signals matching criteria
    """
    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 100")

    signals = await signal_publisher.get_signals(
        user_id=user_id,
        limit=limit,
        since=since,
        ticker=ticker
    )

    return signals


@app.get("/api/v1/signals/{signal_id}", response_model=Signal)
async def get_signal(
    signal_id: str,
    user_id: str = Depends(verify_api_key)
):
    """Get specific signal by ID."""
    signal = await signal_publisher.get_signal(signal_id)

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    return signal


@app.post("/api/v1/config")
async def update_config(
    config: UserConfig,
    user_id: str = Depends(verify_api_key)
):
    """Update user configuration."""
    await ws_manager.update_config(user_id, config.dict())

    return {
        'status': 'updated',
        'user_id': user_id,
        'config': config.dict()
    }


@app.get("/api/v1/config", response_model=UserConfig)
async def get_config(
    user_id: str = Depends(verify_api_key)
):
    """Get user configuration."""
    config = await ws_manager.get_config(user_id)

    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    return UserConfig(**config)


@app.post("/api/v1/feedback")
async def submit_feedback(
    outcome: TradeOutcome,
    user_id: str = Depends(verify_api_key)
):
    """
    Submit trade execution outcome.

    This feedback is used to improve signal quality.
    """
    await signal_publisher.process_feedback(
        user_id,
        outcome.signal_id,
        outcome.dict()
    )

    return {'status': 'received'}


@app.get("/api/v1/stats")
async def get_stats(
    user_id: str = Depends(verify_api_key)
):
    """Get user statistics."""
    stats = await signal_publisher.get_user_stats(user_id)
    return stats


# =============================================================================
# Server Lifecycle
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize server on startup."""
    logger.info("server_starting")

    # Start signal publisher
    await signal_publisher.start()

    # Start background tasks
    asyncio.create_task(signal_publisher.signal_broadcast_loop())

    logger.info("server_started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("server_stopping")

    # Disconnect all clients
    await ws_manager.disconnect_all()

    # Stop signal publisher
    await signal_publisher.stop()

    logger.info("server_stopped")


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error("unhandled_exception path=%s err=%s", request.url.path, str(exc), exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            'error': 'Internal server error',
            'message': str(exc) if settings.debug else 'An error occurred'
        }
    )


# =============================================================================
# Run Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "catalyst_bot.server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )
```

---

## WebSocket Manager

**src/catalyst_bot/server/websocket_manager.py:**

```python
"""
WebSocket connection manager.
"""

from fastapi import WebSocket
from typing import Dict, Optional, Set
from datetime import datetime, timedelta
import asyncio
import logging
import json

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and subscriptions."""

    def __init__(self):
        # Active connections: client_id -> WebSocket
        self.connections: Dict[str, WebSocket] = {}

        # Client filters: client_id -> filter dict
        self.filters: Dict[str, dict] = {}

        # Client configs: client_id -> config dict
        self.configs: Dict[str, dict] = {}

        # Last pong timestamp: client_id -> datetime
        self.last_pong: Dict[str, datetime] = {}

        # Database connection (would be initialized from config)
        self.db = None  # TODO: Initialize database connection

    async def connect(self, client_id: str, websocket: WebSocket):
        """Register new WebSocket connection."""
        self.connections[client_id] = websocket
        self.last_pong[client_id] = datetime.utcnow()

        # Load user config from database
        config = await self._load_config(client_id)
        self.configs[client_id] = config
        self.filters[client_id] = config.get('filters', {})

        logger.info("client_connected client_id=%s total_clients=%d",
                   client_id, len(self.connections))

    async def disconnect(self, client_id: str):
        """Remove WebSocket connection."""
        if client_id in self.connections:
            del self.connections[client_id]
            del self.last_pong[client_id]
            logger.info("client_disconnected client_id=%s total_clients=%d",
                       client_id, len(self.connections))

    async def disconnect_all(self):
        """Disconnect all clients (for server shutdown)."""
        for client_id in list(self.connections.keys()):
            try:
                ws = self.connections[client_id]
                await ws.close(code=1001, reason="Server shutting down")
            except Exception as e:
                logger.error("disconnect_error client_id=%s err=%s", client_id, str(e))
            finally:
                await self.disconnect(client_id)

    async def send_to_client(self, client_id: str, message: dict):
        """Send message to specific client."""
        ws = self.connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error("send_failed client_id=%s err=%s", client_id, str(e))
                await self.disconnect(client_id)

    async def broadcast(self, message: dict, filter_func=None):
        """Broadcast message to all connected clients (with optional filter)."""
        disconnected = []

        for client_id, ws in self.connections.items():
            # Apply filter if provided
            if filter_func and not filter_func(client_id):
                continue

            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error("broadcast_failed client_id=%s err=%s", client_id, str(e))
                disconnected.append(client_id)

        # Cleanup disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)

    async def broadcast_signal(self, signal: dict):
        """Broadcast signal to clients matching their filters."""
        async def should_receive_signal(client_id: str) -> bool:
            """Check if client should receive this signal."""
            filters = self.filters.get(client_id, {})

            # Check min confidence
            min_confidence = filters.get('min_confidence', 0.0)
            if signal['confidence'] < min_confidence:
                return False

            # Check ticker filter
            if 'tickers' in filters:
                if signal['ticker'] not in filters['tickers']:
                    return False

            # Check catalyst types
            if 'catalyst_types' in filters:
                if signal['catalyst_type'] not in filters['catalyst_types']:
                    return False

            # Check sectors
            if 'sectors' in filters:
                if signal.get('sector') not in filters['sectors']:
                    return False

            # Check min RVOL
            min_rvol = filters.get('min_rvol')
            if min_rvol and signal.get('rvol', 0) < min_rvol:
                return False

            # Check max price
            max_price = filters.get('max_price')
            if max_price and signal.get('price', float('inf')) > max_price:
                return False

            return True

        # Send to matching clients
        sent_count = 0
        for client_id in list(self.connections.keys()):
            if await should_receive_signal(client_id):
                await self.send_to_client(client_id, {
                    'type': 'signal',
                    'data': signal
                })
                sent_count += 1

        logger.info("signal_broadcast signal_id=%s sent_to=%d clients",
                   signal['signal_id'], sent_count)

    async def update_filters(self, client_id: str, filters: dict):
        """Update client signal filters."""
        self.filters[client_id] = filters

        # Persist to database
        await self._save_filters(client_id, filters)

    async def update_config(self, client_id: str, config: dict):
        """Update client configuration."""
        self.configs[client_id] = config

        # Persist to database
        await self._save_config(client_id, config)

    async def get_config(self, client_id: str) -> Optional[dict]:
        """Get client configuration."""
        return self.configs.get(client_id)

    async def update_pong(self, client_id: str):
        """Update last pong timestamp."""
        self.last_pong[client_id] = datetime.utcnow()

    async def heartbeat_loop(self, client_id: str, websocket: WebSocket):
        """Send periodic heartbeat and check for stale connections."""
        while True:
            try:
                # Wait 30 seconds
                await asyncio.sleep(30)

                # Send ping
                await websocket.send_json({'type': 'heartbeat'})

                # Check last pong
                last = self.last_pong.get(client_id)
                if last and (datetime.utcnow() - last).seconds > 120:
                    # No pong for 2 minutes - disconnect
                    logger.warning("heartbeat_timeout client_id=%s", client_id)
                    await websocket.close(code=4000, reason="Heartbeat timeout")
                    break

            except Exception as e:
                logger.error("heartbeat_error client_id=%s err=%s", client_id, str(e))
                break

    def get_connection_count(self) -> int:
        """Get number of connected clients."""
        return len(self.connections)

    # Database methods (to be implemented with actual DB)
    async def _load_config(self, client_id: str) -> dict:
        """Load user config from database."""
        # TODO: Implement database query
        return {}

    async def _save_config(self, client_id: str, config: dict):
        """Save user config to database."""
        # TODO: Implement database insert/update
        pass

    async def _save_filters(self, client_id: str, filters: dict):
        """Save user filters to database."""
        # TODO: Implement database insert/update
        pass
```

---

## Signal Publisher

**src/catalyst_bot/server/signal_publisher.py:**

```python
"""
Signal publisher - integrates with Catalyst-Bot runner.
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta
import json
import uuid

from catalyst_bot.runner import run_once  # Existing Catalyst runner
from .websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class SignalPublisher:
    """Publishes signals from Catalyst-Bot to connected clients."""

    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self.signal_queue = asyncio.Queue()
        self.running = False

        # In-memory signal storage (for REST API)
        # In production, use database
        self.signals = []
        self.max_signals = 1000

    async def start(self):
        """Start signal publisher."""
        self.running = True
        logger.info("signal_publisher_started")

    async def stop(self):
        """Stop signal publisher."""
        self.running = False
        logger.info("signal_publisher_stopped")

    async def signal_broadcast_loop(self):
        """Background task to process and broadcast signals."""
        while self.running:
            try:
                # Run Catalyst-Bot classification once
                # This integrates with your existing runner.py
                signals = await self._run_catalyst_once()

                # Publish each signal
                for signal in signals:
                    await self.publish_signal(signal)

                # Wait before next run (e.g., 5 minutes)
                await asyncio.sleep(300)

            except Exception as e:
                logger.error("signal_broadcast_error err=%s", str(e), exc_info=True)
                await asyncio.sleep(60)  # Wait 1 min on error

    async def _run_catalyst_once(self) -> List[dict]:
        """
        Run Catalyst-Bot classification once and return signals.

        This wraps your existing runner.py logic.
        """
        # TODO: Integrate with your existing runner.py
        # For now, return mock signals
        return [
            {
                'signal_id': str(uuid.uuid4()),
                'ticker': 'ABCD',
                'signal_type': 'BUY',
                'confidence': 0.85,
                'catalyst_type': 'FDA',
                'source': 'SEC_8K',
                'price': 12.50,
                'rvol': 2.3,
                'sector': 'Healthcare',
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': {}
            }
        ]

    async def publish_signal(self, signal: dict):
        """Publish signal to all subscribed clients."""
        # Add to signal history
        self.signals.insert(0, signal)
        if len(self.signals) > self.max_signals:
            self.signals = self.signals[:self.max_signals]

        # Broadcast to WebSocket clients
        await self.ws_manager.broadcast_signal(signal)

        logger.info("signal_published signal_id=%s ticker=%s confidence=%.2f",
                   signal['signal_id'], signal['ticker'], signal['confidence'])

    async def get_signals(self, user_id: str, limit: int = 50,
                         since: Optional[str] = None,
                         ticker: Optional[str] = None) -> List[dict]:
        """Get recent signals with filters."""
        filtered = self.signals

        # Filter by timestamp
        if since:
            since_dt = datetime.fromisoformat(since)
            filtered = [s for s in filtered
                       if datetime.fromisoformat(s['timestamp']) > since_dt]

        # Filter by ticker
        if ticker:
            filtered = [s for s in filtered if s['ticker'] == ticker]

        # Apply user filters
        user_filters = self.ws_manager.filters.get(user_id, {})
        if user_filters:
            # Apply min confidence
            min_conf = user_filters.get('min_confidence', 0)
            filtered = [s for s in filtered if s['confidence'] >= min_conf]

        # Limit results
        return filtered[:limit]

    async def get_signal(self, signal_id: str) -> Optional[dict]:
        """Get specific signal by ID."""
        for signal in self.signals:
            if signal['signal_id'] == signal_id:
                return signal
        return None

    async def process_feedback(self, user_id: str, signal_id: str, outcome: dict):
        """Process trade execution outcome feedback."""
        logger.info("feedback_received user_id=%s signal_id=%s outcome=%s",
                   user_id, signal_id, outcome)

        # TODO: Store feedback in database
        # TODO: Update signal quality metrics
        # TODO: Feed back into MOA analyzer

    async def get_user_stats(self, user_id: str) -> dict:
        """Get user statistics."""
        # TODO: Calculate from database
        return {
            'signals_received': 0,
            'trades_executed': 0,
            'win_rate': 0.0,
            'avg_return': 0.0
        }
```

---

## Authentication

**src/catalyst_bot/server/auth.py:**

```python
"""
Authentication for Catalyst Signal API.
"""

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets

from .config import get_settings

settings = get_settings()
security = HTTPBearer()

# In-memory API key storage (use database in production)
API_KEYS = {
    'test_key_123': 'user_1',
    'test_key_456': 'user_2',
}


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify API key from Authorization header."""
    api_key = credentials.credentials

    user_id = API_KEYS.get(api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return user_id


async def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return user_id."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=['HS256']
        )

        # Check expiration
        exp = datetime.fromisoformat(payload['exp'])
        if datetime.utcnow() > exp:
            return None

        return payload['user_id']

    except jwt.InvalidTokenError:
        return None


def create_token(user_id: str, expiry_hours: int = 24) -> str:
    """Create JWT token for user."""
    payload = {
        'user_id': user_id,
        'exp': (datetime.utcnow() + timedelta(hours=expiry_hours)).isoformat(),
        'iat': datetime.utcnow().isoformat()
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm='HS256')
    return token


def generate_api_key() -> str:
    """Generate new API key."""
    return 'catalyst_' + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()
```

---

## Configuration

**src/catalyst_bot/server/config.py:**

```python
"""
Server configuration.
"""

from pydantic import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Server settings."""

    # Server
    debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000"]

    # Authentication
    jwt_secret: str = "change_this_secret_in_production"

    # Database
    database_url: str = "sqlite:///./catalyst.db"
    redis_url: str = "redis://localhost:6379"

    # Rate Limiting
    max_connections_per_ip: int = 300
    max_messages_per_client_per_sec: int = 8

    class Config:
        env_file = ".env"


_settings = None


def get_settings() -> Settings:
    """Get singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

---

## Client Example

**examples/signal_client.py:**

```python
"""
Example client for connecting to Catalyst Signal Server.
"""

import asyncio
import websockets
import json
import logging
from typing import Callable, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CatalystClient:
    """Client for Catalyst Signal Server."""

    def __init__(self, api_key: str, ws_url: str = "ws://localhost:8000/ws"):
        self.api_key = api_key
        self.ws_url = ws_url
        self.ws = None
        self.signal_handler = None
        self.token = None

    async def connect(self):
        """Connect to WebSocket server."""
        # In production, get JWT token from REST API first
        # For now, use API key as token
        self.token = self.api_key

        self.ws = await websockets.connect(
            f"{self.ws_url}?token={self.token}"
        )
        logger.info("Connected to %s", self.ws_url)

    async def subscribe(self, signal_handler: Callable, filters: Optional[dict] = None):
        """Subscribe to signals with optional filters."""
        self.signal_handler = signal_handler

        # Send subscription with filters
        if filters:
            await self.ws.send(json.dumps({
                'type': 'subscribe',
                'filters': filters
            }))

        # Listen for messages
        async for message in self.ws:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'signal':
                # Handle signal
                await self.signal_handler(data['data'])

            elif msg_type == 'heartbeat':
                # Respond to heartbeat
                await self.ws.send(json.dumps({'type': 'pong'}))

            elif msg_type == 'welcome':
                logger.info("Authenticated: %s", data)

            elif msg_type == 'error':
                logger.error("Server error: %s", data['message'])

    async def send_feedback(self, signal_id: str, outcome: dict):
        """Send trade execution outcome."""
        await self.ws.send(json.dumps({
            'type': 'feedback',
            'signal_id': signal_id,
            'outcome': outcome
        }))

    async def close(self):
        """Close connection."""
        if self.ws:
            await self.ws.close()


# =============================================================================
# Example Usage
# =============================================================================

async def handle_signal(signal: dict):
    """Handle incoming trading signal."""
    logger.info("Received signal: %s - %s (%.2f confidence)",
               signal['ticker'],
               signal['signal_type'],
               signal['confidence'])

    # Your trading logic here
    if signal['confidence'] >= 0.8:
        logger.info("HIGH CONFIDENCE SIGNAL - Consider executing")


async def main():
    """Main client loop."""
    client = CatalystClient(api_key="test_key_123")

    try:
        # Connect
        await client.connect()

        # Subscribe with filters
        filters = {
            'min_confidence': 0.7,
            'catalyst_types': ['FDA', 'M&A', 'EARNINGS'],
            'min_rvol': 1.5,
            'max_price': 20.0
        }

        await client.subscribe(handle_signal, filters)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Deployment

### Development

```bash
# Install dependencies
pip install fastapi uvicorn python-jose[cryptography] websockets

# Run server
python -m catalyst_bot.server.main

# Or with uvicorn
uvicorn catalyst_bot.server.main:app --reload --host 0.0.0.0 --port 8000
```

### Production (systemd)

**catalyst-server.service:**

```ini
[Unit]
Description=Catalyst Signal Server
After=network.target

[Service]
Type=simple
User=catalyst
WorkingDirectory=/home/catalyst/catalyst-bot
Environment="PATH=/home/catalyst/catalyst-bot/.venv/bin"
ExecStart=/home/catalyst/catalyst-bot/.venv/bin/uvicorn catalyst_bot.server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Install service
sudo cp catalyst-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable catalyst-server
sudo systemctl start catalyst-server

# Check status
sudo systemctl status catalyst-server

# View logs
sudo journalctl -u catalyst-server -f
```

### Production (Docker)

```bash
# Build
docker build -t catalyst-signal-server -f Dockerfile.server .

# Run
docker run -d \
  --name catalyst-server \
  -p 8000:8000 \
  -e JWT_SECRET=your_secret_here \
  -e DATABASE_URL=postgresql://... \
  catalyst-signal-server
```

---

## Testing

```bash
# Test WebSocket connection
pip install websockets

python -c "
import asyncio
import websockets
import json

async def test():
    async with websockets.connect('ws://localhost:8000/ws?token=test_key_123') as ws:
        # Wait for welcome
        msg = await ws.recv()
        print('Received:', msg)

        # Subscribe
        await ws.send(json.dumps({
            'type': 'subscribe',
            'filters': {'min_confidence': 0.7}
        }))

        # Listen for signals
        async for message in ws:
            print('Signal:', message)

asyncio.run(test())
"
```

---

## Next Steps

1. Integrate with existing `runner.py` in `signal_broadcast_loop()`
2. Add database for persistent storage (PostgreSQL or SQLite)
3. Implement proper authentication with user registration
4. Add comprehensive error handling
5. Set up monitoring and logging
6. Deploy to production environment
