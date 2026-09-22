# Demo video script (3–5 minutes)

Record Chrome with both production clients visible. Upload the result to Loom,
YouTube, Google Drive, or another publicly accessible service, verify it in an
incognito window, and replace the pending video value in `SUBMISSION.md`.

## 0:00–0:35 — Scope and architecture

Open https://real-time-feed.vercel.app/ and say:

> I selected Problem 1 and implemented its durable ordered reconnect protocol
> as an incident-update feed. React owns connection state and cursor-based merge;
> FastAPI persists through SQLAlchemy; PostgreSQL is the source of truth; and
> WebSocket is transient low-latency delivery. The documented limitation is that
> this version does not model assistant message/run IDs or terminal run states.

Briefly show the architecture diagram in `SUBMISSION.md`.

## 0:35–1:20 — Successful live path

1. Wait for Client A to show **Connected**.
2. Select **Open Client B** and arrange both Chrome windows side by side.
3. Publish `Live verification from Client A`.
4. Point out that both clients display the same UUID and sequence once.
5. Explain that PostgreSQL assigns ordering and the service commits before
   broadcasting.

## 1:20–2:30 — Failure and recovery

1. On Client B, select **Simulate outage**.
2. Point out the visible **Disconnected** state and retained last sequence.
3. Publish `Missed update one` and `Missed update two` from Client A.
4. Select **Resume connection** on Client B.
5. Show B returning to **Connected** with both events present once and ordered.
6. Explain that reconnect sends `after=<lastSequence>`, the server subscribes
   before replay, and the browser deduplicates by stable update ID.

## 2:30–3:25 — Verification benchmark

From `backend/`, run:

```powershell
.\.venv\Scripts\python.exe scripts\reconnect_benchmark.py --base-url https://real-time-feed.onrender.com
```

Show the report and call out:

- 30 expected and 30 observed events
- zero missing events
- zero duplicate events
- ascending order
- one reconnect
- durable history matching WebSocket delivery

State clearly that `finalRunState` is reported as
`not-modeled-by-incident-feed-interpretation`; do not present that requirement
as complete.

## 3:25–4:15 — Tests and trade-off

Show the commands/results in `SUBMISSION.md`: 50 backend tests, 10 frontend
tests, Alembic check, Ruff, mypy, TypeScript, ESLint, and the production build.

Explain one trade-off:

> I kept WebSocket membership in process and PostgreSQL as the durable log. That
> is simple and correct for one server, but multiple servers would need a
> transactional outbox plus shared pub/sub. I prioritized the replay contract
> over adding distributed infrastructure to a prototype.

## 4:15–4:40 — Honest limitations

End by showing the acceptance table in `SUBMISSION.md`. Mention that durable
event history survives a service restart, while an in-progress reply generator,
terminal `completed`/`failed` state, and explicit expired-cursor response are not
implemented. This is the required restart/failure discussion for the current
submission; it is a disclosed gap, not a demonstrated complete scenario.

## Permission check

Before submitting:

1. Open the video link in a Chrome incognito window.
2. Confirm it plays without requesting access.
3. Open the repository and live demo while signed out.
4. Paste the verified video URL near the top of `SUBMISSION.md`.
