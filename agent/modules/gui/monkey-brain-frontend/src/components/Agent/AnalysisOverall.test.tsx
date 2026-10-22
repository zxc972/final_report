import { afterEach, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import AnalysisResultCard from './AnalysisResultCard';
import { parseAnalysisResult } from '../../utils/analysisResult';
import { parseConversationProcess } from '../../utils/processEvents';
import { errorSummary } from '../../utils/errorSummary';

afterEach(cleanup);

it('shows one overall incomplete review and expandable independent component states', () => {
  const result = parseAnalysisResult({mode: 'analysis', run_id: 'a'.repeat(32), status: 'incomplete_review',
    overall_status: 'incomplete_review', executions: 1, execution: {exit_code: 0},
    component_statuses: {artifacts: 'finalized', public_contract: 'pass', independent_numeric: 'pass', internal_review: 'unreviewed', identity_mismatch_count: 0, numeric_mismatch_count: 0},
    validation: {independent_numeric_status: 'pass'},
    conclusion_card: {verdict: 'deferred', conclusion_text: 'Draft wording claims success.', text_label: 'Agent draft (unreviewed)', checks_not_passed: [{constraint_id: 'internal_review'}]}}, 'r11')!;
  render(<AnalysisResultCard result={result} />);
  expect(screen.getByLabelText('Overall analysis status').textContent).toBe('Overall: incomplete review');
  expect(screen.queryByText('Computation finished')).toBeNull();
  const details = screen.getByLabelText('Analysis component status');
  expect(details.hasAttribute('open')).toBe(false);
  fireEvent.click(screen.getByText('Execution, checks and review'));
  expect(details.hasAttribute('open')).toBe(true);
  expect(screen.getByText('Public contract: pass')).toBeTruthy();
  expect(screen.getByLabelText('Independent numeric check').textContent).toContain('pass');
  expect(screen.getByText('Internal review: unreviewed')).toBeTruthy();
  expect(screen.getByText('Identity differences: 0; Numeric differences: 0')).toBeTruthy();
  fireEvent.click(screen.getByText('Conclusion: deferred'));
  expect(screen.getAllByText('Agent draft (unreviewed)').length).toBeGreaterThan(0);
});

it.each(['accepted', 'qualified', 'deferred', 'incomplete_review', 'failed', 'blocked'])('uses the protected overall event decision %s', overall => {
  const view = parseConversationProcess({enabled: true, status: 'completed', overall_status: overall, events: [], last_seq: 0});
  expect(view.status).toBe(overall);
});

it('never calls an exit-zero result an execution failure', () => {
  const text = 'Traceback from an older attempt; review needs attention. ' + 'x'.repeat(300);
  expect(errorSummary(text, 'failed', 0)).not.toContain('failed during execution');
  expect(errorSummary(text, 'incomplete_review', 0)).toBe('Execution finished; final review is unavailable.');
  expect(errorSummary(text, 'qualified', 0)).toBeNull();
});
