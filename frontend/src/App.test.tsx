import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import App from './App';

vi.mock('./useIncidentFeed', () => ({
  useIncidentFeed: () => ({
    updates: [],
    status: 'connected',
    retryAttempt: 0,
    maxRetries: 8,
    retriesExhausted: false,
    isPaused: false,
    lastSequence: 0,
    connectionError: null,
    simulateOutage: vi.fn(),
    resumeConnection: vi.fn(),
    retry: vi.fn(),
  }),
}));

test('renders the feed and labeled demo controls', () => {
  render(<App />);
  expect(
    screen.getByRole('heading', {
      name: 'Reconnecting Real-Time Incident Feed',
    }),
  ).toBeInTheDocument();
  expect(screen.getByText('connected')).toBeInTheDocument();
  expect(screen.getByDisplayValue('incident-001')).toBeInTheDocument();
  expect(screen.getByText('incident-001')).toBeInTheDocument();
  expect(screen.getByText('Last sequence')).toBeInTheDocument();
  expect(screen.getByText('Reconnect attempt')).toBeInTheDocument();
  const clientBLink = screen.getByRole('link', { name: 'Open Client B' });
  expect(clientBLink).toHaveAttribute('target', '_blank');
  expect(clientBLink).toHaveAttribute('href', expect.stringContaining('client=B'));
  expect(clientBLink).toHaveAttribute('href', expect.stringContaining('room=incident-001'));
  expect(screen.getByRole('region', { name: 'Demo controls' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Simulate outage' })).toBeInTheDocument();
});
