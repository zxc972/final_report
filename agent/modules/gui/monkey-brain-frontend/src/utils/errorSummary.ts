/** Preserve complete failure evidence behind a short accessible summary. */
export function errorSummary(content: string, status?: string): string | null {
  const failed = status === 'failed' || status === 'blocked'
    || /(?:Traceback|\"error\"\s*:|\"status\"\s*:\s*\"failed\"|BudgetExceeded)/i.test(content);
  if (!failed || content.length <= 240) return null;
  if (/MATLAB/i.test(content)) return 'Analysis blocked: missing MATLAB.';
  if (/budget|limit exhausted/i.test(content)) return 'Analysis stopped: run budget exhausted.';
  if (/Traceback|exit.code|execution failed/i.test(content)) return 'Analysis failed during execution.';
  return status === 'blocked' ? 'Analysis blocked by unmet prerequisites.' : 'Analysis did not complete. View details.';
}
