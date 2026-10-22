export const verdicts = ['accepted', 'qualified', 'revised', 'blocked', 'rejected', 'deferred'] as const;
export type ConclusionVerdict = typeof verdicts[number];
export interface ConclusionReview {
  verdict: ConclusionVerdict;
  notPassedCount: number;
  card: Record<string, unknown>;
}

function safeValue(value: unknown, depth = 0): unknown {
  if (depth > 12) return '[Nested evidence omitted]';
  if (typeof value === 'string') return value.slice(0, 8000);
  if (value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) return value;
  if (Array.isArray(value)) return value.slice(0, 256).map(item => safeValue(item, depth + 1));
  if (typeof value === 'object' && value) {
    return Object.fromEntries(Object.entries(value).filter(([key]) => !/api.?key|token|authorization|password|license/i.test(key))
      .slice(0, 128).map(([key, item]) => [key, safeValue(item, depth + 1)]));
  }
  return undefined;
}

export function parseConclusionReview(value: unknown): ConclusionReview | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const raw = value as Record<string, unknown>;
  if (!verdicts.includes(raw.verdict as ConclusionVerdict) || typeof raw.conclusion_text !== 'string') return undefined;
  const card = safeValue(raw) as Record<string, unknown>;
  const checks = Array.isArray(card.checks_not_passed) ? card.checks_not_passed : [];
  return { verdict: raw.verdict as ConclusionVerdict, notPassedCount: checks.length, card };
}
