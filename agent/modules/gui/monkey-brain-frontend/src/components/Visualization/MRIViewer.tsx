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

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Card, Slider, Switch, Select, Button, Space, Tooltip, message } from 'antd';
import { 
  ReloadOutlined,
  FullscreenOutlined,
  ZoomInOutlined,
  ZoomOutOutlined
} from '@ant-design/icons';
import { niftiService, NiftiVolume } from '../../services/niftiService';

const { Option } = Select;

interface MRIViewerProps {
  title: string;
  imageData?: ArrayBuffer | File | null;
  segmentationData?: ArrayBuffer | null;
  showOverlay?: boolean;
  overlayOpacity?: number;
  onOpacityChange?: (opacity: number) => void;
  onOverlayToggle?: (show: boolean) => void;
  onVolumeLoaded?: (volume: NiftiVolume) => void;
  className?: string;
}

interface ViewerControls {
  zoom: number;
  slice: number;
  maxSlice: number;
  contrast: number;
  brightness: number;
  colormap: string;
}

const MRIViewer: React.FC<MRIViewerProps> = ({
  title,
  imageData,
  segmentationData,
  showOverlay = true,
  overlayOpacity = 50,
  onOpacityChange,
  onOverlayToggle,
  onVolumeLoaded,
  className = ''
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [controls, setControls] = useState<ViewerControls>({
    zoom: 100,
    slice: 128,
    maxSlice: 256,
    contrast: 50,
    brightness: 50,
    colormap: 'gray'
  });

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [voxelValue, setVoxelValue] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadedVolume, setLoadedVolume] = useState<NiftiVolume | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  const colormaps = [
    { value: 'gray', label: 'Gray' },
    { value: 'hot', label: 'Hot' },
    { value: 'cool', label: 'Cool' },
    { value: 'jet', label: 'Jet' },
    { value: 'viridis', label: 'Viridis' }
  ];

  // Initialize NiiVue when canvas is ready
  useEffect(() => {
    const initializeNiiVue = async () => {
      const canvas = canvasRef.current;
      if (!canvas || isInitialized) return;

      try {
        // Set canvas size
        canvas.width = 800;
        canvas.height = 600;
        
        await niftiService.initialize(canvas);
        setIsInitialized(true);
        console.log('Canvas initialized successfully');
      } catch (error) {
        console.error('Failed to initialize NiiVue:', error);
        message.error('Failed to initialize medical image viewer');
      }
    };

    // Delay initialization to ensure DOM is rendered
    const timer = setTimeout(initializeNiiVue, 100);
    return () => clearTimeout(timer);
  }, [isInitialized]);

  // Load image data when it changes
  useEffect(() => {
    if (!isInitialized || !imageData) return;

    const loadImageData = async () => {
      setIsLoading(true);
      try {
        let volume: NiftiVolume;
        
        if (imageData instanceof File) {
          volume = await niftiService.loadNiftiFile(imageData);
        } else if (imageData instanceof ArrayBuffer) {
          volume = await niftiService.loadFromArrayBuffer(imageData, 'loaded_image.nii.gz');
        } else {
          throw new Error('Unsupported image data type');
        }

        setLoadedVolume(volume);
        
        // Update controls with actual volume info
        const sliceInfo = niftiService.getCurrentSliceInfo();
        setControls(prev => ({
          ...prev,
          slice: sliceInfo.current,
          maxSlice: sliceInfo.max
        }));

        onVolumeLoaded?.(volume);
        message.success(`Successfully loaded ${volume.name}`);
      } catch (error) {
        console.error('Failed to load image:', error);
        message.error(`Failed to load image: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        setIsLoading(false);
      }
    };

    loadImageData();
  }, [imageData, isInitialized]);

  // Load segmentation overlay when it changes
  useEffect(() => {
    if (!isInitialized || !segmentationData || !loadedVolume) return;

    const loadSegmentation = async () => {
      try {
        await niftiService.addSegmentationOverlay(segmentationData, 'segmentation.nii.gz');
        message.success('Segmentation overlay loaded');
      } catch (error) {
        console.error('Failed to load segmentation:', error);
        message.error('Failed to load segmentation overlay');
      }
    };

    loadSegmentation();
  }, [segmentationData, loadedVolume, isInitialized]);

  // Update overlay visibility and opacity
  useEffect(() => {
    if (!isInitialized) return;
    
    niftiService.setOverlayVisibility(showOverlay);
    if (showOverlay) {
      niftiService.setOverlayOpacity(overlayOpacity);
    }
  }, [showOverlay, overlayOpacity, isInitialized]);

  // Update slice info when controls change
  const updateSliceInfo = useCallback(() => {
    if (!isInitialized) return;
    
    const sliceInfo = niftiService.getCurrentSliceInfo();
    setControls(prev => ({
      ...prev,
      slice: sliceInfo.current,
      maxSlice: sliceInfo.max
    }));
  }, [isInitialized]);

  const handleMouseMove = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !isInitialized) return;

    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    setMousePosition({ x, y });
    
    // Get real voxel value at mouse position
    const value = niftiService.getVoxelValue(x, y);
    setVoxelValue(value);
  }, [isInitialized]);

  const handleControlChange = useCallback((key: keyof ViewerControls, value: number | string) => {
    setControls(prev => ({
      ...prev,
      [key]: value
    }));

    if (!isInitialized) return;

    // Apply changes to NiiVue
    switch (key) {
      case 'slice':
        niftiService.setSlice(value as number);
        break;
      case 'zoom':
        niftiService.setZoom(value as number);
        break;
      case 'contrast':
        niftiService.setContrast(value as number);
        break;
      case 'brightness':
        niftiService.setBrightness(value as number);
        break;
      case 'colormap':
        niftiService.setColormap(value as string);
        break;
    }
  }, [isInitialized]);

  const handleZoom = useCallback((delta: number) => {
    const newZoom = Math.max(25, Math.min(400, controls.zoom + delta));
    handleControlChange('zoom', newZoom);
  }, [controls.zoom, handleControlChange]);

  const handleReset = useCallback(() => {
    if (!isInitialized) return;
    
    niftiService.resetView();
    setControls({
      zoom: 100,
      slice: 128,
      maxSlice: 256,
      contrast: 50,
      brightness: 50,
      colormap: 'gray'
    });
    updateSliceInfo();
  }, [isInitialized, updateSliceInfo]);

  return (
    <Card 
      title={title}
      className={`h-full ${className}`}
      bodyStyle={{ padding: 0, height: 'calc(100% - 57px)' }}
      extra={
        <Space>
          <Tooltip title="Reset view">
            <Button icon={<ReloadOutlined />} size="small" onClick={handleReset} />
          </Tooltip>
          <Tooltip title="Fullscreen">
            <Button 
              icon={<FullscreenOutlined />} 
              size="small" 
              onClick={() => setIsFullscreen(!isFullscreen)} 
            />
          </Tooltip>
        </Space>
      }
    >
      <div className="h-full flex flex-col">
        {/* Control panel */}
        <div className="flex-shrink-0 bg-gray-800 p-3 border-b border-gray-700">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div>
              <label className="text-gray-300 block mb-1">Slice</label>
              <Slider
                min={1}
                max={controls.maxSlice}
                value={controls.slice}
                onChange={(value) => handleControlChange('slice', value)}
                tooltip={{ formatter: (value) => `${value}/${controls.maxSlice}` }}
              />
            </div>
            
            <div>
              <label className="text-gray-300 block mb-1">Contrast</label>
              <Slider
                min={0}
                max={100}
                value={controls.contrast}
                onChange={(value) => handleControlChange('contrast', value)}
              />
            </div>
            
            <div>
              <label className="text-gray-300 block mb-1">Brightness</label>
              <Slider
                min={0}
                max={100}
                value={controls.brightness}
                onChange={(value) => handleControlChange('brightness', value)}
              />
            </div>
            
            <div>
              <label className="text-gray-300 block mb-1">Colormap</label>
              <Select
                value={controls.colormap}
                onChange={(value) => handleControlChange('colormap', value)}
                size="small"
                style={{ width: '100%' }}
              >
                {colormaps.map(cm => (
                  <Option key={cm.value} value={cm.value}>{cm.label}</Option>
                ))}
              </Select>
            </div>
          </div>

          {/* Overlay controls */}
          {segmentationData && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <span className="text-gray-300 text-sm">Segmentation overlay:</span>
                    <Switch
                      checked={showOverlay}
                      onChange={onOverlayToggle}
                      size="small"
                    />
                  </div>
                  {showOverlay && (
                    <div className="flex items-center space-x-2">
                      <span className="text-gray-300 text-sm">Opacity:</span>
                      <Slider
                        min={0}
                        max={100}
                        value={overlayOpacity}
                        onChange={onOpacityChange}
                        style={{ width: 100 }}
                      />
                      <span className="text-gray-400 text-xs w-8">{overlayOpacity}%</span>
                    </div>
                  )}
                </div>
                
                <div className="flex items-center space-x-2">
                  <Button 
                    icon={<ZoomOutOutlined />} 
                    size="small" 
                    onClick={() => handleZoom(-25)}
                  />
                  <span className="text-gray-300 text-sm w-12 text-center">{controls.zoom}%</span>
                  <Button 
                    icon={<ZoomInOutlined />} 
                    size="small" 
                    onClick={() => handleZoom(25)}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Canvas area */}
        <div className="flex-1 relative bg-black">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 z-10">
              <div className="text-white text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-2"></div>
                <div>Loading medical image...</div>
              </div>
            </div>
          )}
          
          <canvas
            ref={canvasRef}
            width={800}
            height={600}
            className="w-full h-full cursor-crosshair"
            onMouseMove={handleMouseMove}
            style={{ 
              background: '#000000',
              display: 'block'
            }}
          />
          
          {!imageData && !isLoading && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-gray-400 text-center border-2 border-dashed border-gray-600 rounded-lg p-8 m-4">
                <div className="text-lg mb-2">Drag NIfTI file here</div>
                <div className="text-sm">or click the load button</div>
                <div className="text-xs mt-2 text-gray-500">Supports .nii, .nii.gz, .dcm formats</div>
              </div>
            </div>
          )}
          
          {/* Info overlay */}
          <div className="absolute top-2 left-2 bg-black bg-opacity-70 text-white text-xs p-2 rounded">
            <div>Coord: ({mousePosition.x}, {mousePosition.y})</div>
            {voxelValue !== null && <div>Voxel: {voxelValue}</div>}
            <div>Zoom: {controls.zoom}%</div>
            <div>Slice: {controls.slice}/{controls.maxSlice}</div>
            {loadedVolume && <div>File: {loadedVolume.name}</div>}
            <div>Status: {isInitialized ? 'Initialized' : 'Initializing'}</div>
          </div>
        </div>
      </div>
    </Card>
  );
};

export default MRIViewer;