# Acceptance coverage for Problem 1

This project applies the resumable-stream protocol to an incident feed. It
implements durable ordered events, reconnect cursors, replay/live handoff, and
client deduplication, but it does not implement the complete assistant-run domain
from **Problem 1: Resumable Realtime Conversation**. The table uses the official
acceptance scenarios and labels the differences explicitly.

| Official scenario | Status | Automated or manual evidence |
| --- | --- | --- |
| AC1: ordered live stream and completed run | Partial | `test_rest_publish_reaches_another_live_client_in_the_same_room` verifies ordered live delivery of committed events. No reply generator or `completed` run state exists. |
| AC2: missed-event recovery | Complete at event-stream level | `test_disconnect_gap_and_reconnect_replays_every_missed_update` records a cursor, disconnects, commits three events, reconnects, and asserts every missed event arrives once in ascending order. |
| AC3: replay/live overlap | Complete at event-stream level | The server registers before replay and queues concurrent live events. `deduplicates replay and live overlap after reconnecting` verifies the hook's UUID merge and sequence ordering. |
| AC4: service restart | Partial | PostgreSQL history remains replayable after restart. In-progress generator recovery/interruption is not modeled because there is no run entity. |
| AC5: generation failure | Incomplete | Persistence failure is sanitized to `503`, and replay failure closes with `1011`; no generator or durable `failed` state exists. |
| AC6: unknown or stale cursor | Partial | Negative/out-of-range cursors return `422`; future cursors safely return an empty page. Retention and explicit expired-cursor errors are not implemented. |

Additional tests cover strict cursor boundaries, initial paging, room isolation,
stable UUIDs, database constraints, transaction behavior, disconnect cleanup,
slow-subscriber eviction, bounded retry/backoff, offline/online transitions, and
socket/timer cleanup.

## Deterministic 30-event reconnect benchmark

With the backend running:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\reconnect_benchmark.py --base-url http://127.0.0.1:8001
```

The benchmark publishes ten events over a live socket, disconnects, commits ten
events during the interruption, reconnects from the processed cursor, and then
receives ten more live events. It compares all WebSocket deliveries with the
durable REST history.

Observed against `https://real-time-feed.onrender.com` on September 22, 2026:

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

The benchmark therefore verifies the submitted reconnect protocol, while
explicitly not claiming the problem brief's missing assistant-run state machine.

## Full verification

From the repository root:

```powershell
docker compose --profile test up -d --wait postgres-test
cd backend
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

Observed result: **50 tests passed** with two upstream deprecation warnings.
Alembic found no pending operations; Ruff and strict mypy passed.

Frontend, from `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Observed result: **10 tests passed** across two files. TypeScript, ESLint, and
the Vite production build passed.
