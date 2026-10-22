import { describe, expect, it } from 'vitest';
import { parseAnalysisResult } from './analysisResult';
const raw = { mode: 'analysis', status: 'completed', run_id: 'a'.repeat(32), executions: 2,
  output_directory: '.analysis_runs/hash/run', validation: { valid: true, independent_numeric_status: 'not_performed' },
  artifacts: [{ path: 'report.md', kind: 'markdown' }, { path: '../.env' }, { path: 'https://untrusted/x' }],
  generated_scripts: [{ path: 'analyze.py' }, { path: 'report.md' }] };
describe('analysis result metadata', () => {
  it('preserves scoped result and code files without authentication or provider secrets', () => {
    const r = parseAnalysisResult(raw, 'conversation', { userId: 'alice', workspaceDirectory: '/root/alice/output', userToken: 'private-session', apiKey: 'private-provider' })!;
    expect(r.files.map(x => x.path)).toEqual(['report.md', 'analyze.py']); expect(r.fileChecksPassed).toBe(true);
    expect(r.numericalReview).toBe('not_performed'); expect(JSON.stringify(r)).not.toMatch(/private-session|private-provider|userToken|apiKey/);
  });
  it('does not label missing caller-required outputs as complete file checks', () => {
    const r = parseAnalysisResult({ ...raw, validation: { valid: true, required_artifact_coverage: { complete: false } } }, 'conv')!;
    expect(r.fileChecksPassed).toBe(false);
  });
  it('does not manufacture successful results from absent or malformed metadata', () => {
    expect(parseAnalysisResult({}, 'conv')).toBeUndefined(); expect(parseAnalysisResult({ ...raw, run_id: '../other' }, 'conv')).toBeUndefined();
    const r = parseAnalysisResult({ ...raw, status: 'failed', artifacts: [], validation: {} }, 'conv')!;
    expect(r.status).toBe('failed'); expect(r.fileChecksPassed).toBe(false); expect(r.numericalReview).toBe('not_performed');
  });
});

it('keeps only safe job fields and never invents a submitted source path', () => {
  const r = parseAnalysisResult({ ...raw, status: 'submitted', analysis_jobs: [
    { job_id: 'b'.repeat(32), status: 'queued', apiKey: 'private-provider', userToken: 'private-session' },
    { job_id: '../unsafe', status: 'completed' }] }, 'conv')!;
  expect(r.jobs?.length).toBe(1); expect(r.jobs?.[0].status).toBe('queued');
  expect(r.files.some(file => file.path.includes('undefined'))).toBe(false);
  expect(JSON.stringify(r)).not.toMatch(/apiKey|userToken|private-provider|private-session/);
});
it('attaches frozen submitted code under its job path without claiming execution', () => {
  const prefix = 'job_outputs/' + 'b'.repeat(32);
  const r = parseAnalysisResult({ ...raw, status: 'submitted', executions: 0, validation: {},
    artifacts: [], generated_scripts: [], analysis_jobs: [{ job_id: 'b'.repeat(32), status: 'queued',
      job_timeout_seconds: 7200, output_relative: prefix, source_path: 'analysis.py' }] }, 'conv')!;
  expect(r.files).toEqual([{ path: prefix + '/analysis.py', kind: 'submitted code' }]);
  expect(r.fileChecksPassed).toBe(false); expect(r.executions).toBe(0);
});
it('exposes only the two declared group table statuses and mismatch counts', () => {
  const r = parseAnalysisResult({ ...raw, validation: { independent_numeric_status: 'fail', independent_numeric: {
    tables: { 'regional_values.csv': { status: 'pass', mismatch_count: 0, expected: [123] },
      'group_results.csv': { status: 'fail', mismatch_count: 1, differences: [{ expected: 99 }] },
      'private.csv': { status: 'pass', mismatch_count: 0 } } } } }, 'conv')!;
  expect(r.independentTables).toEqual([{ file: 'regional_values.csv', status: 'pass', mismatches: 0 },
    { file: 'group_results.csv', status: 'fail', mismatches: 1 }]);
  expect(JSON.stringify(r)).not.toMatch(/expected|differences|private.csv/);
});
