# Resilient incident feed client

`src/useIncidentFeed.ts` owns one WebSocket lifecycle for its current room. It
connects to `/ws/rooms/{roomId}?after={lastSequence}` using `ws:` or `wss:` to
match the page, and exposes `connecting`, `connected`, `reconnecting`, and
`disconnected` states.

The hook keeps its active socket, retry timer, lifecycle generation, and recovery
cursor in refs so socket callbacks never use a stale cursor or create a second
active connection. Changing rooms or unmounting clears the timer, detaches socket
callbacks, closes the socket, and removes online/offline listeners. Changing rooms
also clears the old room's feed and resets its cursor to zero.

Only valid `update` envelopes for the requested room are processed. The hook keeps
the greatest successfully processed server sequence as its next recovery cursor.
It merges replay and live events in a map keyed by `updateId`, then sorts by
`sequence` (with update ID as a stable tie-breaker). This handles the server's
documented replay/live overlap: duplicate delivery and a temporary sequence
step-back cannot create duplicate or incorrectly ordered rendered rows.

Unexpected closure schedules exponential retries at approximately 500 ms, 1 s,
2 s, 4 s, 8 s, then at most 10 s, with 0.75–1.25 jitter and an eight-retry cap.
The current attempt is visible while reconnecting. A successful open resets the
counter. Exhaustion exposes a manual **Retry** button that starts immediately.

Browser `offline` closes the active socket without scheduling retries and exposes
`disconnected`. Browser `online` reconnects immediately unless the demo pause is
active. Repeated online events cannot create parallel sockets.

The clearly labeled **Demo controls** section has **Simulate outage** and
**Resume connection** actions. Simulation intentionally closes the socket and
suppresses automatic retry while preserving updates and the cursor. REST publishing
remains enabled, so a second browser tab can publish during the interruption.
Resume reconnects from the stored cursor and replays those durable updates.

## Verification

Exact commands run from `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

The mocked-WebSocket suite uses fake timers and deterministic jitter. It covers
unexpected-close states, delayed backoff, the retry cap and manual retry, unmount
and room-change cleanup, cursor-bearing reconnect URLs, ID deduplication and
sequence sorting, intentional outage/resume, and browser offline/online behavior.
Final result: **10 tests passed** across two files; type-checking, ESLint, and the
production Vite build also passed.
