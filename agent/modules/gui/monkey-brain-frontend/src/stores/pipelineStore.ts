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
import { pipelineService } from '../services/pipelineService';
import { PipelineRunRequest, PipelineTask } from '../types/pipeline';

interface PipelineState {
  tasks: PipelineTask[];
  isSubmitting: boolean;
  error: string | null;
  submitPipeline: (payload: PipelineRunRequest) => Promise<string>;
  refreshStatuses: () => Promise<void>;
  cancelTask: (taskId: string) => Promise<void>;
  clearFinished: () => void;
  clearError: () => void;
}

export const usePipelineStore = create<PipelineState>()(
  persist(
    (set, get) => ({
      tasks: [],
      isSubmitting: false,
      error: null,

      submitPipeline: async (payload: PipelineRunRequest) => {
        set({ isSubmitting: true, error: null });
        try {
          const response = await pipelineService.runPipeline(payload);
          const now = new Date().toISOString();
          const newTask: PipelineTask = {
            taskId: response.taskId,
            status: 'pending',
            currentStep: payload.steps[0],
            message: 'Queued',
            progress: 0,
            userId: payload.userId,
            subjectId: payload.subjectId,
            t1Path: payload.t1Path,
            workspaceDirectory: payload.workspaceDirectory,
            species: payload.species,
            segSpecies: payload.segSpecies,
            steps: payload.steps,
            threads: payload.threads,
            createdAt: now,
            updatedAt: now,
          };
          set((state) => ({ tasks: [newTask, ...state.tasks] }));
          return response.taskId;
        } catch (error: any) {
          set({ error: error.message || 'Submit Error' });
          throw error;
        } finally {
          set({ isSubmitting: false });
        }
      },

      refreshStatuses: async () => {
        const { tasks } = get();
        if (tasks.length === 0) return;

        const updates = await Promise.all(
          tasks.map(async (task) => {
            try {
              const status = await pipelineService.getStatus(task.taskId);
              return {
                ...task,
                status: status.status,
                currentStep: status.currentStep,
                message: status.message,
                progress: status.progress,
                threads: status.threads ?? task.threads,
                error: (status as any).error,
                updatedAt: new Date().toISOString(),
              };
            } catch (error: any) {
              return {
                ...task,
                error: error.message || 'Status Fetch Error',
                updatedAt: new Date().toISOString(),
              };
            }
          })
        );

        set({ tasks: updates });
      },

      cancelTask: async (taskId: string) => {
        set({ error: null });
        await pipelineService.cancelTask(taskId);
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.taskId === taskId
              ? { ...task, status: 'cancelled', message: 'Cancelled by user' }
              : task
          ),
        }));
      },

      clearFinished: () => {
        set((state) => ({
          tasks: state.tasks.filter(
            (task) => task.status === 'running' || task.status === 'pending'
          ),
        }));
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'pipeline-store',
      version: 1,
      partialize: (state) => ({ tasks: state.tasks }),
      migrate: (persistedState: any, version: number) => {
        if (version < 1 && persistedState?.tasks) {
          persistedState.tasks = persistedState.tasks.map((t: any) => ({
            ...t,
            userId: t.userId || '',
          }));
        }
        return persistedState;
      },
    }
  )
);
