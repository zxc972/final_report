import type { AnalysisResultInfo } from '../utils/analysisResult';
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

export interface Message {
  id: string;
  type: 'user' | 'agent' | 'system';
  content: string;
  timestamp: Date;
  metadata?: MessageMetadata;
}

export interface MessageMetadata {
  analysis?: AnalysisResultInfo;
  /** Which agent the backend routed this request to. */
  route?: 'pipeline' | 'analysis';
  routeReason?: string;
  taskId?: string;
  attachments?: Attachment[];
  actions?: Action[];
}

export interface Attachment {
  id: string;
  name: string;
  type: string;
  url: string;
  size: number;
}

export interface Action {
  id: string;
  type: string;
  label: string;
  data: Record<string, any>;
}

export interface Conversation {
  id: string;
  userId: string;
  messages: Message[];
  context: ConversationContext;
  createdAt: Date;
  updatedAt: Date;
}

export interface ConversationContext {
  taskId?: string;
  workspaceDirectory?: string;
  modelDir?: string;
  currentStep?: string;
  threads?: number;
  [key: string]: any;
}

export interface AgentResponse {
  message: string;
  taskId?: string;
  requiresAction?: ActionType;
  metadata?: Record<string, any>;
}

export interface AgentUpdate {
  type: 'status' | 'progress' | 'result' | 'error';
  data: any;
  timestamp: Date;
}

export enum ActionType {
  CONFIGURE_WORKSPACE = 'configure_workspace',
  SELECT_MODEL = 'select_model',
  START_SEGMENTATION = 'start_segmentation',
  VIEW_RESULTS = 'view_results',
}
