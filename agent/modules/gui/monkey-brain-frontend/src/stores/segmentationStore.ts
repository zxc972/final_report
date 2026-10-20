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
import { SegmentationTask, SegmentationProgress, SegmentationResult } from '../types/segmentation';
import { segmentationService } from '../services/segmentationService';
import { useConfigStore } from './configStore';
import { getSessionId } from '../services/session';

interface SegmentationState {
  tasks: SegmentationTask[];
  currentTask: SegmentationTask | null;
  isSubmitting: boolean;
  error: string | null;
  
  // Actions
  submitSegmentationTask: (inputFiles: string[]) => Promise<string>;
  cancelTask: (taskId: string) => Promise<void>;
  getTaskById: (taskId: string) => SegmentationTask | null;
  clearError: () => void;
  updateTaskProgress: (progress: SegmentationProgress) => void;
  handleTaskCompletion: (result: SegmentationResult) => void;
  downloadResults: (taskId: string) => Promise<void>;
  refreshTasks: () => void;
}

export const useSegmentationStore = create<SegmentationState>()(
  persist(
    (set, get) => ({
      tasks: [],
      currentTask: null,
      isSubmitting: false,
      error: null,

      submitSegmentationTask: async (inputFiles: string[]) => {
        const { config } = useConfigStore.getState();

        if (!config) {
          throw new Error('Please configure the segmentation parameters first');
        }

        if (!inputFiles || inputFiles.length === 0) {
          throw new Error('Please select files for segmentation');
        }

        set({ isSubmitting: true, error: null });

        try {
          const taskId = await segmentationService.submitSegmentationRequest(
            config,
            inputFiles,
            getSessionId()
          );

          // Get the created task
          const task = segmentationService.getTaskStatus(taskId);
          if (task) {
            set(state => ({
              tasks: [...state.tasks, task],
              currentTask: task,
            }));

            // Subscribe to progress updates
            segmentationService.subscribeToProgress(taskId, (progress) => {
              get().updateTaskProgress(progress);
            });

            // Subscribe to completion
            segmentationService.subscribeToCompletion(taskId, (result) => {
              get().handleTaskCompletion(result);
            });
          }

          return taskId;
        } catch (error: any) {
          set({ error: error.message });
          throw error;
        } finally {
          set({ isSubmitting: false });
        }
      },

      cancelTask: async (taskId: string) => {
        set({ error: null });
        
        try {
          await segmentationService.cancelTask(taskId);
          
          // Update local task status
          set(state => ({
            tasks: state.tasks.map(task => 
              task.id === taskId 
                ? { ...task, status: 'cancelled' as const, endTime: new Date() }
                : task
            ),
            currentTask: state.currentTask?.id === taskId 
              ? { ...state.currentTask, status: 'cancelled' as const, endTime: new Date() }
              : state.currentTask,
          }));
        } catch (error: any) {
          set({ error: error.message });
          throw error;
        }
      },

      getTaskById: (taskId: string) => {
        const { tasks } = get();
        return tasks.find(task => task.id === taskId) || null;
      },

      clearError: () => {
        set({ error: null });
      },

      updateTaskProgress: (progress: SegmentationProgress) => {
        set(state => {
          const updatedTasks = state.tasks.map(task => {
            if (task.id === progress.taskId) {
              return {
                ...task,
                progress: progress.progress,
                message: progress.message,
              };
            }
            return task;
          });

          const updatedCurrentTask = state.currentTask?.id === progress.taskId
            ? {
                ...state.currentTask,
                progress: progress.progress,
                message: progress.message,
              }
            : state.currentTask;

          return {
            tasks: updatedTasks,
            currentTask: updatedCurrentTask,
          };
        });
      },

      handleTaskCompletion: (result: SegmentationResult) => {
        set(state => {
          const updatedTasks = state.tasks.map(task => {
            if (task.id === result.taskId) {
              return {
                ...task,
                status: result.success ? 'completed' as const : 'failed' as const,
                progress: 100,
                message: result.success ? 'Segmentation completed' : 'Segmentation failed',
                endTime: new Date(),
                error: result.error,
                resultFiles: result.outputFiles,
                metadata: {
                  ...task.metadata,
                  ...result.metadata,
                },
              };
            }
            return task;
          });

          const updatedCurrentTask = state.currentTask?.id === result.taskId
            ? {
                ...state.currentTask,
                status: result.success ? 'completed' as const : 'failed' as const,
                progress: 100,
                message: result.success ? 'Segmentation completed' : 'Segmentation failed',
                endTime: new Date(),
                error: result.error,
                resultFiles: result.outputFiles,
                metadata: {
                  ...state.currentTask.metadata,
                  ...result.metadata,
                },
              }
            : state.currentTask;

          return {
            tasks: updatedTasks,
            currentTask: updatedCurrentTask,
          };
        });

        // Show notification for completion
        if (result.success) {
          console.log(`Task ${result.taskId} completed successfully`);
        } else {
          console.error(`Task ${result.taskId} failed:`, result.error);
        }
      },

      downloadResults: async (taskId: string) => {
        const task = get().getTaskById(taskId);
        if (!task || task.status !== 'completed') {
          throw new Error('Task not completed or not found');
        }

        try {
          const blob = await segmentationService.downloadResults(taskId);
          
          // Create download link
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `segmentation_results_${taskId}.zip`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          window.URL.revokeObjectURL(url);
        } catch (error: any) {
          set({ error: error.message });
          throw error;
        }
      },

      refreshTasks: () => {
        const userTasks = segmentationService.getUserTasks(getSessionId());
        set({ tasks: userTasks });
      },
    }),
    {
      name: 'segmentation-store',
      partialize: (state) => ({
        tasks: state.tasks,
      }),
    }
  )
);
