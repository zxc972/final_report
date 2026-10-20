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
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  MessageOutlined,
  SettingOutlined,
  ScissorOutlined,
  EyeOutlined,
  DeploymentUnitOutlined,
} from '@ant-design/icons';
import { buildPathWithToken } from '../../services/accessToken';

const { Header, Sider, Content } = Layout;

interface MainLayoutProps {
  children: React.ReactNode;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      key: 'dashboard',
      icon: <MessageOutlined />,
      label: 'Dashboard',
    },
    {
      key: 'agent',
      icon: <MessageOutlined />,
      label: 'Workflow Assistant',
    },
    {
      key: 'pipeline',
      icon: <DeploymentUnitOutlined />,
      label: 'Pipeline Orchestration',
    },
    {
      key: 'segmentation',
      icon: <ScissorOutlined />,
      label: 'Task Management',
    },
    {
      key: 'visualization',
      icon: <EyeOutlined />,
      label: 'Data Visualization',
    },
    {
      key: 'config',
      icon: <SettingOutlined />,
      label: 'Configuration',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(buildPathWithToken(`/${key}`));
  };

  const getSelectedKey = () => {
    const path = location.pathname;
    if (path === '/' || path === '/dashboard') return 'dashboard';
    if (path === '/agent') return 'agent';
    if (path === '/segmentation') return 'segmentation';
    if (path === '/pipeline') return 'pipeline';
    if (path === '/visualization') return 'visualization';
    if (path === '/config') return 'config';
    return 'dashboard';
  };

  return (
    <Layout className="h-screen">
      <Header className="flex justify-between items-center px-6 bg-white shadow-sm flex-shrink-0">
        <div className="text-xl font-bold text-gray-800">
          PrimateX
        </div>
      </Header>
      <Layout className="flex-1">
        <Sider width={250} className="bg-white border-r flex-shrink-0">
          <div className="p-4 h-full overflow-y-auto">
            {/* Navigation Menu */}
            <Menu
              mode="inline"
              selectedKeys={[getSelectedKey()]}
              items={menuItems}
              onClick={handleMenuClick}
              className="border-0"
            />
          </div>
        </Sider>
        <Layout className="flex-1">
          <Content className="h-full flex flex-col relative">
            <div className="flex-1 h-full relative" style={{ minHeight: 0 }}>
              {children}
            </div>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
