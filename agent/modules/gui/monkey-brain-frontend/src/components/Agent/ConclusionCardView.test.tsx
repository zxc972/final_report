import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import ConclusionCardView from './ConclusionCardView';
import { parseConclusionReview, verdicts } from '../../utils/conclusionReview';
import { parseAnalysisResult } from '../../utils/analysisResult';

afterEach(cleanup);

describe('conclusion review card', () => {
  it.each(verdicts)('shows %s and expands the recorded evidence', verdict => {
    const review = parseConclusionReview({ verdict, conclusion_text: 'Fixed offline placeholder.',
      checks_not_passed: [{ constraint_id: 'cross:scale_check', verdict: 'warn', tool_observed: { reason: 'Physical scale unverified' } }],
      scope: 'supplied_descriptive', evidence: { fixture: 'No model request' }, prose_semantic_entailment: 'not_certified' })!;
    render(<ConclusionCardView review={review} />);
    expect(screen.getByText('Conclusion: ' + verdict)).toBeTruthy();
    expect(screen.getByText('1 checks need review')).toBeTruthy();
    fireEvent.click(screen.getByText('Conclusion: ' + verdict));
    expect(screen.getByText('Fixed offline placeholder.')).toBeTruthy();
    expect(screen.getByText('Physical scale unverified')).toBeTruthy();
    expect(document.querySelector('details')?.open).toBe(true);
  });

  it('ignores invalid verdicts and excludes authentication from persisted evidence', () => {
    expect(parseConclusionReview({ verdict: 'success', conclusion_text: 'Wrong verdict' })).toBeUndefined();
    const parsed = parseConclusionReview({ verdict: 'deferred', conclusion_text: 'No evidence.', checks_not_passed: [],
      evidence: { apiKey: 'private-provider', nested: { userToken: 'private-session', observation: 'Kept source' } } })!;
    expect(JSON.stringify(parsed)).not.toMatch(/private-provider|private-session|apiKey|userToken/);
    expect(JSON.stringify(parsed)).toContain('Kept source');
  });

  it('preserves the conclusion metadata and leaves legacy results unchanged', () => {
    const raw = { mode: 'analysis', run_id: 'a'.repeat(32) };
    expect(parseAnalysisResult(raw, 'conv')?.conclusionReview).toBeUndefined();
    expect(parseAnalysisResult({ ...raw, conclusion_card: { verdict: 'blocked', conclusion_text: 'Prerequisites failed.', checks_not_passed: [{ verdict: 'block' }] } }, 'conv')?.conclusionReview?.verdict).toBe('blocked');
  });
});
