import { FormEvent, useState } from 'react';
import { useIncidentFeed } from './useIncidentFeed';

const initialQuery = new URLSearchParams(window.location.search);
const backendUrl = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '');

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date);
}

export default function App() {
  const [roomId, setRoomId] = useState(initialQuery.get('room') || 'incident-001');
  const [content, setContent] = useState('');
  const [publishError, setPublishError] = useState('');
  const feed = useIncidentFeed(roomId);
  const clientLabel = initialQuery.get('client') || 'A';
  const clientBUrl = new URL(window.location.href);
  clientBUrl.searchParams.set('room', roomId);
  clientBUrl.searchParams.set('client', 'B');

  const publish = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPublishError('');
    try {
      const response = await fetch(`${backendUrl}/api/rooms/${encodeURIComponent(roomId)}/updates`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, clientId: clientLabel }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null) as {
          error?: { message?: string };
        } | null;
        throw new Error(body?.error?.message || `Publish failed (${response.status})`);
      }
      setContent('');
    } catch (error) {
      setPublishError(
        error instanceof Error
          ? error.message
          : 'Could not publish the update. Check that the API is running.',
      );
    }
  };

  return (
    <main>
      <div className="page-shell">
        <header className="hero">
          <h1>Reconnecting Real-Time Incident Feed</h1>
          <a
            className="secondary-button"
            href={clientBUrl.toString()}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Client B <span aria-hidden="true">↗</span>
          </a>
        </header>

        <section className={`client-card client-card-${feed.status}`} aria-label={`Client ${clientLabel} incident feed`}>
          <div className="client-header">
            <div className="client-identity">
              <span className="client-avatar">{clientLabel}</span>
              <div>
                <h2>Client {clientLabel}</h2>
                <label className="room-field"><span className="sr-only">Current room</span><input aria-label="Current room" value={roomId} onChange={(event) => setRoomId(event.target.value)} /></label>
              </div>
            </div>
            <div className="client-actions" role="region" aria-label="Demo controls">
              <span className={`status status-${feed.status}`}><span className="status-dot" aria-hidden="true" />{feed.status}</span>
              {!feed.isPaused ? (
                <button className="secondary-button" type="button" onClick={feed.simulateOutage}>Simulate outage</button>
              ) : (
                <button className="secondary-button resume" type="button" onClick={feed.resumeConnection}>Resume connection</button>
              )}
            </div>
          </div>

          <div className="metrics" aria-label="Connection status" aria-live="polite">
            <div><span className="metric-label">Last sequence</span><strong>{feed.lastSequence}</strong></div>
            <div><span className="metric-label">Room</span><strong>{roomId}</strong></div>
            <div><span className="metric-label">Reconnect attempt</span><strong>{feed.retryAttempt} / {feed.maxRetries}</strong></div>
            {feed.retriesExhausted && <button className="secondary-button" onClick={feed.retry}>Retry</button>}
          </div>

          {feed.connectionError && <p className="connection-error">{feed.connectionError}</p>}

        </section>

        <form className="composer" onSubmit={publish}>
          <div className="composer-heading"><span className="eyebrow">Compose update</span><span className="client-chip">Client {clientLabel}</span></div>
          <label><span className="sr-only">Update</span><textarea aria-label="Update" value={content} onChange={(event) => setContent(event.target.value)} placeholder="Describe the current incident status, action taken, or next steps…" required /></label>
          <div className="composer-footer"><span>room: {roomId} · next seq: {feed.lastSequence + 1}</span><button type="submit">Publish Update</button></div>
          {publishError && <p className="publish-error" role="alert">{publishError}</p>}
        </form>

        <section className="data-model" aria-labelledby="model-title">
          <span className="eyebrow" id="model-title">Update data model</span>
          <div className="table-wrap"><table>
            <thead><tr><th>ID (stable)</th><th>Room_id</th><th>Client</th><th>Content</th><th>Seq / Created_at</th></tr></thead>
            <tbody>
              {feed.updates.length === 0 ? <tr className="placeholder-row"><td>—</td><td>Waiting for update</td><td>—</td><td>—</td><td>—</td></tr> : feed.updates.map((update) => (
                <tr key={update.updateId}><td>{update.updateId}</td><td>{update.roomId}</td><td>Client {update.clientId}</td><td title={update.content}>{update.content}</td><td>#{update.sequence} · {formatTime(update.createdAt)}</td></tr>
              ))}
            </tbody>
          </table></div>
        </section>
      </div>
    </main>
  );
}
