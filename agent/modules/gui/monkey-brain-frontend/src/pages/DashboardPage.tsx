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
import { Card, Button, Space, Typography } from 'antd';
import { MessageOutlined, PlayCircleOutlined, ScissorOutlined, SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { buildPathWithToken } from '../services/accessToken';

const { Title, Text } = Typography;
const DEMO_VIDEO_URL = 'https://youtu.be/GWcAMWuRSlk';

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="text-center mb-8">
        <Title level={2}>🧠 PrimateX</Title>
        <Text className="text-lg text-gray-600">
          Welcome! Choose a feature to get started
        </Text>
        <div className="mt-4">
          <Button
            icon={<PlayCircleOutlined />}
            href={DEMO_VIDEO_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Watch Demo
          </Button>
        </div>
      </div>

      {/* Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card 
          hoverable
          className="text-center"
          onClick={() => navigate(buildPathWithToken('/agent'))}
        >
          <div className="p-4">
            <MessageOutlined className="text-4xl text-blue-500 mb-4" />
            <Title level={4}>Workflow Assistant</Title>
            <Text className="text-gray-600">
              Chat with the assistant for T1 preprocessing and cortical reconstruction guidance
            </Text>
          </div>
        </Card>

        <Card 
          hoverable
          className="text-center"
          onClick={() => navigate(buildPathWithToken('/segmentation'))}
        >
          <div className="p-4">
            <ScissorOutlined className="text-4xl text-green-500 mb-4" />
            <Title level={4}>Task Management</Title>
            <Text className="text-gray-600">
              Manage and monitor pipeline tasks
            </Text>
          </div>
        </Card>

        <Card 
          hoverable
          className="text-center"
          onClick={() => navigate(buildPathWithToken('/config'))}
        >
          <div className="p-4">
            <SettingOutlined className="text-4xl text-orange-500 mb-4" />
            <Title level={4}>Parameter Settings</Title>
            <Text className="text-gray-600">
              Configure workspace and pipeline settings
            </Text>
          </div>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card title="Quick Actions">
        <Space wrap>
          <Button 
            type="primary" 
            icon={<MessageOutlined />}
            onClick={() => navigate(buildPathWithToken('/agent'))}
          >
            Start Chat
          </Button>
          <Button 
            icon={<ScissorOutlined />}
            onClick={() => navigate(buildPathWithToken('/segmentation'))}
          >
            New Task
          </Button>
          <Button 
            icon={<SettingOutlined />}
            onClick={() => navigate(buildPathWithToken('/config'))}
          >
            System Settings
          </Button>
        </Space>
      </Card>
    </div>
  );
};

export default DashboardPage;
