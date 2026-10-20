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

export interface ProcessingStats {
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  averageProcessingTime: number;
}
