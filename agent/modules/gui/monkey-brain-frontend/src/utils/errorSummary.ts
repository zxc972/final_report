/** Preserve complete failure evidence behind a short accessible summary. */
export function errorSummary(content: string, status?: string, lastExitCode?: number | null): string | null {
  if (lastExitCode === 0 && ['completed', 'accepted', 'qualified'].includes(status ?? '')) return null;
  const failed = status === 'failed' || status === 'blocked' || status === 'incomplete_review' || status === 'deferred'
    || /(?:Traceback|\"error\"\s*:|\"status\"\s*:\s*\"failed\"|BudgetExceeded)/i.test(content);
  if (!failed || content.length <= 240) return null;
  if (lastExitCode === 0) return status === 'incomplete_review'
    ? 'Execution finished; final review is unavailable.'
    : 'Execution finished; output or review checks need attention.';
  if (/MATLAB/i.test(content)) return 'Analysis blocked: missing MATLAB.';
  if (/budget|limit exhausted/i.test(content)) return 'Analysis stopped: run budget exhausted.';
  if (/Traceback|exit.code|execution failed/i.test(content)) return 'Analysis failed during execution.';
  return status === 'blocked' ? 'Analysis blocked by unmet prerequisites.' : 'Analysis did not complete. View details.';
}
