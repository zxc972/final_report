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
import { Card, Slider, Switch, Button, Space, Tooltip, message } from 'antd';
import { 
  ReloadOutlined,
  EyeOutlined,
  EyeInvisibleOutlined
} from '@ant-design/icons';
import { SimpleNiftiParser, NiftiData } from '../../utils/niftiParser';

interface MultiViewMRIViewerProps {
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
  axialSlice: number;
  sagittalSlice: number;
  coronalSlice: number;
  maxSlices: { axial: number; sagittal: number; coronal: number };
  zoom: number;
  contrast: number;
  brightness: number;
  colormap: string;
}

const MultiViewMRIViewer: React.FC<MultiViewMRIViewerProps> = ({
  title,
  imageData,
  segmentationData,
  showOverlay = true,
  overlayOpacity = 50,
  onOpacityChange,
  onOverlayToggle,
  className = ''
}) => {
  const axialCanvasRef = useRef<HTMLCanvasElement>(null);
  const sagittalCanvasRef = useRef<HTMLCanvasElement>(null);
  const coronalCanvasRef = useRef<HTMLCanvasElement>(null);
  const renderCanvasRef = useRef<HTMLCanvasElement>(null);

  const [niftiData, setNiftiData] = useState<NiftiData | null>(null);
  const [segmentationNiftiData, setSegmentationNiftiData] = useState<NiftiData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [controls, setControls] = useState<ViewerControls>({
    axialSlice: 64,
    sagittalSlice: 64,
    coronalSlice: 64,
    maxSlices: { axial: 128, sagittal: 128, coronal: 128 },
    zoom: 100,
    contrast: 50,
    brightness: 50,
    colormap: 'gray'
  });

  // Load main image data
  useEffect(() => {
    if (!imageData) return;

    const loadImageData = async () => {
      setIsLoading(true);
      try {
        let parsedData: NiftiData;
        
        if (imageData instanceof File) {
          parsedData = await SimpleNiftiParser.parseFile(imageData);
        } else if (imageData instanceof ArrayBuffer) {
          parsedData = SimpleNiftiParser.parseBuffer(imageData);
        } else {
          throw new Error('Unsupported image data type');
        }

        setNiftiData(parsedData);
        
        // Update slice control ranges
        const { width, height, depth } = SimpleNiftiParser.getDimensions(parsedData);
        setControls(prev => ({
          ...prev,
          axialSlice: Math.floor(depth / 2),
          sagittalSlice: Math.floor(width / 2),
          coronalSlice: Math.floor(height / 2),
          maxSlices: {
            axial: depth - 1,
            sagittal: width - 1,
            coronal: height - 1
          }
        }));

        // MRI data loaded successfully (removed message to prevent spam)
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
  }, [imageData]);

  // Load segmentation data
  useEffect(() => {
    if (!segmentationData) {
      setSegmentationNiftiData(null);
      return;
    }

    const loadSegmentationData = async () => {
      try {
        const parsedData = SimpleNiftiParser.parseBuffer(segmentationData);
        setSegmentationNiftiData(parsedData);
        // Segmentation data loaded successfully (removed message to prevent spam)
      } catch (error) {
        console.error('Failed to load segmentation:', error);
        message.error('Failed to load segmentation data');
      }
    };

    loadSegmentationData();
  }, [segmentationData]);

  // Render axial slice
  const renderAxialSlice = useCallback((canvas: HTMLCanvasElement, sliceIndex: number) => {
    if (!niftiData || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
      const imageData = SimpleNiftiParser.extractSlice(niftiData, sliceIndex);
      if (imageData) {
        // Clear canvas
        ctx.fillStyle = '#1f2937';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Compute scale
        const { width, height } = SimpleNiftiParser.getDimensions(niftiData);
        const scale = Math.min(canvas.width / width, canvas.height / height);
        const displayWidth = width * scale;
        const displayHeight = height * scale;
        const offsetX = (canvas.width - displayWidth) / 2;
        const offsetY = (canvas.height - displayHeight) / 2;

        // Create temp canvas
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = width;
        tempCanvas.height = height;
        const tempCtx = tempCanvas.getContext('2d');
        
        if (tempCtx) {
          tempCtx.putImageData(imageData, 0, 0);
          ctx.drawImage(tempCanvas, offsetX, offsetY, displayWidth, displayHeight);
        }

        // Overlay segmentation
        if (showOverlay && segmentationNiftiData) {
          const segImageData = SimpleNiftiParser.extractSlice(segmentationNiftiData, sliceIndex);
          if (segImageData) {
            const overlayCanvas = document.createElement('canvas');
            overlayCanvas.width = width;
            overlayCanvas.height = height;
            const overlayCtx = overlayCanvas.getContext('2d');
            
            if (overlayCtx) {
              overlayCtx.putImageData(segImageData, 0, 0);
              
              // Apply green tint and opacity
              overlayCtx.globalCompositeOperation = 'source-atop';
              overlayCtx.fillStyle = `rgba(0, 255, 0, ${overlayOpacity / 100})`;
              overlayCtx.fillRect(0, 0, width, height);
              
              ctx.globalAlpha = overlayOpacity / 100;
              ctx.drawImage(overlayCanvas, offsetX, offsetY, displayWidth, displayHeight);
              ctx.globalAlpha = 1.0;
            }
          }
        }

        // Draw slice info
        ctx.fillStyle = '#e5e7eb';
        ctx.font = '12px Arial';
        ctx.textAlign = 'left';
        ctx.fillText(
          `Axial: ${sliceIndex + 1}/${controls.maxSlices.axial + 1}`,
          5,
          15
        );
      }
    } catch (error) {
      console.error('Failed to render axial slice:', error);
    }
  }, [niftiData, segmentationNiftiData, showOverlay, overlayOpacity, controls.maxSlices.axial]);

  // Render sagittal slice (re-arrange data)
  const renderSagittalSlice = useCallback((canvas: HTMLCanvasElement, sliceIndex: number) => {
    if (!niftiData || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
      const { width, height, depth } = SimpleNiftiParser.getDimensions(niftiData);
      const { imageData } = niftiData;

      // Create sagittal image data
      const sagittalImageData = ctx.createImageData(depth, height);
      const pixels = sagittalImageData.data;

      // Extract sagittal data
      for (let z = 0; z < depth; z++) {
        for (let y = 0; y < height; y++) {
          const dataIndex = z * width * height + y * width + sliceIndex;
          const pixelIndex = (y * depth + z) * 4;
          
          let value = 0;
          if (dataIndex < imageData.length) {
            const rawValue = imageData[dataIndex];
            // Apply scale and offset
            const scaledValue =
              rawValue * niftiData.header.scl_slope +
              niftiData.header.scl_inter;
            // Dynamic normalization
            value = Math.floor((scaledValue / 4096) * 255);
            value = Math.max(0, Math.min(255, value));
          }
          
          pixels[pixelIndex] = value;     // R
          pixels[pixelIndex + 1] = value; // G
          pixels[pixelIndex + 2] = value; // B
          pixels[pixelIndex + 3] = 255;   // A
        }
      }

      // Clear canvas and draw
      ctx.fillStyle = '#1f2937';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const scale = Math.min(canvas.width / depth, canvas.height / height);
      const displayWidth = depth * scale;
      const displayHeight = height * scale;
      const offsetX = (canvas.width - displayWidth) / 2;
      const offsetY = (canvas.height - displayHeight) / 2;

      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = depth;
      tempCanvas.height = height;
      const tempCtx = tempCanvas.getContext('2d');
      
      if (tempCtx) {
        tempCtx.putImageData(sagittalImageData, 0, 0);
        ctx.drawImage(tempCanvas, offsetX, offsetY, displayWidth, displayHeight);
      }

      // Draw slice info
      ctx.fillStyle = '#e5e7eb';
      ctx.font = '12px Arial';
      ctx.textAlign = 'left';
      ctx.fillText(
        `Sagittal: ${sliceIndex + 1}/${controls.maxSlices.sagittal + 1}`,
        5,
        15
      );
    } catch (error) {
      console.error('Failed to render sagittal slice:', error);
    }
  }, [niftiData, controls.maxSlices.sagittal]);

  // Render coronal slice
  const renderCoronalSlice = useCallback((canvas: HTMLCanvasElement, sliceIndex: number) => {
    if (!niftiData || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
      const { width, height, depth } = SimpleNiftiParser.getDimensions(niftiData);
      const { imageData } = niftiData;

      // Create coronal image data
      const coronalImageData = ctx.createImageData(width, depth);
      const pixels = coronalImageData.data;

      // Extract coronal data
      for (let z = 0; z < depth; z++) {
        for (let x = 0; x < width; x++) {
          const dataIndex = z * width * height + sliceIndex * width + x;
          const pixelIndex = (z * width + x) * 4;
          
          let value = 0;
          if (dataIndex < imageData.length) {
            const rawValue = imageData[dataIndex];
            // Apply scale and offset
            const scaledValue =
              rawValue * niftiData.header.scl_slope +
              niftiData.header.scl_inter;
            // Dynamic normalization
            value = Math.floor((scaledValue / 4096) * 255);
            value = Math.max(0, Math.min(255, value));
          }
          
          pixels[pixelIndex] = value;     // R
          pixels[pixelIndex + 1] = value; // G
          pixels[pixelIndex + 2] = value; // B
          pixels[pixelIndex + 3] = 255;   // A
        }
      }

      // Clear canvas and draw
      ctx.fillStyle = '#1f2937';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const scale = Math.min(canvas.width / width, canvas.height / depth);
      const displayWidth = width * scale;
      const displayHeight = depth * scale;
      const offsetX = (canvas.width - displayWidth) / 2;
      const offsetY = (canvas.height - displayHeight) / 2;

      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = width;
      tempCanvas.height = depth;
      const tempCtx = tempCanvas.getContext('2d');
      
      if (tempCtx) {
        tempCtx.putImageData(coronalImageData, 0, 0);
        ctx.drawImage(tempCanvas, offsetX, offsetY, displayWidth, displayHeight);
      }

      // Draw slice info
      ctx.fillStyle = '#e5e7eb';
      ctx.font = '12px Arial';
      ctx.textAlign = 'left';
      ctx.fillText(
        `Coronal: ${sliceIndex + 1}/${controls.maxSlices.coronal + 1}`,
        5,
        15
      );
    } catch (error) {
      console.error('Failed to render coronal slice:', error);
    }
  }, [niftiData, controls.maxSlices.coronal]);

  // Render 3D view (simplified)
  const render3DView = useCallback((canvas: HTMLCanvasElement) => {
    if (!niftiData || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Simple 3D rendering placeholder
    ctx.fillStyle = '#1f2937';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    ctx.fillStyle = '#9ca3af';
    ctx.font = '16px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('3D rendering view', canvas.width / 2, canvas.height / 2 - 10);
    ctx.fillText('(under development)', canvas.width / 2, canvas.height / 2 + 15);
  }, [niftiData]);

  // Update all views
  const updateAllViews = useCallback(() => {
    if (axialCanvasRef.current) {
      renderAxialSlice(axialCanvasRef.current, controls.axialSlice);
    }
    if (sagittalCanvasRef.current) {
      renderSagittalSlice(sagittalCanvasRef.current, controls.sagittalSlice);
    }
    if (coronalCanvasRef.current) {
      renderCoronalSlice(coronalCanvasRef.current, controls.coronalSlice);
    }
    if (renderCanvasRef.current) {
      render3DView(renderCanvasRef.current);
    }
  }, [controls, renderAxialSlice, renderSagittalSlice, renderCoronalSlice, render3DView]);

  // Update views when data or controls change
  useEffect(() => {
    updateAllViews();
  }, [updateAllViews]);

  const handleControlChange = useCallback((key: keyof ViewerControls, value: number | string) => {
    setControls(prev => ({
      ...prev,
      [key]: value
    }));
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
            <Button icon={<ReloadOutlined />} size="small" />
          </Tooltip>
        </Space>
      }
    >
      <div className="h-full flex flex-col">
        {/* Control panel */}
        <div className="flex-shrink-0 bg-white p-4 border-b border-gray-200 shadow-sm">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Axial slice</label>
              <Slider
                min={0}
                max={controls.maxSlices.axial}
                value={controls.axialSlice}
                onChange={(value) => handleControlChange('axialSlice', value)}
                tooltip={{ formatter: (value) => `${value}/${controls.maxSlices.axial}` }}
              />
            </div>
            
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Sagittal slice</label>
              <Slider
                min={0}
                max={controls.maxSlices.sagittal}
                value={controls.sagittalSlice}
                onChange={(value) => handleControlChange('sagittalSlice', value)}
                tooltip={{ formatter: (value) => `${value}/${controls.maxSlices.sagittal}` }}
              />
            </div>
            
            <div>
              <label className="text-gray-700 block mb-1 font-medium">Coronal slice</label>
              <Slider
                min={0}
                max={controls.maxSlices.coronal}
                value={controls.coronalSlice}
                onChange={(value) => handleControlChange('coronalSlice', value)}
                tooltip={{ formatter: (value) => `${value}/${controls.maxSlices.coronal}` }}
              />
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
              </div>
            </div>
          )}
        </div>

        {/* Four-view display area */}
        <div className="flex-1 grid grid-cols-2 gap-3 p-3 bg-gray-50">
          {/* Axial view */}
          <div className="relative bg-gray-900 rounded-lg border border-gray-300 shadow-sm">
            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 z-10">
                <div className="text-white text-center">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white mx-auto mb-2"></div>
                  <div className="text-sm">Loading...</div>
                </div>
              </div>
            )}
            <canvas
              ref={axialCanvasRef}
              width={400}
              height={300}
              className="w-full h-full cursor-crosshair"
              style={{ background: '#1f2937' }}
            />
          </div>

          {/* Sagittal view */}
          <div className="relative bg-gray-900 rounded-lg border border-gray-300 shadow-sm">
            <canvas
              ref={sagittalCanvasRef}
              width={400}
              height={300}
              className="w-full h-full cursor-crosshair rounded-lg"
              style={{ background: '#1f2937' }}
            />
          </div>

          {/* Coronal view */}
          <div className="relative bg-gray-900 rounded-lg border border-gray-300 shadow-sm">
            <canvas
              ref={coronalCanvasRef}
              width={400}
              height={300}
              className="w-full h-full cursor-crosshair rounded-lg"
              style={{ background: '#1f2937' }}
            />
          </div>

          {/* 3D rendering view */}
          <div className="relative bg-gray-900 rounded-lg border border-gray-300 shadow-sm">
            <canvas
              ref={renderCanvasRef}
              width={400}
              height={300}
              className="w-full h-full cursor-crosshair rounded-lg"
              style={{ background: '#1f2937' }}
            />
          </div>
        </div>
      </div>
    </Card>
  );
};

export default MultiViewMRIViewer;