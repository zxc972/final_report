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

import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Button, Slider, Switch, message, Dropdown, Tabs, Select, Progress, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { DownloadOutlined, CloudServerOutlined } from '@ant-design/icons';
import EnhancedNiiVueViewer from './EnhancedNiiVueViewer';
import SurfaceViewer from './SurfaceViewer';
import ServerFileBrowser from './ServerFileBrowser';
import { resolvePipelineBaseUrl } from '../../utils/runtimePorts';
import { getResolvedAccessToken } from '../../services/accessToken';
import { useConfigStore } from '../../stores/configStore';

interface PipelineStage {
  id: string;
  name: string;
  description: string;
  filePath: string;
  color: string;
  category: 'preprocessing';
}

interface SurfaceFile {
  id: string;
  name: string;
  hemisphere: 'L' | 'R';
  surfaceType: string;
  resolution: 'native' | '32k' | '164k';
  path: string;
}

interface ServerNiftiFile {
  name: string;
  path: string;
  isNifti: boolean;
}

interface BrainSegmentationPipelineProps {
  className?: string;
}

const BrainSegmentationPipeline: React.FC<BrainSegmentationPipelineProps> = ({
  className = '',
}) => {
  const { config } = useConfigStore();
  const fileBrowserInitialPath = useMemo(() => {
    const ws = config?.workspaceDirectory;
    const uid = config?.userId;
    if (ws && uid) return `${ws.replace(/\/$/, '')}/${uid}`;
    if (ws) return ws;
    return '/data';
  }, [config?.workspaceDirectory, config?.userId]);
  const [currentStage, setCurrentStage] = useState<string>('original');
  const [comparisonStage, setComparisonStage] = useState<string>('brain');
  const [overlayOpacity, setOverlayOpacity] = useState<number>(50);
  const [overlayColormap, setOverlayColormap] = useState<string>('red');
  const [showOverlay, setShowOverlay] = useState<boolean>(true);
  const [loadedData, setLoadedData] = useState<{ [key: string]: ArrayBuffer }>(
    {}
  );
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState<boolean>(false);
  const [reportProgress, setReportProgress] = useState<number>(0);
  const [uploadedFiles, setUploadedFiles] = useState<{ [key: string]: File }>(
    {}
  );
  const [serverStageFiles, setServerStageFiles] = useState<{ [key: string]: ServerNiftiFile }>(
    {}
  );
  const [serverBrowserVisible, setServerBrowserVisible] =
    useState<boolean>(false);
  const [pipelineApi, setPipelineApi] = useState<string>('');
  const getAuthHeaders = useCallback(() => {
    const token = getResolvedAccessToken();
    const userToken = useConfigStore.getState().userToken;
    return {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(userToken ? { 'X-User-Token': userToken } : {}),
    };
  }, []);
  const getJsonHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  }), [getAuthHeaders]);
  const applyRefreshedUserToken = useCallback((response: Response) => {
    const refreshed = response.headers.get('X-User-Token');
    if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
  }, []);
  const buildScopedFileUrl = useCallback((baseUrl: string, apiPath: string, filePath: string) => {
    if (!config?.userId || !config?.workspaceDirectory) {
      throw new Error('Please verify your User ID in Configuration before browsing server files.');
    }
    const params = new URLSearchParams({
      path: filePath,
      userId: config.userId,
      workspaceDirectory: config.workspaceDirectory,
    });
    return `${baseUrl}${apiPath}?${params}`;
  }, [config?.userId, config?.workspaceDirectory]);

  // Surface visualization state
  const [activeTab, setActiveTab] = useState<string>('preprocessing');
  const [surfaceResolution, setSurfaceResolution] = useState<
    'native' | '32k' | '164k'
  >('native');
  const [surfaceHemisphere, setSurfaceHemisphere] = useState<'L' | 'R' | 'both'>(
    'L'
  );
  const [currentSurfaceType, setCurrentSurfaceType] =
    useState<string>('midthickness');
  const [loadedSurfaces, setLoadedSurfaces] = useState<{
    [key: string]: ArrayBuffer;
  }>({});
  const [surfaceFiles, setSurfaceFiles] = useState<SurfaceFile[]>([]);

  // Surface types available
  const surfaceTypes = [
    { id: 'midthickness', name: 'Midthickness', description: 'Mid-cortical surface' },
    { id: 'pial', name: 'Pial', description: 'Outer cortical surface' },
    { id: 'white', name: 'White', description: 'White matter surface' },
    { id: 'inflated', name: 'Inflated', description: 'Inflated surface' },
    { id: 'very_inflated', name: 'Very Inflated', description: 'Highly inflated surface' },
    { id: 'smoothwm', name: 'Smooth WM', description: 'Smoothed white matter' },
    { id: 'sphere', name: 'Sphere', description: 'Spherical surface' },
  ];

  // Define preprocessing pipeline stages (simplified)
  const pipelineStages: PipelineStage[] = [
    // 1. Raw T1
    {
      id: 'original_raw',
      name: 'Raw T1',
      description: 'T1',
      filePath: '/ION001/T1/ION_1_0000.nii.gz',
      color: '#1890ff',
      category: 'preprocessing'
    },
    // 2. Preprocessed T1
    {
      id: 'processed',
      name: 'Preprocessed T1',
      description: 'T1.nii.gz',
      filePath: '/ION001/T1.nii.gz',
      color: '#52c41a',
      category: 'preprocessing'
    },
    // 3. Skull stripping
    {
      id: 'brain',
      name: 'Skull Stripping',
      description: 'brain.nii.gz',
      filePath: '/ION001/brain.nii.gz',
      color: '#13c2c2',
      category: 'preprocessing'
    },
    // 4. Brain mask
    {
      id: 'brain_mask',
      name: 'Brain Mask',
      description: 'brain_mask.nii.gz',
      filePath: '/ION001/brainmask.nii.gz',
      color: '#f5222d',
      category: 'preprocessing'
    },
    // 5. White matter segmentation
    {
      id: 'white_matter',
      name: 'White Matter',
      description: 'wm.nii.gz',
      filePath: '/ION001/wm.nii.gz',
      color: '#a0d911',
      category: 'preprocessing'
    }
  ];

  // Group by category (now only preprocessing)
  const stagesByCategory = {
    preprocessing: pipelineStages.filter(s => s.category === 'preprocessing')
  };

  const getCurrentStageData = useCallback(() => {
    return loadedData[currentStage] || null;
  }, [loadedData, currentStage]);

  const loadStageData = useCallback(async (stageId: string) => {
    if (loadedData[stageId]) {
      return loadedData[stageId];
    }

    const serverFile = serverStageFiles[stageId];
    if (!uploadedFiles[stageId] && !serverFile) {
      message.warning('Please select a folder containing the data for this stage first');
      return null;
    }

    const stage = pipelineStages.find(s => s.id === stageId);
    if (!stage) return null;

    setIsLoading(true);
    try {
      let arrayBuffer: ArrayBuffer;
      let file: File | undefined = uploadedFiles[stageId];

      if (file) {
        arrayBuffer = await file.arrayBuffer();
      } else if (serverFile) {
        let baseUrl = pipelineApi;
        if (!baseUrl) {
          baseUrl = await resolvePipelineBaseUrl();
          setPipelineApi(baseUrl);
        }
        const response = await fetch(buildScopedFileUrl(baseUrl, '/api/files/read', serverFile.path), {
          headers: getAuthHeaders(),
        });
        applyRefreshedUserToken(response);
        if (!response.ok) {
          throw new Error(`Failed to load: ${response.status}`);
        }
        arrayBuffer = await response.arrayBuffer();
        file = new File([arrayBuffer], serverFile.name, { type: 'application/gzip' });
        setUploadedFiles(prev => ({ ...prev, [stageId]: file! }));
      } else {
        return null;
      }

      setLoadedData(prev => ({
        ...prev,
        [stageId]: arrayBuffer
      }));

      // Removed continuous success messages to prevent spam
      return arrayBuffer;
    } catch (error) {
      console.error(`Failed to load stage ${stageId}:`, error);
      message.error(`Failed to load: ${stage?.name}`);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [loadedData, pipelineApi, pipelineStages, serverStageFiles, uploadedFiles, buildScopedFileUrl, getAuthHeaders, applyRefreshedUserToken]);

  const handleStageChange = useCallback(async (stageId: string) => {
    setCurrentStage(stageId);
    await loadStageData(stageId);
  }, [loadStageData]);

  // File name matching rules - for files in the root folder
  const fileMatchingRules = {
    processed: [/^T1\.nii\.gz$/i],
    brain: [/^brain\.nii\.gz$/i],
    brain_mask: [/^brainmask\.nii\.gz$/i, /^brain_mask\.nii\.gz$/i],
    white_matter: [/^wm\.nii\.gz$/i],
  };

  const identifyFileType = (fileName: string): string | null => {
    for (const [stageId, patterns] of Object.entries(fileMatchingRules)) {
      for (const pattern of patterns) {
        if (pattern.test(fileName)) {
          return stageId;
        }
      }
    }
    return null;
  };

  useEffect(() => {
    resolvePipelineBaseUrl().then(setPipelineApi).catch(() => setPipelineApi(''));
  }, []);
  const handleServerFolderSelect = useCallback(
    async (
      folderPath: string,
      niftiFiles: { name: string; path: string; isNifti: boolean }[]
    ) => {
      let baseUrl = pipelineApi;
      if (!baseUrl) {
        try {
          baseUrl = await resolvePipelineBaseUrl();
          setPipelineApi(baseUrl);
        } catch (error) {
          message.error('Pipeline backend is not configured yet. Please retry in a moment.');
          return;
        }
      }
      setIsLoading(true);
      setCurrentSubjectPath(folderPath); // Save subject path for surface loading
      message.info(`Loading files from server...`);

      const discoveredStageFiles: { [key: string]: ServerNiftiFile } = {};

      // 1. Index files in the selected folder. Do not download every NIfTI eagerly:
      // large T1/brain/wm volumes make folder selection feel slow.
      for (const fileInfo of niftiFiles) {
        const stageId = identifyFileType(fileInfo.name);
        if (stageId) {
          discoveredStageFiles[stageId] = fileInfo;
          console.log(`Found server file: ${fileInfo.name} -> ${stageId}`);
        } else {
          console.log(`Unidentified file: ${fileInfo.name}`);
        }
      }

      // 2. Check T1/ subfolder and index raw T1, but leave download lazy.
      try {
        const t1FolderPath = `${folderPath}/T1`;
        const t1Response = await fetch(
          buildScopedFileUrl(baseUrl, '/api/files/list', t1FolderPath),
          { headers: getAuthHeaders() }
        );
        applyRefreshedUserToken(t1Response);
        if (t1Response.ok) {
          const t1Data = await t1Response.json();
          if (!t1Data.error && t1Data.items) {
            // 找到第一个 NIfTI 文件
            const rawT1File = t1Data.items.find(
              (item: { isNifti: boolean }) => item.isNifti
            );
            if (rawT1File) {
              discoveredStageFiles['original_raw'] = rawT1File;
              console.log(`Found Raw T1: ${rawT1File.name}`);
            }
          }
        }
      } catch (error) {
        console.log('No T1 subfolder found or error loading:', error);
      }

      const discoveredStages = Object.keys(discoveredStageFiles);
      if (discoveredStages.length > 0) {
        setServerStageFiles((prev) => ({ ...prev, ...discoveredStageFiles }));

        const loadServerStage = async (stageId: string) => {
          const serverFile = discoveredStageFiles[stageId];
          if (!serverFile) return false;
          try {
            const response = await fetch(
              buildScopedFileUrl(baseUrl, '/api/files/read', serverFile.path),
              { headers: getAuthHeaders() }
            );
            applyRefreshedUserToken(response);
            if (!response.ok) return false;
            const arrayBuffer = await response.arrayBuffer();
            const file = new File([arrayBuffer], serverFile.name, { type: 'application/gzip' });
            setLoadedData((prev) => ({ ...prev, [stageId]: arrayBuffer }));
            setUploadedFiles((prev) => ({ ...prev, [stageId]: file }));
            return true;
          } catch (error) {
            console.error(`Failed to load initial stage ${stageId}:`, error);
            return false;
          }
        };

        const initialStage =
          discoveredStageFiles.processed ? 'processed' :
          discoveredStageFiles.brain ? 'brain' :
          discoveredStageFiles.original_raw ? 'original_raw' :
          discoveredStages[0];
        if (initialStage) setCurrentStage(initialStage);

        const initialLoads = [initialStage];
        if (discoveredStageFiles.white_matter) {
          initialLoads.push('white_matter');
          setComparisonStage('white_matter');
        } else if (discoveredStageFiles.brain_mask) {
          initialLoads.push('brain_mask');
          setComparisonStage('brain_mask');
        }
        const uniqueInitialLoads = Array.from(new Set(initialLoads));
        const loadedCount = (await Promise.all(uniqueInitialLoads.map(loadServerStage))).filter(Boolean).length;

        message.success(`Found ${discoveredStages.length} files on server; loaded ${loadedCount} initial file${loadedCount === 1 ? '' : 's'}`);
      } else {
        message.error('No files could be identified');
      }

      setIsLoading(false);
    },
    [pipelineApi, getAuthHeaders, buildScopedFileUrl, applyRefreshedUserToken]
  );

  // Load single file from server
  const handleServerFileSelect = useCallback(
    async (fileInfo: { name: string; path: string }) => {
      setIsLoading(true);
      message.info(`Loading ${fileInfo.name}...`);

      try {
        let baseUrl = pipelineApi;
        if (!baseUrl) {
          baseUrl = await resolvePipelineBaseUrl();
          setPipelineApi(baseUrl);
        }
        const response = await fetch(
          buildScopedFileUrl(baseUrl, '/api/files/read', fileInfo.path),
          { headers: getAuthHeaders() }
        );
        applyRefreshedUserToken(response);
        if (!response.ok) {
          throw new Error(`Failed to load: ${response.status}`);
        }
        const arrayBuffer = await response.arrayBuffer();
        let stageId = identifyFileType(fileInfo.name);

        // If not identified, use custom id
        if (!stageId) {
          stageId = 'custom_' + Date.now();
        }

        const file = new File([arrayBuffer], fileInfo.name, {
          type: 'application/gzip',
        });

        setLoadedData((prev) => ({ ...prev, [stageId!]: arrayBuffer }));
        setUploadedFiles((prev) => ({ ...prev, [stageId!]: file }));
        setCurrentStage(stageId);

        message.success(`Loaded: ${fileInfo.name}`);
      } catch (error) {
        console.error(`Failed to load ${fileInfo.name}:`, error);
        message.error(`Failed to load: ${fileInfo.name}`);
      }

      setIsLoading(false);
    },
    [pipelineApi, getAuthHeaders, buildScopedFileUrl, applyRefreshedUserToken]
  );

  // Load surface file
  const [currentSubjectPath, setCurrentSubjectPath] = useState<string>('');

  const handleLoadSurface = useCallback(
    async (surfaceType: string) => {
      if (!currentSubjectPath) {
        message.warning('Please select a subject folder first');
        return;
      }

      setIsLoading(true);
      const hemispheres =
        surfaceHemisphere === 'both' ? ['L', 'R'] : [surfaceHemisphere];

      // Extract subject ID from path
      const pathParts = currentSubjectPath.split('/');
      const subjectId = pathParts[pathParts.length - 1];

      // Try multiple possible HCP directory structures
      const possibleBasePaths = [
        `${currentSubjectPath}/${subjectId}`, // e.g., KM006/KM006/
        currentSubjectPath, // e.g., KM006/
      ];

      const possibleHCPDirs = ['HCP_Style_Dir', 'HCP_Stype_Dir']; // Handle typo

      // Determine suffix based on resolution
      let subFolder = '';
      let suffix = '';
      if (surfaceResolution === 'native') {
        subFolder = 'Native';
        suffix = 'native';
      } else if (surfaceResolution === '32k') {
        subFolder = 'fsaverage_LR32k';
        suffix = '32k_fs_LR';
      } else {
        subFolder = ''; // 164k files are in root HCP dir
        suffix = '164k_fs_LR';
      }

      let loadedCount = 0;

      for (const hemi of hemispheres) {
        const fileName = `${subjectId}.${hemi}.${surfaceType}.${suffix}.surf.gii`;
        let loaded = false;

        // Try all possible paths
        for (const basePath of possibleBasePaths) {
          if (loaded) break;
          for (const hcpDir of possibleHCPDirs) {
            if (loaded) break;
            const folderPath = subFolder
              ? `${basePath}/${hcpDir}/${subFolder}`
              : `${basePath}/${hcpDir}`;
            const filePath = `${folderPath}/${fileName}`;

            try {
              const response = await fetch(
                buildScopedFileUrl(pipelineApi, '/api/files/read', filePath),
                { headers: getAuthHeaders() }
              );
              applyRefreshedUserToken(response);
              if (response.ok) {
                const arrayBuffer = await response.arrayBuffer();
                const key = `${hemi}_${surfaceType}_${surfaceResolution}`;
                setLoadedSurfaces((prev) => ({ ...prev, [key]: arrayBuffer }));

                // Add to surfaceFiles list
                setSurfaceFiles((prev) => {
                  const existing = prev.find((f) => f.id === key);
                  if (!existing) {
                    return [
                      ...prev,
                      {
                        id: key,
                        name: fileName,
                        hemisphere: hemi as 'L' | 'R',
                        surfaceType,
                        resolution: surfaceResolution,
                        path: filePath,
                      },
                    ];
                  }
                  return prev;
                });

                console.log(`Loaded surface: ${filePath}`);
                loaded = true;
                loadedCount++;
              }
            } catch (error) {
              // Continue trying other paths
            }
          }
        }

        if (!loaded) {
          console.warn(`Surface file not found for ${hemi} hemisphere`);
        }
      }

      setIsLoading(false);
    },
    [currentSubjectPath, surfaceHemisphere, surfaceResolution, pipelineApi, buildScopedFileUrl, getAuthHeaders, applyRefreshedUserToken]
  );

  // Auto-reload surface when hemisphere or resolution changes
  useEffect(() => {
    if (currentSubjectPath && currentSurfaceType && activeTab === 'surface') {
      // Check if the surface for current selection is already loaded
      const key = surfaceHemisphere === 'both' 
        ? `L_${currentSurfaceType}_${surfaceResolution}`
        : `${surfaceHemisphere}_${currentSurfaceType}_${surfaceResolution}`;
      
      if (!loadedSurfaces[key]) {
        handleLoadSurface(currentSurfaceType);
      }
    }
  }, [surfaceHemisphere, surfaceResolution, currentSubjectPath, currentSurfaceType, activeTab, loadedSurfaces, handleLoadSurface]);

  // Handle local single file upload
  const handleLocalFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    const fileName = file.name.toLowerCase();
    
    if (!fileName.endsWith('.nii') && !fileName.endsWith('.nii.gz')) {
      message.error('Please select a valid NIfTI file (.nii, .nii.gz)');
      return;
    }

    setIsLoading(true);
    message.info(`Loading ${file.name}...`);

    try {
      const arrayBuffer = await file.arrayBuffer();
      let stageId = identifyFileType(file.name);
      
      if (!stageId) {
        stageId = 'custom_' + Date.now();
      }
      
      setLoadedData(prev => ({ ...prev, [stageId!]: arrayBuffer }));
      setUploadedFiles(prev => ({ ...prev, [stageId!]: file }));
      setCurrentStage(stageId);
      
      message.success(`Loaded: ${file.name}`);
    } catch (error) {
      console.error('Failed to load file:', error);
      message.error(`Failed to load: ${file.name}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleFolderUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setIsLoading(true);
    message.info(`Processing ${files.length} files...`);

    const niftiFiles = Array.from(files).filter(file => 
      file.name.endsWith('.nii') || file.name.endsWith('.nii.gz')
    );

    if (niftiFiles.length === 0) {
      message.error('No NIfTI files (.nii, .nii.gz) found');
      setIsLoading(false);
      return;
    }

    const identifiedFiles: {[key: string]: File} = {};
    const unidentifiedFiles: File[] = [];

    // Automatically identify file types
    for (const file of niftiFiles) {
      const stageId = identifyFileType(file.name);
      if (stageId) {
        identifiedFiles[stageId] = file;
        console.log(`Identified file: ${file.name} -> ${stageId}`);
      } else {
        unidentifiedFiles.push(file);
        console.log(`Unidentified file: ${file.name}`);
      }
    }

    // Load identified files
    let successCount = 0;
    const newLoadedData: {[key: string]: ArrayBuffer} = {};

    for (const [stageId, file] of Object.entries(identifiedFiles)) {
      try {
        const arrayBuffer = await file.arrayBuffer();
        newLoadedData[stageId] = arrayBuffer;
        successCount++;
        
        const stage = pipelineStages.find(s => s.id === stageId);
        console.log(`Loaded successfully: ${stage?.name} (${file.name})`);
      } catch (error) {
        console.error(`Failed to load: ${file.name}`, error);
      }
    }

    setLoadedData(prev => ({ ...prev, ...newLoadedData }));
    setUploadedFiles(identifiedFiles);
    setIsLoading(false);

    // Show result
    const identifiedCount = Object.keys(identifiedFiles).length;
    
    message.success(
      `Folder processing completed! Successfully identified and loaded ${successCount}/${identifiedCount} files`
    );

    if (unidentifiedFiles.length > 0) {
      message.warning(
        `There are ${unidentifiedFiles.length} files that could not be identified automatically: ${unidentifiedFiles.map(f => f.name).join(', ')}`
      );
    }

    // Automatically switch to the first loaded stage
    const firstLoadedStage = Object.keys(newLoadedData)[0];
    if (firstLoadedStage) {
      setCurrentStage(firstLoadedStage);
    }

  }, [pipelineStages]);

  const getCurrentStage = () => pipelineStages.find(s => s.id === currentStage);

  const renderStageSelector = (category: keyof typeof stagesByCategory, title: string) => (
    <div className="mb-4">
      {title && <h4 className="text-gray-700 text-sm font-semibold mb-3 border-b border-gray-200 pb-1">{title}</h4>}
      <div className="space-y-2">
        {stagesByCategory[category].map(stage => (
          <div
            key={stage.id}
            className={`p-3 rounded-lg border-2 cursor-pointer transition-all duration-200 ${
              currentStage === stage.id 
                ? 'border-blue-500 bg-blue-50 shadow-sm' 
                : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
            }`}
            onClick={() => handleStageChange(stage.id)}
          >
            <div className="flex items-start">
              <div 
                className="w-4 h-4 rounded-full mr-3 mt-0.5 flex-shrink-0" 
                style={{ backgroundColor: stage.color }}
              />
              <div className="flex-1 min-w-0">
                <div className={`font-medium text-sm ${
                  currentStage === stage.id ? 'text-blue-700' : 'text-gray-800'
                }`}>
                  {stage.name}
                </div>
                <div className={`text-xs mt-1 ${
                  currentStage === stage.id ? 'text-blue-600' : 'text-gray-500'
                }`}>
                  {stage.description}
                </div>
                {loadedData[stage.id] && (
                  <div className="text-xs text-green-600 mt-1 font-medium">
                    ✓ Loaded ({uploadedFiles[stage.id]?.name})
                  </div>
                )}
                {!loadedData[stage.id] && serverStageFiles[stage.id] && (
                  <div className="text-xs text-blue-500 mt-1">
                    Available on server
                  </div>
                )}
                {!uploadedFiles[stage.id] && !serverStageFiles[stage.id] && (
                  <div className="text-xs text-gray-400 mt-1">
                    Waiting for file upload
                  </div>
                )}
                {isLoading && currentStage === stage.id && (
                  <div className="text-xs text-blue-600 mt-1">Loading...</div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const localMenuItems: MenuProps['items'] = [
    {
      key: 'folder',
      label: '📁 Select Folder',
      onClick: () => document.getElementById('folderInput')?.click(),
    },
    {
      key: 'file',
      label: '📄 Select Single File',
      onClick: () => document.getElementById('localFileInput')?.click(),
    },
  ];

  const currentImageData = getCurrentStageData();
  const hasSelectableVolume =
    Object.keys(uploadedFiles).length > 0 || Object.keys(serverStageFiles).length > 0;
  const currentOverlayData =
    showOverlay && comparisonStage ? loadedData[comparisonStage] : null;
  const currentSurfaceKey = `${surfaceHemisphere}_${currentSurfaceType}_${surfaceResolution}`;
  const currentLeftSurfaceKey = `L_${currentSurfaceType}_${surfaceResolution}`;
  const currentRightSurfaceKey = `R_${currentSurfaceType}_${surfaceResolution}`;
  const currentSurfaceData =
    surfaceHemisphere === 'both'
      ? loadedSurfaces[currentLeftSurfaceKey]
      : loadedSurfaces[currentSurfaceKey];
  const currentSurfaceDataRight =
    surfaceHemisphere === 'both' ? loadedSurfaces[currentRightSurfaceKey] : undefined;
  const hasCurrentSurfaceData =
    !!currentSurfaceData && currentSurfaceData.byteLength > 0;
  const loadedSurfaceCount = Object.keys(loadedSurfaces).length;

  return (
    <div className={`h-full flex ${className}`} style={{ background: 'var(--px-bg)' }}>
      {/* Left control panel */}
      <div className="w-80 p-4 overflow-y-auto" style={{ background: 'var(--px-surface)', borderRight: '1px solid var(--px-border)' }}>
        <div className="mb-5">
          <h1 className="px-page-title" style={{ fontSize: 18 }}>Visualization</h1>
          <p className="px-page-desc" style={{ fontSize: 13 }}>Load volumes or surfaces and inspect overlays.</p>
        </div>

        {/* File operations */}
        <div className="mb-6">
          <input
            type="file"
            id="folderInput"
            {...({ webkitdirectory: "", directory: "" } as any)}
            multiple
            style={{ display: 'none' }}
            onChange={handleFolderUpload}
          />
          <input
            type="file"
            id="localFileInput"
            style={{ display: 'none' }}
            onChange={handleLocalFileUpload}
          />
          <Button 
            type="primary"
            icon={<CloudServerOutlined />}
            onClick={() => setServerBrowserVisible(true)}
            className="w-full mb-2"
            loading={isLoading}
            size="large"
          >
            🖥️ Browse Server Files
          </Button>
          
          <Dropdown menu={{ items: localMenuItems }} trigger={['click']}>
            <Button 
              className="w-full mb-3"
              loading={isLoading}
              size="large"
            >
              📂 Select Local Files ▾
            </Button>
          </Dropdown>
          
          <div className="text-xs text-gray-500 text-center mb-3">
            Browse server or select from local machine
          </div>
          
          <Button 
            icon={<DownloadOutlined />}
            className="w-full"
            disabled={!currentSubjectPath || isGeneratingReport}
            loading={isGeneratingReport}
            onClick={async () => {
              if (!currentSubjectPath) {
                message.warning('Please select a subject folder first');
                return;
              }
              if (!config?.userId || !config?.workspaceDirectory) {
                message.error('Please verify your User ID in Configuration before generating a report.');
                return;
              }
              setIsGeneratingReport(true);
              setReportProgress(8);
              const progressTimer = window.setInterval(() => {
                setReportProgress(prev => {
                  if (prev >= 92) return prev;
                  const step = Math.max(1, Math.round((92 - prev) * 0.14));
                  return Math.min(prev + step, 92);
                });
              }, 600);
              try {
                const baseUrl = pipelineApi || await resolvePipelineBaseUrl();
                if (!pipelineApi) {
                  setPipelineApi(baseUrl);
                }
                const response = await fetch(`${baseUrl}/api/report/generate`, {
                  method: 'POST',
                  headers: getJsonHeaders(),
                  body: JSON.stringify({
                    subjectPath: currentSubjectPath,
                    userId: config?.userId,
                    workspaceDirectory: config?.workspaceDirectory,
                  })
                });
                applyRefreshedUserToken(response);
                const result = await response.json();
                if (result.success) {
                  setReportProgress(100);
                  message.success('Report generated successfully!');
                  // Open report in new tab using the view API
                  const token = getResolvedAccessToken();
                  const tokenQuery = token ? `&token=${encodeURIComponent(token)}` : '';
                  const userToken = useConfigStore.getState().userToken;
                  const userTokenQuery = userToken ? `&userToken=${encodeURIComponent(userToken)}` : '';
                  const scopeQuery = config?.userId && config?.workspaceDirectory
                    ? `&userId=${encodeURIComponent(config.userId)}&workspaceDirectory=${encodeURIComponent(config.workspaceDirectory)}`
                    : '';
                  const reportUrl = `${baseUrl}/api/report/view?path=${encodeURIComponent(currentSubjectPath)}${tokenQuery}${userTokenQuery}${scopeQuery}`;
                  const reportWindow = window.open(reportUrl, '_blank');
                  if (reportWindow) {
                    reportWindow.opener = null;
                  } else {
                    Modal.info({
                      title: 'Report generated',
                      content: 'Your browser blocked the automatic report tab. Click Open report to view it.',
                      okText: 'Open report',
                      onOk: () => {
                        window.open(reportUrl, '_blank');
                      },
                    });
                  }
                } else {
                  message.error(result.error || 'Failed to generate report');
                }
              } catch (error) {
                console.error('Report generation error:', error);
                message.error('Failed to generate report');
              } finally {
                window.clearInterval(progressTimer);
                window.setTimeout(() => {
                  setIsGeneratingReport(false);
                  setReportProgress(0);
                }, 700);
              }
            }}
          >
            📊 Generate Report
          </Button>
          {isGeneratingReport && (
            <div className="mt-3">
              <Progress
                percent={reportProgress}
                size="small"
                status={reportProgress >= 100 ? 'success' : 'active'}
              />
              <div className="text-xs text-gray-500 text-center mt-1">
                Generating report and QC visualizations...
              </div>
            </div>
          )}
        </div>

        {/* Overlay Controls */}
        {activeTab !== 'surface' && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="text-gray-700 text-sm font-medium mb-3">Overlay</div>

            {/* Overlay source selector */}
            <div className="mb-3">
              <div className="text-xs text-gray-500 mb-1">Overlay Layer</div>
              <Select
                value={comparisonStage}
                onChange={(value) => {
                  setComparisonStage(value);
                  if (value && loadedData[value]) {
                    setShowOverlay(true);
                  }
                }}
                size="small"
                className="w-full"
                options={[
                  { value: '', label: 'None' },
                  { value: 'brain_mask', label: 'Brain Mask', disabled: !loadedData['brain_mask'] },
                  { value: 'white_matter', label: 'White Matter', disabled: !loadedData['white_matter'] },
                ]}
              />
            </div>

            {/* Overlay toggle and opacity */}
            {comparisonStage && loadedData[comparisonStage] && (
              <>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-600 text-xs">Show Overlay</span>
                  <Switch
                    checked={showOverlay}
                    onChange={setShowOverlay}
                    size="small"
                  />
                </div>
                {showOverlay && (
                  <>
                    {/* Color selector */}
                    <div className="mb-3">
                      <div className="text-xs text-gray-500 mb-1">Color</div>
                      <Select
                        value={overlayColormap}
                        onChange={setOverlayColormap}
                        size="small"
                        className="w-full"
                        options={[
                          { value: 'red', label: '🔴 Red' },
                          { value: 'green', label: '🟢 Green' },
                          { value: 'blue', label: '🔵 Blue' },
                          { value: 'yellow', label: '🟡 Yellow' },
                          { value: 'cyan', label: '🩵 Cyan' },
                          { value: 'hot', label: '🔥 Hot' },
                          { value: 'cool', label: '❄️ Cool' },
                          { value: 'winter', label: '🌨️ Winter' },
                        ]}
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-gray-600 text-xs">Opacity</span>
                        <span className="text-gray-600 text-xs font-medium">{overlayOpacity}%</span>
                      </div>
                      <Slider
                        min={0}
                        max={100}
                        value={overlayOpacity}
                        onChange={setOverlayOpacity}
                      />
                    </div>
                  </>
                )}
              </>
            )}

            <div className="text-xs text-gray-400 mt-2">
              Status: {loadedData['brain_mask'] ? '🟢 Mask' : '⚪ Mask'} | {loadedData['white_matter'] ? '🟢 WM' : '⚪ WM'}
            </div>
          </div>
        )}

        {/* Main Tabs - Preprocessing and Surface */}
        <div className="flex-1 min-h-0">
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            size="small"
            items={[
              {
                key: 'preprocessing',
                label: 'Preprocessing',
                children: (
                  <div className="max-h-[400px] overflow-y-auto pr-2">
                    {renderStageSelector('preprocessing', '')}
                  </div>
                ),
              },
              {
                key: 'surface',
                label: 'Surface',
                children: (
                  <div className="max-h-[400px] overflow-y-auto pr-2">
                    {/* Resolution selector */}
                    <div className="mb-4">
                      <div className="text-xs text-gray-500 mb-2">Resolution</div>
                      <Select
                        value={surfaceResolution}
                        onChange={setSurfaceResolution}
                        size="small"
                        className="w-full"
                        options={[
                          { value: 'native', label: 'Native' },
                          { value: '32k', label: '32k_fs_LR' },
                          { value: '164k', label: '164k_fs_LR' },
                        ]}
                      />
                    </div>

                    {/* Hemisphere selector */}
                    <div className="mb-4">
                      <div className="text-xs text-gray-500 mb-2">Hemisphere</div>
                      <Select
                        value={surfaceHemisphere}
                        onChange={(value: 'L' | 'R' | 'both') => {
                          setSurfaceHemisphere(value);
                        }}
                        size="small"
                        className="w-full"
                        options={[
                          { value: 'L', label: 'Left (L)' },
                          { value: 'R', label: 'Right (R)' },
                          { value: 'both', label: 'Both (L+R)' },
                        ]}
                      />
                    </div>

                    {/* Surface type selector */}
                    <div className="text-xs text-gray-500 mb-2">Surface Type</div>
                    <div className="space-y-2">
                      {surfaceTypes.map((surface) => (
                        <div
                          key={surface.id}
                          className={`p-3 rounded-lg border-2 cursor-pointer transition-all duration-200 ${
                            currentSurfaceType === surface.id
                              ? 'border-blue-500 bg-blue-50 shadow-sm'
                              : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                          }`}
                          onClick={() => {
                            setCurrentSurfaceType(surface.id);
                            handleLoadSurface(surface.id);
                          }}
                        >
                          <div className="font-medium text-sm">
                            {surface.name}
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            {surface.description}
                          </div>
                          {loadedSurfaces[`${surfaceHemisphere}_${surface.id}_${surfaceResolution}`] && (
                            <div className="text-xs text-green-600 mt-1">
                              ✓ Loaded
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    {surfaceFiles.length === 0 && (
                      <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700">
                        Browse server files and select a subject folder with HCP_Style_Dir to load surfaces
                      </div>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </div>

        {/* File identification status */}
        {Object.keys(uploadedFiles).length > 0 && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-center mb-2">
              <span className="text-green-700 text-sm font-semibold">📂 Identified files</span>
            </div>
            <div className="text-xs text-green-600">
              Successfully identified {Object.keys(uploadedFiles).length} files
            </div>
          </div>
        )}
      </div>

      {/* Right display area */}
      <div className="flex-1 flex flex-col">
        {activeTab === 'surface' ? (
          // Surface visualization mode
          hasCurrentSurfaceData ? (
            <div className="flex-1">
              <SurfaceViewer
                title={`Surface: ${currentSurfaceType} (${surfaceResolution}, ${surfaceHemisphere})`}
                surfaceData={currentSurfaceData}
                surfaceDataRight={currentSurfaceDataRight}
                surfaceName={`${currentSurfaceType}.${surfaceResolution}.surf.gii`}
                className="h-full"
              />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center bg-gray-50">
              <div className="text-center p-8">
                {isLoading ? (
                  <>
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <div className="text-gray-700 font-medium">Loading surface...</div>
                  </>
                ) : currentSubjectPath ? (
                  <>
                    <div className="text-5xl mb-4">🧬</div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">
                      No surface result available
                    </h3>
                    <p className="text-gray-500 max-w-md">
                      No matching surface file was found for the selected hemisphere, resolution, and surface type.
                    </p>
                  </>
                ) : (
                  <>
                    <div className="text-5xl mb-4">📁</div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">
                      Select result folder
                    </h3>
                    <p className="text-gray-500 max-w-md">
                      Browse server files and select a subject folder before viewing surfaces.
                    </p>
                  </>
                )}
              </div>
            </div>
          )
        ) : !hasSelectableVolume ? (
          // Empty state - no file loaded
          <div className="flex-1 flex items-center justify-center bg-gray-50">
            <div className="text-center p-8">
              <div className="text-6xl mb-4">📁</div>
              <h3 className="text-xl font-semibold text-gray-700 mb-2">
                Select result folder
              </h3>
              <p className="text-gray-500 mb-6 max-w-md">
                Click the "Browse Server Files" button on the left and select a subject folder
              </p>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-left">
                <h4 className="font-medium text-blue-800 mb-2">Supported file types:</h4>
                <ul className="text-sm text-blue-700 space-y-1">
                  <li>• Volume: T1.nii.gz, brain.nii.gz, wm.nii.gz</li>
                  <li>• Surface: *.surf.gii (in HCP_Style_Dir)</li>
                </ul>
              </div>
            </div>
          </div>
        ) : !currentImageData ? (
          <div className="flex-1 flex items-center justify-center bg-gray-50">
            <div className="text-center p-8">
              {isLoading ? (
                <>
                  <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
                  <div className="text-gray-700 font-medium">Loading image...</div>
                </>
              ) : (
                <>
                  <div className="px-blocker-icon" style={{ marginBottom: 12 }}>◎</div>
                  <h3 className="text-lg font-semibold text-gray-700 mb-2">
                    Image not loaded
                  </h3>
                  <p className="text-gray-500 max-w-md">
                    Select an available preprocessing stage from the left panel to load it.
                  </p>
                </>
              )}
            </div>
          </div>
        ) : (
          // Single viewer mode with optional overlay
          <div className="flex-1">
            <EnhancedNiiVueViewer
              title={`${getCurrentStage()?.name || 'Brain Visualization'}`}
              imageData={currentImageData}
              segmentationData={currentOverlayData}
              showOverlay={showOverlay}
              overlayOpacity={overlayOpacity}
              overlayColormap={overlayColormap}
              onOpacityChange={setOverlayOpacity}
              onOverlayToggle={setShowOverlay}
              className="h-full"
              viewMode="multiplanar"
            />
          </div>
        )}

        {/* Bottom status bar */}
        <div className="flex-shrink-0 bg-white border-t border-gray-200 px-4 py-3 shadow-sm">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center space-x-6 text-gray-600">
              <span>
                Current:{' '}
                <span className="font-medium text-gray-800">
                  {activeTab === 'surface'
                    ? `${currentSurfaceType} (${surfaceResolution}, ${surfaceHemisphere})`
                    : getCurrentStage()?.name || 'Not selected'}
                </span>
              </span>
              {activeTab !== 'surface' && showOverlay && comparisonStage && loadedData[comparisonStage] && (
                <span className="text-xs bg-blue-100 px-2 py-1 rounded">
                  Overlay: {comparisonStage} ({overlayOpacity}%)
                </span>
              )}
            </div>
            <div className="flex items-center space-x-4 text-gray-600">
              <span>
                Loaded:{' '}
                <span className="font-semibold text-green-600">
                  {activeTab === 'surface' ? loadedSurfaceCount : Object.keys(loadedData).length}
                </span>
                {activeTab === 'surface' ? ' surfaces' : `/${pipelineStages.length}`}
              </span>
              <div className="flex items-center space-x-2">
                <div className={`w-3 h-3 rounded-full ${isLoading ? 'bg-yellow-400' : 'bg-green-500'}`}></div>
                <span className="font-medium">{isLoading ? 'Loading' : 'Ready'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Server File Browser Modal */}
      <ServerFileBrowser
        visible={serverBrowserVisible}
        onClose={() => setServerBrowserVisible(false)}
        onSelectFolder={handleServerFolderSelect}
        onSelectFile={handleServerFileSelect}
        initialPath={fileBrowserInitialPath}
      />
    </div>
  );
};

export default BrainSegmentationPipeline;
