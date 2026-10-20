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

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { agentService } from '../../services/agentService';

vi.mock('../../utils/runtimePorts', () => ({
  resolveAgentBaseUrl: vi.fn().mockResolvedValue('http://agent.test'),
}));

(globalThis as any).fetch = vi.fn();

describe('Agent API Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    agentService.disconnect();
    agentService.setProvider('platform');
    agentService.setMode('pipeline');
  });

  it('should configure a custom provider with both a model and API key', () => {
    const testApiKey = 'test-api-key-123';

    agentService.setProvider('custom');
    agentService.setModel('test-model');
    agentService.setApiKey(testApiKey);
    expect(agentService.getApiKey()).toBe(testApiKey);
    expect(agentService.isConnected()).toBe(true);
  });

  it('should clear the model and API key on disconnect', () => {
    agentService.setProvider('custom');
    agentService.setModel('test-model');
    agentService.setApiKey('test-key');
    expect(agentService.isConnected()).toBe(true);

    agentService.disconnect();
    expect(agentService.getApiKey()).toBe('');
    expect(agentService.getModel()).toBe('');
    expect(agentService.isConnected()).toBe(false);
  });

  it('should maintain chat history', async () => {
    agentService.setModel('test-model');

    const mockResponse = {
      ok: true,
      headers: { get: () => null },
      json: () => Promise.resolve({
        message: 'Hello, how can I help you?',
        conversationId: 'test-conv-123',
        metadata: {},
      })
    };

    ((globalThis as any).fetch as any).mockResolvedValueOnce(mockResponse);

    const response = await agentService.sendMessage('Hello');
    expect(response.message).toBe('Hello, how can I help you?');

    const history = await agentService.getConversationHistory();
    expect(history).toHaveLength(2);
    expect(history[0].content).toBe('Hello');
    expect(history[1].content).toBe('Hello, how can I help you?');
  });

  it('should handle API errors gracefully', async () => {
    agentService.setModel('test-model');

    const mockErrorResponse = {
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: () => Promise.resolve({
        detail: 'Unauthorized'
      })
    };

    ((globalThis as any).fetch as any).mockResolvedValueOnce(mockErrorResponse);

    await expect(agentService.sendMessage('Hello')).rejects.toThrow('Unauthorized');
  });

  it('should require complete configuration before sending messages', async () => {
    agentService.setProvider('custom');
    agentService.setModel('test-model');
    agentService.setApiKey('');

    await expect(agentService.sendMessage('Hello')).rejects.toThrow('Please configure a model first');
  });
  it('keeps analysis results and generated code files without persisting request credentials', async () => {
    agentService.setMode('analysis'); agentService.setModel('test-model');
    const context = { userId: 'alice', workspaceDirectory: '/workspace/alice/output', userToken: 'private-session' };
    ((globalThis as any).fetch as any).mockResolvedValueOnce({ ok: true, headers: { get: () => null }, json: async () => ({ message: 'fixture result', conversationId: 'analysis-conv', metadata: {
      mode: 'analysis', status: 'completed', run_id: 'a'.repeat(32), executions: 1,
      validation: { valid: true, independent_numeric_status: 'not_performed' },
      artifacts: [{ path: 'table.tsv', kind: 'tsv' }], generated_scripts: [{ path: 'analyze.py' }],
    } }) });
    const response = await agentService.sendMessage('fixture-only analysis', context);
    expect(response.metadata?.analysis.files.map((f: any) => f.path)).toEqual(['table.tsv', 'analyze.py']);
    expect(response.metadata?.analysis.conversationId).toBe('analysis-conv');
    expect(JSON.stringify(response.metadata?.analysis)).not.toContain('private-session');
  });
  it('rejects unattached analysis download paths before making a request', async () => {
    const result: any = { files: [{ path: 'table.tsv', kind: 'tsv' }] };
    await expect(agentService.downloadAnalysisFile(result, '../.env')).rejects.toThrow('Choose a file');
    expect((globalThis as any).fetch).not.toHaveBeenCalled();
  });

});
