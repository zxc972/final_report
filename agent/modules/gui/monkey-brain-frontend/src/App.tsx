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


import { useEffect, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { message } from 'antd';
import MainLayout from './components/Layout/MainLayout';
import DashboardPage from './pages/DashboardPage';
import ConfigPage from './pages/ConfigPage';
import SegmentationPage from './pages/SegmentationPage';
import VisualizationPage from './pages/VisualizationPage';
import AgentPage from './pages/AgentPage';
import PipelinePage from './pages/PipelinePage';
import { getTokenFromUrl, setAccessToken } from './services/accessToken';
import { USER_SESSION_EXPIRED_EVENT, useConfigStore } from './stores/configStore';



function App() {
  const location = useLocation();
  const [token, setToken] = useState<string | null>(
    () => getTokenFromUrl(window.location.search)
  );
  const [tokenInput, setTokenInput] = useState('');
  const { loadConfig } = useConfigStore();

  useEffect(() => {
    const accessToken = getTokenFromUrl(location.search);
    setAccessToken(accessToken);
    setToken(accessToken);
  }, [location.search]);

  useEffect(() => {
    if (token) {
      loadConfig();
    }
  }, [token, loadConfig]);

  useEffect(() => {
    const handleUserSessionExpired = (event: Event) => {
      const detail = (event as CustomEvent<{ message?: string }>).detail;
      message.warning({
        key: 'user-session-expired',
        content: detail?.message || 'Your User ID verification has expired. Please enter your password again on the Configuration page.',
        duration: 6,
      });
    };
    window.addEventListener(USER_SESSION_EXPIRED_EVENT, handleUserSessionExpired);
    return () => window.removeEventListener(USER_SESSION_EXPIRED_EVENT, handleUserSessionExpired);
  }, []);

  const handleTokenSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = tokenInput.trim();
    if (!trimmed) return;
    const url = new URL(window.location.href);
    url.searchParams.set('token', trimmed);
    window.history.replaceState({}, '', url.toString());
    setAccessToken(trimmed);
    setToken(trimmed);
  };

  if (!token) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-50">
        <div className="max-w-xl text-center bg-white border border-slate-200 rounded-2xl p-10 shadow-sm">
          <div className="px-brand-mark" style={{ width: 40, height: 40, fontSize: 15, margin: '0 auto 16px' }}>PX</div>
          <h1 className="text-2xl font-semibold text-slate-800 mb-3">
            Access token required
          </h1>
          <p className="text-slate-600 mb-6">
            This UI is gated by a one-time token. Launch the stack and open the URL that includes
            <code className="mx-1 px-2 py-1 bg-slate-100 rounded">?token=...</code>.
          </p>
          <form onSubmit={handleTokenSubmit} className="mb-6">
            <div className="flex flex-col gap-3">
              <input
                type="password"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="Enter access token"
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
              <button
                type="submit"
                className="w-full rounded-lg px-4 py-2 text-white font-medium border-0 cursor-pointer" style={{ background: 'var(--px-primary)' }}
              >
                Unlock
              </button>
            </div>
          </form>
          <div className="text-left bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-600">
            Example:
            <div className="mt-2 font-mono text-slate-800">
              http://localhost:5173/?token=YOUR_TOKEN
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/config" element={<ConfigPage />} />
        <Route path="/segmentation" element={<SegmentationPage />} />
        <Route path="/visualization" element={<VisualizationPage />} />
        <Route path="/agent" element={<AgentPage />} />
      </Routes>
    </MainLayout>
  );
}

export default App;
