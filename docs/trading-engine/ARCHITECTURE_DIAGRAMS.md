# Architecture Diagrams & Visual Reference

Visual representations of the distributed trading system architecture at different scales.

---

## Table of Contents

1. [MVP Architecture](#mvp-architecture)
2. [Small Production Architecture](#small-production-architecture)
3. [Medium Production Architecture](#medium-production-architecture)
4. [Large Production Architecture](#large-production-architecture)
5. [Data Flow Diagrams](#data-flow-diagrams)
6. [Sequence Diagrams](#sequence-diagrams)
7. [Network Architecture](#network-architecture)

---

## MVP Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    SINGLE SERVER                             │
│                 (Railway.app or Local)                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  FastAPI Server (Port 8000)                            │ │
│  │                                                         │ │
│  │  ┌──────────────┐       ┌──────────────┐              │ │
│  │  │  REST API    │       │  WebSocket   │              │ │
│  │  │  /signals    │       │  /ws/{id}    │              │ │
│  │  └──────┬───────┘       └──────┬───────┘              │ │
│  │         │                      │                       │ │
│  │         │      ┌───────────────▼────────────┐          │ │
│  │         └─────▶│  In-Memory Storage         │          │ │
│  │                │  - connections: Dict       │          │ │
│  │                │  - signals: List           │          │ │
│  │                │  - filters: Dict           │          │ │
│  │                └───────────────┬────────────┘          │ │
│  │                                │                       │ │
│  │                ┌───────────────▼────────────┐          │ │
│  │                │  SQLite Database           │          │ │
│  │                │  catalyst_server.db        │          │ │
│  │                │  - signals table           │          │ │
│  │                │  - client_configs table    │          │ │
│  │                └────────────────────────────┘          │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  Catalyst-Bot Integration                        │  │ │
│  │  │  - Publishes signals via HTTP POST /signal       │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │ WebSocket (WSS)
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼──────┐   ┌────▼──────┐   ┌────▼──────┐
    │  Client 1  │   │ Client 2  │   │ Client 3  │
    │            │   │           │   │           │
    │ [Filter]   │   │ [Filter]  │   │ [Filter]  │
    │  0.7 min   │   │  0.8 min  │   │  0.6 min  │
    │  conf      │   │  conf     │   │  conf     │
    └────────────┘   └───────────┘   └───────────┘
```

### Component Responsibilities

```
FastAPI Server:
├─ WebSocket Manager
│  ├─ Accept connections
│  ├─ Authenticate clients
│  ├─ Manage subscriptions
│  └─ Broadcast signals
│
├─ Signal Publisher
│  ├─ Receive from Catalyst-Bot
│  ├─ Validate signals
│  ├─ Store in database
│  └─ Publish to clients
│
└─ Storage
   ├─ SQLite (persistence)
   └─ In-memory (active connections)
```

---

## Small Production Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    DigitalOcean Droplet                          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  nginx Reverse Proxy (Port 80/443)                         │ │
│  │  - SSL/TLS termination                                     │ │
│  │  - Load balancing                                          │ │
│  │  - Static file serving                                     │ │
│  └──────────┬──────────────────────────┬──────────────────────┘ │
│             │                          │                        │
│  ┌──────────▼──────────┐    ┌──────────▼──────────┐            │
│  │  FastAPI Server     │    │  FastAPI Server     │            │
│  │  (Port 8000)        │    │  (Port 8001)        │            │
│  │  - REST API         │    │  - WebSocket        │            │
│  │  - Health checks    │    │  - Real-time push   │            │
│  └──────────┬──────────┘    └──────────┬──────────┘            │
│             │                          │                        │
│             └────────┬─────────────────┘                        │
│                      │                                          │
│         ┌────────────▼────────────┐                             │
│         │  Redis (Port 6379)      │                             │
│         │  - Pub/Sub (signals)    │                             │
│         │  - Cache (market data)  │                             │
│         │  - Session storage      │                             │
│         └────────────┬────────────┘                             │
│                      │                                          │
│         ┌────────────▼────────────┐                             │
│         │  PostgreSQL (Port 5432) │                             │
│         │  - Signals              │                             │
│         │  - User configs         │                             │
│         │  - Audit logs           │                             │
│         └─────────────────────────┘                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Monitoring                                              │  │
│  │  - Prometheus (metrics collection)                       │  │
│  │  - Grafana Cloud (dashboards)                            │  │
│  │  - Sentry (error tracking)                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                          │
                          │ WSS (WebSocket Secure)
          ┌───────────────┼───────────────┐
          │               │               │
    ┌─────▼──────┐  ┌────▼──────┐  ┌────▼──────┐
    │ Client 1   │  │ Client 2  │  │ Client N  │
    │ (Python)   │  │ (Python)  │  │ (Python)  │
    └────────────┘  └───────────┘  └───────────┘
```

### Data Flow

```
1. Signal Generation:
   Catalyst-Bot → HTTP POST → FastAPI → Validate → PostgreSQL
                                        ↓
                                   Redis Pub/Sub
                                        ↓
                                   WebSocket Clients

2. Client Subscription:
   Client → WebSocket → Authenticate → Redis (store filters)
                                     ↓
                                Subscribe to Redis Pub/Sub
                                     ↓
                          Receive filtered signals

3. Caching:
   Request → FastAPI → Check Redis → If miss → PostgreSQL
                         ↓                          ↓
                     Return cached           Cache & return
```

---

## Medium Production Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                        AWS Cloud (Multi-AZ)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Application Load Balancer                                   │  │
│  │  - Health checks                                             │  │
│  │  - SSL termination                                           │  │
│  │  - Sticky sessions (WebSocket)                               │  │
│  └──────┬──────────────────────────────────────┬────────────────┘  │
│         │                                      │                   │
│  ┌──────▼────────────┐              ┌─────────▼─────────────┐     │
│  │  ECS Cluster (AZ-1)│              │  ECS Cluster (AZ-2)   │     │
│  │                   │              │                       │     │
│  │  ┌─────────────┐  │              │  ┌─────────────┐      │     │
│  │  │ API Task    │  │              │  │ API Task    │      │     │
│  │  │ (2 tasks)   │  │              │  │ (2 tasks)   │      │     │
│  │  └──────┬──────┘  │              │  └──────┬──────┘      │     │
│  │         │         │              │         │             │     │
│  │  ┌──────▼──────┐  │              │  ┌──────▼──────┐      │     │
│  │  │ WS Task     │  │              │  │ WS Task     │      │     │
│  │  │ (2 tasks)   │  │              │  │ (2 tasks)   │      │     │
│  │  └──────┬──────┘  │              │  └──────┬──────┘      │     │
│  │         │         │              │         │             │     │
│  │  ┌──────▼──────┐  │              │  ┌──────▼──────┐      │     │
│  │  │ Worker Task │  │              │  │ Worker Task │      │     │
│  │  │ (4 tasks)   │  │              │  │ (4 tasks)   │      │     │
│  │  └──────┬──────┘  │              │  └──────┬──────┘      │     │
│  └─────────┼─────────┘              └─────────┼─────────────┘     │
│            │                                  │                   │
│            └──────────────┬───────────────────┘                   │
│                           │                                       │
│  ┌────────────────────────▼────────────────────────┐              │
│  │  ElastiCache Redis Cluster (3 nodes)           │              │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │              │
│  │  │ Primary  │──│ Replica 1│──│ Replica 2│     │              │
│  │  └──────────┘  └──────────┘  └──────────┘     │              │
│  │  - Redis Streams (event distribution)         │              │
│  │  - Cache (market data, API responses)         │              │
│  │  - Rate limiting counters                     │              │
│  └────────────────────────────────────────────────┘              │
│                           │                                       │
│  ┌────────────────────────▼────────────────────────┐              │
│  │  RDS PostgreSQL (Multi-AZ)                     │              │
│  │  ┌──────────┐           ┌──────────┐           │              │
│  │  │ Primary  │──────────▶│ Standby  │           │              │
│  │  │ (AZ-1)   │           │ (AZ-2)   │           │              │
│  │  └──────────┘           └──────────┘           │              │
│  │         │                                       │              │
│  │  ┌──────▼──────┐                                │              │
│  │  │ Read Replica│                                │              │
│  │  │ (AZ-3)      │                                │              │
│  │  └─────────────┘                                │              │
│  │  - Event store (signals, deliveries)           │              │
│  │  - User configs                                 │              │
│  │  - Audit logs                                   │              │
│  └─────────────────────────────────────────────────┘              │
│                           │                                       │
│  ┌────────────────────────▼────────────────────────┐              │
│  │  InfluxDB (Time-Series)                        │              │
│  │  - Performance metrics                          │              │
│  │  - Signal quality tracking                      │              │
│  │  - User engagement metrics                      │              │
│  └─────────────────────────────────────────────────┘              │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Monitoring & Observability                                  ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     ││
│  │  │CloudWatch│  │ Datadog  │  │  Sentry  │  │PagerDuty │     ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘     ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ WSS
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────▼──────┐  ┌────▼──────┐  ┌────▼──────┐
        │ Client 1   │  │ Client 2  │  │ Client N  │
        │ (50 users) │  │           │  │           │
        └────────────┘  └───────────┘  └───────────┘
```

### Auto-Scaling Configuration

```
ECS Auto-Scaling:
├─ Target Tracking
│  ├─ CPU Utilization: 70%
│  ├─ Memory Utilization: 80%
│  └─ Custom: Active WebSocket Connections / Task
│
├─ Scaling Policies
│  ├─ Scale Out: +2 tasks when above threshold for 2 minutes
│  ├─ Scale In: -1 task when below threshold for 5 minutes
│  └─ Cool Down: 5 minutes
│
└─ Limits
   ├─ Minimum Tasks: 2 (HA)
   ├─ Maximum Tasks: 10 (cost control)
   └─ Desired Tasks: 4 (normal load)
```

---

## Large Production Architecture

### System Overview (Multi-Region)

```
┌────────────────────────────────────────────────────────────────────┐
│                    Global Load Balancer (Route 53)                 │
│                    - Latency-based routing                          │
│                    - Health checks                                  │
│                    - Failover                                       │
└──────────────┬──────────────────────────────────┬───────────────────┘
               │                                  │
    ┌──────────▼──────────────┐      ┌──────────▼──────────────┐
    │   US-EAST-1 (Primary)   │      │   EU-WEST-1 (Secondary) │
    │                         │      │                         │
    │  ┌───────────────────┐  │      │  ┌───────────────────┐  │
    │  │  Application LB   │  │      │  │  Application LB   │  │
    │  └─────────┬─────────┘  │      │  └─────────┬─────────┘  │
    │            │            │      │            │            │
    │  ┌─────────▼─────────┐  │      │  ┌─────────▼─────────┐  │
    │  │  ECS Cluster      │  │      │  │  ECS Cluster      │  │
    │  │  (4-10 tasks)     │  │      │  │  (4-10 tasks)     │  │
    │  │  - Signal Gen     │  │      │  │  - Signal Gen     │  │
    │  │  - API Server     │  │      │  │  - API Server     │  │
    │  │  - WS Server      │  │      │  │  - WS Server      │  │
    │  │  - Workers        │  │      │  │  - Workers        │  │
    │  └─────────┬─────────┘  │      │  └─────────┬─────────┘  │
    │            │            │      │            │            │
    │  ┌─────────▼─────────┐  │      │  ┌─────────▼─────────┐  │
    │  │  Kafka Cluster    │  │      │  │  Kafka Cluster    │  │
    │  │  (3 brokers)      │  │      │  │  (3 brokers)      │  │
    │  │  - Partitions: 10 │  │      │  │  - Partitions: 10 │  │
    │  │  - Replication: 3 │  │      │  │  - Replication: 3 │  │
    │  └─────────┬─────────┘  │      │  └─────────┬─────────┘  │
    │            │            │      │            │            │
    │  ┌─────────▼─────────┐  │      │  ┌─────────▼─────────┐  │
    │  │  Redis Cluster    │  │      │  │  Redis Cluster    │  │
    │  │  (6 nodes)        │  │      │  │  (6 nodes)        │  │
    │  │  3 primaries      │  │      │  │  3 primaries      │  │
    │  │  3 replicas       │  │      │  │  3 replicas       │  │
    │  └─────────┬─────────┘  │      │  └─────────┬─────────┘  │
    │            │            │      │            │            │
    │  ┌─────────▼─────────┐  │      │  ┌─────────▼─────────┐  │
    │  │  RDS Primary      │  │      │  │  RDS Read Replica │  │
    │  │  (Multi-AZ)       │◄─┼──────┼──┤  (Cross-region)   │  │
    │  │  - Write master   │  │      │  │  - Read-only      │  │
    │  └─────────┬─────────┘  │      │  └─────────┬─────────┘  │
    │            │            │      │            │            │
    │  ┌─────────▼─────────┐  │      │  ┌─────────▼─────────┐  │
    │  │  InfluxDB Cluster │  │      │  │  InfluxDB Cluster │  │
    │  │  (3 nodes)        │  │      │  │  (3 nodes)        │  │
    │  └───────────────────┘  │      │  └───────────────────┘  │
    └─────────────────────────┘      └─────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                    Observability Stack                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Datadog  │  │  Sentry  │  │Prometheus│  │  Grafana │           │
│  │ (Metrics)│  │ (Errors) │  │(Alerting)│  │(Dashboards)          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                         │
│  │ELK Stack │  │PagerDuty │  │StatusPage│                         │
│  │  (Logs)  │  │(Alerting)│  │(Status)  │                         │
│  └──────────┘  └──────────┘  └──────────┘                         │
└────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### Signal Generation & Distribution

```
┌─────────────────────────────────────────────────────────────────┐
│                    Signal Generation Flow                        │
└─────────────────────────────────────────────────────────────────┘

1. Feed Aggregation
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │   SEC    │    │GlobeNews │    │  PR Wire │
   │   EDGAR  │    │   RSS    │    │   RSS    │
   └────┬─────┘    └────┬─────┘    └────┬─────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                ┌───────▼──────┐
                │Feed Aggregator│
                │- Deduplication│
                │- Enrichment   │
                └───────┬───────┘
                        │
2. Classification
                ┌───────▼──────┐
                │  Prescale    │
                │  Filtering   │
                │  (keyword)   │
                └───────┬───────┘
                        │ (if score > 0.2)
                ┌───────▼──────┐
                │     LLM      │
                │ Classification│
                └───────┬───────┘
                        │ (if score > 0.7)
                ┌───────▼──────┐
                │  Multi-Factor│
                │   Scoring    │
                │ (RVOL, Fund) │
                └───────┬───────┘
                        │
3. Sequencing
                ┌───────▼──────┐
                │   Sequencer  │
                │ (assign ID)  │
                └───────┬───────┘
                        │
4. Persistence
                ┌───────▼──────┐
                │  Event Store │
                │  (PostgreSQL)│
                └───────┬───────┘
                        │
5. Distribution
                ┌───────▼──────┐
                │ Redis Pub/Sub│
                │   or Kafka   │
                └───────┬───────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   ┌────▼────┐     ┌───▼────┐     ┌───▼────┐
   │Client 1 │     │Client 2│     │Client N│
   │Filter✓  │     │Filter✗ │     │Filter✓ │
   │Receive  │     │Discard │     │Receive │
   └─────────┘     └────────┘     └────────┘
```

### Client Subscription Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client Subscription Flow                      │
└─────────────────────────────────────────────────────────────────┘

1. Connection
   ┌──────────┐
   │  Client  │
   └────┬─────┘
        │ WebSocket connect
        ▼
   ┌────────────┐
   │   Server   │
   └────┬───────┘
        │ Accept connection
        ▼

2. Authentication
   ┌──────────┐
   │  Client  │
   └────┬─────┘
        │ {"type": "auth", "token": "..."}
        ▼
   ┌────────────┐
   │   Server   │
   │  Verify    │
   │   Token    │
   └────┬───────┘
        │ {"type": "welcome", "client_id": "..."}
        ▼

3. Subscription
   ┌──────────┐
   │  Client  │
   └────┬─────┘
        │ {"type": "subscribe", "filters": {...}}
        ▼
   ┌────────────┐
   │   Server   │
   │   Store    │
   │  Filters   │
   └────┬───────┘
        │ {"type": "subscribed"}
        ▼

4. Signal Reception
   ┌────────────┐
   │   Server   │
   │ New Signal │
   └────┬───────┘
        │ Check filters
        ▼
   ┌────────────┐
   │  Matches?  │
   └─┬────────┬─┘
     │ Yes    │ No
     ▼        ▼
   Send    Discard
     │
     ▼
   ┌──────────┐
   │  Client  │
   │ Receive  │
   └──────────┘
```

---

## Sequence Diagrams

### Signal Broadcast Sequence

```
Client1    Client2    WebSocket    Signal      Redis      Database
  │          │         Manager    Publisher      │           │
  │          │            │           │           │           │
  │──Connect─────────────▶│           │           │           │
  │          │            │           │           │           │
  │◄────Welcome───────────│           │           │           │
  │          │            │           │           │           │
  │──Subscribe(filters)──▶│           │           │           │
  │          │            │           │           │           │
  │          │            │──Store────────────────────────────▶│
  │          │            │           │           │           │
  │          │──Connect───────────────▶           │           │
  │          │            │           │           │           │
  │          │◄────Welcome─────────────           │           │
  │          │            │           │           │           │
  │          │            │           │◄──New Signal──────────│
  │          │            │           │           │           │
  │          │            │           │──Validate─────────────▶│
  │          │            │           │           │           │
  │          │            │           │──Publish──▶           │
  │          │            │◄──Signal──────────────│           │
  │          │◄──Signal(filtered)─────│           │           │
  │◄─Signal(filtered)─────│           │           │           │
  │          │            │           │           │           │
```

### Circuit Breaker Sequence

```
Client     API        Circuit      External
           Server     Breaker      Service
  │          │           │            │
  │──Request─▶           │            │
  │          │           │            │
  │          │──Call────▶│            │
  │          │           │            │
  │          │           │──Request──▶│
  │          │           │            │
  │          │           │◄──Success──│
  │          │           │            │
  │          │◄─Response─│            │
  │◄─Response│           │            │
  │          │           │            │
  │──Request─▶           │            │
  │          │──Call────▶│            │
  │          │           │──Request──▶│
  │          │           │            │
  │          │           │◄──Error────│
  │          │           │            │
  │          │           │ (increment fail count)
  │          │◄─Error────│            │
  │◄─Error───│           │            │
  │          │           │            │
  │          │           │ (after N failures)
  │          │           │            │
  │          │      [Circuit OPEN]    │
  │          │           │            │
  │──Request─▶           │            │
  │          │──Call────▶│            │
  │          │◄─Error────│ (circuit open, no call)
  │◄─Error───│           │            │
  │          │           │            │
  │          │    (after timeout)     │
  │          │           │            │
  │          │    [Circuit HALF-OPEN] │
  │          │           │            │
  │──Request─▶           │            │
  │          │──Call────▶│            │
  │          │           │──Request──▶│
  │          │           │◄──Success──│
  │          │           │            │
  │          │    [Circuit CLOSED]    │
  │          │           │            │
  │          │◄─Response─│            │
  │◄─Response│           │            │
```

---

## Network Architecture

### Multi-AZ Deployment (AWS)

```
┌──────────────────────────────────────────────────────────────────┐
│                         AWS Region (us-east-1)                   │
│                                                                  │
│  ┌────────────────────────────┐  ┌────────────────────────────┐│
│  │  Availability Zone 1a      │  │  Availability Zone 1b      ││
│  │                            │  │                            ││
│  │  ┌──────────────────────┐  │  │  ┌──────────────────────┐ ││
│  │  │  Public Subnet       │  │  │  │  Public Subnet       │ ││
│  │  │  10.0.1.0/24        │  │  │  │  10.0.2.0/24        │ ││
│  │  │                      │  │  │  │                      │ ││
│  │  │  ┌────────────────┐  │  │  │  │  ┌────────────────┐ │ ││
│  │  │  │  NAT Gateway   │  │  │  │  │  │  NAT Gateway   │ │ ││
│  │  │  └────────────────┘  │  │  │  │  └────────────────┘ │ ││
│  │  └──────────────────────┘  │  │  └──────────────────────┘ ││
│  │                            │  │                            ││
│  │  ┌──────────────────────┐  │  │  ┌──────────────────────┐ ││
│  │  │  Private Subnet      │  │  │  │  Private Subnet      │ ││
│  │  │  10.0.11.0/24       │  │  │  │  10.0.12.0/24       │ ││
│  │  │                      │  │  │  │                      │ ││
│  │  │  ┌────────────────┐  │  │  │  │  ┌────────────────┐ │ ││
│  │  │  │  ECS Tasks     │  │  │  │  │  │  ECS Tasks     │ │ ││
│  │  │  │  (2-4 tasks)   │  │  │  │  │  │  (2-4 tasks)   │ │ ││
│  │  │  └────────────────┘  │  │  │  │  └────────────────┘ │ ││
│  │  │                      │  │  │  │                      │ ││
│  │  │  ┌────────────────┐  │  │  │  │  ┌────────────────┐ │ ││
│  │  │  │ ElastiCache    │  │  │  │  │  │ ElastiCache    │ │ ││
│  │  │  │ Node (Primary) │  │  │  │  │  │ Node (Replica) │ │ ││
│  │  │  └────────────────┘  │  │  │  │  └────────────────┘ │ ││
│  │  └──────────────────────┘  │  │  └──────────────────────┘ ││
│  │                            │  │                            ││
│  │  ┌──────────────────────┐  │  │  ┌──────────────────────┐ ││
│  │  │  Data Subnet         │  │  │  │  Data Subnet         │ ││
│  │  │  10.0.21.0/24       │  │  │  │  10.0.22.0/24       │ ││
│  │  │                      │  │  │  │                      │ ││
│  │  │  ┌────────────────┐  │  │  │  │  ┌────────────────┐ │ ││
│  │  │  │ RDS Primary    │  │  │  │  │  │ RDS Standby    │ │ ││
│  │  │  │ (Active)       │◄─┼──┼──┼──┼──│ (Sync Replica) │ │ ││
│  │  │  └────────────────┘  │  │  │  │  └────────────────┘ │ ││
│  │  └──────────────────────┘  │  │  └──────────────────────┘ ││
│  └────────────────────────────┘  └────────────────────────────┘│
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Internet Gateway                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       │ Internet
                       │
                ┌──────▼──────┐
                │   Clients   │
                └─────────────┘
```

### Security Groups

```
┌─────────────────────────────────────────────────────────────┐
│                    Security Group Architecture               │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│  ALB Security Group      │
│  ┌────────────────────┐  │
│  │ Inbound:           │  │
│  │  - 443 (0.0.0.0/0) │  │
│  │  - 80 (0.0.0.0/0)  │  │
│  │ Outbound:          │  │
│  │  - All (ECS SG)    │  │
│  └────────────────────┘  │
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  ECS Security Group      │
│  ┌────────────────────┐  │
│  │ Inbound:           │  │
│  │  - 8000 (ALB SG)   │  │
│  │  - 8001 (ALB SG)   │  │
│  │ Outbound:          │  │
│  │  - All (Redis SG)  │  │
│  │  - All (RDS SG)    │  │
│  │  - 443 (Internet)  │  │
│  └────────────────────┘  │
└─────────┬────────────────┘
          │
    ┌─────┴─────┐
    │           │
┌───▼───────┐ ┌─▼───────────┐
│ Redis SG  │ │  RDS SG     │
│┌─────────┐│ │┌───────────┐│
││Inbound: ││ ││Inbound:   ││
││6379(ECS)││ ││5432 (ECS) ││
│└─────────┘│ │└───────────┘│
└───────────┘ └─────────────┘
```

---

## Component Interaction Matrix

```
┌──────────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
│ Component    │ FastAPI │  Redis  │  DB     │ Clients │ Catalyst│
├──────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ FastAPI      │    -    │  R/W    │  R/W    │   WS    │  HTTP   │
├──────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Redis        │   R/W   │    -    │    -    │    -    │    -    │
├──────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Database     │   R/W   │    -    │    -    │    -    │    -    │
├──────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Clients      │   WS    │    -    │    -    │    -    │    -    │
├──────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Catalyst Bot │  HTTP   │    -    │    -    │    -    │    -    │
└──────────────┴─────────┴─────────┴─────────┴─────────┴─────────┘

Legend:
  R/W   = Read and Write
  WS    = WebSocket bidirectional
  HTTP  = HTTP POST requests
  -     = No direct communication
```

---

## Performance Metrics

### Target Latencies by Scale

```
┌──────────────┬──────────┬──────────┬──────────┬──────────┐
│ Metric       │   MVP    │  Small   │  Medium  │  Large   │
├──────────────┼──────────┼──────────┼──────────┼──────────┤
│ Signal Gen   │  < 1s    │  < 500ms │  < 200ms │  < 100ms │
│ to Delivery  │          │          │          │          │
├──────────────┼──────────┼──────────┼──────────┼──────────┤
│ WebSocket    │  < 50ms  │  < 20ms  │  < 10ms  │  < 5ms   │
│ Push Latency │          │          │          │          │
├──────────────┼──────────┼──────────┼──────────┼──────────┤
│ API Response │  < 200ms │  < 100ms │  < 50ms  │  < 20ms  │
│ Time (P95)   │          │          │          │          │
├──────────────┼──────────┼──────────┼──────────┼──────────┤
│ Database     │  < 100ms │  < 50ms  │  < 20ms  │  < 10ms  │
│ Query (P95)  │          │          │          │          │
├──────────────┼──────────┼──────────┼──────────┼──────────┤
│ Cache Hit    │  < 10ms  │  < 5ms   │  < 2ms   │  < 1ms   │
│ Latency      │          │          │          │          │
└──────────────┴──────────┴──────────┴──────────┴──────────┘
```

---

## Disaster Recovery

### Backup Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    Backup Architecture                       │
└─────────────────────────────────────────────────────────────┘

PostgreSQL:
  ├─ Automated Backups: Daily (7-day retention)
  ├─ Manual Snapshots: Before major changes
  ├─ Point-in-Time Recovery: 5-minute granularity
  └─ Cross-Region Replication: Async (15-30 sec lag)

Redis:
  ├─ RDB Snapshots: Every 1 hour
  ├─ AOF Persistence: Every second
  └─ Backup to S3: Daily

InfluxDB:
  ├─ Full Backup: Weekly
  ├─ Incremental Backup: Daily
  └─ Retention: 90 days

Application Logs:
  ├─ CloudWatch Logs: 30 days
  ├─ S3 Archive: 1 year
  └─ Compliance Logs: 7 years
```

---

## Summary

These architecture diagrams provide visual references for:
- System components and their relationships
- Data flow through the system
- Network topology and security
- Scaling patterns at different phases
- Interaction patterns between components

Use these diagrams to:
1. Understand system architecture
2. Plan infrastructure
3. Debug issues
4. Communicate with team
5. Document decisions

**Next Steps:**
- Choose architecture based on your scale
- Review technology decision matrix
- Follow MVP implementation guide
- Deploy and iterate
