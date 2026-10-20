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

import { AgentResponse, AgentUpdate, ConversationContext } from '../types/agent';
import { getResolvedAccessToken } from './accessToken';
import { AnalysisResultInfo, parseAnalysisResult } from '../utils/analysisResult';
import { resolveAgentBaseUrl } from '../utils/runtimePorts';
import { isUserSessionAuthError, notifyUserSessionExpired, useConfigStore } from '../stores/configStore';

export type Provider = 'platform' | 'custom';
export type AgentMode = 'pipeline' | 'analysis';
export interface PlatformModel { id: string; label: string }

type ChatRole = 'user' | 'assistant' | 'system';

interface RecentUploadInfo {
  fileName: string;
  subjectId: string;
  t1Path: string;
  inputDir: string;
  userId?: string;
  uploadedAt: string;
}

class AgentService {
  private updateCallbacks: ((update: AgentUpdate) => void)[] = [];
  private apiKey: string = '';
  private baseUrl: string = '';
  private model: string = '';
  private provider: Provider = 'platform';
  private mode: AgentMode = localStorage.getItem('agent_mode') === 'analysis' ? 'analysis' : 'pipeline';
  private conversationId: string | null = null;
  private chatHistory: Array<{role: ChatRole, content: string}> = [];
  private readonly MAX_HISTORY = 12;
  private agentBaseUrl: string = '';
  private requireExplicitUrl: boolean = false;
  private recentUpload: RecentUploadInfo | null = null;

  constructor() {
    this.apiKey = localStorage.getItem('agent_api_key') || '';
    this.baseUrl = localStorage.getItem('agent_base_url') || '';
    this.model = localStorage.getItem('agent_model') || '';
    this.provider = (localStorage.getItem('agent_provider') as Provider) || 'platform';
    try {
      this.recentUpload = JSON.parse(localStorage.getItem('agent_recent_upload') || 'null');
    } catch {
      this.recentUpload = null;
    }
    const envUrl = import.meta.env.VITE_AGENT_BACKEND_URL;
    this.requireExplicitUrl = !envUrl && ['localhost', '127.0.0.1'].includes(window.location.hostname);
  }

  setApiKey(apiKey: string): void {
    this.apiKey = apiKey;
    localStorage.setItem('agent_api_key', apiKey);
    this.notifyUpdate({
      type: 'status',
      data: { connected: this.isConfigured() },
      timestamp: new Date(),
    });
  }

  getApiKey(): string {
    return this.apiKey;
  }

  setBaseUrl(baseUrl: string): void {
    this.baseUrl = baseUrl;
    localStorage.setItem('agent_base_url', baseUrl);
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  setModel(model: string): void {
    this.model = model;
    localStorage.setItem('agent_model', model);
    this.notifyUpdate({
      type: 'status',
      data: { connected: this.isConfigured() },
      timestamp: new Date(),
    });
  }

  getModel(): string {
    return this.model;
  }

  setProvider(provider: Provider): void {
    this.provider = provider;
    localStorage.setItem('agent_provider', provider);
  }

  getProvider(): Provider {
    return this.provider;
  }

  getMode(): AgentMode { return this.mode; }

  setMode(mode: AgentMode): void {
    if (mode !== this.mode) this.clearChatHistory();
    this.mode = mode;
    localStorage.setItem('agent_mode', mode);
  }

  /** Fetch the platform's available model list (id/label only — the server never sends its API key). */
  async getModels(): Promise<{ models: PlatformModel[]; platformAvailable: boolean }> {
    const baseUrl = await resolveAgentBaseUrl();
    const accessToken = getResolvedAccessToken();
    const headers: Record<string, string> = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    const response = await fetch(`${baseUrl}/api/agent/models`, { headers });
    if (!response.ok) return { models: [], platformAvailable: false };
    return response.json();
  }

  /** Whether enough configuration is present to start chatting. */
  isConfigured(): boolean {
    if (this.provider === 'platform') return !!this.model;
    return !!this.apiKey && !!this.model;
  }

  clearChatHistory(): void {
    this.chatHistory = [];
    this.conversationId = null;
  }

  setRecentUpload(upload: Omit<RecentUploadInfo, 'uploadedAt'>): void {
    this.recentUpload = {
      ...upload,
      uploadedAt: new Date().toISOString(),
    };
    localStorage.setItem('agent_recent_upload', JSON.stringify(this.recentUpload));
  }

  private buildContext(context?: ConversationContext): ConversationContext | undefined {
    if (!context) return this.recentUpload ? { recentUpload: this.recentUpload } : undefined;
    if (!this.recentUpload) return context;
    if (this.recentUpload.userId && context.userId && this.recentUpload.userId !== context.userId) {
      return context;
    }
    return {
      ...context,
      recentUpload: {
        ...this.recentUpload,
        instruction:
          'If the user refers to the file they just uploaded, use this exact t1Path and subjectId. Do not list all subjects or rediscover the file first.',
      },
    };
  }

  private notifyUpdate(update: AgentUpdate) {
    this.updateCallbacks.forEach(callback => {
      try {
        callback(update);
      } catch (error) {
        console.error('Error in update callback:', error);
      }
    });
  }

  async sendMessage(message: string, context?: ConversationContext, onStream?: (content: string) => void): Promise<AgentResponse> {
    if (this.requireExplicitUrl) {
      console.warn('VITE_AGENT_BACKEND_URL is not set; defaulting to localhost may fail on remote servers.');
    }
    if (!this.isConfigured()) {
      throw new Error('Please configure a model first');
    }
    if (!this.agentBaseUrl) {
      this.agentBaseUrl = await resolveAgentBaseUrl();
    }

    const payload = {
      message,
      mode: this.mode,
      provider: this.provider,
      model: this.model,
      ...(this.provider === 'custom' ? { apiKey: this.apiKey, baseUrl: this.baseUrl || undefined } : {}),
      conversationId: this.conversationId,
      history: this.chatHistory,
      context: this.buildContext(context),
    };

    try {
      const accessToken = getResolvedAccessToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
      }
      const response = await fetch(`${this.agentBaseUrl}/api/agent/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let errorMessage = 'The Workflow Assistant could not process this request. Please check the model/API settings in Configuration and try again.';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.error || errorMessage;
        } catch (e) {
          // Keep the user-facing fallback above. Some reverse proxies return HTML
          // error pages here, which are not useful inside the chat UI.
        }
        if (response.status === 401 && isUserSessionAuthError(errorMessage)) {
          notifyUserSessionExpired(errorMessage);
        }
        throw new Error(errorMessage);
      }

      const refreshed = response.headers.get('X-User-Token');
      if (refreshed) {
        useConfigStore.getState().refreshUserToken(refreshed);
      }

      const data = await response.json();
      const reply = data.message || '';
      const metadata = data.metadata || {};
      const analysis = parseAnalysisResult(metadata, data.conversationId, context);
      if (analysis) metadata.analysis = analysis;
      if (Array.isArray(metadata.tools)) {
        const actions = metadata.tools
          .filter((tool: any) => tool.taskId)
          .map((tool: any, index: number) => ({
            id: `tool_action_${Date.now()}_${index}`,
            type: 'suggestion',
            label: `Check status for ${tool.taskId}`,
            data: { suggestion: `Check status for task ${tool.taskId}` },
          }));
        if (actions.length > 0) {
          metadata.actions = actions;
        }
      }

      this.conversationId = data.conversationId || this.conversationId;
      this.chatHistory.push({ role: 'user', content: message });
      this.chatHistory.push({ role: 'assistant', content: reply });

      while (this.chatHistory.length > this.MAX_HISTORY) {
        this.chatHistory.shift();
      }

      if (onStream) {
        onStream(reply);
      }

      return {
        message: reply,
        taskId: metadata.tools?.[0]?.taskId,
        metadata,
      } as AgentResponse;

    } catch (error) {
      let errorMessage = 'Failed to send message';
      if (error instanceof Error) {
        errorMessage = error.message;
      }
      throw new Error(errorMessage);
    }
  }

  async getAnalysisJobStatus(result: AnalysisResultInfo, jobId: string, cancel = false): Promise<AnalysisResultInfo> {
    if (!/^[a-f0-9]{32}$/.test(jobId) || !result.jobs?.some(job => job.id === jobId)) {
      throw new Error('Choose a job attached to this analysis.');
    }
    const { config, userToken } = useConfigStore.getState();
    const workspace = config?.workspaceDirectory && config?.userId
      ? config.workspaceDirectory.replace(/\/$/, '') + '/' + config.userId + '/output' : '';
    if (!userToken || result.userId !== config?.userId || result.workspaceDirectory !== workspace) {
      throw new Error('Verify the original analysis user and workspace in Configuration before querying a job.');
    }
    const baseUrl = await resolveAgentBaseUrl();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const access = getResolvedAccessToken(); if (access) headers.Authorization = 'Bearer ' + access;
    const response = await fetch(baseUrl + '/api/agent/analysis/job/' + (cancel ? 'cancel' : 'status'), {
      method: 'POST', headers, body: JSON.stringify({ conversationId: result.conversationId,
        runId: result.runId, jobId, context: { userId: result.userId, workspaceDirectory: workspace, userToken } }),
    });
    const body = await response.json();
    if (!response.ok) {
      const error = typeof body.detail === 'string' ? body.detail.slice(0, 1000) : 'Could not query this analysis job.';
      if (response.status === 401 && isUserSessionAuthError(error)) notifyUserSessionExpired(error);
      throw new Error(error);
    }
    const next = parseAnalysisResult(body.metadata, result.conversationId,
      { userId: result.userId, workspaceDirectory: result.workspaceDirectory });
    if (!next || next.runId !== result.runId || !next.jobs?.some(job => job.id === jobId)) {
      throw new Error('The job response does not match the original analysis.');
    }
    const refreshed = response.headers.get('X-User-Token');
    if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
    return next;
  }

  async downloadAnalysisFile(result: AnalysisResultInfo, path: string): Promise<void> {
    if (!result.files.some(file => file.path === path)) throw new Error('Choose a file attached to this analysis.');
    const { config, userToken } = useConfigStore.getState();
    const workspace = config?.workspaceDirectory && config?.userId
      ? `${config.workspaceDirectory.replace(/\/$/, '')}/${config.userId}/output` : '';
    if (!userToken || result.userId !== config?.userId || result.workspaceDirectory !== workspace) {
      throw new Error('Verify the original analysis user and workspace in Configuration before downloading.');
    }
    const baseUrl = await resolveAgentBaseUrl();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const access = getResolvedAccessToken();
    if (access) headers.Authorization = `Bearer ${access}`;
    const response = await fetch(`${baseUrl}/api/agent/analysis/artifact`, {
      method: 'POST', headers, body: JSON.stringify({ conversationId: result.conversationId,
        runId: result.runId, path, context: { userId: result.userId, workspaceDirectory: workspace, userToken } }),
    });
    if (!response.ok) {
      let error = 'Could not download this analysis file.';
      try { const body = await response.json(); if (typeof body.detail === 'string') error = body.detail; } catch { /* Use bounded fallback. */ }
      if (response.status === 401 && isUserSessionAuthError(error)) notifyUserSessionExpired(error);
      throw new Error(error);
    }
    const refreshed = response.headers.get('X-User-Token');
    if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob), anchor = document.createElement('a');
    anchor.href = url; anchor.download = path.split('/').pop() || 'analysis-output';
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  async getConversationHistory(): Promise<any[]> {
    return this.chatHistory.map((msg, index) => ({
      id: `history_${index}`,
      type: msg.role === 'user' ? 'user' : 'agent',
      content: msg.content,
      timestamp: new Date(),
    }));
  }

  subscribeToUpdates(callback: (update: AgentUpdate) => void): () => void {
    this.updateCallbacks.push(callback);

    return () => {
      const index = this.updateCallbacks.indexOf(callback);
      if (index > -1) {
        this.updateCallbacks.splice(index, 1);
      }
    };
  }

  isConnected(): boolean {
    return this.isConfigured();
  }

  reconnect(): void {
    this.notifyUpdate({
      type: 'status',
      data: { connected: this.isConnected() },
      timestamp: new Date(),
    });
  }

  disconnect(): void {
    this.apiKey = '';
    this.model = '';
    localStorage.removeItem('agent_api_key');
    localStorage.removeItem('agent_model');
    this.clearChatHistory();
    this.notifyUpdate({
      type: 'status',
      data: { connected: false },
      timestamp: new Date(),
    });
  }
}

export const agentService = new AgentService();
