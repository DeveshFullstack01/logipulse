# LogiPulse — Real-Time Logistics Control Tower

An operations screen for a shipping fleet. Vessel events stream through Kafka
into two independent workers; one maintains current state, the other watches
for trouble. The Angular dashboard updates over a WebSocket without polling.

Built as a one-week project to demonstrate event-driven architecture rather
than another CRUD application.

---

## Architecture

```
              ┌──────────────────┐
              │ Shipment         │   walks each vessel along its
              │ Simulator        │   great-circle route, emits events
              └────────┬─────────┘
                       │  keyed by shipment_number
                       ▼
              ┌──────────────────┐
              │ Kafka            │   topic: shipment-events (3 partitions)
              │ (Redpanda)       │   durable, replayable log
              └────────┬─────────┘
              ┌────────┴────────┐
              │                 │      two consumer groups,
              ▼                 ▼      independent offsets
      ┌───────────────┐  ┌──────────────┐
      │ state-worker  │  │ alert-worker │
      └───┬───────┬───┘  └──────┬───────┘
          │       │             │
          ▼       ▼             ▼
     ┌────────┐ ┌──────────────────┐
     │ Redis  │ │ PostgreSQL       │
     │ live   │ │ event log,       │
     │ state  │ │ shipments,alerts │
     └───┬────┘ └────────┬─────────┘
         │ pub/sub       │
         ▼               ▼
      ┌─────────────────────┐
      │ FastAPI             │  REST + WebSocket
      └──────────┬──────────┘
                 ▼
      ┌─────────────────────┐
      │ Angular             │  live chart, manifest, analysis
      └─────────────────────┘
```

### Why each piece is here

**Kafka, not a queue.** A queue hands each message to exactly one consumer.
Here two workers need *every* event: one to track position, one to detect
delays. Adding a third consumer later changes nothing about the first two.

**Partitioned by shipment number.** Kafka guarantees ordering within a
partition, not across a topic. Keying by shipment number keeps each vessel's
events on one partition, so a `DELAYED` can never overtake a later position
report and leave the dashboard showing stale state.

**Redis for current state.** The dashboard asks for the position of every
active vessel on each load. Rebuilding that from thousands of log entries per
request would be absurd; Redis answers it in one round trip.

**PostgreSQL for the log.** Every event is appended and never mutated, which
is what makes the per-shipment timeline possible — and what would make replay
possible, since current state is derived rather than authoritative.

**Redis pub/sub between workers and API.** The workers are separate OS
processes and cannot touch FastAPI's WebSocket objects. They publish to a
channel; each API instance subscribes and fans out to its own clients. This is
also why running several API replicas needs no extra work.

---

## Running it

Requires Docker, Python 3.12, and Node 20+.

```bash
# 1. infrastructure
docker compose up -d
docker exec -it logipulse-redpanda rpk topic create shipment-events -p 3

# 2. backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy ..\.env .env                 # macOS/Linux: cp ../.env .env
python seed.py
```

Then four processes, each in its own terminal:

```bash
uvicorn app.main:app --reload --port 8000   # API + WebSocket
python -m workers.state_worker              # position -> Redis + event log
python -m workers.alert_worker              # delay + stale detection
python -m simulator.shipment_simulator      # generates the fleet
```

```bash
# 3. frontend
cd frontend && npm install && ng serve
```

| | |
|---|---|
| Dashboard | http://localhost:4200 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Kafka console | http://localhost:8090 |

### Reset to a fresh fleet

```bash
docker exec -it logipulse-postgres psql -U logipulse -d logipulse -c "TRUNCATE shipment_events, alerts, shipments RESTART IDENTITY CASCADE;"
docker exec -it logipulse-redis redis-cli FLUSHALL
python seed.py
```

---

## Tests

```bash
cd backend && pytest
```

34 tests against a real Postgres and Redis rather than mocks — the behaviour
worth testing (an `ON CONFLICT` insert, an atomic `SADD`) is behaviour of those
systems, and a mock would only assert that the mock works.

They cover idempotent ingestion under message redelivery, alert deduplication
and auto-resolution, the API surface, and the great-circle geometry that the
simulator and the map both depend on.

---

## Failure handling

| Condition | Behaviour |
|---|---|
| Worker crashes mid-batch | Kafka redelivers; the `event_id` unique index makes reprocessing a no-op |
| Duplicate event | `ON CONFLICT DO NOTHING`; the row is not written twice |
| Malformed message | Logged and skipped; the consumer keeps running |
| Redis down | `/health` reports degraded; the dashboard falls back to Postgres aggregates |
| Redis pub/sub drops | The API's bridge reconnects on a timer rather than dying silently |
| WebSocket closes | Dead sockets are dropped from the broadcast set on the next send |
| Browser reconnects | Receives a full snapshot on connect, not only subsequent deltas |

---

## Notes on the demo

The **chaos panel** writes to a Redis key the simulator reads each tick.
Congesting a port produces real `SHIPMENT_DELAYED` events that travel the full
pipeline — Kafka, both workers, Redis, WebSocket — and surface as alerts about
eight seconds later. Nothing is faked in the UI.

Two things are demo affordances rather than production choices, and are worth
saying out loud:

- The simulator compresses a multi-day voyage into 8–30 minutes of wall clock,
  so every route stays visible during a demo.
- Stale detection therefore measures **real** elapsed seconds
  (`stale_after_seconds`, default 45) rather than simulated hours.

---

## Not built

Deliberately out of scope for one week: authentication, real carrier
integrations, route optimisation, Kubernetes, and ETA prediction. The event log
would support replay — rebuilding the dashboard at any past moment — which is
the most interesting thing left undone.

## Stack

Angular 20 (standalone, signals, zoneless) · Leaflet · FastAPI · SQLAlchemy 2 ·
PostgreSQL 16 · Redis 7 · Redpanda (Kafka API) · aiokafka · pytest · Docker Compose
