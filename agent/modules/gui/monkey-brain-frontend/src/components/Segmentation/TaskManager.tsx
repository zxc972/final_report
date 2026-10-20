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

import React, { useEffect, useState } from 'react';
import { Card, Button, Space, Empty, Tabs, Badge, Input, Select, message } from 'antd';
import { 
  PlusOutlined, 
  ReloadOutlined, 
  SearchOutlined,
  FilterOutlined 
} from '@ant-design/icons';
import { useSegmentationStore } from '../../stores/segmentationStore';
import { useConfigStore } from '../../stores/configStore';
import { SegmentationTask } from '../../types/segmentation';
import TaskResults from './TaskResults';

const { TabPane } = Tabs;
const { Search } = Input;
const { Option } = Select;

interface TaskManagerProps {
  onCreateNewTask?: () => void;
  onViewResults?: (task: SegmentationTask) => void;
}

const TaskManager: React.FC<TaskManagerProps> = ({ onCreateNewTask, onViewResults }) => {
  const { 
    tasks, 
    currentTask, 
    isSubmitting, 
    error,
    refreshTasks,
    clearError 
  } = useSegmentationStore();
  
  const { config } = useConfigStore();
  
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [activeTab, setActiveTab] = useState('all');

  useEffect(() => {
    refreshTasks();
  }, [refreshTasks]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  // Filter tasks based on search and status
  const filteredTasks = tasks.filter(task => {
    const matchesSearch = searchTerm === '' || 
      task.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      task.message.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesStatus = statusFilter === 'all' || task.status === statusFilter;
    
    const matchesTab = activeTab === 'all' || 
      (activeTab === 'active' && (task.status === 'running' || task.status === 'pending')) ||
      (activeTab === 'completed' && task.status === 'completed') ||
      (activeTab === 'failed' && (task.status === 'failed' || task.status === 'cancelled'));
    
    return matchesSearch && matchesStatus && matchesTab;
  });

  // Get task counts for badges
  const getTaskCounts = () => {
    const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'pending').length;
    const completedTasks = tasks.filter(t => t.status === 'completed').length;
    const failedTasks = tasks.filter(t => t.status === 'failed' || t.status === 'cancelled').length;
    
    return { activeTasks, completedTasks, failedTasks };
  };

  const { activeTasks, completedTasks, failedTasks } = getTaskCounts();

  const handleCreateNewTask = () => {
    if (!config) {
      message.warning('Please configure segmentation parameters first');
      return;
    }
    
    if (onCreateNewTask) {
      onCreateNewTask();
    }
  };

  const handleRefresh = () => {
    refreshTasks();
    message.success('Task list refreshed');
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Segmentation Task Management</h2>
          <Space>
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={handleCreateNewTask}
              loading={isSubmitting}
              disabled={!config}
            >
              New Task
            </Button>
            <Button 
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
            >
              Refresh
            </Button>
          </Space>
        </div>

        {/* Search and Filter */}
        <div className="flex items-center space-x-4 mb-4">
          <Search
            placeholder="Search by Task ID or message"
            allowClear
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ width: 300 }}
            prefix={<SearchOutlined />}
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 150 }}
            suffixIcon={<FilterOutlined />}
          >
            <Option value="all">All Statuses</Option>
            <Option value="pending">Pending</Option>
            <Option value="running">Running</Option>
            <Option value="completed">Completed</Option>
            <Option value="failed">Failed</Option>
            <Option value="cancelled">Cancelled</Option>
          </Select>
        </div>

        {!config && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4">
            <div className="text-yellow-800 text-sm">
              ⚠️ Please configure segmentation parameters on the "Parameter Configuration" page before creating a new task.
            </div>
          </div>
        )}
      </div>

      {/* Task Tabs */}
      <Card className="flex-1">
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          className="h-full"
        >
          <TabPane 
            tab={
              <Badge count={tasks.length} showZero>
                <span>All Tasks</span>
              </Badge>
            } 
            key="all"
          >
            <div className="h-full overflow-y-auto">
              {filteredTasks.length === 0 ? (
                <Empty 
                  description={
                    tasks.length === 0 
                      ? "No segmentation tasks yet" 
                      : "No tasks matching the criteria"
                  }
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  {tasks.length === 0 && config && (
                    <Button 
                      type="primary" 
                      icon={<PlusOutlined />}
                      onClick={handleCreateNewTask}
                    >
                      Create First Task
                    </Button>
                  )}
                </Empty>
              ) : (
                <div className="space-y-4">
                  {filteredTasks.map(task => (
                    <TaskResults 
                      key={task.id} 
                      task={task} 
                      onViewResults={onViewResults}
                    />
                  ))}
                </div>
              )}
            </div>
          </TabPane>

          <TabPane 
            tab={
              <Badge count={activeTasks} showZero>
                <span>In Progress</span>
              </Badge>
            } 
            key="active"
          >
            <div className="h-full overflow-y-auto">
              {filteredTasks.length === 0 ? (
                <Empty 
                  description="No tasks in progress"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <div className="space-y-4">
                  {filteredTasks.map(task => (
                    <TaskResults 
                      key={task.id} 
                      task={task} 
                      onViewResults={onViewResults}
                    />
                  ))}
                </div>
              )}
            </div>
          </TabPane>

          <TabPane 
            tab={
              <Badge count={completedTasks} showZero>
                <span>Completed</span>
              </Badge>
            } 
            key="completed"
          >
            <div className="h-full overflow-y-auto">
              {filteredTasks.length === 0 ? (
                <Empty 
                  description="No completed tasks"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <div className="space-y-4">
                  {filteredTasks.map(task => (
                    <TaskResults 
                      key={task.id} 
                      task={task} 
                      onViewResults={onViewResults}
                    />
                  ))}
                </div>
              )}
            </div>
          </TabPane>

          <TabPane 
            tab={
              <Badge count={failedTasks} showZero>
                <span>Failed</span>
              </Badge>
            } 
            key="failed"
          >
            <div className="h-full overflow-y-auto">
              {filteredTasks.length === 0 ? (
                <Empty 
                  description="No failed tasks"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <div className="space-y-4">
                  {filteredTasks.map(task => (
                    <TaskResults 
                      key={task.id} 
                      task={task} 
                      onViewResults={onViewResults}
                    />
                  ))}
                </div>
              )}
            </div>
          </TabPane>
        </Tabs>
      </Card>

      {/* Current Task Status */}
      {currentTask && (currentTask.status === 'running' || currentTask.status === 'pending') && (
        <Card className="mt-4" size="small">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
              <span className="text-sm font-medium">Current Task: {currentTask.id.slice(-8)}</span>
              <span className="text-sm text-gray-600">{currentTask.message}</span>
            </div>
            <div className="text-sm text-gray-500">
              {currentTask.progress}%
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default TaskManager;