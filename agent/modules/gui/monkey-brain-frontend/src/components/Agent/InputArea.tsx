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

import React, { useState, useRef, useEffect } from 'react';
import { Button, Input, Modal, Upload, Select, message } from 'antd';
import { SendOutlined, PaperClipOutlined, LoadingOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useAgentStore } from '../../stores/agentStore';
import { agentService, AgentMode } from '../../services/agentService';
import { useConfigStore } from '../../stores/configStore';
import { pipelineService } from '../../services/pipelineService';
import {
  SAFE_SUBJECT_ID_HELP,
  isSafeSubjectId,
  makeSafeIdFromFilename,
} from '../../utils/idValidation';

const { TextArea } = Input;

interface InputAreaProps {
  disabled?: boolean;
}

const InputArea: React.FC<InputAreaProps> = ({ disabled = false }) => {
  const [inputValue, setInputValue] = useState('');
  const [agentMode, setAgentMode] = useState<AgentMode>(() => agentService.getMode?.() ?? 'pipeline');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingUploadFile, setPendingUploadFile] = useState<File | null>(null);
  const [uploadSubjectId, setUploadSubjectId] = useState('');
  const [isUploadConfirmOpen, setIsUploadConfirmOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const { addMessage, updateStreamingMessage, setStreamingMessageId, isLoading, isConnected } = useAgentStore();
  const { config, userToken } = useConfigStore();
  const textAreaRef = useRef<any>(null);

  // Focus input area on mount
  useEffect(() => {
    if (textAreaRef.current) {
      textAreaRef.current.focus();
    }
  }, []);

  const handleSubmit = async (overrideText?: string) => {
    const trimmedInput = (overrideText ?? inputValue).trim();
    if (!trimmedInput || isSubmitting || !isConnected) {
      return;
    }

    try {
      setIsSubmitting(true);
      
      // Add user message to chat
      addMessage({
        type: 'user',
        content: trimmedInput,
      });

      // Clear input immediately for better UX (only if this came from the text box itself)
      if (overrideText === undefined) setInputValue('');

      // Create streaming message placeholder
      const streamingMessage = {
        type: 'agent' as const,
        content: 'Thinking...',
      };
      
      addMessage(streamingMessage);
      
      // Get the last message ID (the one we just added)
      const messages = useAgentStore.getState().messages;
      const lastMessage = messages[messages.length - 1];
      const messageId = lastMessage.id;
      
      setStreamingMessageId(messageId);

      // Send message to agent service with streaming callback
      const effectiveWorkspace = config?.workspaceDirectory && config?.userId
        ? `${config.workspaceDirectory.replace(/\/$/, '')}/${config.userId}/output`
        : config?.workspaceDirectory;
      const response = await agentService.sendMessage(trimmedInput, {
        workspaceDirectory: effectiveWorkspace,
        userId: config?.userId,
        userToken: userToken || undefined,
        modelDir: config?.modelDir,
        description: config?.description,
        maxConcurrentTasks: config?.maxConcurrentTasks,
        threads: config?.processingOptions?.threads ?? 2,
      }, (streamContent) => {
        // Update the streaming message content in real-time
        updateStreamingMessage(messageId, streamContent);
      });
      
      // Final update with complete response and metadata
      updateStreamingMessage(messageId, response.message);

      // Update with metadata if available
      if (response.metadata?.actions || response.metadata?.analysis) {
        const state = useAgentStore.getState();
        const updatedMessages = state.messages.map(msg =>
          msg.id === messageId
            ? { ...msg, content: response.message, metadata: { actions: response.metadata?.actions || [], analysis: response.metadata?.analysis } }
            : msg
        );
        useAgentStore.setState({ messages: updatedMessages });
      }

      // Only hint when a pipeline task was actually submitted (run_pipeline returns a taskId)
      const pipelineSubmitted = Array.isArray(response.metadata?.tools) &&
        (response.metadata.tools as any[]).some((t) => t?.taskId);
      if (pipelineSubmitted) {
        addMessage({
          type: 'system',
          content: 'Pipeline task submitted. Once processing is complete, go to **Data Visualization** to view the results.',
        });
      }

    } catch (error: any) {
      console.error('Failed to send message:', error);
      const errMsg = error?.message || 'Failed to send message, please try again';
      message.error(errMsg);

      // Add error message to chat
      addMessage({
        type: 'system',
        content: `Sorry, the message failed to send: ${errMsg}`,
      });
    } finally {
      setIsSubmitting(false);
      setStreamingMessageId(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileSelected = (file: File) => {
    if (!config?.userId) {
      message.warning('Please set your User ID in Configuration first');
      return false;
    }
    if (!config.workspaceDirectory) {
      message.warning('Please set the Workspace Directory in Configuration first');
      return false;
    }

    setPendingUploadFile(file);
    setUploadSubjectId(makeSafeIdFromFilename(file.name));
    setIsUploadConfirmOpen(true);
    return false;
  };

  const handleUploadCancel = () => {
    if (isUploading) return;
    setIsUploadConfirmOpen(false);
    setPendingUploadFile(null);
    setUploadSubjectId('');
  };

  const handleFileUpload = async () => {
    const file = pendingUploadFile;
    const subjectId = uploadSubjectId.trim();
    const userId = config?.userId;
    const workspaceDir = config?.workspaceDirectory;

    if (!file || !userId || !workspaceDir) {
      message.error('Upload information is incomplete. Please select the file again.');
      handleUploadCancel();
      return;
    }
    if (!isSafeSubjectId(subjectId)) {
      message.warning(SAFE_SUBJECT_ID_HELP);
      return;
    }

    setIsUploading(true);
    message.loading({ content: `Uploading ${file.name}…`, key: 'upload', duration: 0 });
    try {
      const result = await pipelineService.uploadFile(
        file,
        userId,
        subjectId,
        workspaceDir,
        () => {}, // no progress bar in chat - just loading indicator
      );
      const confirmedSubjectId = result.subjectId || subjectId;
      message.success({ content: `Uploaded → ${result.savedPath}`, key: 'upload' });
      // Append a system message to chat showing where the file was saved
      addMessage({
        type: 'system',
        content: `File uploaded: \`${file.name}\`\nSubject ID: \`${confirmedSubjectId}\`\nSaved to: \`${result.inputDir}\`\nT1 path for pipeline: \`${result.savedPath}\``,
      });
      agentService.setRecentUpload({
        fileName: file.name,
        subjectId: confirmedSubjectId,
        t1Path: result.savedPath,
        inputDir: result.inputDir,
        userId,
      });
      setIsUploadConfirmOpen(false);
      setPendingUploadFile(null);
      setUploadSubjectId('');
    } catch (error: any) {
      message.error({ content: `Upload failed: ${error.message}`, key: 'upload' });
    } finally {
      setIsUploading(false);
    }
  };

  const isDisabled = disabled || !isConnected || isLoading || isSubmitting || isUploading;
  const normalizedUploadSubjectId = uploadSubjectId.trim();
  const uploadSubjectIdIsValid = isSafeSubjectId(normalizedUploadSubjectId);
  const uploadDestination = config?.workspaceDirectory && config?.userId && normalizedUploadSubjectId
    ? `${config.workspaceDirectory.replace(/\/$/, '')}/${config.userId}/input/${normalizedUploadSubjectId}/T1`
    : '';

  return (
    <div className="p-4">
      <div className="flex items-end space-x-2">
        {/* File upload button */}
        <Upload
          beforeUpload={handleFileSelected}
          showUploadList={false}
          accept=".nii,.nii.gz,.gz,.dcm,application/gzip,application/x-gzip,application/octet-stream"
        >
          <Button
            icon={<PaperClipOutlined />}
            disabled={isDisabled}
            className="flex-shrink-0"
            title="Upload MRI file"
          />
        </Upload>

        <Select<AgentMode>
          aria-label="Agent mode"
          value={agentMode}
          disabled={isDisabled}
          style={{ width: 155 }}
          options={[{ value: 'pipeline', label: 'Preprocessing' }, { value: 'analysis', label: 'Coding analysis' }]}
          onChange={(mode) => { agentService.setMode(mode); setAgentMode(mode); }}
        />

        {/* Use sample data button */}
        <Button
          icon={<ExperimentOutlined />}
          disabled={isDisabled}
          className="flex-shrink-0"
          title="Use sample data (preprocessing mode)"
          onClick={() => { agentService.setMode('pipeline'); setAgentMode('pipeline'); void handleSubmit(
            "I don't have my own data yet — please show me the available official sample subjects, " +
            'and help me copy one into my own workspace so I can try the pipeline.'
          ); }}
        />

        {/* Text input area */}
        <div className="flex-1">
          <TextArea
            ref={textAreaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled
                ? "Please configure a model first..."
                : !isConnected
                ? "Connecting..." 
                : "Enter your question or command... (Shift+Enter for newline, Enter to send)"
            }
            disabled={isDisabled}
            autoSize={{ minRows: 1, maxRows: 4 }}
            className="resize-none"
          />
        </div>

        {/* Send button */}
        <Button
          type="primary"
          icon={isSubmitting ? <LoadingOutlined /> : <SendOutlined />}
          onClick={() => handleSubmit()}
          disabled={isDisabled || !inputValue.trim()}
          className="flex-shrink-0 bg-gradient-to-r from-blue-500 to-purple-600 border-none hover:from-blue-600 hover:to-purple-700 shadow-lg"
          loading={isSubmitting}
          size="large"
        >
          Send
        </Button>
      </div>

      {/* Status hints */}
      {disabled ? (
        <div className="text-xs text-gray-500 mt-2 text-center">
          Please configure a model above first
        </div>
      ) : !isConnected ? (
        <div className="text-xs text-gray-500 mt-2 text-center">
          Connecting to server...
        </div>
      ) : null}
      
      {/* Input hints */}
      <div className="text-xs text-gray-400 mt-2">
        Supported file formats: .nii, .nii.gz, .dcm | 
        Shortcuts: Enter to send, Shift+Enter for newline
      </div>

      <Modal
        title="Confirm subject ID"
        open={isUploadConfirmOpen}
        onOk={handleFileUpload}
        onCancel={handleUploadCancel}
        okText="Confirm and upload"
        cancelText="Cancel"
        confirmLoading={isUploading}
        okButtonProps={{ disabled: !uploadSubjectIdIsValid }}
        cancelButtonProps={{ disabled: isUploading }}
        closable={!isUploading}
        maskClosable={!isUploading}
        keyboard={!isUploading}
      >
        <div className="space-y-4">
          <div>
            <div className="text-sm font-medium text-gray-700 mb-1">Selected file</div>
            <div className="font-mono text-sm break-all rounded bg-gray-50 p-2">
              {pendingUploadFile?.name}
            </div>
          </div>

          <div>
            <label htmlFor="agent-upload-subject-id" className="block text-sm font-medium text-gray-700 mb-1">
              Subject ID
            </label>
            <Input
              id="agent-upload-subject-id"
              value={uploadSubjectId}
              onChange={(event) => setUploadSubjectId(event.target.value)}
              onPressEnter={() => {
                if (uploadSubjectIdIsValid && !isUploading) void handleFileUpload();
              }}
              status={normalizedUploadSubjectId && !uploadSubjectIdIsValid ? 'error' : undefined}
              disabled={isUploading}
              autoFocus
            />
            <div className={`text-xs mt-1 ${normalizedUploadSubjectId && !uploadSubjectIdIsValid ? 'text-red-500' : 'text-gray-500'}`}>
              Verify that this identifies the subject, not the scan or protocol name. {SAFE_SUBJECT_ID_HELP}
            </div>
          </div>

          <div>
            <div className="text-sm font-medium text-gray-700 mb-1">Upload destination</div>
            <div className="font-mono text-xs break-all rounded bg-blue-50 text-blue-700 p-2">
              {uploadDestination || 'Enter a valid Subject ID to preview the destination.'}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default InputArea;
