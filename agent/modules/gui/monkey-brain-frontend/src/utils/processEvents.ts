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

import {
  ConversationProcess,
  PlanBasis,
  PlanCheckItem,
  ProcessEvent,
  ProcessRunStatus,
  ProcessStage,
  ProcessStatus,
} from '../types/process';

const STAGES: ProcessStage[] = ['data', 'knowledge', 'constraints', 'plan', 'code', 'run', 'pipeline', 'review', 'repair', 'result', 'other'];
const STATUSES: ProcessStatus[] = ['running', 'done', 'warn', 'blocked', 'failed'];

const text = (value: unknown, max: number): string | undefined =>
  typeof value === 'string' && value.trim() ? value.trim().slice(0, max) : undefined;

const count = (value: unknown): number =>
  Number.isInteger(value) && (value as number) >= 0 && (value as number) < 1_000_000 ? (value as number) : 0;

/** Relative output path without traversal, hidden segments or drive letters. */
const safePath = (value: unknown): value is string =>
  typeof value === 'string' && value.length > 0 && value.length <= 1024 && !/[\\:\x00\r\n]/.test(value)
  && value.split('/').every((part) => part.length > 0 && !part.startsWith('.'));

const safeUrl = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : undefined;
  } catch {
    return undefined;
  }
};

const NAVIGATION_TOOLS = new Set(['ls', 'glob', 'grep', 'read_file', 'list_roots', 'list_data', 'read_data', 'discover_subjects']);
const KNOWLEDGE_TOOLS = new Set([
  'search_evidence', 'read_evidence', 'search_analysis_methods', 'read_analysis_method',
  'search_knowledge', 'read_knowledge', 'search_method_knowledge', 'search_software_graph',
  'read_software_graph', 'search_research_knowledge', 'read_research_knowledge',
]);
/** Detail keys worth showing; nested objects (failures, sources) are summarised elsewhere. */
const DETAIL_KEYS = ['tool', 'path', 'method_id', 'task_category', 'version', 'duration_seconds', 'reason', 'exit_code', 'constraints_sha256', 'profile_sha256'];

const toSeconds = (value: unknown): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const ms = Date.parse(value);
    return Number.isFinite(ms) ? ms / 1000 : 0;
  }
  return 0;
};

/**
 * One event from GET /api/agent/analysis/{conversationId}/events
 * (backend/analysis_events.py). Events are recorded from tool calls and
 * graph nodes; the model does not write them.
 */
function parseEvent(raw: any): ProcessEvent | undefined {
  const title = text(raw?.title, 120);
  if (!title || !Number.isInteger(raw?.seq)) return undefined;
  const source = raw.detail && typeof raw.detail === 'object' && !Array.isArray(raw.detail) ? raw.detail : {};
  const detail: Record<string, string> = {};
  for (const key of DETAIL_KEYS) {
    const value = source[key];
    if (['string', 'number', 'boolean'].includes(typeof value)) detail[key] = String(value).slice(0, 300);
  }
  const tool = typeof source.tool === 'string' ? source.tool : '';
  const blockedIds = (Array.isArray(source.failures) ? source.failures : Array.isArray(source.blocked_constraints) ? source.blocked_constraints : [])
    .map((item: any) => (typeof item?.constraint_id === 'string' ? item.constraint_id : ''))
    .filter(Boolean)
    .slice(0, 6);
  if (blockedIds.length) detail.blocked = blockedIds.join(', ');
  const nextSteps = Array.isArray(source.next_steps) ? source.next_steps.filter((x: unknown) => typeof x === 'string').slice(0, 5) : [];
  if (nextSteps.length) detail['next steps'] = nextSteps.join(' / ').slice(0, 300);
  const summary = text(source.reason, 200)
    ?? (blockedIds.length ? `Blocked: ${blockedIds.join(', ')}` : undefined)
    ?? text(raw.summary, 200);
  return {
    seq: raw.seq,
    time: toSeconds(raw.time),
    stage: STAGES.includes(raw.stage) ? raw.stage : 'other',
    status: STATUSES.includes(raw.status) ? raw.status : 'done',
    title,
    summary,
    group: NAVIGATION_TOOLS.has(tool) ? 'navigation' : KNOWLEDGE_TOOLS.has(tool) ? 'knowledge' : text(raw.group, 80),
    detail: Object.keys(detail).length ? detail : undefined,
    opId: text(source.operation_id, 64),
  };
}

/** Map the backend's committed-plan summary to the panel's basis card. */
function parsePlan(raw: any): PlanBasis | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const files: string[] = (Array.isArray(raw.data?.files) ? raw.data.files : [])
    .filter((f: unknown) => typeof f === 'string').slice(0, 64).map((f: string) => f.slice(0, 300));
  const subjects: string[] = (Array.isArray(raw.data?.subjects) ? raw.data.subjects : [])
    .filter((f: unknown) => typeof f === 'string').slice(0, 64);
  const items: PlanCheckItem[] = [];
  for (const item of Array.isArray(raw.must_disclose) ? raw.must_disclose.slice(0, 32) : []) {
    const id = text(item?.constraint_id ?? item?.condition_id, 80);
    if (id) items.push({ id, verdict: item?.verification === 'unverified' || item?.status === 'unverified' ? 'unverified' : 'warn', note: text(item?.statement ?? item?.tool_observed?.reason, 200) });
  }
  const atlasName = text(raw.atlas?.name, 120);
  const methodName = text(raw.method?.name, 160) ?? text(raw.method?.method_id, 160);
  const sourceUrl = Array.isArray(raw.method?.sources) ? safeUrl(raw.method.sources[0]?.url) : undefined;
  const codePath = typeof raw.code_path === 'string' ? raw.code_path.replace(/^\/work\//, '') : undefined;
  const dataSummary = [
    subjects.length ? `${subjects.length} subject${subjects.length > 1 ? 's' : ''}` : '',
    files.length ? `${files.length} file${files.length > 1 ? 's' : ''}` : '',
  ].filter(Boolean).join(' · ');
  return {
    version: count(raw.version),
    sealed: true,
    data: dataSummary ? { summary: subjects.length ? `${subjects.slice(0, 3).join(', ')} · ${dataSummary}` : dataSummary, files } : undefined,
    atlas: atlasName
      ? { name: [atlasName, text(raw.atlas.version, 40)].filter(Boolean).join(' '), space: text(raw.atlas.space, 80), rule: text(raw.atlas.hemisphere_rule, 160) }
      : undefined,
    method: methodName ? { name: methodName, id: text(raw.method?.method_id, 120), sourceUrl } : undefined,
    checks: raw.constraints
      ? { pass: count(raw.constraints.pass), warn: count(raw.constraints.warn), block: count(raw.constraints.block), unverified: count(raw.constraints.unverified), items }
      : undefined,
    codePath: safePath(codePath) ? codePath : undefined,
  };
}

const VIEW_STATUS: Record<string, ProcessRunStatus> = {
  running: 'running', pending: 'idle', done: 'completed', completed: 'completed',
  failed: 'failed', blocked: 'blocked', warn: 'completed',
};

/** Validate the response of GET /api/agent/analysis/{conversationId}/events. */
export function parseConversationProcess(raw: any): ConversationProcess {
  const events: ProcessEvent[] = [];
  for (const item of Array.isArray(raw?.events) ? raw.events.slice(0, 500) : []) {
    const event = parseEvent(item);
    if (event) events.push(event);
  }
  const lastSeq = events.length ? events[events.length - 1].seq : 0;
  const enabled = raw?.enabled === true;
  return {
    available: enabled,
    status: VIEW_STATUS[raw?.status] ?? 'idle',
    runId: text(raw?.run_id, 64),
    startedAt: events.length ? events[0].time || undefined : undefined,
    events,
    plan: parsePlan(raw?.plan),
    outputs: [],
    nextAfter: Number.isInteger(raw?.last_seq) ? raw.last_seq : lastSeq,
    hasMore: raw?.has_more === true,
  };
}

export interface CollapsedStep {
  key: string;
  event: ProcessEvent;
  repeat: number;
}

/** Merge consecutive finished events that share a group key. */
export function collapseEvents(events: ProcessEvent[]): CollapsedStep[] {
  const steps: CollapsedStep[] = [];
  const byOp = new Map<string, number>();
  for (const event of events) {
    // A finished event replaces its own "running" event in place.
    if (event.opId && byOp.has(event.opId)) {
      const index = byOp.get(event.opId)!;
      steps[index] = { ...steps[index], event: { ...event, time: steps[index].event.time } };
      const previous = steps[index - 1];
      const current = steps[index];
      if (index === steps.length - 1 && previous && current.event.group
          && previous.event.group === current.event.group
          && previous.event.status === 'done' && current.event.status === 'done') {
        previous.repeat += current.repeat;
        previous.event = { ...current.event, title: previous.event.title, time: previous.event.time };
        steps.pop();
        byOp.set(event.opId, index - 1);
      }
      continue;
    }
    const last = steps[steps.length - 1];
    if (last && event.group && last.event.group === event.group
        && last.event.status === 'done' && event.status === 'done') {
      last.repeat += 1;
      last.event = { ...event, title: last.event.title, time: event.time };
      continue;
    }
    steps.push({ key: `${event.seq}`, event, repeat: 1 });
    if (event.opId) byOp.set(event.opId, steps.length - 1);
  }
  return steps;
}

/** "0:42" relative to the run start, or a clock time when no start is known. */
export function formatStepTime(time: number, startedAt?: number): string {
  if (!time) return '';
  if (startedAt && time >= startedAt) {
    const seconds = Math.round(time - startedAt);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  }
  return new Date(time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
