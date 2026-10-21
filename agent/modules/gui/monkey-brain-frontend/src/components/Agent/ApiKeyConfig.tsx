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

import React, { useState, useEffect, useMemo } from 'react';
import { Input, Button, Alert, Space, Typography, Select, Segmented, Spin, message } from 'antd';
import { KeyOutlined, SaveOutlined, EyeInvisibleOutlined, EyeTwoTone } from '@ant-design/icons';
import { agentService, Provider, PlatformModel } from '../../services/agentService';

const { Text } = Typography;

interface ApiKeyConfigProps {
  onApiKeySet?: (hasKey: boolean) => void;
}

interface SavedModelConfig {
  provider: Provider;
  model: string;
  baseUrl: string;
  hasApiKey: boolean;
}

const ApiKeyConfig: React.FC<ApiKeyConfigProps> = ({ onApiKeySet }) => {
  const [provider, setProvider] = useState<Provider>('platform');
  const [platformModel, setPlatformModel] = useState('');
  const [platformModels, setPlatformModels] = useState<PlatformModel[]>([]);
  const [platformAvailable, setPlatformAvailable] = useState(true);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [customBaseUrl, setCustomBaseUrl] = useState('');
  const [customModel, setCustomModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConfigured, setIsConfigured] = useState(false);
  const [savedConfig, setSavedConfig] = useState<SavedModelConfig | null>(null);

  useEffect(() => {
    const existingProvider = agentService.getProvider();
    setProvider(existingProvider);
    setApiKey(agentService.getApiKey());
    setCustomBaseUrl(agentService.getBaseUrl());
    if (existingProvider === 'platform') {
      setPlatformModel(agentService.getModel());
    } else {
      setCustomModel(agentService.getModel());
    }
    const configured = agentService.isConfigured();
    setIsConfigured(configured);
    setSavedConfig(configured ? {
      provider: existingProvider,
      model: agentService.getModel(),
      baseUrl: agentService.getBaseUrl(),
      hasApiKey: !!agentService.getApiKey(),
    } : null);
    onApiKeySet?.(configured);
  }, [onApiKeySet]);

  useEffect(() => {
    let cancelled = false;
    setIsLoadingModels(true);
    agentService.getModels()
      .then(({ models, platformAvailable: available }) => {
        if (cancelled) return;
        setPlatformModels(models);
        setPlatformAvailable(available);
      })
      .catch(() => {
        if (!cancelled) setPlatformAvailable(false);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingModels(false);
      });
    return () => { cancelled = true; };
  }, []);

  const handleSave = () => {
    setIsLoading(true);
    try {
      agentService.setProvider(provider);
      if (provider === 'platform') {
        agentService.setModel(platformModel);
      } else {
        agentService.setBaseUrl(customBaseUrl.trim());
        agentService.setModel(customModel.trim());
        agentService.setApiKey(apiKey.trim());
      }
      const configured = agentService.isConfigured();
      setIsConfigured(configured);
      setSavedConfig(configured ? {
        provider,
        model: provider === 'platform' ? platformModel : customModel.trim(),
        baseUrl: provider === 'platform' ? '' : customBaseUrl.trim(),
        hasApiKey: provider === 'custom' ? !!apiKey.trim() : false,
      } : null);
      onApiKeySet?.(configured);
      if (configured) {
        message.success('AI assistant configuration saved.');
      } else {
        message.warning('Please complete the model configuration before saving.');
      }
    } catch (error) {
      console.error('Failed to save model configuration:', error);
      message.error('Failed to save AI assistant configuration.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = () => {
    agentService.disconnect();
    setPlatformModel('');
    setCustomModel('');
    setCustomBaseUrl('');
    setApiKey('');
    setIsConfigured(false);
    setSavedConfig(null);
    onApiKeySet?.(false);
    message.success('AI assistant configuration cleared.');
  };

  const canSave = provider === 'platform'
    ? !!platformModel
    : !!customModel.trim() && !!apiKey.trim();

  const currentFormConfig = useMemo<SavedModelConfig>(() => ({
    provider,
    model: provider === 'platform' ? platformModel : customModel.trim(),
    baseUrl: provider === 'platform' ? '' : customBaseUrl.trim(),
    hasApiKey: provider === 'custom' ? !!apiKey.trim() : false,
  }), [apiKey, customBaseUrl, customModel, platformModel, provider]);

  const hasUnsavedChanges = useMemo(() => {
    if (!savedConfig) return canSave;
    return savedConfig.provider !== currentFormConfig.provider
      || savedConfig.model !== currentFormConfig.model
      || savedConfig.baseUrl !== currentFormConfig.baseUrl
      || savedConfig.hasApiKey !== currentFormConfig.hasApiKey;
  }, [canSave, currentFormConfig, savedConfig]);

  const savedModelLabel = useMemo(() => {
    if (!savedConfig) return '';
    if (savedConfig.provider === 'platform') {
      return platformModels.find((m) => m.id === savedConfig.model)?.label || savedConfig.model;
    }
    return savedConfig.model;
  }, [platformModels, savedConfig]);

  return (
    <div>
      <Space direction="vertical" className="w-full">
        {!isConfigured && (
          <Alert
            message="Model not configured"
            description="Pick a built-in platform model, or enter your own API key, to start using the AI assistant."
            type="warning"
            showIcon
          />
        )}

        <div className="flex items-center gap-3">
          <KeyOutlined className="text-blue-600" />
          <Text strong>Model Source:</Text>
        </div>

        <Segmented
          value={provider}
          onChange={(value) => setProvider(value as Provider)}
          options={[
            { label: 'Platform models', value: 'platform' },
            { label: 'Your own API key', value: 'custom' },
          ]}
          disabled={isLoading}
          block
        />

        {provider === 'platform' ? (
          <>
            {!platformAvailable && (
              <Alert
                message="Platform API not configured"
                description="The server administrator hasn't set up a platform API key yet. Please use your own API key instead."
                type="info"
                showIcon
              />
            )}
            <div className="flex items-center gap-3">
              <Text strong>Model:</Text>
            </div>
            {isLoadingModels ? (
              <Spin size="small" />
            ) : (
              <Select
                value={platformModel || undefined}
                onChange={(value) => setPlatformModel(value)}
                options={platformModels.map((m) => ({ label: m.label, value: m.id }))}
                placeholder="Select a model"
                className="w-full"
                disabled={isLoading || !platformAvailable || platformModels.length === 0}
                notFoundContent={platformModels.length === 0 ? 'No models configured yet' : undefined}
              />
            )}
            <div className="text-xs text-gray-500">
              <Text type="secondary">
                The API key for these models is managed by the server and never leaves it.
              </Text>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <Text strong>API Base URL (optional):</Text>
            </div>
            <Input
              value={customBaseUrl}
              onChange={(e) => setCustomBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              disabled={isLoading}
            />

            <div className="flex items-center gap-3">
              <Text strong>Model name:</Text>
            </div>
            <Input
              value={customModel}
              onChange={(e) => setCustomModel(e.target.value)}
              placeholder="e.g. gpt-4o, deepseek-chat"
              disabled={isLoading}
            />

            <div className="flex items-center gap-3">
              <KeyOutlined className="text-blue-600" />
              <Text strong>API Key:</Text>
            </div>
            <Input.Password
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Please enter your API Key"
              iconRender={(visible) => (visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />)}
              disabled={isLoading}
              onPressEnter={handleSave}
            />
            <div className="text-xs text-gray-500">
              <Text type="secondary">
                Your API key is stored in the local browser and sent to the agent backend only when needed. Any OpenAI-compatible endpoint works (OpenAI, DeepSeek, self-hosted, etc.).
              </Text>
            </div>
          </>
        )}

        <div className="flex gap-2">
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={isLoading}
            disabled={!canSave}
          >
            Save
          </Button>
          {isConfigured && (
            <Button danger onClick={handleClear}>
              Clear
            </Button>
          )}
        </div>

        {hasUnsavedChanges ? (
          <Alert
            message="Unsaved model changes"
            description="Click Save to apply the selected AI assistant model."
            type="warning"
            showIcon
          />
        ) : isConfigured && savedConfig ? (
          <Alert
            message="AI assistant configuration saved"
            description={`Current model: ${savedModelLabel || savedConfig.model}`}
            type="success"
            showIcon
          />
        ) : null}
      </Space>
    </div>
  );
};

export default ApiKeyConfig;
