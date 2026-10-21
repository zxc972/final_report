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

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Modal,
  Progress,
  Space,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  DownloadOutlined,
  FileTextOutlined,
  InboxOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { usePipelineStore } from '../stores/pipelineStore';
import { useConfigStore } from '../stores/configStore';
import { pipelineService } from '../services/pipelineService';
import { PipelineTask, PipelineStep, WorkspaceSubject } from '../types/pipeline';
import { buildPathWithToken } from '../services/accessToken';
import { PageHeader } from '../components/Layout/Page';

// ---------- types ----------

interface SubjectRow {
  subjectId: string;
  pipelineTask: PipelineTask | null;
  fsData: WorkspaceSubject | null;
  status: 'running' | 'pending' | 'completed' | 'failed' | 'cancelled' | 'has_input' | 'unknown';
}

interface LogPreview {
  log: string;
  updatedAt: string;
  error?: string;
}

// ---------- helpers ----------

// Higher number = higher priority when multiple tasks share the same subjectId
const STATUS_PRIORITY: Record<string, number> = {
  running: 5,
  pending: 4,
  failed: 3,
  cancelled: 2,
  completed: 1,
};

const STATUS_COLOR: Record<string, string> = {
  running: 'processing',
  pending: 'default',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
  has_input: 'geekblue',
  unknown: 'default',
};

const STATUS_LABEL: Record<string, string> = {
  running: 'Running',
  pending: 'Pending',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  has_input: 'Has Input',
  unknown: 'Unknown',
};

const ACTIVE_STATUSES = new Set(['running', 'pending']);
const LOG_PREVIEW_LINES = 8;
const LOG_PREVIEW_LINE_CHARS = 180;
const LOG_PREVIEW_TOTAL_CHARS = 1800;
const ISO_TIMEZONE_SUFFIX_RE = /(Z|[+-]\d{2}:?\d{2})$/;

function fsStatus(row: Pick<SubjectRow, 'fsData' | 'pipelineTask'>): SubjectRow['status'] {
  if (!row.fsData?.hasOutput) {
    return row.fsData?.hasInput ? 'has_input' : 'unknown';
  }

  const completedSteps = new Set(row.fsData.completedSteps || []);
  const plannedSteps = row.pipelineTask?.steps || [];
  if (plannedSteps.length > 0) {
    return plannedSteps.every((step) => completedSteps.has(step)) ? 'completed' : 'unknown';
  }

  return 'completed';
}

function filesystemOnlyStatus(fsData: WorkspaceSubject | null): SubjectRow['status'] {
  return fsStatus({ fsData, pipelineTask: null });
}

function deriveStatus(row: Omit<SubjectRow, 'status'>): SubjectRow['status'] {
  if (row.pipelineTask) {
    return row.pipelineTask.status as SubjectRow['status'];
  }
  return fsStatus(row);
}

function mergeRows(tasks: PipelineTask[], fsSubjects: WorkspaceSubject[], userId: string): SubjectRow[] {
  const map = new Map<string, SubjectRow>();

  // Add tasks from pipelineStore (filter by current user).
  // Multiple historical tasks may share the same subjectId — keep the most relevant one:
  // prefer higher-priority status (running > pending > failed > cancelled > completed),
  // then prefer newer createdAt when priority is equal.
  for (const task of tasks) {
    if (task.userId !== userId) continue;
    const existing = map.get(task.subjectId);
    if (existing?.pipelineTask) {
      const existPri = STATUS_PRIORITY[existing.pipelineTask.status] ?? 0;
      const newPri   = STATUS_PRIORITY[task.status] ?? 0;
      const existTime = existing.pipelineTask.createdAt ?? '';
      const newTime   = task.createdAt ?? '';
      if (newPri < existPri) continue;                        // existing is more active → skip
      if (newPri === existPri && newTime <= existTime) continue; // same priority, existing is newer → skip
    }
    const partial = { subjectId: task.subjectId, pipelineTask: task, fsData: null };
    map.set(task.subjectId, { ...partial, status: deriveStatus(partial) });
  }

  // Merge/add filesystem subjects
  for (const fs of fsSubjects) {
    const existing = map.get(fs.subjectId);
    if (existing) {
      existing.fsData = fs;
      existing.status = deriveStatus(existing);
    } else {
      const partial = { subjectId: fs.subjectId, pipelineTask: null, fsData: fs };
      map.set(fs.subjectId, { ...partial, status: deriveStatus(partial) });
    }
  }

  return Array.from(map.values()).sort((a, b) => a.subjectId.localeCompare(b.subjectId));
}

function tailLogLines(log: string, maxLines = LOG_PREVIEW_LINES): string {
  const lines = log
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.trim().length > 0);
  const preview = lines
    .slice(-maxLines)
    .map((line) => (
      line.length > LOG_PREVIEW_LINE_CHARS
        ? `${line.slice(0, LOG_PREVIEW_LINE_CHARS)} ...`
        : line
    ))
    .join('\n');
  return preview.length > LOG_PREVIEW_TOTAL_CHARS
    ? `... ${preview.slice(-LOG_PREVIEW_TOTAL_CHARS)}`
    : preview;
}

function parseTaskTimeMs(value?: string | null): number {
  if (!value) return Number.NaN;
  const normalized = ISO_TIMEZONE_SUFFIX_RE.test(value) ? value : `${value}Z`;
  return Date.parse(normalized);
}

function computeDurationSeconds(task: PipelineTask | null | undefined, nowMs: number): number | null {
  if (!task?.startTime) return null;
  if (typeof task.durationSeconds === 'number' && Number.isFinite(task.durationSeconds) && task.endTime) {
    return task.durationSeconds;
  }
  const startMs = parseTaskTimeMs(task.startTime);
  const endMs = task.endTime ? parseTaskTimeMs(task.endTime) : nowMs;
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return null;
  return Math.round((endMs - startMs) / 1000);
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return 'Not available';
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function formatTaskStartedAt(task?: PipelineTask | null): string | null {
  if (!task?.startTime) return null;
  const date = new Date(parseTaskTimeMs(task.startTime));
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

function chooseServerTask(existing: PipelineTask | undefined, incoming: PipelineTask): PipelineTask {
  if (!existing) return incoming;
  const existingActive = ACTIVE_STATUSES.has(existing.status);
  const incomingActive = ACTIVE_STATUSES.has(incoming.status);
  if (incomingActive && !existingActive) return incoming;
  if (!incomingActive && existingActive) return existing;

  const existingTime = existing.updatedAt || existing.createdAt || '';
  const incomingTime = incoming.updatedAt || incoming.createdAt || '';
  return incomingTime >= existingTime ? incoming : existing;
}

// ---------- component ----------

const SegmentationPage: React.FC = () => {
  const { tasks, refreshStatuses, cancelTask } = usePipelineStore();
  const { config } = useConfigStore();

  const [fsSubjects, setFsSubjects] = useState<WorkspaceSubject[]>([]);
  // Server-side tasks: active tasks that may not be in pipelineStore
  // (e.g. after page refresh or submitted from another session)
  const [serverTasks, setServerTasks] = useState<PipelineTask[]>([]);
  const [scanning, setScanning] = useState(false);
  const [logModalTask, setLogModalTask] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<string>('');
  const [logLoading, setLogLoading] = useState(false);
  const [logPreviews, setLogPreviews] = useState<Record<string, LogPreview>>({});
  const [downloadingIds, setDownloadingIds] = useState<Set<string>>(new Set());
  const [durationNowMs, setDurationNowMs] = useState(() => Date.now());

  const userId = config?.userId || '';
  const workspaceDirectory = config?.workspaceDirectory || '';

  // Pull active tasks from BOTH the Node.js pipeline backend AND the FastAPI agent backend
  const fetchServerTasks = useCallback(async () => {
    if (!userId) return;
    try {
      // Node.js backend tasks (submitted via Pipeline page)
      const pipelineTasks = await pipelineService.getServerTasks(userId, workspaceDirectory);
      const normalized = pipelineTasks.map((t: any) => ({
        taskId: t.taskId,
        status: t.status,
        currentStep: t.currentStep,
        message: t.message,
        progress: t.progress ?? 0,
        userId,
        subjectId: t.subjectId,
        t1Path: t.t1Path || '',
        workspaceDirectory: t.workspaceDirectory || workspaceDirectory,
        species: t.species || 'Macaque',
        segSpecies: t.segSpecies || 'cynomolgus',
        steps: t.steps || [],
        createdAt: t.startTime || new Date().toISOString(),
        startTime: t.startTime,
        endTime: t.endTime,
        durationSeconds: t.durationSeconds ?? null,
        updatedAt: new Date().toISOString(),
        logPath: t.logPath,
        source: 'pipeline' as const,
      }));

      // FastAPI agent backend tasks (submitted via Workflow Assistant)
      const agentRaw = await pipelineService.getAgentTasks(userId, workspaceDirectory);
      const effectiveWsPrefix = workspaceDirectory
        ? workspaceDirectory.replace(/\/$/, '') + '/' + userId
        : null;
      const agentTasks = agentRaw
        .filter((t: any) => {
          // Only include tasks whose workspace matches current user's workspace
          if (!effectiveWsPrefix) return true;
          return (t.workspaceDirectory || '').startsWith(effectiveWsPrefix);
        })
        .map((t: any) => ({
          taskId: t.taskId,
          status: t.status,
          currentStep: t.currentStep,
          message: t.message,
          progress: t.progress ?? 0,
          userId,
          subjectId: t.subjectId,
          t1Path: '',
          workspaceDirectory: t.workspaceDirectory || workspaceDirectory,
          species: t.species || 'Macaque',
          segSpecies: t.segSpecies || 'cynomolgus',
          steps: t.steps || [],
          createdAt: t.startTime || new Date().toISOString(),
          startTime: t.startTime,
          endTime: t.endTime,
          durationSeconds: t.durationSeconds ?? null,
          updatedAt: new Date().toISOString(),
          logPath: t.logPath,
          source: 'agent' as const,
        }));

      setServerTasks([...normalized, ...agentTasks]);
    } catch { /* backend may not be ready */ }
  }, [userId, workspaceDirectory]);

  // Scan filesystem for subjects
  const scanFilesystem = useCallback(async () => {
    if (!userId || !workspaceDirectory) return;
    setScanning(true);
    try {
      const subjects = await pipelineService.getWorkspaceSubjects(userId, workspaceDirectory);
      setFsSubjects(subjects);
    } catch (err: any) {
      console.error('Failed to scan workspace subjects:', err);
    } finally {
      setScanning(false);
    }
  }, [userId, workspaceDirectory]);

  // Full refresh: server tasks + in-memory statuses + filesystem scan
  const handleRefresh = useCallback(async () => {
    await fetchServerTasks();
    try { await refreshStatuses(); } catch (_) {}
    await scanFilesystem();
  }, [fetchServerTasks, refreshStatuses, scanFilesystem]);

  // On mount and when userId/workspace changes
  useEffect(() => {
    fetchServerTasks();
    scanFilesystem();
  }, [fetchServerTasks, scanFilesystem]);

  // Merge pipelineStore tasks with server tasks (server is authoritative for status)
  const allTasks = useMemo(() => {
    const map = new Map<string, PipelineTask>();
    // Start with pipelineStore tasks
    for (const t of tasks) map.set(t.taskId, t);
    // Overlay with server tasks (more up-to-date status)
    for (const t of serverTasks) {
      const existing = map.get(t.taskId);
      if (existing) {
        map.set(t.taskId, {
          ...existing,
          status: t.status,
          currentStep: t.currentStep,
          message: t.message,
          progress: t.progress,
          source: t.source,
          logPath: t.logPath,
          startTime: t.startTime,
          endTime: t.endTime,
          durationSeconds: t.durationSeconds,
        });
      } else {
        map.set(t.taskId, t);
      }
    }
    return Array.from(map.values());
  }, [tasks, serverTasks]);

  // Auto-refresh while any task is running/pending
  const hasActiveTask = allTasks.some((t) => t.status === 'running' || t.status === 'pending');

  useEffect(() => {
    if (!hasActiveTask) return;
    const id = setInterval(() => {
      fetchServerTasks();
      refreshStatuses().catch(() => {});
      scanFilesystem();
    }, 5000);
    return () => clearInterval(id);
  }, [hasActiveTask, fetchServerTasks, refreshStatuses, scanFilesystem]);

  // Keep elapsed runtime moving smoothly in the UI without increasing backend polling.
  useEffect(() => {
    if (!hasActiveTask) return;
    const id = setInterval(() => {
      setDurationNowMs(Date.now());
    }, 1000);
    return () => clearInterval(id);
  }, [hasActiveTask]);

  // mergeRows handles local/persisted tasks, then server state and filesystem state
  // make the final status authoritative. Browser-persisted running/pending tasks are
  // stale after refreshes or backend restarts, so they must never outrank live server
  // state or filesystem-confirmed completion.
  const rows = useMemo(() => {
    const base = mergeRows(allTasks, fsSubjects, userId);

    // Build subjectId → server task map. Server state is authoritative for both
    // active and terminal statuses while the backend still knows about the task.
    const serverBySubject = new Map<string, PipelineTask>();
    for (const t of serverTasks) {
      serverBySubject.set(t.subjectId, chooseServerTask(serverBySubject.get(t.subjectId), t));
    }

    return base.map((row) => {
      const serverTask = serverBySubject.get(row.subjectId);
      if (serverTask) {
        return {
          ...row,
          status: serverTask.status as SubjectRow['status'],
          pipelineTask: {
            ...(row.pipelineTask ?? serverTask),
            status: serverTask.status,
            currentStep: serverTask.currentStep,
            message: serverTask.message,
            progress: serverTask.progress,
            source: serverTask.source,
            logPath: serverTask.logPath,
            startTime: serverTask.startTime,
            endTime: serverTask.endTime,
            durationSeconds: serverTask.durationSeconds,
          },
        };
      }

      const fsOnly = filesystemOnlyStatus(row.fsData);
      if (row.pipelineTask && fsOnly === 'completed') {
        const completedStatus: PipelineTask['status'] = 'completed';
        return {
          ...row,
          status: completedStatus,
          pipelineTask: {
            ...row.pipelineTask,
            status: completedStatus,
            progress: 100,
            message: 'Completed from filesystem scan',
          },
        };
      }

      if (row.pipelineTask && ACTIVE_STATUSES.has(row.pipelineTask.status)) {
        const status = fsOnly;
        return {
          ...row,
          status,
          pipelineTask: {
            ...row.pipelineTask,
            status: status === 'completed' ? 'completed' : row.pipelineTask.status,
            progress: status === 'completed' ? 100 : row.pipelineTask.progress,
            message: status === 'completed'
              ? 'Completed from filesystem scan'
              : 'No active server task found; showing filesystem state',
          },
        };
      }

      if (!row.pipelineTask) {
        return { ...row, status: fsStatus(row) };
      }

      return row;
    });
  }, [allTasks, fsSubjects, userId, serverTasks]);

  const runningCount = rows.filter((r) => r.status === 'running').length;
  const pendingCount = rows.filter((r) => r.status === 'pending').length;
  const completedCount = rows.filter((r) => r.status === 'completed').length;
  const failedCount = rows.filter((r) => r.status === 'failed').length;

  const activeTasks = useMemo(() => {
    const seen = new Set<string>();
    const result: Array<{ task: PipelineTask; row: SubjectRow }> = [];
    for (const row of rows) {
      if (!(row.status === 'running' || row.status === 'pending') || !row.pipelineTask?.taskId) continue;
      if (seen.has(row.pipelineTask.taskId)) continue;
      seen.add(row.pipelineTask.taskId);
      result.push({ task: row.pipelineTask, row });
    }
    return result;
  }, [rows]);

  const fetchRowLog = useCallback(async (row: SubjectRow): Promise<string> => {
    if (row.pipelineTask?.taskId) {
      try {
        const result = await pipelineService.getTaskLog(row.pipelineTask.taskId, row.pipelineTask.source || 'pipeline');
        return result.log;
      } catch (err) {
        // Fall through to the subject-level log lookup below. In-memory task state
        // can disappear after backend restarts or account switches while log files remain on disk.
      }
    }
    if (!userId || !workspaceDirectory) {
      throw new Error('User ID or workspace directory is not available');
    }
    const result = await pipelineService.getSubjectLog(userId, row.subjectId, workspaceDirectory);
    return result.log;
  }, [userId, workspaceDirectory]);

  const fetchLogPreviews = useCallback(async () => {
    if (activeTasks.length === 0) return;
    const entries = await Promise.all(activeTasks.map(async ({ task, row }) => {
      try {
        const log = await fetchRowLog(row);
        return [
          task.taskId,
          {
            log: tailLogLines(log) || '(log not yet available)',
            updatedAt: new Date().toISOString(),
          },
        ] as const;
      } catch (err: any) {
        return [
          task.taskId,
          {
            log: '',
            updatedAt: new Date().toISOString(),
            error: err.message || 'Failed to load log preview',
          },
        ] as const;
      }
    }));
    setLogPreviews((prev) => {
      const next = { ...prev };
      for (const [taskId, preview] of entries) next[taskId] = preview;
      return next;
    });
  }, [activeTasks, fetchRowLog]);

  useEffect(() => {
    if (activeTasks.length === 0) return;
    fetchLogPreviews();
    const id = setInterval(fetchLogPreviews, 5000);
    return () => clearInterval(id);
  }, [activeTasks, fetchLogPreviews]);

  // ---------- actions ----------

  const handleViewLog = async (row: SubjectRow) => {
    setLogModalTask(row.pipelineTask?.taskId || row.subjectId);
    setLogContent('');
    setLogLoading(true);
    try {
      const log = await fetchRowLog(row);
      setLogContent(log);
    } catch (err: any) {
      setLogContent(`Failed to load log: ${err.message}`);
    } finally {
      setLogLoading(false);
    }
  };

  const handleDownloadOutput = async (row: SubjectRow) => {
    const outputDir = row.fsData?.outputDir;
    if (!outputDir || !userId || !workspaceDirectory) return;
    const key = `dl_out_${row.subjectId}`;
    setDownloadingIds((prev) => new Set(prev).add(key));
    try {
      await pipelineService.downloadSubject(userId, row.subjectId, workspaceDirectory);
    } catch (err: any) {
      message.error(err.message || 'Download failed');
    } finally {
      setDownloadingIds((prev) => { const s = new Set(prev); s.delete(key); return s; });
    }
  };

  const handleDownloadInput = async (row: SubjectRow) => {
    const inputDir = row.fsData?.inputDir;
    if (!inputDir) return;
    const key = `dl_in_${row.subjectId}`;
    setDownloadingIds((prev) => new Set(prev).add(key));
    try {
      await pipelineService.downloadDir(inputDir, `${row.subjectId}_input`);
    } catch (err: any) {
      message.error(err.message || 'Download failed');
    } finally {
      setDownloadingIds((prev) => { const s = new Set(prev); s.delete(key); return s; });
    }
  };

  const handleCancel = async (row: SubjectRow) => {
    if (!row.pipelineTask) return;
    try {
      if (row.pipelineTask.source === 'agent') {
        await pipelineService.cancelTask(row.pipelineTask.taskId, 'agent');
        setServerTasks((prev) => prev.map((task) => (
          task.taskId === row.pipelineTask!.taskId
            ? { ...task, status: 'cancelled', message: 'Cancelled by user', updatedAt: new Date().toISOString() }
            : task
        )));
      } else {
        await cancelTask(row.pipelineTask.taskId);
      }
      message.success('Task cancelled');
    } catch (err: any) {
      message.error(err.message || 'Cancel failed');
    }
  };

  // ---------- render helpers ----------

  // Only show filesystem-confirmed completed steps as tags.
  // Do NOT fall back to pipelineTask.steps (planned steps) — that would flash
  // all 7 tags the moment a task is submitted before the filesystem scan returns.
  const stepsDisplay = (row: SubjectRow): PipelineStep[] => {
    return row.fsData?.completedSteps || [];
  };

  // ---------- JSX ----------

  return (
    <>
      {/* Log viewer modal */}
      <Modal
        open={!!logModalTask}
        title={`Pipeline Log — ${logModalTask}`}
        onCancel={() => { setLogModalTask(null); setLogContent(''); }}
        footer={<Button onClick={() => { setLogModalTask(null); setLogContent(''); }}>Close</Button>}
        width={860}
      >
        {logLoading ? (
          <div className="text-center py-8 text-gray-500">Loading log…</div>
        ) : (
          <pre className="bg-gray-900 text-green-300 text-xs p-4 rounded overflow-auto max-h-[60vh] whitespace-pre-wrap break-all">
            {logContent || '(empty)'}
          </pre>
        )}
      </Modal>

      <div className="px-page">
        <div className="px-page-inner">
          <PageHeader
            title="Tasks"
            description="Pipeline tasks and subjects found in your workspace."
            actions={(
            <Space>
              <Badge count={runningCount} overflowCount={99} color="blue" offset={[-4, 4]}>
                <Tag color="blue">Running</Tag>
              </Badge>
              <Badge count={pendingCount} overflowCount={99} color="default" offset={[-4, 4]}>
                <Tag>Pending</Tag>
              </Badge>
              <Badge count={completedCount} overflowCount={99} color="green" offset={[-4, 4]}>
                <Tag color="green">Done</Tag>
              </Badge>
              {failedCount > 0 && (
                <Badge count={failedCount} overflowCount={99} color="red" offset={[-4, 4]}>
                  <Tag color="red">Failed</Tag>
                </Badge>
              )}
              <Button
                icon={<ReloadOutlined />}
                loading={scanning}
                onClick={handleRefresh}
              >
                Refresh
              </Button>
            </Space>
            )}
          />

          {/* User ID warning */}
          {!userId && (
            <Alert
              className="mb-4"
              type="warning"
              showIcon
              message="User ID not set"
              description={
                <span>
                  Please set your User ID in{' '}
                  <Link to={buildPathWithToken('/config')}>Configuration</Link>{' '}
                  to see tasks and subjects.
                </span>
              }
            />
          )}

          {/* Empty state */}
          {userId && rows.length === 0 && !scanning && (
            <Card>
              <div className="text-center py-12 text-gray-400">
                <InboxOutlined style={{ fontSize: 48 }} />
                <p className="mt-4 text-lg">No subjects found</p>
                <p className="text-sm">
                  Run a pipeline task or upload files to see subjects here.
                </p>
              </div>
            </Card>
          )}

          {/* Subject rows */}
          {rows.map((row) => {
            const isActive = row.status === 'running' || row.status === 'pending';
            const dlOutKey = `dl_out_${row.subjectId}`;
            const dlInKey = `dl_in_${row.subjectId}`;
            const steps = stepsDisplay(row);
            const logPreview = row.pipelineTask ? logPreviews[row.pipelineTask.taskId] : null;
            const durationSeconds = computeDurationSeconds(row.pipelineTask, durationNowMs);
            const startedAt = formatTaskStartedAt(row.pipelineTask);
            const durationLabel = isActive ? 'Elapsed' : 'Total runtime';

            return (
              <Card
                key={row.subjectId}
                className="mb-3"
                size="small"
                bodyStyle={{ padding: '12px 16px' }}
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  {/* Left: subject info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-semibold text-base text-gray-900">{row.subjectId}</span>
                      <Tag color={STATUS_COLOR[row.status]}>{STATUS_LABEL[row.status]}</Tag>
                      {row.pipelineTask?.currentStep && isActive && (
                        <Tag color="geekblue">{row.pipelineTask.currentStep}</Tag>
                      )}
                    </div>

                    {/* Steps completed / planned */}
                    {steps.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1">
                        {steps.map((s) => (
                          <Tag key={s} color="default" style={{ fontSize: 11 }}>{s}</Tag>
                        ))}
                      </div>
                    )}

                    {/* Message */}
                    {row.pipelineTask?.message && (
                      <div className="text-xs text-gray-500 mb-1">{row.pipelineTask.message}</div>
                    )}

                    {row.pipelineTask?.startTime && (
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 mb-1">
                        {startedAt && <span>Started: {startedAt}</span>}
                        <span>{durationLabel}: {formatDuration(durationSeconds)}</span>
                      </div>
                    )}

                    {/* Progress bar */}
                    {isActive && row.pipelineTask?.progress !== undefined && (
                      <Progress
                        percent={row.pipelineTask.progress}
                        size="small"
                        status={row.status === 'running' ? 'active' : 'normal'}
                        style={{ maxWidth: 360 }}
                      />
                    )}

                    {isActive && row.pipelineTask && (
                      <div className="mt-3 max-w-3xl">
                        <div className="flex items-center justify-between text-[11px] text-gray-500 mb-1">
                          <span>Live log tail</span>
                          {logPreview?.updatedAt && (
                            <span>Updated {new Date(logPreview.updatedAt).toLocaleTimeString()}</span>
                          )}
                        </div>
                        <pre className="bg-gray-950 text-green-200 text-[11px] leading-4 p-3 rounded overflow-auto max-h-36 whitespace-pre-wrap break-words">
                          {logPreview?.error
                            ? `Failed to load log preview: ${logPreview.error}`
                            : logPreview?.log || 'Waiting for log output...'}
                        </pre>
                      </div>
                    )}

                    {/* Output files hint */}
                    {(row.fsData?.outputFiles?.length ?? 0) > 0 && (
                      <div className="text-xs text-gray-400 mt-1">
                        Output: {row.fsData?.outputFiles?.join(', ')}
                      </div>
                    )}

                    {/* Input files hint */}
                    {(row.fsData?.inputFiles?.length ?? 0) > 0 && (
                      <div className="text-xs text-gray-400">
                        Input: {row.fsData?.inputFiles?.join(', ')}
                      </div>
                    )}
                  </div>

                  {/* Right: action buttons */}
                  <Space wrap>
                    {/* Download Output */}
                    {row.fsData?.hasOutput && row.fsData.outputDir && (
                      <Tooltip title="Download output as tar.gz">
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          loading={downloadingIds.has(dlOutKey)}
                          onClick={() => handleDownloadOutput(row)}
                        >
                          Output
                        </Button>
                      </Tooltip>
                    )}

                    {/* Download Input */}
                    {row.fsData?.hasInput && row.fsData.inputDir && (
                      <Tooltip title="Download input as tar.gz">
                        <Button
                          size="small"
                          icon={<InboxOutlined />}
                          loading={downloadingIds.has(dlInKey)}
                          onClick={() => handleDownloadInput(row)}
                        >
                          Input
                        </Button>
                      </Tooltip>
                    )}

                    {/* View Log */}
                    {(row.pipelineTask?.taskId || row.fsData?.hasOutput) && (
                      <Tooltip title="View pipeline log">
                        <Button
                          size="small"
                          icon={<FileTextOutlined />}
                          onClick={() => handleViewLog(row)}
                        >
                          Log
                        </Button>
                      </Tooltip>
                    )}

                    {/* Cancel */}
                    {isActive && row.pipelineTask && (
                      <Tooltip title="Cancel task">
                        <Button
                          size="small"
                          danger
                          icon={<StopOutlined />}
                          onClick={() => handleCancel(row)}
                        >
                          Cancel
                        </Button>
                      </Tooltip>
                    )}
                  </Space>
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </>
  );
};

export default SegmentationPage;
