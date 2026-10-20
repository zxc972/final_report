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

import React, { useState, useEffect } from 'react';
import {
  Form,
  Input,
  InputNumber,
  Button,
  Card,
  Space,
  message,
  Divider,
  Typography,
  Alert,
  Modal,
  Select,
} from 'antd';
import {
  SettingOutlined,
  SaveOutlined,
  ReloadOutlined,
  LockOutlined,
  CheckCircleFilled,
  LogoutOutlined,
} from '@ant-design/icons';
import { isUserTokenExpired, normalizeWorkspaceDirectory, useConfigStore } from '../../stores/configStore';
import { SAFE_ID_HELP, isSafeId, safeIdRule } from '../../utils/idValidation';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface ParameterFormData {
  userId: string;
  workspaceDirectory: string;
  modelDir: string;
  maxConcurrentTasks: number;
  processingOptions: {
    enablePreprocessing: boolean;
    qualityLevel: string;
    threads: number;
  };
  description?: string;
}

const ParameterForm: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [loadingDefaultWorkspace, setLoadingDefaultWorkspace] = useState(false);
  const {
    config,
    updateConfig,
    saveConfig,
    loadConfig,
    resetConfig,
    defaultWorkspace,
    userToken,
    verifiedUserId,
    verifiedWorkspaceDirectory,
    clearUserSession,
    checkUserIdExists,
    verifyUserId,
    changePassword,
  } = useConfigStore();
  const [idExists, setIdExists] = useState<boolean | null>(null);
  const [checkingId, setCheckingId] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordForm] = Form.useForm();
  const userId = Form.useWatch('userId', form);
  const workspaceDirectory = Form.useWatch('workspaceDirectory', form);
  const effectiveUserId = userId ?? config?.userId ?? '';
  const effectiveWorkspaceDirectory = workspaceDirectory ?? config?.workspaceDirectory ?? defaultWorkspace ?? '';
  const tokenExpired = userToken ? isUserTokenExpired(userToken) : false;
  const workspaceMatches =
    !verifiedWorkspaceDirectory ||
    !effectiveWorkspaceDirectory ||
    normalizeWorkspaceDirectory(effectiveWorkspaceDirectory) === normalizeWorkspaceDirectory(verifiedWorkspaceDirectory);
  const needsVerification =
    !userToken ||
    tokenExpired ||
    effectiveUserId !== verifiedUserId ||
    !workspaceMatches;

  const applyDefaultWorkspace = async () => {
    let nextDefaultWorkspace = defaultWorkspace;
    if (!nextDefaultWorkspace) {
      setLoadingDefaultWorkspace(true);
      try {
        await loadConfig();
        nextDefaultWorkspace = useConfigStore.getState().defaultWorkspace;
      } finally {
        setLoadingDefaultWorkspace(false);
      }
    }
    if (!nextDefaultWorkspace) {
      message.warning('Could not load the default Workspace Directory from the backend. Please check that the pipeline backend is running and reachable.');
      return;
    }
    form.setFields([
      {
        name: 'workspaceDirectory',
        value: nextDefaultWorkspace,
        errors: [],
      },
    ]);
    message.info('Workspace Directory reset to the default path detected by the backend.');
  };

  // Fetch default workspace from backend on first load
  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    if (userToken && tokenExpired) {
      clearUserSession();
      message.warning('Your User ID verification has expired. Please enter your password again.');
    }
  }, [userToken, tokenExpired, clearUserSession]);

  useEffect(() => {
    // Initialize form with stored config
    if (config) {
      form.setFieldsValue({
        userId: config.userId,
        workspaceDirectory: config.workspaceDirectory || defaultWorkspace || '',
        modelDir: config.modelDir,
        maxConcurrentTasks: config.maxConcurrentTasks,
        enablePreprocessing: config.processingOptions?.enablePreprocessing,
        qualityLevel: config.processingOptions?.qualityLevel,
        threads: config.processingOptions?.threads ?? 2,
        description: config.description,
      });
    }
  }, [config, defaultWorkspace, form]);

  useEffect(() => {
    const currentWorkspace = form.getFieldValue('workspaceDirectory');
    if (!currentWorkspace && defaultWorkspace) {
      form.setFieldsValue({ workspaceDirectory: defaultWorkspace });
    }
  }, [defaultWorkspace, form]);

  // Debounced check of whether the typed User ID has already been claimed,
  // so the password field can show the right hint ("set a password" vs "enter it").
  useEffect(() => {
    if (!userId || !needsVerification || !isSafeId(userId)) {
      setIdExists(null);
      return;
    }
    setCheckingId(true);
    const timer = setTimeout(() => {
      checkUserIdExists(userId, workspaceDirectory || defaultWorkspace || '')
        .then(setIdExists)
        .catch(() => setIdExists(null))
        .finally(() => setCheckingId(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [userId, workspaceDirectory, needsVerification, defaultWorkspace, checkUserIdExists]);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    try {
      const submitWorkspace = values.workspaceDirectory || defaultWorkspace || '';
      if (!submitWorkspace) {
        message.error('Workspace Directory is empty. Please enter an absolute path on the backend machine or use the default path.');
        return;
      }
      const submitWorkspaceMatches =
        !verifiedWorkspaceDirectory ||
        normalizeWorkspaceDirectory(submitWorkspace) === normalizeWorkspaceDirectory(verifiedWorkspaceDirectory);
      const submitNeedsVerification =
        !userToken ||
        isUserTokenExpired(userToken) ||
        values.userId !== verifiedUserId ||
        !submitWorkspaceMatches;

      if (!values.userId || submitNeedsVerification) {
        if (!values.password) {
          message.error(
            idExists
              ? 'This User ID already exists. Please enter its password to verify it is yours.'
              : 'Please set a password to protect this User ID.'
          );
          return;
        }
        try {
          const { claimed } = await verifyUserId(
            values.userId,
            values.password,
            submitWorkspace
          );
          message.success(claimed ? `User ID "${values.userId}" claimed.` : 'User ID verified.');
        } catch (error: any) {
          const errorMessage = error.message || 'Unable to verify this User ID. Please check the Workspace Directory and password, then try again.';
          const guidedErrorMessage = defaultWorkspace && /workspace directory|workspace path|backend machine|absolute path|writable/i.test(errorMessage)
            ? `${errorMessage} Click "Use server default" to restore the recommended path.`
            : errorMessage;
          if (/workspace directory|workspace path|backend machine|absolute path|writable/i.test(errorMessage)) {
            form.setFields([
              {
                name: 'workspaceDirectory',
                errors: [guidedErrorMessage],
              },
            ]);
          }
          message.error(guidedErrorMessage);
          return;
        }
      }

      const formData: ParameterFormData = {
        userId: values.userId || '',
        workspaceDirectory: submitWorkspace,
        modelDir: values.modelDir || '',
        maxConcurrentTasks: Number(values.maxConcurrentTasks || 12),
        processingOptions: {
          enablePreprocessing: values.enablePreprocessing || false,
          qualityLevel: config?.processingOptions?.qualityLevel || 'standard',
          threads: Number(values.threads ?? 2),
        },
        description: values.description,
      };

      await updateConfig({
        ...formData,
        processingOptions: {
          ...formData.processingOptions,
          qualityLevel: formData.processingOptions.qualityLevel as 'high' | 'fast' | 'standard',
        },
      });
      await saveConfig();
      message.success('Configuration saved');
    } catch (error: any) {
      message.error(`Save failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    resetConfig();
    form.setFieldsValue({
      userId: '',
      workspaceDirectory: defaultWorkspace || '',
      modelDir: '',
      maxConcurrentTasks: 12,
      enablePreprocessing: true,
      qualityLevel: 'standard',
      threads: 2,
      description: undefined,
      password: undefined,
    });
    setIdExists(null);
    message.info('Configuration reset and User ID signed out');
  };

  const handleSignOut = () => {
    clearUserSession();
    form.setFieldsValue({ password: undefined });
    message.info('Signed out. Please enter the password to verify this User ID again.');
  };

  const handleChangePassword = async (values: { currentPassword: string; newPassword: string }) => {
    if (!verifiedUserId) return;
    setChangingPassword(true);
    try {
      await changePassword(
        verifiedUserId,
        values.currentPassword,
        values.newPassword,
        workspaceDirectory || defaultWorkspace || ''
      );
      message.success('Password changed. Any other sessions using the old password are now signed out.');
      setPasswordModalOpen(false);
      passwordForm.resetFields();
    } catch (error: any) {
      message.error(error.message || 'Failed to change password');
    } finally {
      setChangingPassword(false);
    }
  };

  const validateWorkspaceDirectory = (_: any, value: string) => {
    const effectiveValue = value || defaultWorkspace || '';
    if (!effectiveValue) {
      return Promise.reject(new Error('Workspace Directory is empty. Please enter an absolute path on the backend machine or use the default path.'));
    }
    if (!effectiveValue.startsWith('/')) {
      return Promise.reject(new Error(defaultWorkspace
        ? `Workspace directory must be an absolute path on the backend machine. You can use the default path: ${defaultWorkspace}`
        : 'Workspace directory must be an absolute path'));
    }
    return Promise.resolve();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Card
        title={
          <Space>
            <SettingOutlined />
            <Title level={4} className="mb-0">Parameter Configuration</Title>
          </Space>
        }
        extra={
          <Space>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={handleReset}
            >
              Reset
            </Button>
            <Button 
              type="primary" 
              icon={<SaveOutlined />}
              loading={loading}
              onClick={() => form.submit()}
            >
              Save Configuration
            </Button>
          </Space>
        }
      >
        <Alert
          message="Configuration Guide"
          description="These parameters will be automatically provided to the AI Agent to avoid repeatedly asking for basic information."
          type="info"
          showIcon
          className="mb-6"
        />

        {!effectiveWorkspaceDirectory && (
          <Alert
            message="Workspace Directory is empty"
            description="The system could not load the default workspace path from the backend. Please enter an absolute path on the backend machine before saving, typically the repository tests directory."
            type="warning"
            showIcon
            className="mb-6"
          />
        )}

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            modelDir: '',
            maxConcurrentTasks: 12,
            threads: 2,
            enablePreprocessing: true,
          }}
        >
          {/* Basic Settings */}
          <Divider orientation="left" orientationMargin={0}>Basic Settings</Divider>

          <Form.Item
            label="User ID"
            name="userId"
            rules={[
              { required: true, message: 'Please set a User ID' },
              safeIdRule('User ID'),
            ]}
            help={`Your personal namespace — pipeline outputs are stored under workspace/userId/output/. ${SAFE_ID_HELP}`}
          >
            <Input placeholder="e.g. alice01 or lab_01" />
          </Form.Item>

          {needsVerification ? (
            <Form.Item
              label="Password"
              name="password"
              help={
                checkingId
                  ? 'Checking whether this User ID is already taken...'
                  : idExists
                  ? 'This User ID already exists. Enter its password to verify it is yours — otherwise, choose a different ID.'
                  : 'First time using this User ID: set a password to protect it from being used by someone else.'
              }
            >
              <Input.Password
                placeholder={idExists ? 'Enter existing password' : 'Set a password for this User ID'}
                prefix={<LockOutlined />}
              />
            </Form.Item>
          ) : (
            <div className="mb-4 text-sm flex items-center gap-3">
              <span className="text-green-600 flex items-center gap-1">
                <CheckCircleFilled /> Verified as "{verifiedUserId}"
              </span>
              <a onClick={() => setPasswordModalOpen(true)}>Change password</a>
              <Button size="small" icon={<LogoutOutlined />} onClick={handleSignOut}>
                Sign out
              </Button>
            </div>
          )}

          <Form.Item
            label="Workspace Directory"
            name="workspaceDirectory"
            rules={[
              { validator: validateWorkspaceDirectory }
            ]}
            help={
              defaultWorkspace
                ? `Automatically detected by the backend: ${defaultWorkspace}. Most users do not need to edit this. User data will be stored under workspace/User ID/input and workspace/User ID/output.`
                : 'Path on the machine running the PrimateX backend where MRI data files are stored. The default path could not be loaded automatically, so enter the repository tests directory or another absolute workspace path.'
            }
            extra={
              <Text type={defaultWorkspace ? 'secondary' : 'warning'} className="text-xs">
                {defaultWorkspace
                  ? `Recommended path: ${defaultWorkspace}`
                  : 'Default workspace has not loaded yet. Click "Use server default" to retry.'}
              </Text>
            }
          >
            <Input
              placeholder={defaultWorkspace ? `Use server default: ${defaultWorkspace}` : '/data/mri_workspace'}
              addonAfter={
                <Button size="small" type="link" className="px-0" loading={loadingDefaultWorkspace} onClick={applyDefaultWorkspace}>
                  Use server default
                </Button>
              }
            />
          </Form.Item>

          <Form.Item
            label="Segmentation model directory"
            name="modelDir"
            help="Optional override for primx seg models"
          >
            <Input placeholder="Leave empty to use default models in primx" />
          </Form.Item>

          <Form.Item
            label="Max concurrent tasks"
            name="maxConcurrentTasks"
            rules={[
              { type: 'number', min: 1, max: 64, message: 'Max concurrent tasks must be between 1 and 64' }
            ]}
            help="Maximum number of pipeline tasks running in parallel"
          >
            <InputNumber min={1} max={64} placeholder="12" className="w-full" />
          </Form.Item>

          {/* Processing Options */}
          <Divider orientation="left" orientationMargin={0}>Processing Options</Divider>

          <Form.Item
            label="CPU Threads per Task"
            name="threads"
            rules={[
              { required: true, message: 'Please select the number of CPU threads' },
            ]}
            help="Threads used by supported commands in Preprocess-3. Default: 2. More threads may reduce processing time but use more CPU. Maximum: 4. This does not change how many tasks run simultaneously."
          >
            <Select
              options={[1, 2, 3, 4].map((value) => ({
                value,
                label: `${value} thread${value === 1 ? '' : 's'}`,
              }))}
            />
          </Form.Item>

          {/* Other Settings */}
          <Divider orientation="left" orientationMargin={0}>Other Settings</Divider>

          <Form.Item
            label="Configuration Description"
            name="description"
            help="Optional: add a description for this configuration"
          >
            <TextArea 
              rows={3}
              placeholder="For example: standard configuration for monkey brain cortical segmentation..."
            />
          </Form.Item>
        </Form>
      </Card>

      {/* Current Configuration Preview */}
      {config && (
        <Card title="Current Configuration Preview" size="small">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <Text strong>User ID:</Text>
              <div className="text-gray-600">{config.userId || 'Not set'}</div>
            </div>
            <div>
              <Text strong>Workspace Directory:</Text>
              <div className="text-gray-600">{config.workspaceDirectory || 'Not set'}</div>
            </div>
            <div>
              <Text strong>Model Directory:</Text>
              <div className="text-gray-600">{config.modelDir || 'Not set'}</div>
            </div>
            <div>
              <Text strong>Max Concurrent Tasks:</Text>
              <div className="text-gray-600">{config.maxConcurrentTasks || 12}</div>
            </div>
            <div>
              <Text strong>CPU Threads per Task:</Text>
              <div className="text-gray-600">{config.processingOptions?.threads ?? 2}</div>
            </div>
          </div>
        </Card>
      )}

      <Modal
        title="Change password"
        open={passwordModalOpen}
        onCancel={() => { setPasswordModalOpen(false); passwordForm.resetFields(); }}
        onOk={() => passwordForm.submit()}
        okButtonProps={{ loading: changingPassword }}
        okText="Change password"
        cancelText="Cancel"
      >
        <Form form={passwordForm} layout="vertical" onFinish={handleChangePassword}>
          <Form.Item
            label="Current password"
            name="currentPassword"
            rules={[{ required: true, message: 'Please enter your current password' }]}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item
            label="New password"
            name="newPassword"
            rules={[
              { required: true, message: 'Please enter a new password' },
              { min: 4, message: 'Password must be at least 4 characters' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <div className="text-xs text-gray-500">
            Changing your password immediately signs out any other session still using the old one.
          </div>
        </Form>
      </Modal>
    </div>
  );
};

export default ParameterForm;
