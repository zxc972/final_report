export interface AnalysisFileInfo {
  path: string;
  kind: string;
}
export interface AnalysisJobInfo { id: string; status: string; timeoutSeconds: number; message: string; }
export interface AnalysisResultInfo {
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
    status: typeof raw.status === 'string' ? raw.status : 'unknown', conversationId, runId: raw.run_id,
    outputDirectory: typeof raw.output_directory === 'string' ? raw.output_directory : '',
    userId: typeof context?.userId === 'string' ? context.userId : '',
    workspaceDirectory: typeof context?.workspaceDirectory === 'string' ? context.workspaceDirectory : '',
    executions: Number.isInteger(raw.executions) && raw.executions >= 0 ? raw.executions : 0,
    fileChecksPassed: raw.validation?.valid === true && raw.validation?.required_artifact_coverage?.complete !== false,
    numericalReview: typeof raw.validation?.independent_numeric_status === 'string' ? raw.validation.independent_numeric_status : 'not_performed',
    files: [...files.values()],
  };
}
