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

import { AgentResponse, AgentUpdate, ConversationContext, MessageMetadata } from '../types/agent';
import { getResolvedAccessToken } from './accessToken';
import { AnalysisResultInfo, parseAnalysisResult } from '../utils/analysisResult';
import { resolveAgentBaseUrl } from '../utils/runtimePorts';
import { ConversationProcess } from '../types/process';
import { parseConversationProcess } from '../utils/processEvents';
import { isUserSessionAuthError, notifyUserSessionExpired, useConfigStore } from '../stores/configStore';

export type Provider = 'platform' | 'custom';
/** 'auto' lets the backend route each request to preprocessing or analysis. */
export type AgentMode = 'auto' | 'pipeline' | 'analysis';
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

/**
 * Fields from a chat response that are kept on the agent message: suggested
 * actions, the analysis result and which agent the backend routed to.
 * Returns undefined when there is nothing to keep.
 */
export function messageMetadataFrom(metadata: Record<string, any> | undefined): MessageMetadata | undefined {
  if (!metadata) return undefined;
  const routeValue = metadata.route ?? metadata.mode;
  const route = routeValue === 'pipeline' || routeValue === 'analysis' ? routeValue : undefined;
  const routeReason = typeof metadata.routeReason === 'string' ? metadata.routeReason.slice(0, 300) : undefined;
  if (!metadata.actions && !metadata.analysis && !route) return undefined;
  return { actions: metadata.actions || [], analysis: metadata.analysis, route, routeReason };
}

class AgentService {
  private updateCallbacks: ((update: AgentUpdate) => void)[] = [];
  private apiKey: string = '';
  private baseUrl: string = '';
  private model: string = '';
  private provider: Provider = 'platform';
  private mode: AgentMode = 'auto';
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

  /**
   * Force a specific agent (tests and controlled experiments). The GUI uses
   * 'auto'; switching between explicit modes starts a new backend context.
   */
  setMode(mode: AgentMode): void {
    if (mode !== this.mode && mode !== 'auto' && this.mode !== 'auto') this.clearChatHistory();
    this.mode = mode;
  }

  /** Current backend conversation ID, or null before the first message. */
  getConversationId(): string | null { return this.conversationId; }

  /** Restore an actual backend ID and message context when opening saved history. */
  restoreConversation(conversationId: string | null, messages: Array<{ type: string; content: string }> = []): void {
    if (conversationId !== null && !/^[a-zA-Z0-9_-]{1,256}$/.test(conversationId)) {
      throw new Error('Invalid saved backend conversation ID');
    }
    this.conversationId = conversationId;
    this.chatHistory = messages
      .filter((message) => message.type === 'user' || message.type === 'agent')
      .map((message) => ({ role: message.type === 'user' ? 'user' as const : 'assistant' as const, content: message.content }))
      .slice(-this.MAX_HISTORY);
  }

  /**
   * Create the conversation ID on the client before the first request so the
   * process panel can poll for events while that request is still running.
   */
  ensureConversationId(): string {
    if (!this.conversationId) {
      const bytes = new Uint8Array(16);
      if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
        crypto.getRandomValues(bytes);
      } else {
        for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
      }
      this.conversationId = 'conv_' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    }
    return this.conversationId;
  }

  /**
   * Fetch recorded process events for a conversation from
   * GET /api/agent/analysis/{conversationId}/events (data profile, checks,
   * sealed plan, tool calls, executions). Returns { available: false } when
   * the server or the active knowledge profile does not record events, so
   * callers can fall back to request-level status.
   */
  async getConversationProcess(conversationId: string, after = 0): Promise<ConversationProcess> {
    const unavailable: ConversationProcess = { available: false, status: 'idle', events: [], outputs: [], nextAfter: after };
    const { config, userToken } = useConfigStore.getState();
    if (!conversationId || !config?.userId || !config.workspaceDirectory || !userToken) return unavailable;
    const workspace = config.workspaceDirectory.replace(/\/$/, '') + '/' + config.userId + '/output';
    if (!this.agentBaseUrl) this.agentBaseUrl = await resolveAgentBaseUrl();
    const headers: Record<string, string> = { 'X-User-Token': userToken };
    const access = getResolvedAccessToken(); if (access) headers.Authorization = 'Bearer ' + access;
    const params = new URLSearchParams({ userId: config.userId, workspaceDirectory: workspace, after: String(after) });
    const response = await fetch(
      this.agentBaseUrl + '/api/agent/analysis/' + encodeURIComponent(conversationId) + '/events?' + params,
      { headers },
    );
    if (response.status === 404 || response.status === 405) return unavailable;
    let body: any = {};
    try { body = await response.json(); } catch { body = {}; }
    if (!response.ok) {
      const error = typeof body.detail === 'string' ? body.detail.slice(0, 500) : 'Could not load the run progress.';
      if (response.status === 401 && isUserSessionAuthError(error)) notifyUserSessionExpired(error);
      throw new Error(error);
    }
    const refreshed = response.headers.get('X-User-Token');
    if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
    return parseConversationProcess(body);
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
      conversationId: this.ensureConversationId(),
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
