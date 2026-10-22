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
import { Tooltip } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppstoreOutlined,
  MessageOutlined,
  NodeIndexOutlined,
  UnorderedListOutlined,
  EyeOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { buildPathWithToken } from '../../services/accessToken';
import { agentService } from '../../services/agentService';
import { useConfigStore } from '../../stores/configStore';
import { useAgentStore } from '../../stores/agentStore';

interface MainLayoutProps {
  children: React.ReactNode;
}

interface NavItem {
  key: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: 'Workspace',
    items: [
      { key: 'dashboard', label: 'Overview', icon: <AppstoreOutlined /> },
      { key: 'agent', label: 'Assistant', icon: <MessageOutlined /> },
    ],
  },
  {
    label: 'Processing',
    items: [
      { key: 'pipeline', label: 'Pipeline', icon: <NodeIndexOutlined /> },
      { key: 'segmentation', label: 'Tasks', icon: <UnorderedListOutlined /> },
    ],
  },
  {
    label: 'Results',
    items: [{ key: 'visualization', label: 'Visualization', icon: <EyeOutlined /> }],
  },
];

const COLLAPSE_KEY = 'px_sidebar_collapsed';

const readCollapsed = (): boolean => {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
};

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { config } = useConfigStore();
  const isConnected = useAgentStore((state) => state.isConnected);
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);
  const [modelName, setModelName] = useState<string>(() => agentService.getModel());

  // The model is configured on the Settings page and stored in agentService,
  // which is not reactive; refresh the label periodically.
  useEffect(() => {
    const id = setInterval(() => setModelName(agentService.getModel()), 3000);
    return () => clearInterval(id);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      const next = !value;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
      } catch {
        // Ignore unavailable storage; the toggle still works for this session.
      }
      return next;
    });
  };

  const selectedKey = (() => {
    const path = location.pathname;
    if (path === '/' || path === '/dashboard') return 'dashboard';
    return path.replace(/^\//, '').split('/')[0] || 'dashboard';
  })();

  const go = (key: string) => navigate(buildPathWithToken(`/${key}`));

  const renderItem = (item: NavItem) => {
    const button = (
      <button
        key={item.key}
        type="button"
        className={`px-nav-item${selectedKey === item.key ? ' is-active' : ''}`}
        onClick={() => go(item.key)}
        aria-current={selectedKey === item.key ? 'page' : undefined}
      >
        {item.icon}
        <span className="px-nav-text">{item.label}</span>
      </button>
    );
    return collapsed ? (
      <Tooltip key={item.key} title={item.label} placement="right">
        {button}
      </Tooltip>
    ) : (
      button
    );
  };

  const messages = useAgentStore((state) => state.messages);
  const hasHistory = messages.some((entry) => entry.type === 'agent');
  const recordedModels = [...messages].reverse().find((entry) => entry.type === 'agent')?.metadata?.usedModels;
  const displayedModel = selectedKey === 'agent' && hasHistory
    ? (recordedModels?.length ? recordedModels.join(', ') : 'not recorded') : modelName;
  const agentReady = isConnected && !!modelName;

  return (
    <div className={`px-shell${collapsed ? ' is-collapsed' : ''}`}>
      <aside className="px-side" aria-label="Main navigation">
        <div className="px-brand">
          <div className="px-brand-mark">PX</div>
          <div className="px-brand-text">
            <div className="px-brand-name">PrimateX</div>
            <div className="px-brand-sub">Structural MRI workspace</div>
          </div>
        </div>

        <nav>
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="px-nav-label">{group.label}</div>
              {group.items.map(renderItem)}
            </div>
          ))}
        </nav>

        <div className="px-side-spacer" />

        {renderItem({ key: 'config', label: 'Settings', icon: <SettingOutlined /> })}
        <button
          type="button"
          className="px-nav-item"
          onClick={toggleCollapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          <span className="px-nav-text">Collapse</span>
        </button>

        <div className="px-account" aria-label="Session status">
          <div className="px-account-row">
            <span>User</span>
            <b title={config?.userId || ''}>{config?.userId || 'not set'}</b>
          </div>
          <div className="px-account-row">
            <span>Model</span>
            <b title={displayedModel}>{displayedModel || 'not set'}</b>
          </div>
          <div className="px-account-row">
            <span>Assistant</span>
            <span style={{ color: 'var(--px-text)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span className={`px-dot ${agentReady ? 'is-ok' : 'is-err'}`} />
              {agentReady ? 'Ready' : 'Not ready'}
            </span>
          </div>
        </div>
      </aside>

      <main className="px-main">{children}</main>
    </div>
  );
};

export default MainLayout;
