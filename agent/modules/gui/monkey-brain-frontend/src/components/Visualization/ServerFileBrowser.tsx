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

import React, { useState, useEffect, useCallback } from 'react';
import { Modal, Button, Input, List, Spin, message } from 'antd';
import {
  FolderOutlined,
  FileOutlined,
  ArrowUpOutlined,
  HomeOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import { getResolvedAccessToken } from '../../services/accessToken';
import { resolvePipelineBaseUrl } from '../../utils/runtimePorts';
import { useConfigStore } from '../../stores/configStore';

interface FileItem {
  name: string;
  path: string;
  isDirectory: boolean;
  isNifti: boolean;
}

interface ServerFileBrowserProps {
  visible: boolean;
  onClose: () => void;
  onSelectFolder: (folderPath: string, niftiFiles: FileItem[]) => void;
  onSelectFile: (file: FileItem) => void;
  initialPath?: string;
}

const STORAGE_KEY = 'serverFileBrowser_lastPath';

const ServerFileBrowser: React.FC<ServerFileBrowserProps> = ({
  visible,
  onClose,
  onSelectFolder,
  onSelectFile,
  initialPath = '/data',
}) => {
  const [pipelineApi, setPipelineApi] = useState<string>('');
  const { config } = useConfigStore();

  const getAuthHeaders = useCallback(() => {
    const token = getResolvedAccessToken();
    const userToken = useConfigStore.getState().userToken;
    return {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(userToken ? { 'X-User-Token': userToken } : {}),
    };
  }, []);

  const applyRefreshedUserToken = (response: Response) => {
    const refreshed = response.headers.get('X-User-Token');
    if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
  };

  useEffect(() => {
    resolvePipelineBaseUrl().then(setPipelineApi).catch(() => setPipelineApi(''));
  }, []);
  const getInitialPath = useCallback(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return initialPath;
    const normalizedInitial = initialPath.replace(/\/$/, '');
    return saved === normalizedInitial || saved.startsWith(`${normalizedInitial}/`)
      ? saved
      : initialPath;
  }, [initialPath]);

  const [currentPath, setCurrentPath] = useState(getInitialPath());
  const [items, setItems] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [pathInput, setPathInput] = useState(getInitialPath());
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);

  const loadDirectory = useCallback(async (dirPath: string) => {
    setLoading(true);
    setSelectedFile(null);
    try {
      let baseUrl = pipelineApi;
      if (!baseUrl) {
        try {
          baseUrl = await resolvePipelineBaseUrl();
          setPipelineApi(baseUrl);
        } catch (error) {
          message.error('Pipeline backend is not configured yet. Please retry in a moment.');
          setLoading(false);
          return;
        }
      }
      if (!config?.userId || !config?.workspaceDirectory) {
        message.error('Please verify your User ID in Configuration before browsing server files.');
        setLoading(false);
        return;
      }
      const params = new URLSearchParams({
        path: dirPath,
        userId: config.userId,
        workspaceDirectory: config.workspaceDirectory,
      });
      const url = `${baseUrl}/api/files/list?${params}`;
      const response = await fetch(url, { headers: getAuthHeaders() });
      applyRefreshedUserToken(response);
      const data = await response.json();
      if (data.error) {
        message.error(data.error);
        setLoading(false);
        if (dirPath !== initialPath) {
          localStorage.removeItem(STORAGE_KEY);
          setTimeout(() => loadDirectory(initialPath), 100);
        }
        return;
      }
      setCurrentPath(data.path);
      setPathInput(data.path);
      setItems(data.items);
      localStorage.setItem(STORAGE_KEY, data.path);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load directory:', err);
      message.error('Failed to load directory - check if backend is running');
      setLoading(false);
      if (dirPath !== initialPath) {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
  }, [initialPath, pipelineApi, getAuthHeaders, config?.userId, config?.workspaceDirectory]);

  useEffect(() => {
    if (visible && pipelineApi) {
      loadDirectory(getInitialPath());
    }
  }, [visible, pipelineApi, getInitialPath, loadDirectory]);

  const handleItemClick = (item: FileItem) => {
    if (item.isDirectory) {
      loadDirectory(item.path);
    } else if (item.isNifti) {
      setSelectedFile(item);
    }
  };

  const handleItemDoubleClick = (item: FileItem) => {
    if (item.isNifti) {
      onSelectFile(item);
      onClose();
    }
  };

  const handleGoUp = () => {
    const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/';
    loadDirectory(parentPath);
  };

  const handlePathSubmit = () => {
    loadDirectory(pathInput);
  };

  const handleSelectCurrentFolder = () => {
    const niftiFiles = items.filter(item => item.isNifti);
    if (niftiFiles.length === 0) {
      message.warning('No NIfTI files found in this folder');
      return;
    }
    onSelectFolder(currentPath, niftiFiles);
    onClose();
  };

  const handleSelectSingleFile = () => {
    if (selectedFile) {
      onSelectFile(selectedFile);
      onClose();
    }
  };

  const niftiCount = items.filter(i => i.isNifti).length;

  return (
    <Modal
      title="Browse Server Files"
      open={visible}
      onCancel={onClose}
      width={700}
      footer={[
        <Button key="cancel" onClick={onClose}>Cancel</Button>,
        <Button 
          key="selectFile" 
          onClick={handleSelectSingleFile}
          disabled={!selectedFile}
          icon={<CheckOutlined />}
        >
          Load Selected File
        </Button>,
        <Button 
          key="selectFolder" 
          type="primary" 
          onClick={handleSelectCurrentFolder}
          disabled={niftiCount === 0}
        >
          Load All ({niftiCount} files)
        </Button>,
      ]}
    >
      <div className="mb-4">
        <div className="flex gap-2 mb-2">
          <Button icon={<HomeOutlined />} onClick={() => loadDirectory(initialPath)} />
          <Button icon={<ArrowUpOutlined />} onClick={handleGoUp} />
          <Input
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            onPressEnter={handlePathSubmit}
            placeholder="Enter path..."
            className="flex-1"
          />
          <Button onClick={handlePathSubmit}>Go</Button>
        </div>
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">Current: {currentPath}</div>
        </div>
        {selectedFile && (
          <div className="text-sm text-blue-600 mt-1">
            Selected: {selectedFile.name}
          </div>
        )}
      </div>

      <Spin spinning={loading}>
        <List
          className="max-h-96 overflow-y-auto border rounded"
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              className={`cursor-pointer hover:bg-gray-50 px-3 ${
                item.isNifti ? 'bg-green-50' : ''
              } ${selectedFile?.path === item.path ? 'ring-2 ring-blue-500 bg-blue-50' : ''}`}
              onClick={() => handleItemClick(item)}
              onDoubleClick={() => handleItemDoubleClick(item)}
            >
              <div className="flex items-center gap-2 w-full">
                {item.isDirectory ? (
                  <FolderOutlined className="text-yellow-500" />
                ) : (
                  <FileOutlined className={item.isNifti ? 'text-green-500' : 'text-gray-400'} />
                )}
                <div className="flex-1 min-w-0">
                  <span className={item.isNifti ? 'text-green-700 font-medium' : ''}>
                    {item.name}
                  </span>
                </div>
                {item.isNifti && (
                  <span className="ml-auto text-xs text-green-600 bg-green-100 px-2 py-0.5 rounded">
                    NIfTI
                  </span>
                )}
                {selectedFile?.path === item.path && (
                  <CheckOutlined className="ml-2 text-blue-500" />
                )}
              </div>
            </List.Item>
          )}
        />
      </Spin>
      
      <div className="mt-3 text-xs text-gray-500">
        💡 Click to select a file, double-click to load immediately. Or click "Load All" to load all NIfTI files in current folder.
      </div>
    </Modal>
  );
};

export default ServerFileBrowser;
