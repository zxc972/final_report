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
import { Card, Slider, Switch, Button, Space, Tooltip, message, Select } from 'antd';
import { 
  ReloadOutlined,
  FullscreenOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  SettingOutlined
} from '@ant-design/icons';
import { Niivue, NVImage } from '@niivue/niivue';

const { Option } = Select;

interface ProfessionalMRIViewerProps {
  title: string;
  imageData?: ArrayBuffer | File | null;
  segmentationData?: ArrayBuffer | null;
  showOverlay?: boolean;
  overlayOpacity?: number;
  onOpacityChange?: (opacity: number) => void;
  onOverlayToggle?: (show: boolean) => void;
  className?: string;
}

interface ViewerControls {
  slice: number;
  maxSlice: number;
  zoom: number;
  contrast: number;
  brightness: number;
  colormap: string;
  crosshair: boolean;
  radiological: boolean;
}

const ProfessionalMRIViewer: React.FC<ProfessionalMRIViewerProps> = ({
  title,
  imageData,
  segmentationData,
  showOverlay = true,
  overlayOpacity = 50,
  onOpacityChange,
  onOverlayToggle,
  className = ''
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const niivueRef = useRef<Niivue | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadedVolumes, setLoadedVolumes] = useState<NVImage[]>([]);
  const [controls, setControls] = useState<ViewerControls>({
    slice: 0,
    maxSlice: 100,
    zoom: 1.0,
    contrast: 0.5,
    brightness: 0.5,
    colormap: 'gray',
    crosshair: true,
    radiological: false
  });

  const colormaps = [
    { value: 'gray', label: 'Gray' },
    { value: 'viridis', label: 'Viridis' },
    { value: 'plasma', label: 'Plasma' },
    { value: 'inferno', label: 'Inferno' },
    { value: 'hot', label: 'Hot' },
    { value: 'cool', label: 'Cool' },
    { value: 'jet', label: 'Jet' },
    { value: 'hsv', label: 'HSV' }
  ];

  // Initialize NiiVue
  useEffect(() => {
    const initializeNiiVue = async () => {
      const canvas = canvasRef.current;
      if (!canvas || isInitialized) return;

      try {
        // Create NiiVue instance
        const nv = new Niivue({
          backColor: [0.1, 0.1, 0.1, 1], // dark gray background
          crosshairColor: [1, 0, 0, 1],   // red crosshair
          show3Dcrosshair: true,
          multiplanarPadPixels: 4,
          multiplanarForceRender: true,
          isRadiologicalConvention: false,
          dragMode: 'pan' as any,
          isColorbar: true,
          colorbarHeight: 0.05
        });

        // Attach to canvas
        await nv.attachToCanvas(canvas);
        niivueRef.current = nv;
        setIsInitialized(true);
        
        console.log('NiiVue initialized successfully');
        message.success('Professional MRI viewer initialized successfully');
      } catch (error) {
        console.error('Failed to initialize NiiVue:', error);
        message.error('Failed to initialize MRI viewer');
      }
    };

    initializeNiiVue();
  }, [isInitialized]);

  // Load main image data
  useEffect(() => {
    if (!isInitialized || !imageData || !niivueRef.current) return;

    const loadImageData = async () => {
      setIsLoading(true);
      try {
        const nv = niivueRef.current!;
        
        let nvImage: NVImage;
        
        if (imageData instanceof File) {
          // Create NVImage from file
          nvImage = await NVImage.loadFromFile({
            file: imageData,
            name: imageData.name
          });
        } else if (imageData instanceof ArrayBuffer) {
          // Create NVImage from ArrayBuffer
          nvImage = await NVImage.loadFromUrl({
            url: '',
            buffer: imageData,
            name: 'loaded_image.nii.gz'
          });
        } else {
          throw new Error('Unsupported image data type');
        }

        // Clear previous images
        nv.volumes = [];
        
        // Add new image
        await nv.addVolume(nvImage);
        setLoadedVolumes([nvImage]);

        // Update control parameters
        const dims = nvImage.dims;
        setControls(prev => ({
          ...prev,
          maxSlice: (dims?.[2] || 1) - 1,
          slice: Math.floor((dims?.[2] || 1) / 2)
        }));

        // Set default display parameters
        nv.setSliceType(nv.sliceTypeMultiplanar);
        nv.setInterpolation(true);
        
        console.log('Image loaded successfully:', nvImage);
      } catch (error) {
        console.error('Failed to load image:', error);
        message.error(
          `Failed to load image: ${error instanceof Error ? error.message : 'Unknown error'}`
        );
      } finally {
        setIsLoading(false);
      }
    };

    loadImageData();
  }, [imageData, isInitialized]);

  // Load segmentation overlay data
  useEffect(() => {
    if (!isInitialized || !segmentationData || !niivueRef.current || loadedVolumes.length === 0) return;

    const loadSegmentationData = async () => {
      try {
        const nv = niivueRef.current!;
        
        // Create segmentation image from ArrayBuffer
        const segImage = await NVImage.loadFromUrl({
          url: '',
          buffer: segmentationData,
          name: 'segmentation.nii.gz'
        });

        // Set as overlay image
        segImage.opacity = overlayOpacity / 100;
        segImage.colormap = 'red';
        
        // Add overlay image
        await nv.addVolume(segImage);
        
        console.log('Segmentation overlay loaded successfully');
      } catch (error) {
        console.error('Failed to load segmentation:', error);
        message.error('Failed to load segmentation overlay');
      }
    };

    loadSegmentationData();
  }, [segmentationData, isInitialized, loadedVolumes, overlayOpacity]);

  // Update overlay visibility and opacity
  useEffect(() => {
    if (!niivueRef.current || loadedVolumes.length === 0) return;

    const nv = niivueRef.current;
    
    // Update opacity for all overlay images
    if (nv.volumes.length > 1) {
      for (let i = 1; i < nv.volumes.length; i++) {
        nv.volumes[i].opacity = showOverlay ? overlayOpacity / 100 : 0;
      }
      nv.updateGLVolume();
    }
  }, [showOverlay, overlayOpacity, loadedVolumes]);

  const handleControlChange = useCallback((key: keyof ViewerControls, value: number | string | boolean) => {
    setControls(prev => ({
      ...prev,
      [key]: value
    }));

    if (!niivueRef.current) return;

    const nv = niivueRef.current;

    // Apply control parameters to NiiVue
    switch (key) {
      case 'slice':
        (nv as any).setSliceMM(value as number);
        break;
      case 'zoom':
        nv.setScale(value as number);
        break;
      case 'contrast':
        if (nv.volumes.length > 0) {
          nv.volumes[0].cal_max = (nv.volumes[0].robust_max || 1) * (value as number);
          nv.updateGLVolume();
        }
        break;
      case 'brightness':
        if (nv.volumes.length > 0) {
          nv.volumes[0].cal_min = (nv.volumes[0].robust_min || 0) * (value as number);
          nv.updateGLVolume();
        }
        break;
      case 'colormap':
        if (nv.volumes.length > 0) {
          nv.volumes[0].colormap = value as string;
          nv.updateGLVolume();
        }
        break;
      case 'crosshair':
        nv.opts.show3Dcrosshair = value as boolean;
        nv.drawScene();
        break;
      case 'radiological':
        nv.opts.isRadiologicalConvention = value as boolean;
        nv.drawScene();
        break;
    }
  }, []);

  const handleReset = useCallback(() => {
    if (!niivueRef.current) return;
    
    const nv = niivueRef.current;
    nv.setScale(1.0);
    nv.scene.crosshairPos = [0.5, 0.5, 0.5];
    
    setControls(prev => ({
      ...prev,
      zoom: 1.0,
      contrast: 0.5,
      brightness: 0.5,
      slice: Math.floor(prev.maxSlice / 2)
    }));
    
    nv.drawScene();
  }, []);

  const handleFullscreen = useCallback(() => {
    if (!canvasRef.current) return;
    
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      canvasRef.current.requestFullscreen();
    }
  }, []);

  return (
    <Card 
      title={title}
      className={`h-full ${className}`}
      styles={{ body: { padding: 0, height: 'calc(100% - 57px)' } }}
      extra={
        <Space>
          <Tooltip title="Show/Hide overlay">
            <Button 
              icon={showOverlay ? <EyeOutlined /> : <EyeInvisibleOutlined />} 
              size="small" 
              onClick={() => onOverlayToggle?.(!showOverlay)}
            />
          </Tooltip>
          <Tooltip title="Reset view">
            <Button icon={<ReloadOutlined />} size="small" onClick={handleReset} />
          </Tooltip>
          <Tooltip title="Fullscreen">
            <Button icon={<FullscreenOutlined />} size="small" onClick={handleFullscreen} />
          </Tooltip>
          <Tooltip title="Settings">
            <Button icon={<SettingOutlined />} size="small" />
          </Tooltip>
        </Space>
      }
    >
      <div className="h-full flex flex-col">
        {/* Control panel */}
        <div className="flex-shrink-0 bg-white p-4 border-b border-gray-200">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Slice position</label>
              <Slider
                min={0}
                max={controls.maxSlice}
                value={controls.slice}
                onChange={(value) => handleControlChange('slice', value)}
                tooltip={{ formatter: (value) => `${value}/${controls.maxSlice}` }}
              />
            </div>
            
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Contrast</label>
              <Slider
                min={0}
                max={1}
                step={0.01}
                value={controls.contrast}
                onChange={(value) => handleControlChange('contrast', value)}
                tooltip={{ formatter: (value) => `${Math.round(value! * 100)}%` }}
              />
            </div>
            
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Brightness</label>
              <Slider
                min={0}
                max={1}
                step={0.01}
                value={controls.brightness}
                onChange={(value) => handleControlChange('brightness', value)}
                tooltip={{ formatter: (value) => `${Math.round(value! * 100)}%` }}
              />
            </div>
            
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Colormap</label>
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

          {/* Advanced controls */}
          <div className="mt-4 pt-4 border-t border-gray-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-6">
                <div className="flex items-center space-x-2">
                  <span className="text-gray-700 text-sm">Crosshair:</span>
                  <Switch
                    checked={controls.crosshair}
                    onChange={(checked) => handleControlChange('crosshair', checked)}
                    size="small"
                  />
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-gray-700 text-sm">Radiological view:</span>
                  <Switch
                    checked={controls.radiological}
                    onChange={(checked) => handleControlChange('radiological', checked)}
                    size="small"
                  />
                </div>
              </div>
              
              <div className="flex items-center space-x-2">
                <span className="text-gray-700 text-sm">Zoom:</span>
                <Slider
                  min={0.1}
                  max={5.0}
                  step={0.1}
                  value={controls.zoom}
                  onChange={(value) => handleControlChange('zoom', value)}
                  style={{ width: 100 }}
                  tooltip={{ formatter: (value) => `${Math.round(value! * 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Overlay controls */}
          {segmentationData && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <span className="text-gray-700 text-sm font-medium">Segmentation overlay:</span>
                    <Switch
                      checked={showOverlay}
                      onChange={onOverlayToggle}
                      size="small"
                    />
                  </div>
                  {showOverlay && (
                    <div className="flex items-center space-x-2">
                      <span className="text-gray-700 text-sm">Opacity:</span>
                      <Slider
                        min={0}
                        max={100}
                        value={overlayOpacity}
                        onChange={onOpacityChange}
                        style={{ width: 120 }}
                        tooltip={{ formatter: (value) => `${value}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* NiiVue canvas area */}
        <div className="flex-1 relative bg-gray-900">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 z-10">
              <div className="text-white text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-2"></div>
                <div>Loading MRI data...</div>
              </div>
            </div>
          )}
          
          <canvas
            ref={canvasRef}
            className="w-full h-full"
            style={{ 
              background: '#1f2937',
              display: 'block'
            }}
          />
          
          {!imageData && !isLoading && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-gray-400 text-center border-2 border-dashed border-gray-600 rounded-lg p-8 m-4">
                <div className="text-6xl mb-4">🧠</div>
                <div className="text-lg mb-2">Professional MRI viewer</div>
                <div className="text-sm">High-quality visualization of NIfTI medical imaging</div>
                <div className="text-xs mt-4 text-gray-500">
                  • Multiplanar reconstruction (MPR) • Volume rendering • Professional measurement tools
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

export default ProfessionalMRIViewer;