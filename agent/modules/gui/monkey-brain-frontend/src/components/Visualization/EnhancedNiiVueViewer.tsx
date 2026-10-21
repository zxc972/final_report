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
import { Card, Button, Space, Tooltip, message } from 'antd';
import {
  ReloadOutlined,
  FullscreenOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  CameraOutlined,
} from '@ant-design/icons';
import { Niivue, SLICE_TYPE, MULTIPLANAR_TYPE } from '@niivue/niivue';

interface ImageInfo {
  matrixSize: string;
  voxelSize: string;
}

interface CrosshairInfo {
  voxelCoord: string;
  worldCoord: string;
  value: number;
}

interface EnhancedNiiVueViewerProps {
  title: string;
  imageData?: ArrayBuffer | File | null;
  segmentationData?: ArrayBuffer | null;
  showOverlay?: boolean;
  overlayOpacity?: number;
  overlayColormap?: string;
  onOpacityChange?: (opacity: number) => void;
  onOverlayToggle?: (show: boolean) => void;
  className?: string;
  viewMode?: 'multiplanar' | 'axial' | 'sagittal' | 'coronal' | 'render';
}

const EnhancedNiiVueViewer: React.FC<EnhancedNiiVueViewerProps> = ({
  title,
  imageData,
  segmentationData,
  showOverlay = true,
  overlayOpacity = 50,
  overlayColormap = 'red',
  onOverlayToggle,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const niivueRef = useRef<Niivue | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [imageInfo, setImageInfo] = useState<ImageInfo | null>(null);
  const [crosshairInfo, setCrosshairInfo] = useState<CrosshairInfo | null>(null);
  const [baseVolumeLoaded, setBaseVolumeLoaded] = useState(false);
  const hasImageData =
    imageData instanceof File
      ? imageData.size > 0
      : !!imageData && imageData.byteLength > 0;

  // Initialize NiiVue
  useEffect(() => {
    const initializeNiiVue = async () => {
      const canvas = canvasRef.current;
      if (!canvas || isInitialized) return;

      try {
        const nv = new Niivue({
          backColor: [0, 0, 0, 1],
          show3Dcrosshair: true,
          crosshairColor: [1, 0, 0, 1],
          isRadiologicalConvention: false,
          multiplanarForceRender: true,
          multiplanarLayout: MULTIPLANAR_TYPE.GRID,
          isColorbar: false,
        });

        await nv.attachToCanvas(canvas);
        niivueRef.current = nv;
        setIsInitialized(true);
        console.log('NiiVue initialized');
      } catch (error) {
        console.error('Failed to initialize NiiVue:', error);
        message.error('Failed to initialize viewer');
      }
    };

    initializeNiiVue();
  }, [isInitialized]);

  // 设置位置变化监听（在初始化后）
  useEffect(() => {
    if (!isInitialized || !niivueRef.current) return;

    const nv = niivueRef.current;
    nv.onLocationChange = (data: unknown) => {
      try {
        const locationData = data as {
          vox?: number[];
          mm?: number[];
          values?: { value: number }[];
        };
        if (locationData && locationData.vox && locationData.mm) {
          const vox = locationData.vox;
          const mm = locationData.mm;
          const value = locationData.values?.[0]?.value ?? 0;
          setCrosshairInfo({
            voxelCoord: `${Math.round(vox[0])} x ${Math.round(vox[1])} x ${Math.round(vox[2])}`,
            worldCoord: `${mm[0].toFixed(2)} x ${mm[1].toFixed(2)} x ${mm[2].toFixed(2)} mm`,
            value: value,
          });
        }
      } catch (e) {
        console.warn('Error parsing location data:', e);
      }
    };
  }, [isInitialized]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (niivueRef.current && containerRef.current && canvasRef.current) {
        const container = containerRef.current;
        const canvas = canvasRef.current;
        
        // 获取容器的实际尺寸
        const rect = container.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        
        // 设置 canvas 的实际像素尺寸（考虑设备像素比）
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        
        // 设置 canvas 的 CSS 尺寸
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
        
        niivueRef.current.resizeListener();
        niivueRef.current.drawScene();
      }
    };

    // 延迟执行以确保容器已经渲染
    const timer = setTimeout(handleResize, 100);
    
    window.addEventListener('resize', handleResize);
    
    // 使用 ResizeObserver 监听容器大小变化
    const resizeObserver = new ResizeObserver(() => {
      setTimeout(handleResize, 50);
    });
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
    };
  }, [isInitialized]);

  // Load main image
  useEffect(() => {
    if (!isInitialized || !niivueRef.current) return;

    if (!hasImageData || !imageData) {
      niivueRef.current.volumes = [];
      niivueRef.current.drawScene();
      setImageInfo(null);
      setCrosshairInfo(null);
      setBaseVolumeLoaded(false);
      loadedOverlayRef.current = null;
      setIsLoading(false);
      return;
    }

    const loadImage = async () => {
      setIsLoading(true);
      setImageInfo(null);
      setCrosshairInfo(null);
      setBaseVolumeLoaded(false);
      loadedOverlayRef.current = null;

      try {
        const nv = niivueRef.current!;

        let url: string;
        if (imageData instanceof File) {
          url = URL.createObjectURL(imageData);
        } else {
          const blob = new Blob([imageData], { type: 'application/gzip' });
          url = URL.createObjectURL(blob);
        }

        await nv.loadVolumes([{ url, name: 'image.nii.gz' }]);

        // 提取图像信息
        if (nv.volumes.length > 0) {
          const vol = nv.volumes[0];
          try {
            // NiiVue volume 直接有 dims 属性
            const dims = vol.dims || [0, 0, 0, 0];
            const pixDims = vol.pixDims || [1, 1, 1, 1];
            setImageInfo({
              matrixSize: `${dims[1]} x ${dims[2]} x ${dims[3]}`,
              voxelSize: `${pixDims[1].toFixed(2)} x ${pixDims[2].toFixed(2)} x ${pixDims[3].toFixed(2)}`,
            });
          } catch (e) {
            console.warn('Could not extract image info:', e);
          }
        }

        nv.setSliceType(SLICE_TYPE.MULTIPLANAR);

        URL.revokeObjectURL(url);
        console.log('Image loaded with 4-view layout');
        setBaseVolumeLoaded(true);
      } catch (error) {
        console.error('Failed to load image:', error);
        message.error('Failed to load image');
      } finally {
        setIsLoading(false);
      }
    };

    loadImage();
  }, [imageData, isInitialized, hasImageData]);

  // Track loaded overlay data to avoid reloading
  const loadedOverlayRef = useRef<ArrayBuffer | null>(null);

  // Load segmentation overlay (when segmentationData changes, or once the base volume finishes loading)
  useEffect(() => {
    if (!isInitialized || !segmentationData || !niivueRef.current) return;
    if (!baseVolumeLoaded || niivueRef.current.volumes.length === 0) return;

    // Skip if same overlay data is already loaded
    if (loadedOverlayRef.current === segmentationData) return;

    const loadOverlay = async () => {
      try {
        const nv = niivueRef.current!;
        
        // 先移除已有的 overlay（保留第一个 volume 即底图）
        while (nv.volumes.length > 1) {
          nv.removeVolumeByIndex(1);
        }
        
        const blob = new Blob([segmentationData], { type: 'application/gzip' });
        const url = URL.createObjectURL(blob);

        // 使用 addVolumeFromUrl 添加 overlay，而不是 loadVolumes
        await nv.addVolumeFromUrl({
          url,
          name: 'overlay.nii.gz',
          colormap: overlayColormap,
          opacity: showOverlay ? overlayOpacity / 100 : 0,
          cal_min: 0.1,
        });
        
        loadedOverlayRef.current = segmentationData;
        nv.updateGLVolume();
        URL.revokeObjectURL(url);
        console.log('Overlay loaded on top of base image');
      } catch (error) {
        console.error('Failed to load overlay:', error);
      }
    };

    loadOverlay();
  }, [segmentationData, isInitialized, baseVolumeLoaded]); // 不再依赖 overlayOpacity

  // Update overlay opacity and colormap smoothly (without reloading)
  useEffect(() => {
    if (!niivueRef.current || niivueRef.current.volumes.length < 2) return;
    
    const nv = niivueRef.current;
    for (let i = 1; i < nv.volumes.length; i++) {
      nv.volumes[i].opacity = showOverlay ? overlayOpacity / 100 : 0;
      nv.volumes[i].colormap = overlayColormap;
    }
    nv.updateGLVolume();
  }, [showOverlay, overlayOpacity, overlayColormap]);

  const handleReset = useCallback(() => {
    if (!niivueRef.current) return;
    const nv = niivueRef.current;
    nv.setScale(1.0);
    if (nv.scene) {
      nv.scene.crosshairPos = [0.5, 0.5, 0.5];
    }
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

  const handleScreenshot = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const link = document.createElement('a');
    link.download = `screenshot_${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
    message.success('Screenshot saved');
  }, []);

  return (
    <Card 
      title={title}
      className={`h-full ${className}`}
      styles={{ body: { padding: 0, height: 'calc(100% - 57px)' } }}
      extra={
        <Space>
          {segmentationData && (
            <Tooltip title="Toggle overlay">
              <Button 
                icon={showOverlay ? <EyeOutlined /> : <EyeInvisibleOutlined />} 
                size="small" 
                onClick={() => onOverlayToggle?.(!showOverlay)}
              />
            </Tooltip>
          )}
          <Tooltip title="Screenshot">
            <Button icon={<CameraOutlined />} size="small" onClick={handleScreenshot} disabled={!hasImageData} />
          </Tooltip>
          <Tooltip title="Reset">
            <Button icon={<ReloadOutlined />} size="small" onClick={handleReset} disabled={!hasImageData} />
          </Tooltip>
          <Tooltip title="Fullscreen">
            <Button icon={<FullscreenOutlined />} size="small" onClick={handleFullscreen} disabled={!hasImageData} />
          </Tooltip>
        </Space>
      }
    >
      <div ref={containerRef} className="h-full relative bg-black">
        {/* 顶部图像信息 */}
        {imageInfo && (
          <div className="absolute top-2 left-2 z-20 text-white text-xs font-mono bg-black bg-opacity-50 px-2 py-1 rounded">
            matrix size: {imageInfo.matrixSize}, voxel size: {imageInfo.voxelSize} mm
          </div>
        )}

        {hasImageData && isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black z-10">
            <div className="text-white text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-white mx-auto mb-3"></div>
              <div>Loading...</div>
            </div>
          </div>
        )}

        <canvas
          ref={canvasRef}
          style={{
            display: hasImageData ? 'block' : 'none',
            width: '100%',
            height: '100%',
          }}
        />

        {/* 底部十字光标位置信息 */}
        {crosshairInfo && hasImageData && (
          <div className="absolute bottom-2 left-2 z-20 text-white text-xs font-mono bg-black bg-opacity-50 px-2 py-1 rounded">
            <div>{crosshairInfo.voxelCoord}: {crosshairInfo.value.toFixed(2)}</div>
            <div>{crosshairInfo.worldCoord}</div>
          </div>
        )}

        {!hasImageData && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50">
            <div className="text-gray-500 text-center">
              <div className="px-blocker-icon" style={{ marginBottom: 12 }}>◎</div>
              <div className="font-medium text-gray-600">No image loaded</div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};

export default EnhancedNiiVueViewer;
