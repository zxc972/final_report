import { useEffect, useState } from 'react';
import { Button, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
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
  const statusClass = finished ? 'is-ok' : failed ? 'is-err' : 'is-run';
  return <section className="px-result" aria-label="Analysis results">
    <div className="px-result-head">
      <span className={'px-tag ' + statusClass}>{label}</span>
      <span className={'px-tag ' + (live.fileChecksPassed ? 'is-ok' : 'is-warn')}>{live.fileChecksPassed ? 'File checks passed' : 'File checks incomplete'}</span>
      <span className="px-tag">Numerical review: {live.numericalReview === 'not_performed' ? 'not run' : live.numericalReview}</span>
    </div>
    <div className="px-result-body">
      <p className="px-result-note">File checks do not establish anatomical or scientific validity.</p>
      {job && <div className="mb-2" aria-label="Background computation">
        <div className="flex items-center gap-2 flex-wrap">
          <span>Background job: {job.status}{job.timeoutSeconds ? ' (limit ' + job.timeoutSeconds + ' seconds)' : ''}</span>
          <Button size="small" loading={updating} onClick={() => control(false)}>Refresh computation</Button>
          {pending && <Button size="small" danger disabled={updating} onClick={() => control(true)}>Cancel computation</Button>}
        </div>
        {job.message && <p className="text-xs px-secondary" style={{ margin: '4px 0 0' }}>{job.message}</p>}
        {pollError && <p role="alert" className="text-xs" style={{ color: 'var(--px-err)', margin: '4px 0 0' }}>{pollError}</p>}
      </div>}
      {live.files.length > 0 ? <ul className="px-files">{live.files.map(file => <li key={file.path}>
        <span className="px-file-name px-mono" title={file.path}>{file.path}</span>
        <span className="px-file-kind">{file.kind}</span>
        <Button size="small" type="text" icon={<DownloadOutlined />} aria-label={'Download ' + file.path} loading={downloading === file.path}
          disabled={!live.userId || !live.workspaceDirectory || (downloading !== null && downloading !== file.path)}
          onClick={() => download(file.path)} />
      </li>)}</ul> : <p className="px-muted" style={{ margin: 0 }}>No output files are attached to this run.</p>}
    </div>
  </section>;
}
