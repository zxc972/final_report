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
import { PlusOutlined, ReloadOutlined, SearchOutlined, FilterOutlined } from '@ant-design/icons';
import { usePipelineStore } from '../../stores/pipelineStore';
import TaskCard from './TaskCard';

const { TabPane } = Tabs;
const { Search } = Input;
const { Option } = Select;

interface TaskManagerProps {
  onCreateNewTask?: () => void;
}

const TaskManager: React.FC<TaskManagerProps> = ({ onCreateNewTask }) => {
  const { tasks, error, refreshStatuses, clearError, clearFinished } = usePipelineStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [activeTab, setActiveTab] = useState('all');

  useEffect(() => {
    refreshStatuses();
    const timer = setInterval(refreshStatuses, 5000);
    return () => clearInterval(timer);
  }, [refreshStatuses]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const filteredTasks = tasks.filter((task) => {
    const matchesSearch =
      searchTerm === '' ||
      task.taskId.toLowerCase().includes(searchTerm.toLowerCase()) ||
      task.subjectId.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesStatus = statusFilter === 'all' || task.status === statusFilter;

    const matchesTab =
      activeTab === 'all' ||
      (activeTab === 'active' && (task.status === 'running' || task.status === 'pending')) ||
      (activeTab === 'completed' && task.status === 'completed') ||
      (activeTab === 'failed' && (task.status === 'failed' || task.status === 'cancelled'));

    return matchesSearch && matchesStatus && matchesTab;
  });

  const getTaskCounts = () => {
    const activeTasks = tasks.filter((t) => t.status === 'running' || t.status === 'pending').length;
    const completedTasks = tasks.filter((t) => t.status === 'completed').length;
    const failedTasks = tasks.filter((t) => t.status === 'failed' || t.status === 'cancelled').length;

    return { activeTasks, completedTasks, failedTasks };
  };

  const { activeTasks, completedTasks, failedTasks } = getTaskCounts();

  const handleCreateNewTask = () => {
    if (onCreateNewTask) {
      onCreateNewTask();
    }
  };

  const handleRefresh = () => {
    refreshStatuses();
    message.success('Task list refreshed');
  };

  const handleClearFinished = () => {
    clearFinished();
    message.success('Cleared completed/failed/cancelled tasks');
  };

  return (
    <div className="h-full flex flex-col">
      <div className="mb-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Task Manager</h2>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateNewTask}>
              New Task
            </Button>
            <Button onClick={handleClearFinished}>Clear Completed/Failed</Button>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              Refresh
            </Button>
          </Space>
        </div>

        <div className="flex items-center space-x-4 mb-4">
          <Search
            placeholder="Search by Task ID or Subject ID"
            allowClear
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ width: 300 }}
            prefix={<SearchOutlined />}
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 180 }}
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
      </div>

      <Card className="flex-1">
        <Tabs activeKey={activeTab} onChange={setActiveTab} className="h-full">
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
                  description={tasks.length === 0 ? 'No tasks yet' : 'No tasks match the current filters'}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  {tasks.length === 0 && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateNewTask}>
                      Create First Task
                    </Button>
                  )}
                </Empty>
              ) : (
                <div className="space-y-4">
                  {filteredTasks.map((task) => (
                    <TaskCard key={task.taskId} task={task} />
                  ))}
                </div>
              )}
            </div>
          </TabPane>

          <TabPane
            tab={
              <Badge count={activeTasks} showZero>
                <span>Active</span>
              </Badge>
            }
            key="active"
          />
          <TabPane
            tab={
              <Badge count={completedTasks} showZero>
                <span>Completed</span>
              </Badge>
            }
            key="completed"
          />
          <TabPane
            tab={
              <Badge count={failedTasks} showZero>
                <span>Failed/Cancelled</span>
              </Badge>
            }
            key="failed"
          />
        </Tabs>
      </Card>
    </div>
  );
};

export default TaskManager;
