import {afterEach, expect, it} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import AnalysisResultCard from './AnalysisResultCard';
import {parseAnalysisResult} from '../../utils/analysisResult';

afterEach(cleanup);
it.each(['pass', 'fail', 'not_configured'])('shows host check %s without reference values', status => {
  const result = parseAnalysisResult({mode: 'analysis', run_id: 'a'.repeat(32), status: 'completed', executions: 1,
    validation: {independent_numeric_status: status, independent_numeric: {mismatch_count: status === 'fail' ? 1 : 0}}}, 'round10')!;
  render(<AnalysisResultCard result={result} />);
  expect(screen.getByLabelText('Independent numeric check').textContent).toContain(status === 'not_configured' ? 'not assessed' : status);
  if (status === 'not_configured') {
    expect(screen.queryByText('0 mismatches')).toBeNull();
  } else {
    expect(screen.getByText(status === 'fail' ? '1 mismatches' : '0 mismatches')).toBeTruthy();
  }
});

it('unassessed component checks do not imply zero differences', () => {
  const result = parseAnalysisResult({mode: 'analysis', run_id: 'b'.repeat(32), status: 'blocked', executions: 0,
    overall_status: 'blocked', component_statuses: {identity_mismatch_count: null, numeric_mismatch_count: null},
    validation: {independent_numeric_status: 'not_performed'}}, 'round13')!;
  render(<AnalysisResultCard result={result} />);
  expect(screen.getByText('Identity differences: not assessed; Numeric differences: not assessed')).toBeTruthy();
});
