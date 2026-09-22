# Room WebSocket protocol

Connect to:

```text
WS /ws/rooms/{room_id}?after={last_processed_sequence}
```

`after` defaults to 0 and is an exclusive, nonnegative BIGINT cursor. The server
validates room IDs exactly as the REST API does. Each message uses one envelope:

```json
{
  "type": "update",
  "data": {
    "updateId": "76e944c2-3be1-4fab-b265-ce180024e27f",
    "roomId": "incident-001",
    "content": "Investigating elevated error rate",
    "createdAt": "2026-09-18T11:30:00+00:00",
    "sequence": 42
  }
}
```

PostgreSQL is the durable source of truth. The in-memory connection manager only
tracks sockets and bounded per-connection queues for this FastAPI process. It
keeps subscribers in exact room-ID sets and broadcasts only to the matching set.
There is no Redis, cross-process fan-out, or durable in-memory event buffer.

## Connection and replay ordering

The server accepts and registers a socket before querying PostgreSQL. It then:

1. Reads every persisted row for the room with `sequence > after`, paging through
   the existing ordered repository query.
2. Sends that replay in ascending sequence order.
3. Drains live events accumulated in the connection's queue during replay.
4. Continues consuming that queue until disconnect.

This closes the replay/live loss window. An update committed during replay is
either visible to the database query, present in the live queue, or both. The
overlap deliberately permits duplicate delivery. For example, replay may send
sequences 41 and 42 and the queue may then repeat 41 and 42, temporarily moving
backward. Clients must merge events by stable `updateId`, sort the merged feed by
`sequence`, and persist the greatest sequence they have processed. Sequence, not
timestamp, remains the recovery cursor.

POST publishing is serialized by room within this one process from identity
allocation through commit and queue fan-out. This prevents two concurrent writes
to one room from committing/broadcasting in reverse sequence order. The REST
response and queue fan-out occur only after a successful PostgreSQL commit.

Publishing performs only nonblocking queue insertion; it never writes to a socket.
Each connection has a 256-event queue. If that queue fills, the manager removes
the slow subscriber immediately and schedules a WebSocket close with code 1013.
The client reconnects with its last processed sequence and recovers from
PostgreSQL. Send failures and disconnect frames also remove the subscriber safely.

No application heartbeat was added. The endpoint watches incoming disconnect
frames while waiting for queued events, and normal WebSocket/TCP liveness plus
cursor-based reconnect is sufficient for this single-process assessment.

## Verification

Using the isolated PostgreSQL 17 database on port 5433, from `backend/`:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Tests cover two same-room subscribers receiving one committed update, replay
strictly after a cursor, cross-room isolation, disconnect cleanup, and a bounded
slow subscriber that does not block a healthy subscriber. No schema change was
needed; WebSocket replay uses migration `0001_incident_updates`.

Final result: **49 tests passed** against PostgreSQL 17. Alembic reported no
pending upgrade or model/migration drift. Ruff lint, Ruff format, and strict mypy
passed. The frontend proxy change also passed TypeScript checking and ESLint.
The two test warnings come from the current Starlette test client compatibility
layer and do not affect the application protocol or test results.
