/*
 * Copyright (C) 2026 Wang Zheng Lab, Peking University
 *
 * This file is part of PrimateX.
 *
 * PrimateX is free software: you can redistribute it and/or modify it under the
 * terms of the GNU Affero General Public License as published by the Free
 * Software Foundation, either version 3 of the License, or (at your option) any
 * later version.
 *
 * PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
 * A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
 * details.
 *
 * If you use PrimateX in academic work, please cite:
 * Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
 * Multi-agentic routing with PrimateX: standardized structural MRI analysis
 * for non-human primates and humans.
 *
 * * Equal contribution.
 * Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
 * (zheng.wang@pku.edu.cn).
 *
 * See CITATION.cff for full citation details.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Tooltip, message as toast } from 'antd';
import { CheckOutlined, CloseOutlined, ExclamationOutlined, DownloadOutlined } from '@ant-design/icons';
import { Message } from '../../types/agent';
import { ProcessEvent, ProcessStatus } from '../../types/process';
import { AnalysisResultInfo } from '../../utils/analysisResult';
import { collapseEvents, currentStepIndex, formatStepTime } from '../../utils/processEvents';
import { useConversationProcess } from '../../hooks/useConversationProcess';
import { agentService } from '../../services/agentService';

interface ProcessPanelProps {
  conversationId: string | null;
  /** True while a chat request is in flight. */
  active: boolean;
  messages: Message[];
  onClose?: () => void;
}

const STATUS_ICON: Record<ProcessStatus, React.ReactNode> = {
  done: <CheckOutlined />,
  warn: <ExclamationOutlined />,
  blocked: <ExclamationOutlined />,
  failed: <CloseOutlined />,
  running: null,
};

const RUN_LABEL: Record<string, { text: string; cls: string }> = {
  running: { text: 'Running', cls: 'is-run' },
  completed: { text: 'Completed', cls: 'is-ok' },
  warning: { text: 'Warning', cls: 'is-warn' },
  incomplete_review: { text: 'Incomplete review', cls: 'is-warn' },
  deferred: { text: 'Deferred', cls: 'is-warn' },
  qualified: { text: 'Qualified', cls: 'is-warn' },
  accepted: { text: 'Accepted', cls: 'is-ok' },
  failed: { text: 'Failed', cls: 'is-err' },
  blocked: { text: 'Blocked', cls: 'is-warn' },
  idle: { text: 'Idle', cls: '' },
};

/** Request-level steps used when the server does not record process events. */
function fallbackEvents(messages: Message[], active: boolean): ProcessEvent[] {
  let lastUser = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type === 'user') { lastUser = i; break; }
  }
  if (lastUser < 0) return [];
  const toSeconds = (value: Date | string) => new Date(value).getTime() / 1000;
  const request = messages[lastUser];
  const events: ProcessEvent[] = [{
    seq: 1, time: toSeconds(request.timestamp), stage: 'other', status: 'done',
    title: 'Request sent', summary: request.content.slice(0, 80),
  }];
  const replies = messages.slice(lastUser + 1);
  const failed = replies.find((m) => m.type === 'system' && /failed/i.test(m.content));
  const answer = replies.find((m) => m.type === 'agent');
  if (active) {
    events.push({ seq: 2, time: 0, stage: 'other', status: 'running', title: 'Waiting for the assistant' });
  } else if (failed) {
    events.push({ seq: 2, time: toSeconds(failed.timestamp), stage: 'result', status: 'failed', title: 'Request failed', summary: failed.content.slice(0, 120) });
  } else if (answer) {
    events.push({ seq: 2, time: toSeconds(answer.timestamp), stage: 'result', status: 'done', title: 'Response received' });
  }
  return events;
}

function latestAnalysis(messages: Message[]): AnalysisResultInfo | undefined {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const analysis = messages[i].metadata?.analysis;
    if (analysis) return analysis;
    if (messages[i].type === 'user') return undefined;
  }
  return undefined;
}

const ProcessPanel: React.FC<ProcessPanelProps> = ({ conversationId, active, messages, onClose }) => {
  const { process, error } = useConversationProcess(conversationId, active);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showChecks, setShowChecks] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);

  // Use recorded events when the server has any for this conversation;
  // otherwise (legacy profile, preprocessing mode) show request-level status.
  const tracked = !!process?.available && process.events.length > 0;
  const events = tracked ? process!.events : fallbackEvents(messages, active);
  const steps = useMemo(() => collapseEvents(events), [events]);
  const runningIndex = currentStepIndex(steps, active || process?.status === 'running');
  const analysis = latestAnalysis(messages);
  const plan = tracked ? process!.plan : undefined;
  const outputs = tracked && process!.outputs.length ? process!.outputs : analysis?.files ?? [];
  const codePath = plan?.codePath ?? analysis?.files.find((f) => f.kind === 'generated code')?.path;
  const runStatus = tracked ? process!.status : active ? 'running' : steps.length ? (steps[steps.length - 1].event.status === 'failed' ? 'failed' : 'completed') : 'idle';
  const latestRoute = [...messages].reverse().find((message) => message.metadata?.route)?.metadata?.route;
  const isPipelineReply = latestRoute === 'pipeline' && runStatus === 'completed';
  const isOfflineReply = analysis?.status === 'not_executed_offline_fixture'
    || analysis?.conclusionReview?.card.text_authorship === 'explicit_offline_placeholder';
  const label = (isPipelineReply || (isOfflineReply && runStatus === 'completed')) ? { text: 'Reply finished', cls: 'is-ok' } : RUN_LABEL[runStatus] ?? RUN_LABEL.idle;

  useEffect(() => {
    if (runningIndex < 0) return undefined;
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [runningIndex]);

  const download = async (path: string) => {
    if (!analysis || !analysis.files.some((f) => f.path === path)) return;
    setDownloading(path);
    try {
      await agentService.downloadAnalysisFile(analysis, path);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not download this file.');
    } finally {
      setDownloading(null);
    }
  };

  const canDownload = (path: string) => !!analysis && analysis.files.some((f) => f.path === path);

  const renderFile = (path: string) => (canDownload(path)
    ? <button type="button" className="px-link px-mono" onClick={() => download(path)} disabled={downloading !== null}>{path}</button>
    : <span className="px-mono">{path}</span>);

  return (
    <aside className="px-panel" aria-label="Run details">
      <div className="px-panel-head">
        <h2>Run details</h2>
        {steps.length > 0 && <span className={`px-tag ${label.cls}`}>{label.text}</span>}
        <div className="px-spacer" />
        {process?.runId && (
          <Tooltip title={process.runId}>
            <span className="px-mono px-muted" style={{ fontSize: 11 }}>run {process.runId.slice(0, 4)}…{process.runId.slice(-3)}</span>
          </Tooltip>
        )}
        {onClose && <Button type="text" size="small" icon={<CloseOutlined />} aria-label="Hide run details" onClick={onClose} />}
      </div>

      <div className="px-panel-body">
        {steps.length === 0 ? (
          <div className="px-panel-sec">
            <p className="px-panel-empty">Nothing has run in this conversation yet. When you send a request, the data, methods, checks and code the assistant uses will appear here.</p>
          </div>
        ) : (
          <>
            {plan && (
              <section className="px-panel-sec">
                <h3>Basis <span>{plan.version ? `Plan v${plan.version}` : 'Plan'}{plan.sealed ? ' · sealed' : ' · draft'}</span></h3>
                <dl className="px-kv">
                  {plan.data && (<>
                    <dt>Data</dt>
                    <dd>
                      {plan.data.summary}{' '}
                      {plan.data.files.length > 0 && (
                        <button type="button" className="px-link" onClick={() => setShowFiles((v) => !v)}>{showFiles ? 'hide' : 'view'}</button>
                      )}
                      {showFiles && plan.data.files.map((file) => <span key={file} className="px-kv-sub px-mono">{file}</span>)}
                    </dd>
                  </>)}
                  {plan.atlas && (<>
                    <dt>Atlas</dt>
                    <dd>
                      {plan.atlas.name}{plan.atlas.space ? ` · ${plan.atlas.space}` : ''}
                      {plan.atlas.rule && <span className="px-kv-sub">{plan.atlas.rule}</span>}
                    </dd>
                  </>)}
                  {plan.method && (<>
                    <dt>Method</dt>
                    <dd>
                      {plan.method.name}{' '}
                      {plan.method.sourceUrl && <a className="px-link" href={plan.method.sourceUrl} target="_blank" rel="noopener noreferrer">source</a>}
                    </dd>
                  </>)}
                  {plan.checks && (<>
                    <dt>Checks</dt>
                    <dd>
                      <button type="button" className="px-link" onClick={() => setShowChecks((v) => !v)} aria-expanded={showChecks} style={{ color: 'inherit' }}>
                        {plan.checks.pass > 0 && <span className="px-tag is-ok">{plan.checks.pass} pass</span>}
                        {plan.checks.warn > 0 && <span className="px-tag is-warn">{plan.checks.warn} warn</span>}
                        <span className="px-tag">{plan.checks.unverified ?? 0} unverified</span>
                        {plan.checks.block > 0 && <span className="px-tag is-err">{plan.checks.block} block</span>}
                      </button>
                      {showChecks && plan.checks.items.map((item) => (
                        <span key={item.id} className="px-kv-sub">
                          <span className={`px-tag ${item.verdict === 'pass' ? 'is-ok' : item.verdict === 'warn' ? 'is-warn' : 'is-err'}`}>{item.verdict}</span>
                          {item.id}{item.note ? ` — ${item.note}` : ''}
                        </span>
                      ))}
                    </dd>
                  </>)}
                  {codePath && (<><dt>Code</dt><dd>{renderFile(codePath)}</dd></>)}
                </dl>
              </section>
            )}

            {!plan && codePath && (
              <section className="px-panel-sec">
                <h3>Basis</h3>
                <dl className="px-kv"><dt>Code</dt><dd>{renderFile(codePath)}</dd></dl>
              </section>
            )}

            <section className="px-panel-sec">
              <h3>Steps</h3>
              <ol className="px-timeline">
                {steps.map((step, index) => {
                  const { event } = step;
                  const isCurrent = index === runningIndex;
                  const isOpen = !!expanded[step.key];
                  const hasDetail = !!event.detail;
                  const time = event.status === 'running' && event.time
                    ? `${Math.max(0, Math.round(now - event.time))} s`
                    : formatStepTime(event.time, process?.startedAt);
                  return (
                    <li key={step.key} className={`px-step${isCurrent ? ' is-current' : ''}`}>
                      <span className={`px-step-icon is-${event.status}`} aria-label={event.status === 'warn' ? 'warning' : event.status}>{STATUS_ICON[event.status]}</span>
                      <div>
                        <button
                          type="button"
                          className={`px-step-title${hasDetail ? ' is-expandable' : ''}`}
                          onClick={() => hasDetail && setExpanded((v) => ({ ...v, [step.key]: !isOpen }))}
                          aria-expanded={hasDetail ? isOpen : undefined}
                        >
                          {isCurrent ? 'Now: ' : ''}{event.title}{step.repeat > 1 ? ` ×${step.repeat}` : ''}
                          {event.status === 'warn' && <span className="px-tag is-warn">Warning</span>}
                        </button>
                        {event.summary && <span className="px-step-sub">{event.summary}</span>}
                        {isOpen && event.detail && (
                          <div className="px-step-detail">
                            {Object.entries(event.detail).map(([key, value]) => (
                              <div key={key}><span>{key}</span><span className="px-mono" style={{ fontSize: 12 }}>{value}</span></div>
                            ))}
                          </div>
                        )}
                      </div>
                      <span className="px-step-time">{time}</span>
                    </li>
                  );
                })}
              </ol>
            </section>

            {outputs.length > 0 && (
              <section className="px-panel-sec">
                <h3>Outputs <span>{outputs.length}</span></h3>
                <ul className="px-files">
                  {outputs.map((file) => (
                    <li key={file.path}>
                      <span className="px-file-name px-mono" title={file.path}>{file.path}</span>
                      <span className="px-file-kind">{file.kind}</span>
                      {canDownload(file.path) && (
                        <Button
                          type="text"
                          size="small"
                          icon={<DownloadOutlined />}
                          aria-label={`Download ${file.path} from run details`}
                          loading={downloading === file.path}
                          disabled={downloading !== null && downloading !== file.path}
                          onClick={() => download(file.path)}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
        {error && <div className="px-panel-sec"><p role="alert" className="px-panel-empty" style={{ color: 'var(--px-err)' }}>{error}</p></div>}
      </div>

      <div className="px-panel-foot">
        {tracked
          ? 'Steps are recorded from actual tool calls, not written by the model.'
          : process?.available === false && steps.length > 0
          ? 'Step-by-step tracking is not available for this request; showing request status only.'
          : 'Steps are recorded from actual tool calls once a request starts.'}
      </div>
    </aside>
  );
};

export default ProcessPanel;
