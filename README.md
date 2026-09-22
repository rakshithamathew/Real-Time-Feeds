# Reconnecting Real-Time Incident Feed

An interview-sized incident feed that combines durable, ordered updates with
low-latency room notifications and cursor-based recovery. REST submits commands;
WebSocket delivers transient live events; PostgreSQL remains the durable source
of truth.

> **Challenge scope:** This is an incident-feed adaptation of Problem 1's
> resumable event-stream protocol. It does not model assistant run IDs or
> `running`/`completed`/`failed` run states. See [SUBMISSION.md](SUBMISSION.md)
> for the official acceptance-scenario mapping, observed benchmark results, and
> explicitly incomplete requirements.

## Problem and architecture

Clients must see incident updates quickly, survive a dropped connection, avoid
duplicates, and recover without losing events. WebSocket was selected for
low-latency server push and explicit connection lifecycle handling. Publishing
uses REST to separate command submission from transient event delivery.

```mermaid
flowchart LR
  A[React client] -->|POST update| API[FastAPI]
  A <-->|WS room + after cursor| API
  API -->|commit, sequence, replay| DB[(PostgreSQL)]
  API -->|in-process room queues| WS[Connected clients]
```

PostgreSQL assigns the `sequence`, which determines deterministic ordering.
Each update also has a stable `updateId` for deduplication. The client’s
centralized merge function deduplicates by `updateId`, sorts by `sequence`, and
retains the highest successfully processed server sequence for reconnects.

The server registers a connection before replay to avoid missing the replay/live
boundary. Replay and live delivery may overlap; ID-based deduplication makes that
overlap safe. Publishing is serialized per room in one process, committed before
fan-out, and delivered through bounded per-connection queues.

## Technology choices

- Backend: Python 3.11+, FastAPI, Uvicorn, SQLAlchemy async, asyncpg, Alembic.
- Frontend: React 19, TypeScript, Vite, Vitest, React Testing Library.
- Data: PostgreSQL 17, with a database identity column for ordering.
- Recovery: exclusive `after` sequence cursor plus stable UUID update IDs.

## Prerequisites and setup

Install Node.js 22.12+ and npm, Python 3.11+, and Docker Desktop with a running
Compose daemon. From `incident-feed/` in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d --wait postgres

cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api`, `/health`, and `/ws` to
`http://127.0.0.1:8001`. API docs are at <http://127.0.0.1:8001/docs>.

## Environment variables

The backend loads the repository-root `.env`; exported variables take precedence.
`.env.example` contains these local-development values:

| Variable | Purpose | Default |
| --- | --- | --- |
| `POSTGRES_USER` | Compose database user | `incident_feed` |
| `POSTGRES_PASSWORD` | Compose database password | `incident_feed` |
| `POSTGRES_DB` | Compose database name | `incident_feed` |
| `POSTGRES_PORT` | Host port mapped to PostgreSQL | `5432` |
| `DATABASE_URL` | Backend async database URL | `postgresql+asyncpg://incident_feed:incident_feed@localhost:5432/incident_feed` |
| `TEST_DATABASE_URL` | Optional integration-test database URL | `postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test` |
| `FRONTEND_ORIGIN` | Exact browser origin allowed by CORS | `http://localhost:5173` |
| `VITE_BACKEND_URL` | Production REST/WebSocket backend origin | Empty locally; Vite uses its proxy |
| `VITE_BACKEND_TARGET` | Optional Vite development proxy target | `http://127.0.0.1:8001` |

Keep `POSTGRES_*` and `DATABASE_URL` aligned. Compose credentials initialize only
a new volume. Do not commit `.env`.

## Migrations and commands

From `backend/` with the virtual environment active (or use the explicit Windows
interpreter path shown above):

```powershell
python -m alembic upgrade head
python -m alembic check
python -m alembic downgrade -1
```

Run the backend with `python -m uvicorn app.main:app --reload --host 127.0.0.1
--port 8001`. Run the frontend from `frontend/` with `npm run dev`; use
`npm run build` for a type-check plus production build and `npm run preview` to
serve that build. Stop PostgreSQL with `docker compose down` (add `--volumes` to
delete its local data).

## Protocol

Publish an update through REST. The server creates `updateId`, `createdAt`, and
the PostgreSQL-assigned `sequence`, then commits before broadcasting:

```http
POST /api/rooms/incident-001/updates
Content-Type: application/json

{"content":"Investigating elevated error rate","clientId":"A"}
```

The `201` response has this shape:

```json
{"sequence":42,"updateId":"76e944c2-3be1-4fab-b265-ce180024e27f","roomId":"incident-001","clientId":"A","content":"Investigating elevated error rate","createdAt":"2026-09-18T11:30:00+00:00"}
```

Recover over REST with an exclusive cursor:

```http
GET /api/rooms/incident-001/updates?after=41&limit=50
```

The response is `{ "updates": [...], "latestSequence": 42, "hasMore": false }`.
Connect for live delivery with the same cursor:

```text
ws://localhost:5173/ws/rooms/incident-001?after=41
```

Each WebSocket message is:

```json
{"type":"update","data":{"updateId":"76e944c2-3be1-4fab-b265-ce180024e27f","roomId":"incident-001","clientId":"A","content":"Investigating elevated error rate","createdAt":"2026-09-18T11:30:00+00:00","sequence":42}}
```

The client reconnects with the highest sequence it successfully processed.
Retries use bounded exponential backoff with jitter, capped at eight retries, so
an outage does not create a tight retry loop.

## Two-client demo

1. Open `http://localhost:5173/?room=incident-001&client=A`.
2. Select **Open Client B** and keep both clients in the same room.
3. Publish from Client A and confirm Client B receives it live.
4. Select **Simulate outage** on Client B.
5. Publish two updates from Client A, then select **Resume connection** on B.
6. Confirm the missed updates replay once and remain in sequence order.

The development UI exposes the cursor and retry state. See [DEMO.md](DEMO.md)
for the longer walkthrough and server log examples.

## Tests and strategy

Frontend commands from `frontend/`:

```powershell
npm run typecheck
npm run lint
npm test
npm run build
```

Backend commands from `backend/`:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

The default backend suite runs without PostgreSQL. For integration coverage,
start the isolated test database from the repository root and run from `backend/`:

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:RUN_DB_TESTS = '1'
python -m alembic upgrade head
python -m pytest
```

Tests cover schemas, health, REST publishing and paging, persistence, room
isolation, replay, multiple subscribers, disconnect cleanup, slow-subscriber
handling, and the React reconnect/merge behavior. Database tests roll back their
work and migrations are applied explicitly.

## Limitations and out of scope

The current connection manager assumes one FastAPI process. Multiple production
servers are out of scope; a multi-server version would require a shared pub/sub
layer, which is intentionally excluded. There is no authentication,
authorization, durable event broker, heartbeat protocol, history retention policy,
editing/deletion, or attachments. The Vercel/Render deployment is a demonstration,
not production infrastructure. A full queue or slow client is disconnected with
WebSocket code 1013 and recovers from PostgreSQL on reconnect. The selected
challenge's assistant generator, stable user-message/run IDs, and terminal run
states are not implemented; [ACCEPTANCE.md](ACCEPTANCE.md) records that gap.
