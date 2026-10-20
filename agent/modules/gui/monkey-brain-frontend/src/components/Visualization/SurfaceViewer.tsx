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
  CameraOutlined,
} from '@ant-design/icons';
import { Niivue } from '@niivue/niivue';

interface SurfaceViewerProps {
  title: string;
  surfaceData?: ArrayBuffer | null;
  surfaceDataRight?: ArrayBuffer | null; // For both hemispheres
  surfaceName?: string;
  className?: string;
}

const SurfaceViewer: React.FC<SurfaceViewerProps> = ({
  title,
  surfaceData,
  surfaceDataRight,
  surfaceName = 'surface.gii',
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const niivueRef = useRef<Niivue | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [meshInfo, setMeshInfo] = useState<string | null>(null);
  const hasSurfaceData = !!surfaceData && surfaceData.byteLength > 0;

  // Initialize NiiVue for mesh rendering
  useEffect(() => {
    const initializeNiiVue = async () => {
      const canvas = canvasRef.current;
      if (!canvas || isInitialized) return;

      try {
        const nv = new Niivue({
          backColor: [0.1, 0.1, 0.15, 1], // Dark blue-gray background
          show3Dcrosshair: false,
          isColorbar: false,
        });

        await nv.attachToCanvas(canvas);
        niivueRef.current = nv;
        setIsInitialized(true);
        console.log('NiiVue Surface Viewer initialized');
      } catch (error) {
        console.error('Failed to initialize NiiVue:', error);
        message.error('Failed to initialize surface viewer');
      }
    };

    initializeNiiVue();
  }, [isInitialized]);


  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (niivueRef.current && containerRef.current && canvasRef.current) {
        const container = containerRef.current;
        const canvas = canvasRef.current;

        const rect = container.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;

        niivueRef.current.resizeListener();
        niivueRef.current.drawScene();
      }
    };

    const timer = setTimeout(handleResize, 100);
    window.addEventListener('resize', handleResize);

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

  // Load surface mesh
  useEffect(() => {
    if (!isInitialized || !niivueRef.current) return;

    if (!hasSurfaceData) {
      niivueRef.current.meshes = [];
      niivueRef.current.drawScene();
      setMeshInfo(null);
      setIsLoading(false);
      return;
    }

    const loadSurface = async () => {
      setIsLoading(true);
      setMeshInfo(null);

      try {
        const nv = niivueRef.current!;

        // Clear existing meshes
        nv.meshes = [];

        // Create blob URL for left hemisphere - white color
        const blobL = new Blob([surfaceData], {
          type: 'application/octet-stream',
        });
        const urlL = URL.createObjectURL(blobL);

        const meshesToLoad = [{ url: urlL, name: surfaceName, rgba255: [255, 255, 255, 255] }];

        // If right hemisphere data is provided, add it - slightly different shade
        if (surfaceDataRight) {
          const blobR = new Blob([surfaceDataRight], {
            type: 'application/octet-stream',
          });
          const urlR = URL.createObjectURL(blobR);
          meshesToLoad.push({
            url: urlR,
            name: surfaceName.replace('.L.', '.R.'),
            rgba255: [240, 240, 255, 255], // Slightly blue tint for right hemisphere
          });
        }

        await nv.loadMeshes(meshesToLoad);

        // Get mesh info
        if (nv.meshes.length > 0) {
          const mesh = nv.meshes[0];
          const vertexCount = mesh.pts ? mesh.pts.length / 3 : 0;
          const faceCount = mesh.tris ? mesh.tris.length / 3 : 0;
          setMeshInfo(`Vertices: ${vertexCount.toLocaleString()}, Faces: ${faceCount.toLocaleString()}`);
        }

        // Cleanup URLs
        URL.revokeObjectURL(urlL);

        console.log('Surface loaded:', surfaceName);
      } catch (error) {
        console.error('Failed to load surface:', error);
        message.error('Failed to load surface');
      } finally {
        setIsLoading(false);
      }
    };

    loadSurface();
  }, [surfaceData, surfaceDataRight, surfaceName, isInitialized, hasSurfaceData]);

  const handleReset = useCallback(() => {
    if (!niivueRef.current) return;
    const nv = niivueRef.current;
    nv.setScale(1.0);
    nv.scene.renderAzimuth = 110;
    nv.scene.renderElevation = 10;
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
    link.download = `surface_${Date.now()}.png`;
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
          <Tooltip title="Screenshot">
            <Button
              icon={<CameraOutlined />}
              size="small"
              onClick={handleScreenshot}
              disabled={!hasSurfaceData}
            />
          </Tooltip>
          <Tooltip title="Reset View">
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={handleReset}
              disabled={!hasSurfaceData}
            />
          </Tooltip>
          <Tooltip title="Fullscreen">
            <Button
              icon={<FullscreenOutlined />}
              size="small"
              onClick={handleFullscreen}
              disabled={!hasSurfaceData}
            />
          </Tooltip>
        </Space>
      }
    >
      <div ref={containerRef} className="h-full relative bg-gray-900">
        {/* Mesh info */}
        {meshInfo && (
          <div className="absolute top-2 left-2 z-20 text-white text-xs font-mono bg-black bg-opacity-50 px-2 py-1 rounded">
            {meshInfo}
          </div>
        )}

        {hasSurfaceData && isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-900 z-10">
            <div className="text-white text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-white mx-auto mb-3"></div>
              <div>Loading surface...</div>
            </div>
          </div>
        )}

        <canvas
          ref={canvasRef}
          style={{
            display: hasSurfaceData ? 'block' : 'none',
            width: '100%',
            height: '100%',
          }}
        />

        {!hasSurfaceData && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50">
            <div className="text-gray-400 text-center">
              <div className="text-4xl mb-3">🧬</div>
              <div className="font-medium text-gray-600">No surface result available</div>
              <div className="text-xs mt-2">Select another surface type, hemisphere, or resolution.</div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};

export default SurfaceViewer;
