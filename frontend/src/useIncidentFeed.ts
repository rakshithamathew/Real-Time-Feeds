import { useCallback, useEffect, useRef, useState } from 'react';

export type ConnectionStatus =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected';

export interface IncidentUpdate {
  updateId: string;
  roomId: string;
  clientId: string;
  content: string;
  createdAt: string;
  sequence: number;
}

interface UpdateEnvelope {
  type: 'update';
  data: IncidentUpdate;
}

export const MAX_RETRIES = 8;
const BASE_RETRY_DELAY_MS = 500;
const MAX_RETRY_DELAY_MS = 10_000;

interface ConnectionControls {
  pause: () => void;
  resume: () => void;
  retry: () => void;
}

const noOp = () => undefined;

function isIncidentUpdate(value: unknown): value is IncidentUpdate {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.updateId === 'string' &&
    typeof candidate.roomId === 'string' &&
    typeof candidate.clientId === 'string' &&
    typeof candidate.content === 'string' &&
    typeof candidate.createdAt === 'string' &&
    typeof candidate.sequence === 'number' &&
    Number.isSafeInteger(candidate.sequence) &&
    candidate.sequence > 0
  );
}

function parseUpdateEnvelope(raw: string): UpdateEnvelope | null {
  try {
    const envelope = JSON.parse(raw) as Record<string, unknown>;
    if (envelope.type !== 'update' || !isIncidentUpdate(envelope.data)) return null;
    return { type: 'update', data: envelope.data };
  } catch {
    return null;
  }
}

function websocketUrl(roomId: string, after: number): string {
  const configuredBackend = import.meta.env.VITE_BACKEND_URL?.replace(/\/+$/, '');
  const backend = configuredBackend ? new URL(configuredBackend) : window.location;
  const protocol = backend.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${backend.host}/ws/rooms/${encodeURIComponent(roomId)}?after=${after}`;
}

function retryDelay(attempt: number): number {
  const exponential = Math.min(
    MAX_RETRY_DELAY_MS,
    BASE_RETRY_DELAY_MS * 2 ** (attempt - 1),
  );
  const jitter = 0.75 + Math.random() * 0.5;
  return Math.min(MAX_RETRY_DELAY_MS, Math.round(exponential * jitter));
}

export function useIncidentFeed(roomId: string) {
  const [updates, setUpdates] = useState<IncidentUpdate[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [retryAttempt, setRetryAttempt] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [retriesExhausted, setRetriesExhausted] = useState(false);
  const [lastSequence, setLastSequence] = useState(0);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const lastSequenceRef = useRef(0);
  const lifecycleRef = useRef(0);
  const controlsRef = useRef<ConnectionControls>({
    pause: noOp,
    resume: noOp,
    retry: noOp,
  });

  useEffect(() => {
    const lifecycle = ++lifecycleRef.current;
    let retryCount = 0;
    let intentionallyPaused = false;
    let online = navigator.onLine;

    lastSequenceRef.current = 0;
    // A room is a distinct subscription identity, so its visible and recovery
    // state must reset together before the new external connection is started.
    /* eslint-disable react-hooks/set-state-in-effect */
    setUpdates([]);
    setRetryAttempt(0);
    setIsPaused(false);
    setRetriesExhausted(false);
    setLastSequence(0);
    setConnectionError(null);
    setStatus(online ? 'connecting' : 'disconnected');
    /* eslint-enable react-hooks/set-state-in-effect */

    const isCurrent = () => lifecycleRef.current === lifecycle;

    const clearRetryTimer = () => {
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };

    const closeActiveSocket = (reason: string) => {
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket === null) return;
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      if (
        socket.readyState === WebSocket.CONNECTING ||
        socket.readyState === WebSocket.OPEN
      ) {
        socket.close(1000, reason);
      }
    };

    let connect = noOp;

    const scheduleRetry = () => {
      if (!isCurrent() || intentionallyPaused || !online) {
        setStatus('disconnected');
        return;
      }
      const nextAttempt = retryCount + 1;
      if (nextAttempt > MAX_RETRIES) {
        setRetriesExhausted(true);
        setConnectionError(`Connection unavailable after ${MAX_RETRIES} retries.`);
        setStatus('disconnected');
        return;
      }
      retryCount = nextAttempt;
      setRetryAttempt(nextAttempt);
      setStatus('reconnecting');
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null;
        connect();
      }, retryDelay(nextAttempt));
    };

    connect = () => {
      if (
        !isCurrent() ||
        intentionallyPaused ||
        !online ||
        socketRef.current !== null ||
        retryTimerRef.current !== null
      ) {
        return;
      }

      let socket: WebSocket;
      try {
        socket = new WebSocket(websocketUrl(roomId, lastSequenceRef.current));
      } catch {
        scheduleRetry();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        if (!isCurrent() || socketRef.current !== socket) return;
        retryCount = 0;
        setRetryAttempt(0);
        setRetriesExhausted(false);
        setConnectionError(null);
        setStatus('connected');
      };

      socket.onmessage = (event) => {
        if (!isCurrent() || socketRef.current !== socket) return;
        const envelope = parseUpdateEnvelope(String(event.data));
        if (envelope === null || envelope.data.roomId !== roomId) return;

        lastSequenceRef.current = Math.max(
          lastSequenceRef.current,
          envelope.data.sequence,
        );
        setLastSequence(lastSequenceRef.current);
        setUpdates((current) => {
          const merged = new Map(current.map((update) => [update.updateId, update]));
          merged.set(envelope.data.updateId, envelope.data);
          return [...merged.values()].sort(
            (left, right) =>
              left.sequence - right.sequence || left.updateId.localeCompare(right.updateId),
          );
        });
      };

      socket.onerror = () => {
        if (socket.readyState !== WebSocket.CLOSED) socket.close();
      };

      socket.onclose = (event) => {
        if (!isCurrent() || socketRef.current !== socket) return;
        socketRef.current = null;
        setConnectionError(
          event.code === 1011
            ? 'Replay failed. Retrying connection.'
            : 'Connection interrupted. Retrying.',
        );
        scheduleRetry();
      };
    };

    const pause = () => {
      if (!isCurrent()) return;
      intentionallyPaused = true;
      clearRetryTimer();
      closeActiveSocket('Demo outage');
      setIsPaused(true);
      setRetriesExhausted(false);
      setConnectionError(null);
      setStatus('disconnected');
    };

    const reconnectNow = () => {
      if (!isCurrent()) return;
      intentionallyPaused = false;
      clearRetryTimer();
      closeActiveSocket('Manual retry');
      retryCount = 0;
      setRetryAttempt(0);
      setIsPaused(false);
      setRetriesExhausted(false);
      setConnectionError(null);
      if (!online) {
        setStatus('disconnected');
        return;
      }
      setStatus('reconnecting');
      connect();
    };

    controlsRef.current = { pause, resume: reconnectNow, retry: reconnectNow };

    const handleOffline = () => {
      online = false;
      clearRetryTimer();
      closeActiveSocket('Browser offline');
      setConnectionError('Browser is offline.');
      setStatus('disconnected');
    };

    const handleOnline = () => {
      online = true;
      if (intentionallyPaused || socketRef.current !== null) return;
      retryCount = 0;
      setRetryAttempt(0);
      setRetriesExhausted(false);
      setConnectionError(null);
      setStatus('reconnecting');
      connect();
    };

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    if (online) connect();

    return () => {
      clearRetryTimer();
      closeActiveSocket('Subscription cleanup');
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
      controlsRef.current = { pause: noOp, resume: noOp, retry: noOp };
    };
  }, [roomId]);

  const simulateOutage = useCallback(() => controlsRef.current.pause(), []);
  const resumeConnection = useCallback(() => controlsRef.current.resume(), []);
  const retry = useCallback(() => controlsRef.current.retry(), []);

  return {
    updates,
    status,
    retryAttempt,
    maxRetries: MAX_RETRIES,
    retriesExhausted,
    isPaused,
    lastSequence,
    connectionError,
    simulateOutage,
    resumeConnection,
    retry,
  };
}
