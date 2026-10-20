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

import { SegmentationConfig } from '../stores/configStore';
import { getResolvedAccessToken } from './accessToken';
import { resolvePipelineBaseUrl } from '../utils/runtimePorts';

export interface SegmentationRequest {
  id: string;
  workspaceDirectory: string;
  modelDir: string;
  processingOptions: {
    enablePreprocessing: boolean;
    qualityLevel: 'fast' | 'standard' | 'high';
    threads: number;
  };
  inputFiles: string[];
  userId: string;
}

export interface SegmentationTask {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  message: string;
  startTime: Date;
  endTime?: Date;
  error?: string;
  resultFiles?: string[];
  metadata?: Record<string, any>;
}

export interface SegmentationProgress {
  taskId: string;
  progress: number;
  stage: string;
  message: string;
  timestamp: Date;
}

export interface SegmentationResult {
  taskId: string;
  success: boolean;
  outputFiles: string[];
  metadata: {
    processingTime: number;
    modelUsed: string;
    qualityMetrics?: Record<string, number>;
  };
  error?: string;
}

class SegmentationService {
  private tasks: Map<string, SegmentationTask> = new Map();
  private progressCallbacks: Map<string, (progress: SegmentationProgress) => void> = new Map();
  private completionCallbacks: Map<string, (result: SegmentationResult) => void> = new Map();
  private baseUrlPromise: Promise<string> | null = null;
  private retryAttempts: number = 3;
  private retryDelay: number = 1000;

  constructor() {}

  private async getBaseUrl(): Promise<string> {
    if (!this.baseUrlPromise) {
      this.baseUrlPromise = resolvePipelineBaseUrl();
    }
    return this.baseUrlPromise;
  }

  private getAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = getResolvedAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  }

  /**
   * Submit a new segmentation request
   */
  async submitSegmentationRequest(
    config: SegmentationConfig,
    inputFiles: string[],
    userId: string
  ): Promise<string> {
    const taskId = this.generateTaskId();
    
    const request: SegmentationRequest = {
      id: taskId,
      workspaceDirectory: config.workspaceDirectory,
      modelDir: config.modelDir,
      processingOptions: config.processingOptions,
      inputFiles,
      userId,
    };

    // Create initial task
    const task: SegmentationTask = {
      id: taskId,
      status: 'pending',
      progress: 0,
      message: 'Submitting segmentation request...',
      startTime: new Date(),
    };

    this.tasks.set(taskId, task);

    try {
      // Submit to backend with retry logic
      await this.submitWithRetry(request);
      
      // Update task status
      task.status = 'running';
      task.message = 'Segmentation task started';
      this.tasks.set(taskId, task);

      // Start progress monitoring
      this.startProgressMonitoring(taskId);

      return taskId;
    } catch (error: any) {
      task.status = 'failed';
      task.error = error.message;
      task.endTime = new Date();
      this.tasks.set(taskId, task);
      throw error;
    }
  }

  /**
   * Get task status and progress
   */
  getTaskStatus(taskId: string): SegmentationTask | null {
    return this.tasks.get(taskId) || null;
  }

  /**
   * Get all tasks for a user
   */
  getUserTasks(userId: string): SegmentationTask[] {
    return Array.from(this.tasks.values()).filter(task => 
      task.metadata?.userId === userId
    );
  }

  /**
   * Cancel a running task
   */
  async cancelTask(taskId: string): Promise<void> {
    const task = this.tasks.get(taskId);
    if (!task) {
      throw new Error(`Task ${taskId} not found`);
    }

    if (task.status !== 'running' && task.status !== 'pending') {
      throw new Error(`Task ${taskId} cannot be cancelled (status: ${task.status})`);
    }

    try {
      // Send cancellation request to backend
      const baseUrl = await this.getBaseUrl();
      await fetch(`${baseUrl}/api/segmentation/${taskId}/cancel`, {
        method: 'POST',
        headers: this.getAuthHeaders(),
      });

      // Update local task status
      task.status = 'cancelled';
      task.endTime = new Date();
      task.message = 'Task cancelled by user';
      this.tasks.set(taskId, task);

    } catch (error: any) {
      console.error('Failed to cancel task:', error);
      throw new Error(`Failed to cancel task: ${error.message}`);
    }
  }

  /**
   * Subscribe to progress updates for a specific task
   */
  subscribeToProgress(
    taskId: string, 
    callback: (progress: SegmentationProgress) => void
  ): () => void {
    this.progressCallbacks.set(taskId, callback);
    
    return () => {
      this.progressCallbacks.delete(taskId);
    };
  }

  /**
   * Subscribe to task completion
   */
  subscribeToCompletion(
    taskId: string,
    callback: (result: SegmentationResult) => void
  ): () => void {
    this.completionCallbacks.set(taskId, callback);
    
    return () => {
      this.completionCallbacks.delete(taskId);
    };
  }

  /**
   * Download result files
   */
  async downloadResults(taskId: string): Promise<Blob> {
    const task = this.tasks.get(taskId);
    if (!task || task.status !== 'completed') {
      throw new Error('Task not completed or not found');
    }

    try {
      const baseUrl = await this.getBaseUrl();
      const response = await fetch(`${baseUrl}/api/segmentation/${taskId}/download`, {
        method: 'GET',
        headers: this.getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('The results could not be downloaded. Please make sure the task is completed and try again.');
      }

      return await response.blob();
    } catch (error: any) {
      console.error('Failed to download results:', error);
      throw new Error(`Failed to download results: ${error.message}`);
    }
  }

  /**
   * Get processing statistics
   */
  getProcessingStats(): {
    totalTasks: number;
    completedTasks: number;
    failedTasks: number;
    averageProcessingTime: number;
  } {
    const tasks = Array.from(this.tasks.values());
    const completedTasks = tasks.filter(t => t.status === 'completed');
    const failedTasks = tasks.filter(t => t.status === 'failed');
    
    const avgTime = completedTasks.length > 0 
      ? completedTasks.reduce((sum, task) => {
          if (task.endTime && task.startTime) {
            return sum + (task.endTime.getTime() - task.startTime.getTime());
          }
          return sum;
        }, 0) / completedTasks.length
      : 0;

    return {
      totalTasks: tasks.length,
      completedTasks: completedTasks.length,
      failedTasks: failedTasks.length,
      averageProcessingTime: avgTime,
    };
  }

  // Private methods

  private generateTaskId(): string {
    return `seg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private async submitWithRetry(request: SegmentationRequest): Promise<void> {
    let lastError: Error;

    for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
      try {
        const baseUrl = await this.getBaseUrl();
        const response = await fetch(`${baseUrl}/api/segmentation/submit`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          body: JSON.stringify(request),
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.message || 'The backend could not start this segmentation task. Please check Configuration and try again.');
        }

        // Success
        return;
      } catch (error: any) {
        lastError = error;
        console.warn(`Attempt ${attempt} failed:`, error.message);

        if (attempt < this.retryAttempts) {
          await this.delay(this.retryDelay * attempt);
        }
      }
    }

    throw new Error(`Failed after ${this.retryAttempts} attempts: ${lastError!.message}`);
  }

  private async startProgressMonitoring(taskId: string): Promise<void> {
    const pollInterval = 2000; // Poll every 2 seconds
    
    const poll = async () => {
      try {
        const baseUrl = await this.getBaseUrl();
        const response = await fetch(`${baseUrl}/api/segmentation/${taskId}/status`, {
          headers: this.getAuthHeaders(),
        });

        if (!response.ok) {
          throw new Error('The task status could not be updated. Please refresh the page and try again.');
        }

        const data = await response.json();
        this.updateTaskFromBackend(taskId, data);

        // Continue polling if task is still running
        const task = this.tasks.get(taskId);
        if (task && (task.status === 'running' || task.status === 'pending')) {
          setTimeout(poll, pollInterval);
        }
      } catch (error: any) {
        console.error('Progress monitoring error:', error);
        // Continue polling on error, but with longer interval
        setTimeout(poll, pollInterval * 2);
      }
    };

    // Start polling
    setTimeout(poll, pollInterval);
  }

  private updateTaskFromBackend(taskId: string, backendData: any): void {
    const task = this.tasks.get(taskId);
    if (!task) return;

    // Update task from backend response
    task.status = backendData.status;
    task.progress = backendData.progress || 0;
    task.message = backendData.message || task.message;

    if (backendData.error) {
      task.error = backendData.error;
    }

    if (backendData.resultFiles) {
      task.resultFiles = backendData.resultFiles;
    }

    if (backendData.status === 'completed' || backendData.status === 'failed') {
      task.endTime = new Date();
    }

    this.tasks.set(taskId, task);

    // Notify progress callback
    const progressCallback = this.progressCallbacks.get(taskId);
    if (progressCallback) {
      progressCallback({
        taskId,
        progress: task.progress,
        stage: backendData.stage || 'processing',
        message: task.message,
        timestamp: new Date(),
      });
    }

    // Notify completion callback
    if (task.status === 'completed' || task.status === 'failed') {
      const completionCallback = this.completionCallbacks.get(taskId);
      if (completionCallback) {
        completionCallback({
          taskId,
          success: task.status === 'completed',
          outputFiles: task.resultFiles || [],
          metadata: {
            processingTime: task.endTime && task.startTime 
              ? task.endTime.getTime() - task.startTime.getTime()
              : 0,
            modelUsed: backendData.modelUsed || 'unknown',
            qualityMetrics: backendData.qualityMetrics,
          },
          error: task.error,
        });
      }
    }
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Export singleton instance
export const segmentationService = new SegmentationService();
