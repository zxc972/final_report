import { useEffect, useState } from 'react';
import { Button, Tag, message } from 'antd';
import { AnalysisResultInfo } from '../../utils/analysisResult';
import { agentService } from '../../services/agentService';

const pendingStatuses = new Set(['preparing', 'queued', 'running', 'verifying', 'cancelling']);
export default function AnalysisResultCard({ result }: { result: AnalysisResultInfo }) {
  const [live, setLive] = useState(result);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [pollError, setPollError] = useState('');
  useEffect(() => { setLive(result); setPollError(''); }, [result]);
  const job = live.jobs?.[0];
  const pending = !!job && pendingStatuses.has(job.status);
  useEffect(() => {
    if (!pending || !job || pollError) return;
    let stopped = false, timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await agentService.getAnalysisJobStatus(live, job.id);
        if (stopped) return;
        setLive(next);
        if (next.jobs?.some(item => pendingStatuses.has(item.status))) timer = setTimeout(refresh, 10000);
      } catch (error) {
        if (!stopped) setPollError(error instanceof Error ? error.message : 'Could not refresh computation.');
      }
    };
    timer = setTimeout(refresh, 10000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [result.runId, job?.id, pending, pollError]);
  const control = async (cancel = false) => {
    if (!job) return;
    setUpdating(true);
    try { setLive(await agentService.getAnalysisJobStatus(live, job.id, cancel)); setPollError(''); }
    catch (error) { setPollError(error instanceof Error ? error.message : 'Could not query computation.'); }
    finally { setUpdating(false); }
  };
  const finished = live.status === 'completed' && live.executions > 0;
  const failed = ['failed', 'cancelled', 'output_integrity_failed', 'unknown_after_worker_exit'].includes(live.status);
  const label = finished ? 'Computation finished' : live.status === 'failed' ? 'Run failed' : 'Run: ' + live.status;
  const download = async (path: string) => {
    setDownloading(path);
    try { await agentService.downloadAnalysisFile(live, path); }
    catch (error) { message.error(error instanceof Error ? error.message : 'Could not download this analysis file.'); }
    finally { setDownloading(null); }
  };
  return <section className="mt-4 rounded border border-gray-200 p-3" aria-label="Analysis results">
    <div className="mb-2"><Tag color={finished ? 'green' : failed ? 'red' : 'blue'}>{label}</Tag>
      <Tag>{live.fileChecksPassed ? 'File checks passed' : 'File checks incomplete'}</Tag></div>
    <p className="text-xs text-gray-600">Numerical review: {live.numericalReview === 'not_performed' ? 'not run' : live.numericalReview}.
      {' '}File checks do not establish anatomical or scientific validity.</p>
    {job && <div className="my-2 text-sm" aria-label="Background computation">
      <p>Background job: {job.status}{job.timeoutSeconds ? ' (limit ' + job.timeoutSeconds + ' seconds)' : ''}</p>
      {job.message && <p className="text-xs">{job.message}</p>}
      <Button size="small" loading={updating} onClick={() => control(false)}>Refresh computation</Button>
      {pending && <Button size="small" danger disabled={updating} onClick={() => control(true)}>Cancel computation</Button>}
      {pollError && <p role="alert" className="text-xs text-red-600">{pollError}</p>}
    </div>}
    {live.files.length > 0 ? <ul className="mt-2 space-y-1">{live.files.map(file => <li key={file.path} className="flex items-center gap-2 text-sm">
      <span className="min-w-0 flex-1 break-all">{file.path}</span><Tag>{file.kind}</Tag>
      <Button size="small" aria-label={'Download ' + file.path} loading={downloading === file.path}
        disabled={!live.userId || !live.workspaceDirectory || (downloading !== null && downloading !== file.path)}
        onClick={() => download(file.path)}>Download</Button>
    </li>)}</ul> : <p className="text-sm mt-2">No output files are attached to this run.</p>}
  </section>;
}
