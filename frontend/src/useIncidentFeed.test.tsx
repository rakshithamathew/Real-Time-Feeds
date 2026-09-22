import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { MAX_RETRIES, useIncidentFeed } from './useIncidentFeed';

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string | URL) {
    this.url = String(url);
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  sendUpdate(update: Record<string, unknown>) {
    this.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ type: 'update', data: update }),
      }),
    );
  }

  serverClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close'));
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close'));
  }
}

const update = (updateId: string, sequence: number) => ({
  updateId,
  roomId: 'incident-001',
  clientId: 'A',
  content: `update ${sequence}`,
  createdAt: '2026-09-18T11:30:00Z',
  sequence,
});

describe('useIncidentFeed', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  test('moves through connecting, connected, and reconnecting after an unexpected close', () => {
    const { result } = renderHook(() => useIncidentFeed('incident-001'));
    expect(result.current.status).toBe('connecting');

    act(() => MockWebSocket.instances[0].open());
    expect(result.current.status).toBe('connected');

    act(() => MockWebSocket.instances[0].serverClose());
    expect(result.current.status).toBe('reconnecting');
    expect(result.current.retryAttempt).toBe(1);
  });

  test('waits for the backoff delay instead of reconnecting in a tight loop', () => {
    renderHook(() => useIncidentFeed('incident-001'));
    act(() => MockWebSocket.instances[0].serverClose());

    act(() => vi.advanceTimersByTime(499));
    expect(MockWebSocket.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  test('stops after the bounded retry count', () => {
    const { result } = renderHook(() => useIncidentFeed('incident-001'));
    act(() => MockWebSocket.instances[0].serverClose());

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt += 1) {
      const delay = Math.min(10_000, 500 * 2 ** (attempt - 1));
      act(() => vi.advanceTimersByTime(delay));
      act(() => MockWebSocket.instances.at(-1)!.serverClose());
    }

    expect(MockWebSocket.instances).toHaveLength(MAX_RETRIES + 1);
    expect(result.current.status).toBe('disconnected');
    expect(result.current.retryAttempt).toBe(MAX_RETRIES);
    expect(result.current.retriesExhausted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);

    act(() => result.current.retry());
    expect(result.current.status).toBe('reconnecting');
    expect(result.current.retryAttempt).toBe(0);
    expect(result.current.retriesExhausted).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(MAX_RETRIES + 2);
  });

  test('cleans up retry timers when unmounted', () => {
    const { unmount } = renderHook(() => useIncidentFeed('incident-001'));
    act(() => MockWebSocket.instances[0].serverClose());
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(10_000));
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  test('replaces the socket and clears pending retries when the room changes', () => {
    const { result, rerender } = renderHook(
      ({ room }) => useIncidentFeed(room),
      { initialProps: { room: 'incident-001' } },
    );
    act(() => MockWebSocket.instances[0].serverClose());
    expect(vi.getTimerCount()).toBe(1);

    rerender({ room: 'incident-002' });
    expect(vi.getTimerCount()).toBe(0);
    expect(MockWebSocket.instances).toHaveLength(2);
    expect(MockWebSocket.instances[1].url).toContain(
      '/ws/rooms/incident-002?after=0',
    );
    expect(result.current.status).toBe('connecting');
  });

  test('reconnects with the greatest processed cursor and merges by ID in sequence order', () => {
    const { result } = renderHook(() => useIncidentFeed('incident-001'));
    const first = MockWebSocket.instances[0];
    act(() => first.open());
    act(() => {
      first.sendUpdate(update('later', 7));
      first.sendUpdate(update('earlier', 4));
      first.sendUpdate(update('later', 7));
    });

    expect(result.current.updates.map((item) => item.updateId)).toEqual([
      'earlier',
      'later',
    ]);
    expect(result.current.lastSequence).toBe(7);

    act(() => first.serverClose());
    act(() => vi.advanceTimersByTime(500));
    expect(MockWebSocket.instances[1].url).toContain(
      '/ws/rooms/incident-001?after=7',
    );
  });

  test('deduplicates replay and live overlap after reconnecting', () => {
    const { result } = renderHook(() => useIncidentFeed('incident-001'));
    const initialSocket = MockWebSocket.instances[0];
    act(() => initialSocket.open());
    act(() => initialSocket.sendUpdate(update('before-gap', 5)));
    act(() => initialSocket.serverClose());
    act(() => vi.advanceTimersByTime(500));

    const recoveredSocket = MockWebSocket.instances[1];
    expect(recoveredSocket.url).toContain('?after=5');
    act(() => recoveredSocket.open());
    act(() => {
      recoveredSocket.sendUpdate(update('missed-two', 7));
      recoveredSocket.sendUpdate(update('missed-one', 6));
      recoveredSocket.sendUpdate(update('missed-one', 6));
      recoveredSocket.sendUpdate(update('missed-two', 7));
    });

    expect(
      result.current.updates.map(({ updateId, sequence }) => ({ updateId, sequence })),
    ).toEqual([
      { updateId: 'before-gap', sequence: 5 },
      { updateId: 'missed-one', sequence: 6 },
      { updateId: 'missed-two', sequence: 7 },
    ]);
  });

  test('demo outage pauses retries and resumes from the stored cursor', () => {
    const { result } = renderHook(() => useIncidentFeed('incident-001'));
    act(() => MockWebSocket.instances[0].open());
    act(() => MockWebSocket.instances[0].sendUpdate(update('one', 12)));

    act(() => result.current.simulateOutage());
    expect(result.current.status).toBe('disconnected');
    expect(result.current.isPaused).toBe(true);
    expect(vi.getTimerCount()).toBe(0);

    act(() => result.current.resumeConnection());
    expect(result.current.status).toBe('reconnecting');
    expect(MockWebSocket.instances[1].url).toContain('?after=12');
  });

  test('shows disconnected offline and reconnects once when the browser returns online', () => {
    const { result } = renderHook(() => useIncidentFeed('incident-001'));
    act(() => MockWebSocket.instances[0].open());

    act(() => window.dispatchEvent(new Event('offline')));
    expect(result.current.status).toBe('disconnected');
    expect(vi.getTimerCount()).toBe(0);

    act(() => window.dispatchEvent(new Event('online')));
    expect(result.current.status).toBe('reconnecting');
    expect(MockWebSocket.instances).toHaveLength(2);

    act(() => window.dispatchEvent(new Event('online')));
    expect(MockWebSocket.instances).toHaveLength(2);
    act(() => MockWebSocket.instances[1].open());
    expect(result.current.status).toBe('connected');
  });
});
