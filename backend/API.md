# Incident feed REST API

The API is served under `/api`. It persists updates and provides ordered recovery;
live room delivery is provided by the WebSocket endpoint documented in
[WEBSOCKETS.md](WEBSOCKETS.md).

## Publish an update

```http
POST /api/rooms/{room_id}/updates
Content-Type: application/json

{"content":"Investigating elevated error rate","clientId":"A"}
```

A valid request returns HTTP 201 after the database transaction commits:

```json
{
  "sequence": 42,
  "updateId": "76e944c2-3be1-4fab-b265-ce180024e27f",
  "roomId": "incident-001",
  "clientId": "A",
  "content": "Investigating elevated error rate",
  "createdAt": "2026-09-18T11:30:00+00:00"
}
```

The service constructs the accepted event after the insert is flushed, commits,
and only then returns it. A later broadcaster must use that post-commit boundary.
The body accepts `content` and the publishing `clientId`; clients cannot choose
UUIDs, sequences, timestamps, or a room different from the path.

## Read and replay updates

```http
GET /api/rooms/{room_id}/updates?after={sequence}&limit={limit}
```

The default `after` is 0 and the default `limit` is 50. Limits are bounded to
1 through 200. Results always use exact room matching, the exclusive predicate
`sequence > after`, and ascending sequence order.

```json
{
  "updates": [],
  "latestSequence": 42,
  "hasMore": false
}
```

- Omitted `after` and `after=0` behave identically: they start at the beginning
  of the room's retained history.
- `latestSequence` is the greatest durable sequence in that room, independent of
  the page size. It is 0 when the room has no updates.
- `hasMore` is true when the room contains an update after the final item in this
  page. Continue with that final item's sequence as the next `after` cursor.
- A cursor equal to or greater than `latestSequence` returns an empty update list
  with `hasMore: false`; `latestSequence` still reports the room's actual maximum.

Validation failures return HTTP 422 with a stable `validation_error` envelope.
Persistence failures return HTTP 503 with `feed_unavailable`. Unexpected errors
return HTTP 500 with `internal_error`. Responses contain a short public message
and never expose exception text or stack traces.

## Verification

The isolated PostgreSQL 17 cluster described in [PERSISTENCE.md](PERSISTENCE.md)
was started on port 5433. From `backend/`, the exact database test command was:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers successful publishing, blank content, omitted/zero initial
cursors, bounded paging, replay after an exclusive cursor, deterministic ascending
order, equal and greater-than-latest cursors, empty rooms, and two-room isolation.

Formatting and type checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

REST milestone result: **43 tests passed** against PostgreSQL 17. Alembic reported no
pending upgrade or model/migration drift. Ruff lint, Ruff format, and strict mypy
all passed. No migration was required for the REST layer; it uses the existing
`0001_incident_updates` schema.
