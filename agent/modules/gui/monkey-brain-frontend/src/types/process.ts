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

/**
 * Conversation process tracking.
 *
 * Events are recorded by the agent backend from actual tool calls and graph
 * nodes (never written by the model). The frontend only renders them.
 */

export type ProcessStatus = 'running' | 'done' | 'warn' | 'blocked' | 'failed';

export type ProcessStage =
  | 'data'
  | 'knowledge'
  | 'constraints'
  | 'plan'
  | 'code'
  | 'run'
  | 'pipeline'
  | 'review'
  | 'repair'
  | 'result'
  | 'other';

export interface ProcessEvent {
  seq: number;
  /** Unix time in seconds. */
  time: number;
  stage: ProcessStage;
  status: ProcessStatus;
  /** Short human-readable title, e.g. "Built data profile". */
  title: string;
  /** Optional one-line subtitle, e.g. "6 files · native 0.5 mm". */
  summary?: string;
  /** Consecutive events with the same group key are collapsed ("Inspected data ×5"). */
  group?: string;
  /** Small flat key/value detail shown when the step is expanded. */
  detail?: Record<string, string>;
  /** Backend operation ID; a later event with the same ID replaces the earlier one (running -> done). */
  opId?: string;
}

export interface PlanCheckItem {
  id: string;
  verdict: 'pass' | 'warn' | 'block' | 'unverified';
  note?: string;
}

export interface PlanBasis {
  version: number;
  sealed: boolean;
  data?: { summary: string; files: string[] };
  atlas?: { name: string; space?: string; rule?: string };
  method?: { name: string; id?: string; sourceUrl?: string };
  checks?: { pass: number; warn: number; block: number; unverified?: number; items: PlanCheckItem[] };
  codePath?: string;
}

export type ProcessRunStatus = 'idle' | 'running' | 'completed' | 'failed' | 'blocked';

export interface ProcessOutput {
  path: string;
  kind: string;
}

export interface ConversationProcess {
  /** False when the server does not provide process tracking yet. */
  available: boolean;
  status: ProcessRunStatus;
  mode?: 'pipeline' | 'analysis';
  runId?: string;
  startedAt?: number;
  events: ProcessEvent[];
  plan?: PlanBasis;
  outputs: ProcessOutput[];
  /** Pass back as `after` on the next poll. */
  nextAfter: number;
  /** More events are waiting; poll again immediately. */
  hasMore?: boolean;
}
