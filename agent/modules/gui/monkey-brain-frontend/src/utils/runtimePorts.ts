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

interface RuntimePorts {
  pipelinePort?: string;
  agentPort?: string;
  frontendPort?: string;
  pipelineBaseUrl?: string;
  agentBaseUrl?: string;
  sameOriginApi?: boolean;
}

let runtimePortsPromise: Promise<RuntimePorts> | null = null;

const loadRuntimePorts = async (): Promise<RuntimePorts> => {
  if (!runtimePortsPromise) {
    runtimePortsPromise = fetch('/ports.json', { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : {}))
      .catch(() => ({}));
  }
  return runtimePortsPromise;
};

const buildBaseUrl = (port: string) => {
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
};

const normalizeBaseUrl = (url?: string) => {
  return url ? url.replace(/\/$/, '') : '';
};

export const resolvePipelineBaseUrl = async (): Promise<string> => {
  const envUrl = normalizeBaseUrl(import.meta.env.VITE_PIPELINE_API);
  if (envUrl) return envUrl;
  const ports = await loadRuntimePorts();
  const runtimeUrl = normalizeBaseUrl(ports.pipelineBaseUrl);
  if (runtimeUrl) return runtimeUrl;
  if (ports.sameOriginApi) return window.location.origin;
  const envPort = import.meta.env.VITE_PIPELINE_PORT;
  const port = envPort || ports.pipelinePort;
  if (!port) return window.location.origin;
  return buildBaseUrl(port);
};

export const resolveAgentBaseUrl = async (): Promise<string> => {
  const envUrl = normalizeBaseUrl(import.meta.env.VITE_AGENT_BACKEND_URL);
  if (envUrl) return envUrl;
  const ports = await loadRuntimePorts();
  const runtimeUrl = normalizeBaseUrl(ports.agentBaseUrl);
  if (runtimeUrl) return runtimeUrl;
  if (ports.sameOriginApi) return window.location.origin;
  const envPort = import.meta.env.VITE_AGENT_BACKEND_PORT;
  const port = envPort || ports.agentPort;
  if (!port) return window.location.origin;
  return buildBaseUrl(port);
};
