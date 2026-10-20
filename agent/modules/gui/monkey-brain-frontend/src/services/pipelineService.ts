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
  PipelineRunRequest,
  PipelineRunResponse,
  PipelineStatus,
  SubjectStatus,
  WorkspaceSubject,
} from '../types/pipeline';
import { getResolvedAccessToken } from './accessToken';
import { resolvePipelineBaseUrl, resolveAgentBaseUrl } from '../utils/runtimePorts';
import {
  isUserSessionAuthError,
  isUserTokenExpired,
  notifyUserSessionExpired,
  useConfigStore,
} from '../stores/configStore';

class PipelineService {
  private getAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = getResolvedAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    const userToken = useConfigStore.getState().userToken;
    if (userToken) {
      headers['X-User-Token'] = userToken;
    }
    return headers;
  }

  /** Extracts a clean error message from a failed response, whether the body is JSON ({error}) or plain text. */
  private async parseErrorMessage(response: Response, fallback: string): Promise<string> {
    const text = await response.text();
    let messageText = text || fallback;
    try {
      const data = JSON.parse(text);
      messageText = data.error || data.detail || text || fallback;
    } catch {
      messageText = text || fallback;
    }
    if (response.status === 401 && isUserSessionAuthError(messageText)) {
      notifyUserSessionExpired(messageText);
    }
    return messageText;
  }

  private async handleOptionalUnauthorized(response: Response): Promise<boolean> {
    if (response.status !== 401) return false;
    const messageText = await this.parseErrorMessage(response, 'Please verify your User ID first on the Configuration page');
    if (isUserSessionAuthError(messageText)) return true;
    return false;
  }

  private applyRefreshedUserToken(response: Response): void {
    const refreshed = response.headers.get('X-User-Token');
    if (refreshed) {
      useConfigStore.getState().refreshUserToken(refreshed);
    }
  }

  private formatUploadError(status: number, body: string): string {
    if (status === 413) {
      return 'Upload failed: file is larger than the web server upload limit. Ask the server admin to increase nginx client_max_body_size for this site.';
    }
    const compact = body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    return compact
      ? `Upload failed. ${compact}`
      : 'Upload failed. Please check your Workspace Directory, file size, and backend connection, then try again.';
  }

  private buildDownloadUrl(baseUrl: string, path: string, params: URLSearchParams): string {
    const url = new URL(path, baseUrl);
    params.forEach((value, key) => url.searchParams.set(key, value));
    const token = getResolvedAccessToken();
    if (token) url.searchParams.set('token', token);
    const userToken = useConfigStore.getState().userToken;
    if (userToken) url.searchParams.set('userToken', userToken);
    return url.toString();
  }

  private triggerBrowserDownload(url: string): void {
    const a = document.createElement('a');
    a.href = url;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  private async refreshUserSession(userId: string, workspaceDirectory: string): Promise<void> {
    const baseUrl = await resolvePipelineBaseUrl();
    const params = new URLSearchParams({ userId, workspaceDirectory });
    const response = await fetch(`${baseUrl}/api/users/session/refresh?${params}`, {
      headers: this.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not refresh your User ID verification. Please enter your password again on the Configuration page.'));
    }
    this.applyRefreshedUserToken(response);
  }

  private checkUserTokenExpiry(): void {
    const { userToken } = useConfigStore.getState();
    if (userToken && isUserTokenExpired(userToken)) {
      notifyUserSessionExpired();
      throw new Error('Your User ID verification has expired. Please enter your password again on the Configuration page.');
    }
  }

  async runPipeline(payload: PipelineRunRequest): Promise<PipelineRunResponse> {
    const baseUrl = await resolvePipelineBaseUrl();
    const response = await fetch(`${baseUrl}/api/pipeline/run`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not submit the task. Please check Configuration and try again.'));
    }

    this.applyRefreshedUserToken(response);
    return response.json();
  }

  async getStatus(taskId: string): Promise<PipelineStatus> {
    const baseUrl = await resolvePipelineBaseUrl();
    const response = await fetch(`${baseUrl}/api/pipeline/${taskId}/status`, {
      method: 'GET',
      headers: this.getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not load task status. Please refresh the page and try again.'));
    }

    this.applyRefreshedUserToken(response);
    return response.json();
  }

  async cancelTask(taskId: string, source: 'pipeline' | 'agent' = 'pipeline'): Promise<void> {
    const baseUrl = source === 'agent'
      ? await resolveAgentBaseUrl()
      : await resolvePipelineBaseUrl();
    const cancelPath = source === 'agent'
      ? `/api/agent/tasks/${encodeURIComponent(taskId)}/cancel`
      : `/api/pipeline/${encodeURIComponent(taskId)}/cancel`;
    const response = await fetch(`${baseUrl}${cancelPath}`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not cancel this task. Please refresh the task status and try again.'));
    }
    this.applyRefreshedUserToken(response);
  }

  async checkSubjectStatus(userId: string, subjectId: string, workspaceDirectory: string, steps?: string[]): Promise<SubjectStatus> {
    const baseUrl = await resolvePipelineBaseUrl();
    const params = new URLSearchParams({ userId, subjectId, workspaceDirectory });
    if (steps?.length) params.set('steps', steps.join(','));
    const response = await fetch(`${baseUrl}/api/subject/status?${params}`, {
      headers: this.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not check existing results for this subject. Please check Configuration and try again.'));
    }
    this.applyRefreshedUserToken(response);
    return response.json();
  }

  async cleanSubject(userId: string, subjectId: string, workspaceDirectory: string, steps: string[]): Promise<void> {
    const baseUrl = await resolvePipelineBaseUrl();
    const response = await fetch(`${baseUrl}/api/subject/clean`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ userId, subjectId, workspaceDirectory, steps }),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not prepare this subject for rerun. Please check whether it is still running.'));
    }
    this.applyRefreshedUserToken(response);
  }

  async getServerTasks(userId: string, workspaceDirectory?: string): Promise<PipelineStatus[]> {
    const baseUrl = await resolvePipelineBaseUrl();
    const params = new URLSearchParams({ userId });
    if (workspaceDirectory) params.set('workspaceDirectory', workspaceDirectory);
    const response = await fetch(`${baseUrl}/api/pipeline/tasks?${params}`, {
      headers: this.getAuthHeaders(),
    });
    if (!response.ok) {
      await this.handleOptionalUnauthorized(response);
      return [];
    }
    this.applyRefreshedUserToken(response);
    const data = await response.json();
    return (data.tasks || []) as PipelineStatus[];
  }

  async getTaskLog(taskId: string, source: 'pipeline' | 'agent' = 'pipeline'): Promise<{ log: string; size?: number }> {
    const baseUrl = source === 'agent'
      ? await resolveAgentBaseUrl()
      : await resolvePipelineBaseUrl();
    const logPath = source === 'agent'
      ? `/api/agent/tasks/${encodeURIComponent(taskId)}/log`
      : `/api/pipeline/${encodeURIComponent(taskId)}/log`;
    const response = await fetch(`${baseUrl}${logPath}`, {
      headers: this.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not load the task log. Please refresh the task status and try again.'));
    }
    this.applyRefreshedUserToken(response);
    return response.json();
  }

  async getSubjectLog(
    userId: string,
    subjectId: string,
    workspaceDirectory: string,
  ): Promise<{ log: string; size?: number; logPath?: string }> {
    const baseUrl = await resolvePipelineBaseUrl();
    const params = new URLSearchParams({ userId, subjectId, workspaceDirectory });
    const response = await fetch(`${baseUrl}/api/subject/log?${params}`, {
      headers: this.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not load the subject log. Please check that the subject belongs to the current User ID.'));
    }
    this.applyRefreshedUserToken(response);
    return response.json();
  }

  uploadFile(
    file: File,
    userId: string,
    subjectId: string,
    workspaceDirectory: string,
    onProgress: (percent: number) => void,
  ): Promise<{ savedPath: string; inputDir: string; subjectId: string | null; fileName: string }> {
    return resolvePipelineBaseUrl().then((baseUrl) => {
      return new Promise((resolve, reject) => {
        const params = new URLSearchParams({ userId, subjectId, filename: file.name, workspaceDirectory });
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${baseUrl}/api/files/upload?${params}`);
        const token = this.getAuthHeaders().Authorization;
        if (token) xhr.setRequestHeader('Authorization', token);
        const userToken = useConfigStore.getState().userToken;
        if (userToken) xhr.setRequestHeader('X-User-Token', userToken);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const refreshed = xhr.getResponseHeader('X-User-Token');
            if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
            try { resolve(JSON.parse(xhr.responseText)); }
            catch { reject(new Error('Invalid response from upload')); }
          } else {
            if (xhr.status === 401 && isUserSessionAuthError(xhr.responseText || '')) {
              notifyUserSessionExpired(xhr.responseText || undefined);
            }
            reject(new Error(this.formatUploadError(xhr.status, xhr.responseText || '')));
          }
        };
        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.send(file);
      });
    });
  }

  async getWorkspaceSubjects(userId: string, workspaceDirectory: string): Promise<WorkspaceSubject[]> {
    const baseUrl = await resolvePipelineBaseUrl();
    const params = new URLSearchParams({ userId, workspaceDirectory });
    const response = await fetch(`${baseUrl}/api/workspace/subjects?${params}`, {
      headers: this.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not scan this workspace. Please check Configuration and use the default Workspace Directory if unsure.'));
    }
    this.applyRefreshedUserToken(response);
    const data = await response.json();
    return data.subjects as WorkspaceSubject[];
  }

  async downloadDir(dirPath: string, name: string): Promise<void> {
    this.checkUserTokenExpiry();
    const { config } = useConfigStore.getState();
    if (config?.userId && config.workspaceDirectory) {
      await this.refreshUserSession(config.userId, config.workspaceDirectory);
    }
    const baseUrl = await resolvePipelineBaseUrl();
    if (!config?.userId || !config.workspaceDirectory) {
      throw new Error('Please verify your User ID in Configuration before downloading server files.');
    }
    const params = new URLSearchParams({
      path: dirPath,
      name,
      userId: config.userId,
      workspaceDirectory: config.workspaceDirectory,
    });
    this.triggerBrowserDownload(this.buildDownloadUrl(baseUrl, '/api/files/download-dir', params));
  }

  async downloadSubject(userId: string, subjectId: string, workspaceDirectory: string): Promise<void> {
    this.checkUserTokenExpiry();
    await this.refreshUserSession(userId, workspaceDirectory);
    const baseUrl = await resolvePipelineBaseUrl();
    const params = new URLSearchParams({ userId, subjectId, workspaceDirectory });
    this.triggerBrowserDownload(this.buildDownloadUrl(baseUrl, '/api/subject/download', params));
  }
  /** Fetch agent-submitted pipeline tasks (running/pending) from the FastAPI agent backend. */
  async getAgentTasks(userId?: string, workspaceDirectory?: string): Promise<any[]> {
    try {
      const baseUrl = await resolveAgentBaseUrl();
      const headers = this.getAuthHeaders();
      delete headers['Content-Type'];
      const params = new URLSearchParams();
      if (userId) params.set('userId', userId);
      if (workspaceDirectory) params.set('workspaceDirectory', workspaceDirectory);
      const query = params.toString() ? `?${params}` : '';
      const response = await fetch(`${baseUrl}/api/agent/tasks${query}`, { headers });
      if (!response.ok) {
        await this.handleOptionalUnauthorized(response);
        return [];
      }
      this.applyRefreshedUserToken(response);
      const data = await response.json();
      return (data.tasks || []) as any[];
    } catch {
      return [];
    }
  }

  /** List official sample subjects bundled with PrimateX, for users without their own data. */
  async listSamples(): Promise<Array<{ sampleId: string; t1Path: string }>> {
    const baseUrl = await resolvePipelineBaseUrl();
    const headers = this.getAuthHeaders();
    delete headers['Content-Type'];
    const response = await fetch(`${baseUrl}/api/samples/list`, { headers });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not load sample data. Please check that the backend is running.'));
    }
    const data = await response.json();
    return (data.samples || []) as Array<{ sampleId: string; t1Path: string }>;
  }

  /** Copy a sample subject's T1 image into workspace/<userId>/input/<subjectId>/T1/. */
  async copySample(
    userId: string,
    subjectId: string,
    sampleId: string,
    workspaceDirectory: string,
  ): Promise<{ savedPath: string; inputDir: string }> {
    const baseUrl = await resolvePipelineBaseUrl();
    const response = await fetch(`${baseUrl}/api/samples/copy`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ userId, subjectId, sampleId, workspaceDirectory }),
    });
    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response, 'Could not copy the sample data into your workspace. Please check Configuration and try again.'));
    }
    this.applyRefreshedUserToken(response);
    return response.json();
  }
}

export const pipelineService = new PipelineService();
