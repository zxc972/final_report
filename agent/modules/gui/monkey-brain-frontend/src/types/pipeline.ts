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

export type PipelineStep =
  | 'preprocess-1'
  | 'seg-brain'
  | 'acpc-align'
  | 'seg-wm'
  | 'preprocess-3'
  | 'rescale'
  | 'freesurfer2caret'
  | 'fastsurfer';

export interface PipelineRunRequest {
  userId: string;
  subjectId: string;
  t1Path: string;
  workspaceDirectory: string;
  species: 'Macaque' | 'Chimpanzee' | 'Marmoset' | 'Human';
  segSpecies?: 'rhesus' | 'cynomolgus' | 'chimpanzee' | 'marmoset' | 'human';
  steps: PipelineStep[];
  modelDir?: string;
  brainSize?: number;
  reference?: string;
  lowResMesh?: number;
  threads: number;
}

export interface PipelineRunResponse {
  taskId: string;
}

export interface PipelineStatus {
  taskId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  currentStep?: PipelineStep;
  message?: string;
  progress?: number;
  source?: 'pipeline' | 'agent';
  logPath?: string;
  threads?: number;
  startTime?: string;
  endTime?: string;
  durationSeconds?: number | null;
}

export interface PipelineTask extends PipelineStatus {
  userId: string;
  subjectId: string;
  t1Path: string;
  workspaceDirectory: string;
  species: PipelineRunRequest['species'];
  segSpecies: PipelineRunRequest['segSpecies'];
  steps: PipelineStep[];
  threads?: number;
  createdAt: string;
  updatedAt?: string;
  error?: string;
}

export interface SubjectStatus {
  hasAnyOutput: boolean;
  completedSteps: PipelineStep[];
  cleanupRequired?: boolean;
  cleanupRequiredSteps?: PipelineStep[];
  cleanupPlan?: Array<{
    step: PipelineStep;
    paths: string[];
    message: string;
  }>;
  outPath: string;
}

export interface WorkspaceSubject {
  subjectId: string;
  hasInput: boolean;
  inputDir?: string;
  inputFiles: string[];
  hasOutput: boolean;
  outputDir?: string;
  completedSteps: PipelineStep[];
  outputFiles: string[];
}
