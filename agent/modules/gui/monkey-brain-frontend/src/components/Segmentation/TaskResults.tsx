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
import { Card, Button, Progress, Tag, Space, Descriptions, Alert, Divider } from 'antd';
import { 
  DownloadOutlined, 
  EyeOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined 
} from '@ant-design/icons';
import { SegmentationTask } from '../../types/segmentation';
import { useSegmentationStore } from '../../stores/segmentationStore';

interface TaskResultsProps {
  task: SegmentationTask;
  onViewResults?: (task: SegmentationTask) => void;
}

const TaskResults: React.FC<TaskResultsProps> = ({ task, onViewResults }) => {
  const { downloadResults, error } = useSegmentationStore();

  const getStatusIcon = (status: SegmentationTask['status']) => {
    switch (status) {
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

  const getStatusColor = (status: SegmentationTask['status']) => {
    switch (status) {
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

  const formatDuration = (startTime: Date, endTime?: Date) => {
    const end = endTime || new Date();
    const duration = end.getTime() - startTime.getTime();
    const seconds = Math.floor(duration / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  const handleDownload = async () => {
    try {
      await downloadResults(task.id);
    } catch (error: any) {
      console.error('Download failed:', error);
    }
  };

  const handleViewResults = () => {
    if (onViewResults) {
      onViewResults(task);
    }
  };

  return (
    <Card className="mb-4">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center space-x-3">
          {getStatusIcon(task.status)}
          <div>
            <h3 className="text-lg font-semibold">Segmentation Task {task.id.slice(-8)}</h3>
            <Tag color={getStatusColor(task.status)} className="mt-1">
              {task.status.toUpperCase()}
            </Tag>
          </div>
        </div>
        
        <div className="text-right text-sm text-gray-500">
          <div>Start Time: {task.startTime.toLocaleString()}</div>
          {task.endTime && (
            <div>End Time: {task.endTime.toLocaleString()}</div>
          )}
          <div>
            Duration: {formatDuration(task.startTime, task.endTime)}
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      {(task.status === 'running' || task.status === 'pending') && (
        <div className="mb-4">
          <Progress 
            percent={task.progress} 
            status={task.status === 'running' ? 'active' : 'normal'}
            showInfo={true}
          />
          <div className="text-sm text-gray-600 mt-1">{task.message}</div>
        </div>
      )}

      {/* Error Display */}
      {task.status === 'failed' && task.error && (
        <Alert
          message="Segmentation task failed"
          description={task.error}
          type="error"
          showIcon
          className="mb-4"
        />
      )}

      {/* Task Details */}
      <Descriptions size="small" column={2} className="mb-4">
        <Descriptions.Item label="Task ID">{task.id}</Descriptions.Item>
        <Descriptions.Item label="Status">
          <Tag color={getStatusColor(task.status)}>
            {task.status.toUpperCase()}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Progress">{task.progress}%</Descriptions.Item>
        <Descriptions.Item label="Message">{task.message}</Descriptions.Item>
        
        {task.metadata?.modelUsed && (
          <Descriptions.Item label="Model Used">{task.metadata.modelUsed}</Descriptions.Item>
        )}
        
        {task.metadata?.processingTime && (
          <Descriptions.Item label="Processing Time">
            {Math.round(task.metadata.processingTime / 1000)} s
          </Descriptions.Item>
        )}
      </Descriptions>

      {/* Result Files */}
      {task.resultFiles && task.resultFiles.length > 0 && (
        <div className="mb-4">
          <Divider orientation="left" orientationMargin="0">
            <span className="text-sm font-medium">Output Files</span>
          </Divider>
          <div className="bg-gray-50 p-3 rounded">
            {task.resultFiles.map((file, index) => (
              <div key={index} className="text-sm text-gray-700 mb-1">
                📄 {file}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quality Metrics */}
      {task.metadata?.qualityMetrics && (
        <div className="mb-4">
          <Divider orientation="left" orientationMargin="0">
            <span className="text-sm font-medium">Quality Metrics</span>
          </Divider>
          <div className="grid grid-cols-2 gap-4">
            {Object.entries(task.metadata.qualityMetrics).map(([key, value]) => (
              <div key={key} className="text-sm">
                <span className="text-gray-600">{key}:</span>
                <span className="ml-2 font-medium">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      {task.status === 'completed' && (
        <Space>
          <Button 
            type="primary" 
            icon={<DownloadOutlined />}
            onClick={handleDownload}
          >
            Download Results
          </Button>
          <Button 
            icon={<EyeOutlined />}
            onClick={handleViewResults}
          >
            View Results
          </Button>
        </Space>
      )}

      {/* Error Display for Store Errors */}
      {error && (
        <Alert
          message="Operation failed"
          description={error}
          type="error"
          showIcon
          closable
          className="mt-4"
        />
      )}
    </Card>
  );
};

export default TaskResults;