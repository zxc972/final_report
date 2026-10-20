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

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { resolvePipelineBaseUrl } from '../utils/runtimePorts';
import { getResolvedAccessToken } from '../services/accessToken';

export interface ProcessingOptions {
  enablePreprocessing: boolean;
  qualityLevel: 'fast' | 'standard' | 'high';
  threads: number;
}

export interface SegmentationConfig {
  userId: string;
  workspaceDirectory: string;
  modelDir: string;
  maxConcurrentTasks: number;
  processingOptions: ProcessingOptions;
  description?: string;
  lastUpdated?: Date;
}

interface ConfigState {
  config: SegmentationConfig | null;
  isLoading: boolean;
  error: string | null;
  // The server's default workspace path, fetched independently of whether the
  // user already has one configured — used as a placeholder hint in the UI.
  defaultWorkspace: string | null;
  // Signed session token proving the password for `verifiedUserId` was checked.
  // Sent as the X-User-Token header on requests that touch that user's workspace.
  userToken: string | null;
  verifiedUserId: string | null;
  verifiedWorkspaceDirectory: string | null;

  // Actions
  updateConfig: (newConfig: Partial<SegmentationConfig>) => Promise<void>;
  saveConfig: () => Promise<void>;
  loadConfig: () => Promise<void>;
  resetConfig: () => void;
  clearUserSession: () => void;
  refreshUserToken: (token: string) => void;
  setError: (error: string | null) => void;
  notifyAgentOfConfigUpdate: () => void;
  /** Returns whether a userId has already been claimed (password-protected). */
  checkUserIdExists: (userId: string, workspaceDirectory: string) => Promise<boolean>;
  /** Claims (first use) or verifies (later use) a userId/password pair. Throws on wrong password. */
  verifyUserId: (userId: string, password: string, workspaceDirectory: string) => Promise<{ claimed: boolean }>;
  /** Changes the password for an already-verified userId. Invalidates all previously issued tokens. */
  changePassword: (userId: string, currentPassword: string, newPassword: string, workspaceDirectory: string) => Promise<void>;
}

const defaultConfig: SegmentationConfig = {
  userId: '',
  workspaceDirectory: '',
  modelDir: '',
  maxConcurrentTasks: 12,
  processingOptions: {
    enablePreprocessing: true,
    qualityLevel: 'standard',
    threads: 2,
  },
};

function normalizeThreads(value: unknown): number {
  const threads = Number(value);
  return Number.isInteger(threads) && threads >= 1 && threads <= 4 ? threads : 2;
}

export function getUserTokenExpiry(userToken: string | null): number | null {
  if (!userToken) return null;
  const [payloadB64] = userToken.split('.');
  if (!payloadB64) return null;
  try {
    const padded = payloadB64.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (payloadB64.length % 4)) % 4);
    const payload = atob(padded);
    const idx = payload.lastIndexOf(':');
    if (idx === -1) return null;
    const expiresAt = Number(payload.slice(idx + 1));
    return Number.isFinite(expiresAt) ? expiresAt : null;
  } catch {
    return null;
  }
}

export function isUserTokenExpired(userToken: string | null): boolean {
  const expiresAt = getUserTokenExpiry(userToken);
  return !expiresAt || expiresAt <= Math.floor(Date.now() / 1000);
}

export function normalizeWorkspaceDirectory(workspaceDirectory: string | null | undefined): string {
  return (workspaceDirectory || '').replace(/\/+$/, '');
}

export const USER_SESSION_EXPIRED_EVENT = 'primx:user-session-expired';

export function isUserSessionAuthError(message: string): boolean {
  return /verify your User ID|User ID verification|Configuration page/i.test(message);
}

export function notifyUserSessionExpired(message?: string): void {
  const { clearUserSession } = useConfigStore.getState();
  clearUserSession();
  window.dispatchEvent(new CustomEvent(USER_SESSION_EXPIRED_EVENT, {
    detail: {
      message: message || 'Your User ID verification has expired. Please enter your password again on the Configuration page.',
    },
  }));
}

export const useConfigStore = create<ConfigState>()(
  persist(
    (set, get) => ({
      config: null,
      isLoading: false,
      error: null,
      defaultWorkspace: null,
      userToken: null,
      verifiedUserId: null,
      verifiedWorkspaceDirectory: null,

      updateConfig: async (newConfig: Partial<SegmentationConfig>) => {
        set({ isLoading: true, error: null });
        
        try {
          const currentConfig = get().config || defaultConfig;
          const updatedConfig: SegmentationConfig = {
            ...currentConfig,
            ...newConfig,
            processingOptions: {
              ...currentConfig.processingOptions,
              ...newConfig.processingOptions,
            },
            lastUpdated: new Date(),
          };

          set({ config: updatedConfig });
          
          // Notify agent of config update
          get().notifyAgentOfConfigUpdate();
          
        } catch (error: any) {
          set({ error: error.message });
          throw error;
        } finally {
          set({ isLoading: false });
        }
      },

      saveConfig: async () => {
        const { config } = get();
        if (!config) return;

        set({ isLoading: true, error: null });
        
        try {
          // In a real app, this would save to a backend API
          // For now, we just simulate the API call
          await new Promise(resolve => setTimeout(resolve, 500));
          
          console.log('Configuration saved:', config);
          
        } catch (error: any) {
          set({ error: error.message });
          throw error;
        } finally {
          set({ isLoading: false });
        }
      },

      loadConfig: async () => {
        set({ isLoading: true, error: null });

        try {
          const { config } = get();
          const current: SegmentationConfig = config
            ? {
                ...config,
                processingOptions: {
                  ...defaultConfig.processingOptions,
                  ...config.processingOptions,
                  threads: normalizeThreads(config.processingOptions?.threads),
                },
              }
            : defaultConfig;
          set({ config: current });

          try {
            const baseUrl = await resolvePipelineBaseUrl();
            const token = getResolvedAccessToken();
            const headers: Record<string, string> = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const res = await fetch(`${baseUrl}/api/config`, { headers });
            if (res.ok) {
              const data = await res.json();
              if (data.defaultWorkspace) {
                // Always expose the server default as a placeholder hint, even if
                // the user already has their own workspaceDirectory configured.
                set({ defaultWorkspace: data.defaultWorkspace });
                if (!current.workspaceDirectory) {
                  set({ config: { ...current, workspaceDirectory: data.defaultWorkspace } });
                }
              }
            } else {
              console.warn(`[config] /api/config returned ${res.status}`);
            }
          } catch (err) {
            console.warn('[config] Failed to fetch default workspace from backend:', err);
          }

          if (!get().config) {
            set({ config: defaultConfig });
          }

          const latest = get();
          if (
            latest.userToken &&
            latest.verifiedUserId &&
            !latest.verifiedWorkspaceDirectory &&
            latest.config?.workspaceDirectory
          ) {
            set({ verifiedWorkspaceDirectory: latest.config.workspaceDirectory });
          }
        } catch (error: any) {
          set({ error: error.message });
          throw error;
        } finally {
          set({ isLoading: false });
        }
      },

      resetConfig: () => {
        set({ 
          config: defaultConfig,
          userToken: null,
          verifiedUserId: null,
          verifiedWorkspaceDirectory: null,
          error: null 
        });
      },

      clearUserSession: () => {
        set({
          userToken: null,
          verifiedUserId: null,
          verifiedWorkspaceDirectory: null,
        });
      },

      refreshUserToken: (token: string) => {
        if (!token) return;
        set({ userToken: token });
      },

      setError: (error: string | null) => {
        set({ error });
      },

      notifyAgentOfConfigUpdate: () => {
        const { config } = get();
        if (!config) return;

        // Create a notification for the agent about config update
        const effectiveWorkspace = config.workspaceDirectory && config.userId
          ? `${config.workspaceDirectory.replace(/\/$/, '')}/${config.userId}/output`
          : config.workspaceDirectory;
        const configSummary = {
          workspaceDirectory: effectiveWorkspace,
          modelDir: config.modelDir,
          maxConcurrentTasks: config.maxConcurrentTasks,
          threads: config.processingOptions.threads,
        };

        // In a real implementation, this would notify the agent service
        console.log('Config updated, notifying agent:', configSummary);
        
        // You could dispatch a custom event or call the agent service directly
        window.dispatchEvent(new CustomEvent('configUpdated', {
          detail: configSummary
        }));
      },

      checkUserIdExists: async (userId: string, workspaceDirectory: string) => {
        const baseUrl = await resolvePipelineBaseUrl();
        const token = getResolvedAccessToken();
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const params = new URLSearchParams({ userId, workspaceDirectory });
        const res = await fetch(`${baseUrl}/api/users/check?${params}`, { headers });
        if (!res.ok) return false;
        const data = await res.json();
        return !!data.exists;
      },

      verifyUserId: async (userId: string, password: string, workspaceDirectory: string) => {
        const baseUrl = await resolvePipelineBaseUrl();
        const accessToken = getResolvedAccessToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
        const res = await fetch(`${baseUrl}/api/users/auth`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ userId, password, workspaceDirectory }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error((data as any).error || 'Unable to verify this User ID. Please check the Workspace Directory and try again.');
        }
        const data = await res.json();
        set({ userToken: data.token, verifiedUserId: userId, verifiedWorkspaceDirectory: workspaceDirectory });
        return { claimed: !!data.claimed };
      },

      changePassword: async (userId: string, currentPassword: string, newPassword: string, workspaceDirectory: string) => {
        const baseUrl = await resolvePipelineBaseUrl();
        const accessToken = getResolvedAccessToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
        const res = await fetch(`${baseUrl}/api/users/auth`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ userId, password: currentPassword, newPassword, workspaceDirectory }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error((data as any).error || 'Unable to change the password. Please check the Workspace Directory and try again.');
        }
        const data = await res.json();
        set({ userToken: data.token, verifiedUserId: userId, verifiedWorkspaceDirectory: workspaceDirectory });
      },
    }),
    {
      name: 'config-store',
      partialize: (state) => ({
        config: state.config,
        userToken: state.userToken,
        verifiedUserId: state.verifiedUserId,
        verifiedWorkspaceDirectory: state.verifiedWorkspaceDirectory,
      }),
    }
  )
);
