# Product Engineering Challenge Submission

## Candidate

- **Name:** Rakshitha M
- **Email:** rakshumathew.2614@gmail.com
- **GitHub:** https://github.com/rakshithamathew
- **Selected problem:** Problem 1 — Resumable Realtime Conversation
- **Repository:** https://github.com/rakshithamathew/Real-Time-Feed
- **Live demo:** https://real-time-feed.vercel.app/
- **Demo video:** Pending recording and upload; use the verified script in [`DEMO.md`](DEMO.md).

## Run the project

### Prerequisites

- Node.js 22.12 or newer and npm
- Python 3.11 or newer
- Docker Desktop with the Compose daemon running
- PowerShell for the commands below

From the repository root:

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

Open http://localhost:5173. API documentation is available at
http://127.0.0.1:8001/docs.

The root `.env.example` contains local-only values. Never commit a populated
`.env` file or production credentials.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` | Docker Compose | Local database user |
| `POSTGRES_PASSWORD` | Docker Compose | Local database password |
| `POSTGRES_DB` | Docker Compose | Local database name |
| `POSTGRES_PORT` | Docker Compose | Host port for local PostgreSQL |
| `DATABASE_URL` | FastAPI and Alembic | SQLAlchemy async PostgreSQL connection URL |
| `TEST_DATABASE_URL` | Backend tests | Isolated integration-test database URL |
| `RUN_DB_TESTS` | Backend tests | Set to `1` to enable database and WebSocket integration tests |
| `FRONTEND_ORIGIN` | FastAPI | Exact browser origin allowed by production CORS |
| `VITE_BACKEND_URL` | React/Vite | Public backend base URL used for REST and WebSocket connections |
| `VITE_BACKEND_TARGET` | Vite development server | Optional local proxy target override |

For local development, Vite proxies `/api`, `/health`, and `/ws` to the backend,
so `VITE_BACKEND_URL` is optional. The production deployment sets it to the
Render service URL.

### Successful scenario

1. Open Client A at http://localhost:5173/?room=incident-001&client=A.
2. Select **Open Client B** and keep both clients in the same room.
3. Wait until both clients show **Connected**.
4. Publish an update from Client A.
5. Confirm both clients show the same stable update ID and server-assigned
   sequence exactly once.

### Recovery scenario

1. With both clients connected, publish one update and note Client B's cursor.
2. Select **Simulate outage** on Client B; it visibly changes to
   **Disconnected**.
3. Publish at least two updates from Client A while B is paused.
4. Select **Resume connection** on B.
5. Confirm B reconnects with its stored cursor and renders every missed update
   once, in ascending server-sequence order.

## Run the tests

Frontend, from `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Backend unit tests, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Full PostgreSQL-backed backend suite, starting at the repository root:

```powershell
docker compose --profile test up -d --wait postgres-test
cd backend
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
```

Observed on September 22, 2026:

- Backend: **50 passed**, with two upstream deprecation warnings.
- Alembic: **No new upgrade operations detected**.
- Ruff lint and format: passed across 26 Python files.
- mypy strict mode: passed across 11 application source files.
- Frontend: **10 passed** across two test files.
- TypeScript, ESLint, and the Vite production build: passed.

## Acceptance scenarios and verification

The submitted product intentionally applies the selected problem's reconnect
protocol to an incident-update feed. A room is the stable conversation scope, an
update UUID is stable event identity, and a database sequence is the cursor.
That interpretation exercises the difficult transport and recovery behavior,
but it does **not** implement the brief's assistant-run domain model. The gaps
below are stated explicitly rather than presenting different criteria as the
official acceptance scenarios.

| Official scenario | Status | Evidence and current behavior |
| --- | --- | --- |
| AC1: ordered live stream ending in `completed` | **Partial** | REST-created events stream once and in order to connected clients. There is no deterministic reply generator or durable run `completed` state. |
| AC2: missed-event recovery | **Completed at the event-stream level** | A client reconnects with `after=<lastSequence>` and receives every later PostgreSQL event. `test_disconnect_gap_and_reconnect_replays_every_missed_update` and the live benchmark verify zero loss. |
| AC3: replay/live overlap | **Completed at the event-stream level** | The server subscribes before replay so live events queue behind replay. The React hook merges by `updateId` and sorts by `sequence`; the overlap unit test verifies one logical row per event. |
| AC4: service restart | **Partial** | PostgreSQL event history survives and can be replayed after a process restart. No in-progress generator/run exists, so the required resumable-or-explicitly-interrupted run policy is not modeled. |
| AC5: generation failure | **Incomplete** | Persistence errors return a sanitized `503`, and WebSocket replay failures close with `1011`, but there is no generator and no durable `failed` run state. |
| AC6: unknown or stale cursor | **Partial** | Negative/out-of-range cursors return `422`. A cursor beyond the latest sequence safely returns an empty page. Retention/expiry is not implemented, so there is no explicit expired-cursor response. |

Additional verified behavior includes room isolation, strict exclusive cursor
boundaries, initial paging, stable UUIDs, database constraints, commit-before-
broadcast semantics, subscriber cleanup, slow-client eviction, bounded retries,
browser offline/online handling, and timer/socket cleanup on room changes.

### Problem-specific verification benchmark

With the backend running locally:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\reconnect_benchmark.py --base-url http://127.0.0.1:8001
```

The submitted benchmark was also executed against the deployed Render backend:

```powershell
.\.venv\Scripts\python.exe scripts\reconnect_benchmark.py --base-url https://real-time-feed.onrender.com
```

Observed live result:

```text
expectedEventCount: 30
observedEventCount: 30
uniqueEventCount: 30
missingEventCount: 0
duplicateEventCount: 0
ordered: true
reconnectCount: 1
historyMatchesDeliveredEvents: true
finalConnectionState: connected-and-current
finalRunState: not-modeled-by-incident-feed-interpretation
```

The interruption occurred after ten events. Ten more were committed while the
socket was disconnected, then replayed after reconnect; the final ten arrived
live. The benchmark uses a unique room per run and checks the durable REST
history against all WebSocket deliveries. It honestly reports that the current
implementation has no assistant-run terminal state.

### Failure/recovery path for the video

The video should use the two-client recovery scenario above. Client B visibly
changes from `connected` to `disconnected`; Client A publishes while B is
paused; B resumes from its last sequence and displays the missed rows once and
in order. Then run the benchmark and show its zero-missing/zero-duplicate report.
The fourth demo requirement should be described as a known gap: durable event
history survives a restart, but in-progress generation state is not modeled.

## Architecture and data flow

```text
React client
  |-- POST /api/rooms/{room}/updates ----------> FastAPI service
  |                                                 |
  |                                                 | transaction
  |                                                 v
  |                                            PostgreSQL
  |                                          durable ordered log
  |                                                 |
  |-- WS /ws/rooms/{room}?after=<cursor> <----------+
            replay first, then queued live fan-out
```

- `App.tsx` submits commands through REST and renders user-visible connection
  state and the ordered event table.
- `useIncidentFeed.ts` owns the WebSocket lifecycle, processed cursor,
  exponential backoff, manual outage control, deduplication, and sorting.
- FastAPI validates HTTP/WebSocket inputs and converts domain failures into
  stable public errors.
- `IncidentFeedService` owns the transaction boundary: persist, commit, then
  broadcast.
- `UpdateRepository` owns SQLAlchemy queries and strict cursor semantics.
- `RoomConnectionManager` owns transient in-process subscriptions and bounded
  per-client queues.
- PostgreSQL is the source of truth for event identity, history, and ordering;
  WebSocket fan-out is only an optimization for low latency.

During reconnect, the server registers the subscriber before reading history.
Events committed during replay enter that subscriber's queue and are drained
after the ordered replay. Replay/live overlap is tolerated because the browser
merges by stable UUID and sorts by server sequence.

## Technology choices

- **FastAPI and async Python:** concise typed HTTP/WebSocket handlers and clear
  async lifecycle control. Node/Express was considered, but Python's FastAPI,
  Pydantic, and SQLAlchemy combination kept validation and API contracts close
  to the domain layer.
- **PostgreSQL and SQLAlchemy:** a database identity column supplies a durable
  total order, while UUIDs supply stable event identity. Redis Streams or Kafka
  would support distributed fan-out, but add operational scope unnecessary for
  a single-process prototype.
- **WebSocket for delivery, REST for commands:** WebSocket supports bidirectional
  connection lifecycle and fast fan-out; REST keeps publishing observable and
  independently retryable. SSE would simplify one-way streaming but would not
  materially reduce the required reconnect/cursor logic.
- **React, TypeScript, and Vite:** TypeScript makes event validation and state
  transitions explicit; Vite keeps development and production builds small.

The accepted trade-off is a single backend process with an in-memory connection
registry. Durability is strong at PostgreSQL; instantaneous live fan-out is not
coordinated across multiple processes.

## Important decisions

1. **Commit before broadcast.** A client never observes an event that cannot be
   replayed. If fan-out fails after commit, reconnect repairs delivery from the
   database.
2. **Register before replay and deduplicate in the client.** This avoids the
   replay/live boundary gap. Any overlap is safe because stable IDs are merged
   and sequences are sorted.
3. **Bound reconnects and slow consumers.** Reconnect uses jittered exponential
   backoff capped at eight attempts. Each subscriber has a bounded queue; an
   overflowed client is disconnected with code `1013` and recovers from its
   cursor instead of blocking publishers.

## Assumptions and limitations

- This is an incident-feed domain adaptation of Problem 1, not a complete chat
  generator. Stable user-message IDs, run IDs, `running/completed/failed` run
  states, partial-generation failure, and generator restart policy are absent.
- There is no event-retention window, so stale/expired cursor handling is not
  implemented. A syntactically valid future cursor returns no events.
- The connection manager and publish locks are process-local. One FastAPI
  process is assumed.
- Authentication, authorization, multi-tenancy, editing, attachments, and
  presence are intentionally out of scope.
- There is no transactional outbox. A crash after commit but before broadcast is
  repaired only when clients reconnect.
- The free Render service can cold-start after inactivity. Its free PostgreSQL
  database is scheduled to expire on October 22, 2026 unless migrated or
  upgraded.
- The production deployment is demonstrative infrastructure, not part of the
  core correctness claim.

## Production and scale

The submitted implementation currently uses one FastAPI process, PostgreSQL as
the durable log, and in-memory WebSocket fan-out. At greater scale I would first:

1. Add the actual conversation/message/run schema and an append-only run-event
   table with explicit terminal-state transition constraints. A leased worker
   would either resume a generator or atomically mark an abandoned running run
   as interrupted after restart.
2. Add a transactional outbox and Redis Streams, NATS JetStream, or Kafka for
   cross-process fan-out. This removes the commit/broadcast crash window and
   allows horizontally scaled WebSocket gateways.
3. Define retention and cursor contracts. Return an explicit recoverable error
   (for example `410 cursor_expired`) when history can no longer satisfy a
   checkpoint, and provide a snapshot/resync path.
4. Add authentication and per-conversation authorization, rate limits,
   structured metrics, distributed tracing, SLOs, alerting, backups, and restore
   drills.
5. Move the frontend and backend to reviewed deployment manifests with pinned
   runtimes, secret rotation, staged migrations, and zero-downtime rollout.

These are proposed improvements; they are not claims about the submitted code.

## AI usage

I used OpenAI Codex as a development assistant for code inspection, deployment
troubleshooting, targeted edits, test/benchmark creation, and documentation. I
reviewed changes through repository diffs, ran the complete frontend suite and
production build, ran the 50-test PostgreSQL-backed backend suite plus Ruff and
strict mypy, and executed the 30-event benchmark against the live deployment.
I remain responsible for the submitted design and should be able to explain or
change every part of it during review.

## Credibility note

I previously built and deployed a
[Collaborative Document Editor](https://github.com/rakshithamathew/Collaborative-Google-Docs),
a Google Docs-inspired full-stack application for creating, importing, editing,
autosaving, and sharing rich-text documents. I implemented the React/TypeScript
client, Express/TypeScript API, MongoDB/Mongoose persistence, Tiptap editor
integration, ownership/sharing model, and TXT/Markdown/DOCX import path. The
public repository contains 16 commits and the application is deployed at
https://collaborative-google-docs-theta.vercel.app/.

Its operational scope is a two-application prototype with MongoDB persistence,
autosave, in-memory file processing up to 5 MB, seeded-user sharing, and separate
frontend/backend builds. An important decision was to store Tiptap's structured
JSON instead of rendered HTML, preserving editor semantics and making future
transformations safer. I deliberately excluded concurrent real-time editing:
without conflict resolution or a CRDT/OT model, presenting it as collaborative
editing would have created misleading data-loss behavior. That boundary kept
the shipped prototype reliable within its stated single-user editing model.
