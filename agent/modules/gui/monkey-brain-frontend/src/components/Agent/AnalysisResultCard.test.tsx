import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import AnalysisResultCard from './AnalysisResultCard';
import { agentService } from '../../services/agentService';
vi.mock('../../services/agentService', () => ({ agentService: { downloadAnalysisFile: vi.fn().mockResolvedValue(undefined), getAnalysisJobStatus: vi.fn() } }));
const result = { status: 'completed', conversationId: 'conv', runId: 'a'.repeat(32), outputDirectory: '.analysis_runs/hash/run', userId: 'alice', workspaceDirectory: '/root/alice/output', executions: 1, fileChecksPassed: true, numericalReview: 'not_performed', files: [{ path: 'report.md', kind: 'markdown' }] };
beforeEach(() => { cleanup(); vi.clearAllMocks(); });
describe('analysis file card', () => {
  it('separates computation and file checks from independent numerical review', async () => {
    render(<AnalysisResultCard result={result} />);
    expect(screen.getByText('Computation finished')).toBeTruthy(); expect(screen.getByText(/Numerical review: not run/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Download report.md' }));
    await waitFor(() => expect(agentService.downloadAnalysisFile).toHaveBeenCalledWith(result, 'report.md'));
  });
  it('shows failed/empty results without claiming completion', () => {
    render(<AnalysisResultCard result={{ ...result, status: 'failed', fileChecksPassed: false, files: [] }} />);
    expect(screen.getByText('Run failed')).toBeTruthy(); expect(screen.queryByText('Computation finished')).toBeNull(); expect(screen.getByText('No output files are attached to this run.')).toBeTruthy();
  });
});

it('refreshes a submitted job into actual file-checked completion', async () => {
  const pending = { ...result, status: 'submitted', executions: 0, files: [], fileChecksPassed: false,
    jobs: [{ id: 'b'.repeat(32), status: 'queued', timeoutSeconds: 7200, message: 'Submitted only' }] };
  vi.mocked(agentService.getAnalysisJobStatus).mockResolvedValue({ ...result,
    jobs: [{ ...pending.jobs[0], status: 'completed' }] });
  render(<AnalysisResultCard result={pending} />);
  expect(screen.queryByText('Computation finished')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh computation' }));
  await waitFor(() => expect(screen.getByText('Computation finished')).toBeTruthy());
  expect(screen.getByText(/Numerical review: not run/)).toBeTruthy();
});
it('offers a real cancellation action and shows cancelled without completion', async () => {
  const pending = { ...result, status: 'submitted', executions: 0, files: [], fileChecksPassed: false,
    jobs: [{ id: 'b'.repeat(32), status: 'running', timeoutSeconds: 7200, message: 'Computing' }] };
  vi.mocked(agentService.getAnalysisJobStatus).mockResolvedValue({ ...pending, status: 'cancelled',
    jobs: [{ ...pending.jobs[0], status: 'cancelled' }] });
  render(<AnalysisResultCard result={pending} />);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel computation' }));
  await waitFor(() => expect(screen.getByText('Run: cancelled')).toBeTruthy());
  expect(agentService.getAnalysisJobStatus).toHaveBeenCalledWith(pending, 'b'.repeat(32), true);
  expect(screen.queryByText('Computation finished')).toBeNull();
});
it('polls without model calls only while mounted and active', async () => {
  vi.useFakeTimers();
  const pending = { ...result, status: 'submitted', executions: 0, files: [], fileChecksPassed: false,
    jobs: [{ id: 'b'.repeat(32), status: 'running', timeoutSeconds: 7200, message: 'Computing' }] };
  vi.mocked(agentService.getAnalysisJobStatus).mockResolvedValue({ ...result, jobs: [{ ...pending.jobs[0], status: 'completed' }] });
  const view = render(<AnalysisResultCard result={pending} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(agentService.getAnalysisJobStatus).toHaveBeenCalledTimes(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(agentService.getAnalysisJobStatus).toHaveBeenCalledTimes(1);
  view.unmount();
  await vi.advanceTimersByTimeAsync(30000);
  expect(agentService.getAnalysisJobStatus).toHaveBeenCalledTimes(1);
  vi.useRealTimers();
});

it('stops automatic polling after an authentication/query failure', async () => {
  vi.useFakeTimers();
  const pending = { ...result, status: 'submitted', executions: 0, files: [], fileChecksPassed: false,
    jobs: [{ id: 'b'.repeat(32), status: 'running', timeoutSeconds: 7200, message: 'Computing' }] };
  vi.mocked(agentService.getAnalysisJobStatus).mockRejectedValue(new Error('Verify original user'));
  const view = render(<AnalysisResultCard result={pending} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(screen.getByRole('alert').textContent).toContain('Verify original user');
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(agentService.getAnalysisJobStatus).toHaveBeenCalledTimes(1);
  view.unmount(); vi.useRealTimers();
});
