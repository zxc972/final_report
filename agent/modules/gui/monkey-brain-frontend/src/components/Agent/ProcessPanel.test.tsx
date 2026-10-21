import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ProcessPanel from './ProcessPanel';
import { agentService } from '../../services/agentService';

vi.mock('../../services/agentService', () => ({
  agentService: { getConversationProcess: vi.fn(), downloadAnalysisFile: vi.fn() },
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const userMessage = { id: 'm1', type: 'user' as const, content: 'Analyse surface area for sub-01', timestamp: new Date() };

describe('ProcessPanel', () => {
  it('shows the basis and recorded steps from the server', async () => {
    vi.mocked(agentService.getConversationProcess).mockResolvedValue({
      available: true, status: 'blocked', events: [
        { seq: 1, time: 1, stage: 'constraints', status: 'blocked', title: 'Checks: lGI blocked', summary: 'MATLAB not found',
          detail: { constraint: 'software_available' } },
      ],
      plan: { version: 1, sealed: true, atlas: { name: 'aparc (DK)', space: 'native' },
        method: { name: 'Global convex-hull gyrification' },
        checks: { pass: 4, warn: 1, block: 1, unverified: 6, items: [] }, codePath: 'code/fold.py' },
      outputs: [], nextAfter: 1,
    });
    render(<ProcessPanel conversationId="conv_1" active={false} messages={[userMessage]} />);
    expect(await screen.findByText('Checks: lGI blocked')).toBeTruthy();
    expect(screen.getByText('Blocked')).toBeTruthy();
    expect(screen.getByText(/aparc \(DK\)/)).toBeTruthy();
    expect(screen.getByText('1 block')).toBeTruthy();
    expect(screen.getByText('6 unverified')).toBeTruthy();
    expect(screen.getByText('code/fold.py')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Checks: lGI blocked/ }));
    expect(screen.getByText('software_available')).toBeTruthy();
    expect(screen.getByText(/recorded from actual tool calls/)).toBeTruthy();
  });

  it('falls back to request status when the server has no process tracking', async () => {
    vi.mocked(agentService.getConversationProcess).mockResolvedValue({
      available: false, status: 'idle', events: [], outputs: [], nextAfter: 0,
    });
    render(<ProcessPanel conversationId="conv_2" active messages={[userMessage]} />);
    await waitFor(() => expect(screen.getByText(/not available for this request/)).toBeTruthy());
    expect(screen.getByText('Request sent')).toBeTruthy();
    expect(screen.getByText(/Waiting for the assistant/)).toBeTruthy();
  });

  it('shows an empty state before anything has run', () => {
    render(<ProcessPanel conversationId={null} active={false} messages={[]} />);
    expect(screen.getByText(/Nothing has run in this conversation yet/)).toBeTruthy();
    expect(screen.queryByText(/not available/)).toBeNull();
  });
});

it('labels preprocessing completion as a finished reply', async () => {
  vi.mocked(agentService.getConversationProcess).mockResolvedValue({
    available: true, status: 'completed', events: [{ seq: 1, time: 1, stage: 'other', status: 'done', title: 'Routed to preprocessing' }], outputs: [], nextAfter: 1,
  });
  render(<ProcessPanel conversationId="pipeline-history" active={false} messages={[{ ...userMessage, type: 'agent', metadata: { route: 'pipeline' } }]} />);
  expect(await screen.findByText('Reply finished')).toBeTruthy();
  expect(screen.queryByText('Completed')).toBeNull();
});
