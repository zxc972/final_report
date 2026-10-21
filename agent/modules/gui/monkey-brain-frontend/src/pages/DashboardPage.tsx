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
import { Button, Empty } from 'antd';
import {
  MessageOutlined,
  NodeIndexOutlined,
  EyeOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { buildPathWithToken } from '../services/accessToken';
import { agentService } from '../services/agentService';
import { useConfigStore } from '../stores/configStore';
import { usePipelineStore } from '../stores/pipelineStore';
import { PageContainer, PageHeader } from '../components/Layout/Page';
import { PipelineTask } from '../types/pipeline';

const DEMO_VIDEO_URL = 'https://youtu.be/GWcAMWuRSlk';

const STATUS_CLASS: Record<PipelineTask['status'], string> = {
  pending: '',
  running: 'is-run',
  completed: 'is-ok',
  failed: 'is-err',
  cancelled: 'is-warn',
};

const relativeTime = (iso?: string): string => {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!Number.isFinite(diff)) return '';
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
};

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { config } = useConfigStore();
  const tasks = usePipelineStore((state) => state.tasks);
  const [modelName, setModelName] = useState(() => agentService.getModel());

  useEffect(() => {
    const id = setInterval(() => setModelName(agentService.getModel()), 3000);
    return () => clearInterval(id);
  }, []);

  const go = (path: string) => navigate(buildPathWithToken(path));
  const recent = [...tasks]
    .sort((a, b) => (b.updatedAt || b.createdAt).localeCompare(a.updatedAt || a.createdAt))
    .slice(0, 6);

  const features = [
    {
      key: 'agent',
      icon: <MessageOutlined />,
      title: 'Assistant',
      text: 'Ask in natural language to preprocess scans or analyse existing reconstructions. Every step is shown as it runs.',
    },
    {
      key: 'pipeline',
      icon: <NodeIndexOutlined />,
      title: 'Pipeline',
      text: 'Choose steps and parameters for skull stripping, segmentation and cortical surface reconstruction.',
    },
    {
      key: 'visualization',
      icon: <EyeOutlined />,
      title: 'Visualization',
      text: 'Browse outputs, overlay segmentations and inspect cortical surfaces.',
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Overview"
        description="Preprocess primate T1 scans and run knowledge-guided morphometry analyses."
        actions={(
          <>
            <Button icon={<PlayCircleOutlined />} href={DEMO_VIDEO_URL} target="_blank" rel="noopener noreferrer">
              Watch demo
            </Button>
            <Button type="primary" onClick={() => go('/agent')}>Open assistant</Button>
          </>
        )}
      />

      <div className="px-status-strip" aria-label="Setup status">
        <div>
          <div className="px-status-label">User ID</div>
          <div className="px-status-value">
            <span className={`px-dot ${config?.userId ? 'is-ok' : 'is-err'}`} />
            {config?.userId || <Button type="link" size="small" style={{ padding: 0 }} onClick={() => go('/config')}>Set in Settings</Button>}
          </div>
        </div>
        <div>
          <div className="px-status-label">Workspace</div>
          <div className="px-status-value px-mono" title={config?.workspaceDirectory || ''}>
            {config?.workspaceDirectory || <Button type="link" size="small" style={{ padding: 0 }} onClick={() => go('/config')}>Set in Settings</Button>}
          </div>
        </div>
        <div>
          <div className="px-status-label">Model</div>
          <div className="px-status-value">
            <span className={`px-dot ${modelName ? 'is-ok' : 'is-err'}`} />
            {modelName || <Button type="link" size="small" style={{ padding: 0 }} onClick={() => go('/config')}>Choose in Settings</Button>}
          </div>
        </div>
      </div>

      <div className="px-grid-3">
        {features.map((feature) => (
          <button key={feature.key} type="button" className="px-card px-card-action" onClick={() => go(`/${feature.key}`)}>
            <div className="px-card-icon">{feature.icon}</div>
            <h3>{feature.title}</h3>
            <p>{feature.text}</p>
          </button>
        ))}
      </div>

      <div className="px-section-title">Recent pipeline tasks</div>
      {recent.length === 0 ? (
        <div className="px-card">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No tasks submitted from this browser yet." />
        </div>
      ) : (
        <div className="px-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="px-table">
            <thead>
              <tr><th>Subject</th><th>Species</th><th>Steps</th><th>Status</th><th>Updated</th></tr>
            </thead>
            <tbody>
              {recent.map((task) => (
                <tr key={task.taskId} onClick={() => go('/segmentation')} style={{ cursor: 'pointer' }}>
                  <td className="px-mono">{task.subjectId}</td>
                  <td>{task.species}</td>
                  <td className="px-secondary">{task.steps.join(' → ')}</td>
                  <td><span className={`px-tag ${STATUS_CLASS[task.status] ?? ''}`}>{task.status}</span></td>
                  <td className="px-muted">{relativeTime(task.updatedAt || task.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageContainer>
  );
};

export default DashboardPage;
