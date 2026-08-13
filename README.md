# LogiPulse — Real-Time Logistics Control Tower

Event-driven shipment monitoring. Simulator → Kafka → independent workers → Redis (live state) + Postgres (event log) → FastAPI → WebSocket → Angular.

## Day 1 setup

### 0. Prerequisites
- Docker Desktop (running)
- Python 3.11+
- Node 20+ and `npm i -g @angular/cli`
- VS Code extensions: **Python**, **Angular Language Service**, **Docker**

### 1. Infrastructure
```bash
cd logipulse
cp .env.example .env
docker compose up -d
docker compose ps        # all four should be running/healthy
```
Check: Redpanda Console at http://localhost:8090

### 2. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env .env
python seed.py                   # creates tables + 8 routes + 120 shipments
uvicorn app.main:app --reload --port 8000
```
Check: http://localhost:8000/health → `{"status":"healthy", ...}`
Check: http://localhost:8000/docs

### 3. Create the Kafka topic
```bash
docker exec -it logipulse-redpanda rpk topic create shipment-events -p 3
docker exec -it logipulse-redpanda rpk topic list
```
Three partitions, keyed by shipment ID → per-shipment ordering is guaranteed.

### 4. Frontend
```bash
cd ..
ng new frontend --standalone --routing --style=scss --ssr=false
cd frontend
npm i leaflet @types/leaflet
ng serve
```
Check: http://localhost:4200

### 5. VS Code workspace
Open the `logipulse` folder (not `backend` or `frontend` separately).
Select the interpreter: `Ctrl/Cmd+Shift+P` → *Python: Select Interpreter* → `./backend/.venv`

## Day 1 done when
- [ ] `docker compose ps` shows postgres, redis, redpanda, console
- [ ] `/health` returns healthy for both dependencies
- [ ] `seed.py` printed 8 routes and 120 shipments
- [ ] `shipment-events` topic exists with 3 partitions
- [ ] Angular dev server loads
- [ ] Everything committed to git

## Build order
| Day | Deliverable |
|-----|-------------|
| 1 | Infra, models, seed, both servers running |
| 2 | Simulator + Kafka producer |
| 3 | State worker → Redis → pub/sub → WebSocket |
| 4 | Alert worker + dashboard/analytics APIs |
| 5 | Angular dashboard + Leaflet live map |
| 6 | Shipment detail + charts + Chaos Panel / Replay |
| 7 | Tests, degradation handling, docs, demo video |

No new features after Day 6.
