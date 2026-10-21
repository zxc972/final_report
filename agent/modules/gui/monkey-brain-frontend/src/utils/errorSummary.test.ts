import { describe, expect, it } from 'vitest';
import { errorSummary } from './errorSummary';
describe('long failure disclosure', () => {
  it('collapses paths/JSON only for failure, retaining caller full content', () => {
    const content = '{"error":"Traceback at /data/long-path/"}' + 'x'.repeat(300);
    expect(errorSummary(content)).toBe('Analysis failed during execution.');
    expect(errorSummary('x'.repeat(400), 'completed')).toBeNull();
    expect(errorSummary('short failure', 'failed')).toBeNull();
  });
  it('summarises observed software and budget failures', () => {
    expect(errorSummary('MATLAB' + 'x'.repeat(300), 'blocked')).toContain('MATLAB');
    expect(errorSummary('Budget exhausted' + 'x'.repeat(300), 'failed')).toContain('budget');
  });
});
