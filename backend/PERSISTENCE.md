# Incident-update persistence

`app/models.py` defines `IncidentUpdate`; migration
`alembic/versions/0001_incident_updates.py` creates its table and index.

- `sequence`: PostgreSQL `BIGINT GENERATED ALWAYS AS IDENTITY` primary key.
- `update_id`: required native UUID with a unique constraint; the repository's
  ORM insert generates UUID v4 on the server, never from request input.
- `room_id`: required text, nonblank, at most 128 characters. Identifiers are
  compared exactly, including case and whitespace; no trimming merges rooms.
- `content`: required text, nonblank, at most 10,000 characters; formatting is preserved.
- `created_at`: required `TIMESTAMP WITH TIME ZONE`, database default `now()`.
  It is metadata, never the recovery cursor.
- B-tree index `(room_id, sequence)` supports room-scoped cursor and initial-window queries.

Pydantic request schemas reject blank/whitespace-only strings, negative or
out-of-BIGINT cursors, and limits outside 1–200 (default 50). Database CHECK
constraints also reject empty/whitespace-only values and excessive lengths.
Response validation requires a timezone-aware timestamp and supports ORM attributes.

`UpdateRepository(session)` exposes:

| Operation | Behavior |
| --- | --- |
| `create_update(room_id, content)` | Validate, add, flush; return database-generated fields. |
| `get_updates_after(room_id, after_sequence, limit=50)` | Exact room match, exclusive `sequence > cursor`, ascending order, bounded page. |
| `get_initial_updates(room_id, limit=50)` | Latest N updates for that exact room, returned in ascending sequence order. |

The initial query uses descending order only inside its window-selection subquery;
every returned feed is explicitly ordered by sequence ascending. Missing rooms and
cursors at or beyond the newest update return empty lists. Sequence gaps are valid.

The caller owns the transaction. `create_update` flushes but does not commit;
use `async with session.begin():` or commit explicitly. An update is accepted only
after commit, and any future live delivery must occur after commit. Use separate
sessions per concurrent task. Identity allocation alone does not ensure commit
order across concurrent writers: the future publishing layer must serialize each
room's insert-through-commit/delivery path before treating a delivered sequence as
a recovery watermark. The later REST layer now publishes after commit; WebSocket
behavior remains unimplemented.
See PostgreSQL's [sequence documentation](https://www.postgresql.org/docs/17/functions-sequence.html).

## Verification commands

From `incident-feed/`, the normal test infrastructure command is:

```powershell
docker compose --profile test up -d --wait postgres-test
```

Docker Desktop could not start in this environment. Native PostgreSQL 17 was
available, so these exact fallback commands created an isolated cluster using
the configured test database name and port (no existing PostgreSQL service was changed):

```powershell
New-Item -ItemType Directory -Force .local\postgres-test | Out-Null
Set-Content -LiteralPath .local\postgres-test\password.txt -Value 'incident_feed' -Encoding ascii
& 'C:\Program Files\PostgreSQL\17\bin\initdb.exe' -D .local\postgres-test\data -U incident_feed --pwfile=.local\postgres-test\password.txt --auth=scram-sha-256 --encoding=UTF8 --locale=C
& 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe' -D .local\postgres-test\data -l .local\postgres-test\server.log -o '-h 127.0.0.1 -p 5433' -w start
$env:PGPASSWORD = 'incident_feed'
& 'C:\Program Files\PostgreSQL\17\bin\createdb.exe' -h 127.0.0.1 -p 5433 -U incident_feed incident_feed_test
```

From `backend/`:

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

Integration fixtures use `TEST_DATABASE_URL` (loaded from environment/root `.env`)
and wrap each test in a transaction that is rolled back, including tests that
exercise session commit/rollback via savepoints. Tests cover sequence ordering
with equal timestamps, latest-N ordering, exclusive cursors, missing rooms,
exact room isolation, UUID uniqueness, generated fields, validation boundaries,
database constraints, and transaction behavior.

The migration round trip was also verified against this isolated test database
(these commands intentionally remove and recreate its incident table):

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test'
.\.venv\Scripts\python.exe -m alembic downgrade base
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

Results: **36 tests passed, none skipped** against PostgreSQL 17. Upgrade,
downgrade/re-upgrade, and metadata drift checks passed (`0001_incident_updates`
at head, no new operations detected). Ruff lint/format, strict mypy, and
`docker compose --profile test config --quiet` passed. Existing Starlette/AnyIO
deprecation warnings and a sandbox-related Pytest cache-permission warning did
not affect tests. Frontend code was unchanged.

After verification, the temporary server was stopped from `incident-feed/`:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe' -D .local\postgres-test\data -m fast -w stop
```

Its files remain under ignored `.local/`. To rerun with native PostgreSQL, use
the `pg_ctl start` command above; initialization and database creation are
one-time steps. Alternatively, use the Compose test service while this native
server is stopped.
