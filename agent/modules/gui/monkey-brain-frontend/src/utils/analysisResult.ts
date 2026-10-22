import { parseConclusionReview, type ConclusionReview } from './conclusionReview';
export interface AnalysisFileInfo {
  path: string;
  kind: string;
}
export interface AnalysisJobInfo { id: string; status: string; timeoutSeconds: number; message: string; }
export interface AnalysisResultInfo {
  conclusionReview?: ConclusionReview;
  overallStatus?: string;
  componentStatuses?: Record<string, string | number | null>;
  lastExitCode?: number | null;
  identityMismatches?: number;
  numericMismatches?: number;
  jobs?: AnalysisJobInfo[];
  status: string;
  conversationId: string;
  runId: string;
  outputDirectory: string;
  userId: string;
  workspaceDirectory: string;
  executions: number;
  fileChecksPassed: boolean;
  numericalReview: string;
  independentMismatches?: number;
  independentTables?: { file: string; status: 'pass' | 'fail'; mismatches: number }[];
  files: AnalysisFileInfo[];
}
const safePath = (value: unknown): value is string => typeof value === 'string'
  && value.length > 0 && value.length <= 1024 && !/[\\:\x00\r\n]/.test(value)
  && value.split('/').every(part => part.length > 0 && !part.startsWith('.'));

/** Preserve only business/result fields; session tokens and provider credentials never enter chat persistence. */
export function parseAnalysisResult(raw: any, conversationId: unknown, context?: Record<string, any>): AnalysisResultInfo | undefined {
  if (raw?.mode !== 'analysis' || typeof raw.run_id !== 'string' || !/^[a-f0-9]{32}$/.test(raw.run_id)
    || typeof conversationId !== 'string' || !conversationId || conversationId.length > 256) return undefined;
  const files = new Map<string, AnalysisFileInfo>();
  for (const item of Array.isArray(raw.artifacts) ? raw.artifacts.slice(0, 32) : []) {
    if (safePath(item?.path)) files.set(item.path, { path: item.path, kind: typeof item.kind === 'string' ? item.kind : 'output' });
  }
  for (const item of Array.isArray(raw.generated_scripts) ? raw.generated_scripts.slice(0, 48) : []) {
    if (safePath(item?.path) && !files.has(item.path)) files.set(item.path, { path: item.path, kind: 'generated code' });
  }
  const jobs: AnalysisJobInfo[] = [];
  for (const job of Array.isArray(raw.analysis_jobs) ? raw.analysis_jobs.slice(0, 4) : []) {
    if (typeof job?.job_id !== 'string' || !/^[a-f0-9]{32}$/.test(job.job_id)) continue;
    jobs.push({ id: job.job_id, status: typeof job.status === 'string' ? job.status.slice(0, 100) : 'unknown',
      timeoutSeconds: Number.isInteger(job.job_timeout_seconds) && job.job_timeout_seconds > 0 && job.job_timeout_seconds <= 86400 ? job.job_timeout_seconds : 0,
      message: typeof job.message === 'string' ? job.message.slice(0, 1000) : '' });
    if (safePath(job.output_relative) && safePath(job.source_path)) {
      const path = job.output_relative + '/' + job.source_path;
      if (safePath(path) && !files.has(path)) files.set(path, { path, kind: 'submitted code' });
    }
  }
  return { jobs,
    conclusionReview: parseConclusionReview(raw.conclusion_card),
    status: typeof raw.status === 'string' ? raw.status : 'unknown', conversationId, runId: raw.run_id,
    overallStatus: ['blocked', 'environment_rate_limited', 'failed', 'incomplete_review', 'deferred', 'qualified', 'accepted'].includes(raw.overall_status) ? raw.overall_status : undefined,
    componentStatuses: raw.component_statuses && typeof raw.component_statuses === 'object'
      ? Object.fromEntries(['artifacts', 'public_contract', 'independent_numeric', 'internal_review', 'execution', 'last_exit_code', 'identity_mismatch_count', 'numeric_mismatch_count']
        .filter(key => ['string', 'number'].includes(typeof raw.component_statuses[key]) || raw.component_statuses[key] === null)
        .map(key => [key, raw.component_statuses[key]])) : undefined,
    lastExitCode: Number.isInteger(raw.execution?.exit_code) ? raw.execution.exit_code : null,
    identityMismatches: Number.isInteger(raw.component_statuses?.identity_mismatch_count) ? raw.component_statuses.identity_mismatch_count : undefined,
    numericMismatches: Number.isInteger(raw.component_statuses?.numeric_mismatch_count) ? raw.component_statuses.numeric_mismatch_count : undefined,
    outputDirectory: typeof raw.output_directory === 'string' ? raw.output_directory : '',
    userId: typeof context?.userId === 'string' ? context.userId : '',
    workspaceDirectory: typeof context?.workspaceDirectory === 'string' ? context.workspaceDirectory : '',
    executions: Number.isInteger(raw.executions) && raw.executions >= 0 ? raw.executions : 0,
    fileChecksPassed: (raw.validation?.artifact_structural_passed === true || raw.validation?.valid === true) && raw.validation?.required_artifact_coverage?.complete !== false,
    numericalReview: typeof raw.validation?.independent_numeric_status === 'string' ? raw.validation.independent_numeric_status : 'not_performed',
    independentMismatches: Number.isInteger(raw.validation?.independent_numeric?.mismatch_count)
      && raw.validation.independent_numeric.mismatch_count >= 0
      ? raw.validation.independent_numeric.mismatch_count : undefined,
    independentTables: ['regional_values.csv', 'group_results.csv'].flatMap(file => {
      const table = raw.validation?.independent_numeric?.tables?.[file];
      return table && ['pass', 'fail'].includes(table.status) && Number.isInteger(table.mismatch_count) && table.mismatch_count >= 0
        ? [{ file, status: table.status as 'pass' | 'fail', mismatches: table.mismatch_count }] : [];
    }),
    files: [...files.values()],
  };
}
