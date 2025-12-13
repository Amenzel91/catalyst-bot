# MVP Implementation Guide - Weekend Project

**Goal:** Get a working distributed signal server running in one weekend that you and 2-3 friends can use.

**Timeline:** 2 days (16 hours)
**Cost:** $0 (local development) or $30/month (cloud deployment)

---

## Day 1: Core Server (8 hours)

### Hour 1-2: Project Setup

```bash
# 1. Create server directory
cd /home/user/catalyst-bot
mkdir -p src/catalyst_bot/server
touch src/catalyst_bot/server/__init__.py

# 2. Install dependencies
pip install fastapi uvicorn[standard] websockets python-jose[cryptography] sqlalchemy

# 3. Update requirements.txt
cat >> requirements.txt << EOF

# Signal Server (MVP)
fastapi>=0.104.0,<1
uvicorn[standard]>=0.24.0,<1
websockets>=12.0,<13
python-jose[cryptography]>=3.3.0,<4
sqlalchemy>=2.0,<3
EOF

# 4. Create .env for server
cat >> .env << EOF

# Signal Server Configuration
SERVER_DEBUG=true
SERVER_PORT=8000
JWT_SECRET=$(openssl rand -hex 32)
DATABASE_URL=sqlite:///./catalyst_server.db
EOF
```

### Hour 3-4: Minimal FastAPI Server

**src/catalyst_bot/server/main.py:**

```python
"""
Minimal Signal Server - MVP Version
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict
import asyncio
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Catalyst Signal Server MVP")

# Simple in-memory storage
connections: Dict[str, WebSocket] = {}
signals = []


@app.get("/")
async def root():
    """Health check."""
    return {
        "status": "healthy",
        "clients": len(connections),
        "signals": len(signals)
    }


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket for real-time signals."""
    await websocket.accept()
    connections[client_id] = websocket
    logger.info(f"Client connected: {client_id}")

    try:
        # Send welcome
        await websocket.send_json({
            "type": "welcome",
            "client_id": client_id,
            "message": "Connected to Catalyst Signal Server"
        })

        # Listen for messages
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received from {client_id}: {data}")

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_id}")
    finally:
        connections.pop(client_id, None)


@app.post("/signal")
async def publish_signal(signal: dict):
    """Publish signal to all connected clients."""
    signal['timestamp'] = datetime.utcnow().isoformat()
    signals.append(signal)

    # Broadcast to all clients
    disconnected = []
    for client_id, ws in connections.items():
        try:
            await ws.send_json({"type": "signal", "data": signal})
        except Exception as e:
            logger.error(f"Failed to send to {client_id}: {e}")
            disconnected.append(client_id)

    # Cleanup
    for client_id in disconnected:
        connections.pop(client_id, None)

    return {"status": "published", "clients_notified": len(connections) - len(disconnected)}


@app.get("/signals")
async def get_signals(limit: int = 10):
    """Get recent signals."""
    return signals[-limit:]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Test it:**

```bash
# Terminal 1: Run server
python -m catalyst_bot.server.main

# Terminal 2: Test with curl
curl http://localhost:8000/

# Terminal 3: Connect WebSocket client
python -c "
import asyncio
import websockets
import json

async def test():
    async with websockets.connect('ws://localhost:8000/ws/test_client') as ws:
        msg = await ws.recv()
        print('Received:', msg)

        # Listen for signals
        async for message in ws:
            print('Signal:', message)

asyncio.run(test())
"
```

### Hour 5-6: Integrate with Catalyst-Bot

**src/catalyst_bot/server/catalyst_integration.py:**

```python
"""
Integration with existing Catalyst-Bot runner.
"""

import asyncio
import logging
import aiohttp
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class CatalystIntegration:
    """Integrates Catalyst-Bot with signal server."""

    def __init__(self, server_url: str = "http://localhost:8000"):
        self.server_url = server_url

    async def publish_accepted_item(self, item: dict):
        """Publish accepted item as signal to server."""
        # Transform Catalyst item to signal format
        signal = {
            "ticker": item.get("ticker", "UNKNOWN"),
            "signal_type": "BUY",  # Always BUY for catalyst alerts
            "confidence": item.get("llm_score", 0.0),
            "catalyst_type": self._get_catalyst_type(item),
            "source": item.get("source", "UNKNOWN"),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "price": item.get("price"),
            "rvol": item.get("rvol"),
            "sector": item.get("sector"),
            "metadata": {
                "prescale_score": item.get("prescale_score"),
                "keywords": item.get("keywords_matched", []),
            }
        }

        # Send to signal server
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/signal",
                    json=signal
                ) as response:
                    result = await response.json()
                    logger.info("Signal published: %s (notified %d clients)",
                               signal['ticker'], result.get('clients_notified', 0))
        except Exception as e:
            logger.error("Failed to publish signal: %s", str(e))

    def _get_catalyst_type(self, item: dict) -> str:
        """Determine catalyst type from item."""
        title_lower = item.get("title", "").lower()
        keywords = item.get("keywords_matched", [])

        if "FDA" in keywords or "fda" in title_lower:
            return "FDA"
        elif any(k in keywords for k in ["M&A", "merger", "acquisition"]):
            return "M&A"
        elif "earnings" in title_lower:
            return "EARNINGS"
        elif "insider" in keywords:
            return "INSIDER_BUY"
        else:
            return "CATALYST"
```

**Modify runner.py to publish signals:**

```python
# Add to src/catalyst_bot/runner.py

from catalyst_bot.server.catalyst_integration import CatalystIntegration

# Initialize integration (add near top of file)
signal_publisher = CatalystIntegration()

# In the main loop, after accepting an item:
# (Find the section where you call send_alert_safe)

# BEFORE:
# send_alert_safe(item)

# AFTER:
send_alert_safe(item)

# Publish to signal server
if ENABLE_SIGNAL_SERVER:  # Add this config flag
    try:
        run_async(signal_publisher.publish_accepted_item(item))
    except Exception as e:
        logger.error("Failed to publish signal: %s", str(e))
```

**Add config to .env:**

```bash
# Enable signal server integration
ENABLE_SIGNAL_SERVER=true
SIGNAL_SERVER_URL=http://localhost:8000
```

### Hour 7-8: Simple Python Client

**examples/simple_client.py:**

```python
"""
Simple client to receive signals.
"""

import asyncio
import websockets
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Connect and receive signals."""
    client_id = input("Enter your client ID (e.g., friend1): ")
    server_url = "ws://localhost:8000/ws/" + client_id

    logger.info(f"Connecting to {server_url}...")

    async with websockets.connect(server_url) as websocket:
        # Receive welcome
        welcome = await websocket.recv()
        logger.info(f"Connected: {welcome}")

        # Listen for signals
        logger.info("Listening for signals... (Ctrl+C to exit)")

        async for message in websocket:
            data = json.loads(message)

            if data['type'] == 'signal':
                signal = data['data']
                logger.info("=" * 60)
                logger.info("NEW SIGNAL RECEIVED")
                logger.info(f"Ticker: {signal['ticker']}")
                logger.info(f"Type: {signal['signal_type']}")
                logger.info(f"Confidence: {signal['confidence']:.2%}")
                logger.info(f"Catalyst: {signal['catalyst_type']}")
                logger.info(f"Source: {signal['source']}")
                logger.info(f"Title: {signal['title']}")
                if signal.get('price'):
                    logger.info(f"Price: ${signal['price']:.2f}")
                if signal.get('rvol'):
                    logger.info(f"RVOL: {signal['rvol']:.2f}x")
                logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
```

**Test full pipeline:**

```bash
# Terminal 1: Run signal server
python -m catalyst_bot.server.main

# Terminal 2: Run client
python examples/simple_client.py
# Enter client ID: friend1

# Terminal 3: Run Catalyst-Bot (with ENABLE_SIGNAL_SERVER=true)
python -m catalyst_bot.runner --once

# Terminal 4: Manually test signal
curl -X POST http://localhost:8000/signal \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "TEST",
    "signal_type": "BUY",
    "confidence": 0.85,
    "catalyst_type": "FDA",
    "source": "TEST",
    "title": "Test Signal"
  }'
```

---

## Day 2: Features & Deployment (8 hours)

### Hour 1-2: Signal Filtering

**Update server to support per-client filters:**

```python
# In main.py, add:

client_filters: Dict[str, dict] = {}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    # ... existing code ...

    try:
        await websocket.send_json({"type": "welcome", "client_id": client_id})

        while True:
            message = await websocket.receive_json()

            if message.get('type') == 'set_filters':
                # Store filters
                client_filters[client_id] = message['filters']
                await websocket.send_json({
                    "type": "filters_updated",
                    "filters": message['filters']
                })
                logger.info(f"Updated filters for {client_id}: {message['filters']}")

    except WebSocketDisconnect:
        client_filters.pop(client_id, None)
        connections.pop(client_id, None)


def matches_filters(signal: dict, filters: dict) -> bool:
    """Check if signal matches client filters."""
    if not filters:
        return True

    # Min confidence
    if filters.get('min_confidence', 0) > signal.get('confidence', 0):
        return False

    # Catalyst types
    if 'catalyst_types' in filters:
        if signal.get('catalyst_type') not in filters['catalyst_types']:
            return False

    # Max price
    if 'max_price' in filters and signal.get('price'):
        if signal['price'] > filters['max_price']:
            return False

    # Min RVOL
    if 'min_rvol' in filters and signal.get('rvol'):
        if signal['rvol'] < filters['min_rvol']:
            return False

    return True


@app.post("/signal")
async def publish_signal(signal: dict):
    """Publish signal to filtered clients."""
    signal['timestamp'] = datetime.utcnow().isoformat()
    signals.append(signal)

    sent_to = []
    for client_id, ws in connections.items():
        # Check filters
        filters = client_filters.get(client_id, {})
        if not matches_filters(signal, filters):
            continue

        try:
            await ws.send_json({"type": "signal", "data": signal})
            sent_to.append(client_id)
        except Exception as e:
            logger.error(f"Failed to send to {client_id}: {e}")

    return {"status": "published", "sent_to": sent_to}
```

**Update client to set filters:**

```python
# In simple_client.py, after welcome:

# Set filters
filters = {
    'min_confidence': 0.7,
    'catalyst_types': ['FDA', 'M&A'],
    'max_price': 20.0,
    'min_rvol': 1.5
}

await websocket.send(json.dumps({
    'type': 'set_filters',
    'filters': filters
}))

# Wait for confirmation
confirmation = await websocket.recv()
logger.info(f"Filters set: {confirmation}")
```

### Hour 3-4: Basic Authentication

**Add API key authentication:**

```python
# In main.py, add:

from fastapi import HTTPException, Header
from typing import Optional

# API keys (in production, store in database)
VALID_API_KEYS = {
    "catalyst_friend1_key": "friend1",
    "catalyst_friend2_key": "friend2",
    "catalyst_friend3_key": "friend3",
}


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    client_id = VALID_API_KEYS.get(x_api_key)
    if not client_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return client_id


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    x_api_key: Optional[str] = Header(None)
):
    """WebSocket with API key authentication."""
    # Verify API key
    client_id = VALID_API_KEYS.get(x_api_key)
    if not client_id:
        await websocket.close(code=4001, reason="Invalid API key")
        return

    await websocket.accept()
    # ... rest of code ...
```

**Update client to use API key:**

```python
# In simple_client.py:

API_KEY = "catalyst_friend1_key"

async with websockets.connect(
    "ws://localhost:8000/ws",
    extra_headers={"X-API-Key": API_KEY}
) as websocket:
    # ... rest of code ...
```

**Generate API keys for friends:**

```python
# scripts/generate_api_key.py

import secrets

def generate_api_key(client_id: str) -> str:
    """Generate API key for client."""
    random_part = secrets.token_urlsafe(16)
    api_key = f"catalyst_{client_id}_{random_part}"
    return api_key


if __name__ == "__main__":
    client_id = input("Enter client ID: ")
    api_key = generate_api_key(client_id)
    print(f"\nAPI Key for {client_id}:")
    print(f"  {api_key}")
    print(f"\nAdd to server:")
    print(f'  "{api_key}": "{client_id}",')
```

### Hour 5-6: Persistence (SQLite)

**Create database models:**

```python
# src/catalyst_bot/server/database.py

from sqlalchemy import create_engine, Column, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()


class Signal(Base):
    """Signal model."""
    __tablename__ = 'signals'

    id = Column(String, primary_key=True)
    ticker = Column(String, index=True)
    signal_type = Column(String)
    confidence = Column(Float)
    catalyst_type = Column(String, index=True)
    source = Column(String)
    title = Column(String)
    metadata = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ClientConfig(Base):
    """Client configuration."""
    __tablename__ = 'client_configs'

    client_id = Column(String, primary_key=True)
    filters = Column(JSON)
    updated_at = Column(DateTime, default=datetime.utcnow)


# Initialize database
engine = create_engine('sqlite:///catalyst_server.db')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Update server to use database:**

```python
# In main.py:

from .database import Signal, ClientConfig, get_db
from sqlalchemy.orm import Session
from fastapi import Depends
import uuid

@app.post("/signal")
async def publish_signal(signal: dict, db: Session = Depends(get_db)):
    """Publish and persist signal."""
    # Add ID and timestamp
    signal['id'] = str(uuid.uuid4())
    signal['timestamp'] = datetime.utcnow()

    # Save to database
    db_signal = Signal(
        id=signal['id'],
        ticker=signal['ticker'],
        signal_type=signal['signal_type'],
        confidence=signal['confidence'],
        catalyst_type=signal['catalyst_type'],
        source=signal['source'],
        title=signal.get('title', ''),
        metadata=signal.get('metadata', {}),
        timestamp=signal['timestamp']
    )
    db.add(db_signal)
    db.commit()

    # Broadcast
    # ... existing broadcast code ...

    return {"status": "published", "signal_id": signal['id']}


@app.get("/signals")
async def get_signals(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get recent signals from database."""
    signals = db.query(Signal).order_by(
        Signal.timestamp.desc()
    ).limit(limit).all()

    return [
        {
            "id": s.id,
            "ticker": s.ticker,
            "signal_type": s.signal_type,
            "confidence": s.confidence,
            "catalyst_type": s.catalyst_type,
            "timestamp": s.timestamp.isoformat()
        }
        for s in signals
    ]
```

### Hour 7: Cloud Deployment

**Option A: DigitalOcean Droplet ($6/month)**

```bash
# 1. Create droplet (Ubuntu 22.04, $6/month smallest)
# 2. SSH into droplet
ssh root@your-droplet-ip

# 3. Install dependencies
apt update
apt install -y python3.11 python3-pip git nginx

# 4. Clone repository
git clone https://github.com/yourusername/catalyst-bot.git
cd catalyst-bot

# 5. Install Python dependencies
pip3 install -r requirements.txt

# 6. Create systemd service
cat > /etc/systemd/system/catalyst-server.service << EOF
[Unit]
Description=Catalyst Signal Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/catalyst-bot
ExecStart=/usr/local/bin/uvicorn catalyst_bot.server.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 7. Start service
systemctl daemon-reload
systemctl enable catalyst-server
systemctl start catalyst-server

# 8. Configure nginx reverse proxy
cat > /etc/nginx/sites-available/catalyst << EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
}
EOF

ln -s /etc/nginx/sites-available/catalyst /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# 9. Get SSL certificate (optional but recommended)
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

**Option B: Railway.app (Free tier, then $5/month)**

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize project
cd catalyst-bot
railway init

# 4. Create Procfile
echo "web: uvicorn catalyst_bot.server.main:app --host 0.0.0.0 --port \$PORT" > Procfile

# 5. Deploy
railway up

# 6. Set environment variables
railway variables set JWT_SECRET=$(openssl rand -hex 32)
railway variables set DATABASE_URL=sqlite:///./catalyst_server.db

# 7. Get URL
railway open
```

### Hour 8: Documentation & Testing

**Create README for friends:**

```markdown
# Catalyst Signal Client - Setup Guide

## Installation

1. Install Python 3.10+
2. Install dependencies:
   ```bash
   pip install websockets aiohttp
   ```

3. Download client script:
   ```bash
   curl -O https://your-server.com/client.py
   ```

## Configuration

Create `config.json`:
```json
{
  "api_key": "YOUR_API_KEY_HERE",
  "server_url": "wss://your-server.com/ws",
  "filters": {
    "min_confidence": 0.7,
    "catalyst_types": ["FDA", "M&A", "EARNINGS"],
    "max_price": 20.0,
    "min_rvol": 1.5
  }
}
```

## Usage

```bash
python client.py
```

## Filters

Customize your signal filters in `config.json`:

- **min_confidence**: Minimum signal confidence (0.0-1.0)
- **catalyst_types**: Types of catalysts to receive (FDA, M&A, EARNINGS, etc.)
- **max_price**: Maximum stock price
- **min_rvol**: Minimum relative volume

## Support

Contact: your-email@example.com
```

**Test with friends:**

```bash
# 1. Send API keys to friends
# 2. Share client.py script
# 3. Help them set up config.json
# 4. Test connection
# 5. Run Catalyst-Bot and verify they receive signals
```

---

## Quick Reference

### Start Everything

```bash
# Terminal 1: Signal Server
python -m catalyst_bot.server.main

# Terminal 2: Catalyst-Bot Runner
python -m catalyst_bot.runner --loop

# Terminal 3: Monitor logs
tail -f data/logs/runner.log
```

### Check Status

```bash
# Server health
curl http://localhost:8000/

# Recent signals
curl http://localhost:8000/signals

# Connected clients
curl http://localhost:8000/ | jq '.clients'
```

### Troubleshooting

**WebSocket won't connect:**
```bash
# Check server is running
curl http://localhost:8000/

# Check firewall
sudo ufw allow 8000/tcp

# Check logs
journalctl -u catalyst-server -f
```

**No signals received:**
```bash
# Verify Catalyst-Bot is running
ps aux | grep catalyst

# Check if signals are being published
curl http://localhost:8000/signals | jq '.[0]'

# Verify client filters aren't too restrictive
```

---

## Next Steps After MVP

1. **Add user management** - Registration, password reset
2. **Add rate limiting** - Prevent abuse
3. **Add monitoring** - Grafana dashboards
4. **Scale infrastructure** - Move to ECS/Kubernetes
5. **Add billing** - Stripe integration (if monetizing)

---

## Cost Breakdown

**Free (Local Development):**
- Server: Your machine
- Clients: Friends' machines
- Database: SQLite
- **Total: $0/month**

**Cheap Cloud:**
- DigitalOcean Droplet $6/month
- Domain $12/year ($1/month)
- **Total: $7/month**

**Production Cloud:**
- AWS EC2 t3.small: $15/month
- RDS PostgreSQL db.t3.micro: $15/month
- CloudWatch: $5/month
- **Total: $35/month**

---

## Success Criteria

MVP is complete when:
- ✅ Server runs and accepts WebSocket connections
- ✅ Catalyst-Bot publishes signals to server
- ✅ Multiple clients can connect simultaneously
- ✅ Clients receive filtered signals in real-time
- ✅ System runs for 24+ hours without crashes
- ✅ Friends successfully receive and use signals

**Time to first signal: < 4 hours**
**Time to production-ready: < 16 hours**
