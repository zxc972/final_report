import { describe, expect, it } from 'vitest';
import { collapseEvents, formatStepTime, parseConversationProcess } from './processEvents';

// Shapes follow backend/analysis_events.py (AnalysisEvents.view).
describe('process event parsing', () => {
  it('maps the backend view, keeps safe fields and summarises blocked checks', () => {
    const parsed = parseConversationProcess({
      enabled: true, status: 'blocked', run_id: 'abc', last_seq: 4, has_more: false,
      events: [
        { seq: 1, time: '2026-10-20T19:42:49.965234+00:00', stage: 'data', status: 'running', title: '生成数据画像：1 个文件',
          detail: { operation_id: 'op1', tool: 'profile_data' }, refs: [] },
        { seq: 2, time: '2026-10-20T19:42:50.182543+00:00', stage: 'data', status: 'done', title: '生成数据画像：1 个文件',
          detail: { operation_id: 'op1', tool: 'profile_data', duration_seconds: 0.217 }, refs: [] },
        { seq: 3, time: '2026-10-20T19:42:50.19+00:00', stage: 'constraints', status: 'blocked', title: '约束检查：2 通过 / 1 警告 / 1 阻断',
          detail: { operation_id: 'op2', tool: 'compile_constraints', failures: [{ constraint_id: 'software_available' }] }, refs: [] },
        { seq: 'x', title: 'no seq' },
      ],
      plan: { version: 1, code_path: '/work/surface_area.py',
        data: { files: ['/inputs/0/surf/lh.pial', '/inputs/0/surf/rh.pial'], subjects: ['sub-01'] },
        atlas: { name: 'none', version: 'n/a', space: 'native', hemisphere_rule: 'per hemisphere' },
        method: { method_id: 'method:v12:surface_mesh_area', name: 'Triangle mesh area', sources: [{ url: 'javascript:alert(1)', source_id: 'x' }] },
        constraints: { pass: 3, warn: 1, block: 0 },
        must_disclose: [{ constraint_id: 'scale_consistent:physical_scale', tool_observed: { reason: 'scale not verified' } }] },
    });
    expect(parsed.available).toBe(true);
    expect(parsed.status).toBe('blocked');
    expect(parsed.events).toHaveLength(3);
    expect(parsed.events[0].time).toBeGreaterThan(1.7e9);
    expect(parsed.events[2].summary).toBe('Blocked: software_available');
    expect(parsed.events[2].detail?.operation_id).toBeUndefined();
    expect(parsed.plan?.codePath).toBe('surface_area.py');
    expect(parsed.plan?.method?.sourceUrl).toBeUndefined();
    expect(parsed.plan?.data?.summary).toBe('sub-01 · 1 subject · 2 files');
    expect(parsed.plan?.checks).toMatchObject({ pass: 3, warn: 1, block: 0 });
    expect(parsed.plan?.checks?.items[0]).toMatchObject({ id: 'scale_consistent:physical_scale', verdict: 'warn' });
    expect(parsed.nextAfter).toBe(4);
  });

  it('treats a disabled profile as unavailable', () => {
    expect(parseConversationProcess({ enabled: false, events: [], status: 'disabled' }).available).toBe(false);
  });

  it('replaces running events by operation and collapses navigation', () => {
    const steps = collapseEvents([
      { seq: 1, time: 1, stage: 'data', status: 'running', title: 'ls', group: 'navigation', opId: 'a' },
      { seq: 2, time: 2, stage: 'data', status: 'done', title: 'ls', group: 'navigation', opId: 'a' },
      { seq: 3, time: 3, stage: 'data', status: 'running', title: 'glob', group: 'navigation', opId: 'b' },
      { seq: 4, time: 4, stage: 'data', status: 'done', title: 'glob', group: 'navigation', opId: 'b' },
      { seq: 5, time: 5, stage: 'run', status: 'running', title: 'Running script', opId: 'c' },
    ]);
    expect(steps).toHaveLength(2);
    expect(steps[0].repeat).toBe(2);
    expect(steps[1].event.status).toBe('running');
  });

  it('formats times relative to the run start', () => {
    expect(formatStepTime(142, 100)).toBe('0:42');
    expect(formatStepTime(0, 100)).toBe('');
  });
});


it('keeps unmapped conditions separate from executable warnings', () => {
  const result = parseConversationProcess({ enabled: true, events: [], plan: {
    version: 1, constraints: { pass: 5, warn: 2, block: 0, unverified: 6 },
    must_disclose: [{ condition_id: 'fact:unmapped', statement: 'Needs expert QC', status: 'unverified' }],
  } });
  expect(result.plan?.checks?.unverified).toBe(6);
  expect(result.plan?.checks?.warn).toBe(2);
  expect(result.plan?.checks?.items[0].verdict).toBe('unverified');
});


it('treats running to warn as a terminal warning and ignores stale running', () => {
  const steps = collapseEvents([
    {seq: 1, time: 1, stage: 'run', status: 'running', title: 'Check', opId: 'r10'},
    {seq: 2, time: 2, stage: 'run', status: 'warn', title: 'Check warning', opId: 'r10'},
    {seq: 1, time: 1, stage: 'run', status: 'running', title: 'Check', opId: 'r10'},
  ]);
  expect(steps).toHaveLength(1);
  expect(steps[0].event.status).toBe('warn');
  expect(parseConversationProcess({enabled: true, status: 'warn', events: []}).status).toBe('warning');
  expect(parseConversationProcess({enabled: true, status: 'route_failed', events: []}).status).toBe('failed');
});
