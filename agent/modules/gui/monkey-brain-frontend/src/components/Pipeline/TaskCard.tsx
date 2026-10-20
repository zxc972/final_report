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

import React from 'react';
import { Card, Button, Progress, Tag, Space, Descriptions } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { PipelineTask } from '../../types/pipeline';
import { usePipelineStore } from '../../stores/pipelineStore';

interface TaskCardProps {
  task: PipelineTask;
}

const TaskCard: React.FC<TaskCardProps> = ({ task }) => {
  const { cancelTask } = usePipelineStore();

  const getStatusIcon = () => {
    switch (task.status) {
      case 'completed':
        return <CheckCircleOutlined className="text-green-500" />;
      case 'failed':
        return <CloseCircleOutlined className="text-red-500" />;
      case 'running':
        return <LoadingOutlined className="text-blue-500" />;
      case 'cancelled':
        return <CloseCircleOutlined className="text-gray-500" />;
      default:
        return <ClockCircleOutlined className="text-yellow-500" />;
    }
  };

  const getStatusColor = () => {
    switch (task.status) {
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      case 'running':
        return 'processing';
      case 'cancelled':
        return 'default';
      default:
        return 'warning';
    }
  };

  const handleCancel = async () => {
    await cancelTask(task.taskId);
  };

  return (
    <Card className="mb-4">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center space-x-3">
          {getStatusIcon()}
          <div>
            <h3 className="text-lg font-semibold">Pipeline Task {task.taskId.slice(-8)}</h3>
            <Tag color={getStatusColor()} className="mt-1">
              {task.status.toUpperCase()}
            </Tag>
          </div>
        </div>
        <div className="text-right text-sm text-gray-500">
          <div>Submitted at: {new Date(task.createdAt).toLocaleString()}</div>
          {task.updatedAt && <div>Updated at: {new Date(task.updatedAt).toLocaleString()}</div>}
        </div>
      </div>

      {(task.status === 'running' || task.status === 'pending') && (
        <div className="mb-4">
          <Progress percent={task.progress || 0} status={task.status === 'running' ? 'active' : 'normal'} />
          <div className="text-sm text-gray-600 mt-1">{task.message}</div>
        </div>
      )}

      <Descriptions size="small" column={2} className="mb-4">
        <Descriptions.Item label="Subject ID">{task.subjectId}</Descriptions.Item>
        <Descriptions.Item label="Species">{task.species}</Descriptions.Item>
        <Descriptions.Item label="Segmentation Species">{task.segSpecies || '-'}</Descriptions.Item>
        <Descriptions.Item label="Current Step">{task.currentStep || '-'}</Descriptions.Item>
        <Descriptions.Item label="Workspace Directory">{task.workspaceDirectory}</Descriptions.Item>
        <Descriptions.Item label="T1 Path">{task.t1Path}</Descriptions.Item>
      </Descriptions>

      {task.status === 'failed' && task.error && (
        <div className="mb-4 text-sm text-red-600">
          Failure reason: {task.error}
        </div>
      )}

      <Space>
        {(task.status === 'running' || task.status === 'pending') && (
          <Button danger icon={<StopOutlined />} onClick={handleCancel}>
            Terminate Task
          </Button>
        )}
      </Space>
    </Card>
  );
};

export default TaskCard;
