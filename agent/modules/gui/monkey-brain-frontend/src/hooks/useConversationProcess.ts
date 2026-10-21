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

import { useEffect, useState } from 'react';
import { agentService } from '../services/agentService';
import { ConversationProcess } from '../types/process';

const POLL_MS = 2000;
const RETRY_MS = 5000;

function merge(previous: ConversationProcess, next: ConversationProcess): ConversationProcess {
  const seen = new Set(previous.events.map((event) => event.seq));
  const events = [...previous.events, ...next.events.filter((event) => !seen.has(event.seq))]
    .sort((a, b) => a.seq - b.seq);
  return {
    ...previous,
    ...next,
    events,
    plan: next.plan ?? previous.plan,
    outputs: next.outputs.length ? next.outputs : previous.outputs,
    startedAt: next.startedAt ?? previous.startedAt,
  };
}

/**
 * Poll recorded process events for a conversation. Polls every 2 s while a
 * request is in flight (`active`) or the server reports the run as running,
 * then performs one final fetch and stops.
 */
export function useConversationProcess(conversationId: string | null, active: boolean) {
  const [process, setProcess] = useState<ConversationProcess | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setProcess(null);
    setError('');
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return undefined;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let after = 0;
    let accumulated: ConversationProcess | null = null;

    const tick = async () => {
      try {
        const next = await agentService.getConversationProcess(conversationId, after);
        if (stopped) return;
        if (!next.available) {
          setProcess(next);
          return;
        }
        accumulated = accumulated ? merge(accumulated, next) : next;
        after = next.nextAfter;
        setProcess(accumulated);
        setError('');
        if (next.hasMore) timer = setTimeout(tick, 0);
        else if (active || next.status === 'running') timer = setTimeout(tick, POLL_MS);
      } catch (err) {
        if (stopped) return;
        setError(err instanceof Error ? err.message : 'Could not load the run progress.');
        if (active) timer = setTimeout(tick, RETRY_MS);
      }
    };

    void tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [conversationId, active]);

  return { process, error };
}
