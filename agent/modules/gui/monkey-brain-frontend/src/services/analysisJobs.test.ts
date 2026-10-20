import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({
  state: { config: { userId: 'alice', workspaceDirectory: '/workspace' }, userToken: 'fixture-session', refreshUserToken: vi.fn() },
  expired: vi.fn(),
}));
vi.mock('../stores/configStore', () => ({
  useConfigStore: { getState: () => mocks.state }, isUserSessionAuthError: () => true, notifyUserSessionExpired: mocks.expired,
}));
vi.mock('../utils/runtimePorts', () => ({ resolveAgentBaseUrl: vi.fn().mockResolvedValue('https://agent.invalid') }));
vi.mock('./accessToken', () => ({ getResolvedAccessToken: () => 'fixture-gateway' }));
import { agentService } from './agentService';
import type { AnalysisResultInfo } from '../utils/analysisResult';
const id = 'b'.repeat(32);
const result: AnalysisResultInfo = { status: 'submitted', conversationId: 'original-conv', runId: 'a'.repeat(32),
  userId: 'alice', workspaceDirectory: '/workspace/alice/output', outputDirectory: 'run', executions: 0,
  fileChecksPassed: false, numericalReview: 'not_performed', files: [],
  jobs: [{ id, status: 'queued', timeoutSeconds: 7200, message: 'Submitted' }] };
const body = { metadata: { mode: 'analysis', run_id: result.runId, status: 'completed', executions: 1,
  validation: { valid: true, required_artifact_coverage: { complete: true }, independent_numeric_status: 'not_performed' },
  artifacts: [{ path: 'job_outputs/' + id + '/summary.json', kind: 'json' }],
  analysis_jobs: [{ job_id: id, status: 'completed', job_timeout_seconds: 7200 }] } };
beforeEach(() => { vi.clearAllMocks(); mocks.state.config.userId = 'alice';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, headers: new Headers({ 'X-User-Token': 'refreshed-fixture' }), json: async () => body })); });
describe('authenticated background job controls', () => {
  it('queries with original identity and current session, without a provider key', async () => {
    const next = await agentService.getAnalysisJobStatus(result, id);
    expect(next.status).toBe('completed'); expect(next.fileChecksPassed).toBe(true);
    const [url, options] = vi.mocked(fetch).mock.calls[0]; expect(url).toBe('https://agent.invalid/api/agent/analysis/job/status');
    const payload = JSON.parse(options!.body as string);
    expect(payload.context.userToken).toBe('fixture-session'); expect(payload.conversationId).toBe('original-conv');
    expect(JSON.stringify(payload)).not.toContain('apiKey'); expect(JSON.stringify(next)).not.toContain('fixture-session');
    expect(mocks.state.refreshUserToken).toHaveBeenCalledWith('refreshed-fixture');
  });
  it('sends cancellation to the dedicated owner-scoped route', async () => {
    await agentService.getAnalysisJobStatus(result, id, true);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('https://agent.invalid/api/agent/analysis/job/cancel');
  });
  it('rejects changed ownership and unattached jobs before fetch', async () => {
    mocks.state.config.userId = 'other';
    await expect(agentService.getAnalysisJobStatus(result, id)).rejects.toThrow('original analysis user');
    await expect(agentService.getAnalysisJobStatus(result, 'c'.repeat(32))).rejects.toThrow('attached');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not replace a result using a different run response', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => ({ metadata: { ...body.metadata, run_id: 'c'.repeat(32) } }) } as Response);
    await expect(agentService.getAnalysisJobStatus(result, id)).rejects.toThrow('does not match');
  });
});

it('notifies session expiry instead of sending repeated model or job requests', async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: false, status: 401, headers: new Headers(), json: async () => ({ detail: 'Please verify your User ID first' }) } as Response);
  await expect(agentService.getAnalysisJobStatus(result, id)).rejects.toThrow('verify your User ID');
  expect(mocks.expired).toHaveBeenCalledTimes(1); expect(fetch).toHaveBeenCalledTimes(1);
});
