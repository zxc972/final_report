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

// import { Niivue, NVImage } from '@niivue/niivue';
import { SimpleNiftiParser, NiftiData } from '../utils/niftiParser';

export interface NiftiVolume {
  id: string;
  name: string;
  image: any; // NVImage;
  niftiData?: NiftiData; // Parsed NIfTI data
  isSegmentation?: boolean;
}

export interface ViewerState {
  volumes: NiftiVolume[];
  currentSlice: number;
  maxSlice: number;
  zoom: number;
  contrast: number;
  brightness: number;
  colormap: string;
  overlayOpacity: number;
  showOverlay: boolean;
}

export class NiftiService {
  private niivue: any | null = null; // Niivue | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private currentVolume: NiftiVolume | null = null;
  private currentSlice: number = 0;

  constructor() {
    // Initialize with default options
  }

  async initialize(canvas: HTMLCanvasElement): Promise<void> {
    this.canvas = canvas;
    
    // Temporarily use a simplified version while waiting for the NiiVue library installation
    console.log('NiftiService initialized with canvas:', canvas);
    
    // Draw placeholder
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      ctx.fillStyle = '#666';
      ctx.font = '16px Arial';
      ctx.textAlign = 'center';
      ctx.fillText('NiiVue library is loading...', canvas.width / 2, canvas.height / 2 - 10);
      ctx.fillText('Please wait or manually install @niivue/niivue', canvas.width / 2, canvas.height / 2 + 15);
    }
  }

  async loadNiftiFile(file: File): Promise<NiftiVolume> {
    console.log('Loading NIfTI file:', file.name);
    
    try {
      // Parse NIfTI file
      const niftiData = await SimpleNiftiParser.parseFile(file);
      console.log('NIfTI data parsed:', niftiData.header);
      
      const volume: NiftiVolume = {
        id: `volume_${Date.now()}`,
        name: file.name,
        image: null,
        niftiData: niftiData,
        isSegmentation: false
      };

      this.currentVolume = volume;
      this.currentSlice = Math.floor(niftiData.header.dims[3] / 2); // Start from the middle slice

      // Render the first slice
      this.renderSlice();

      return volume;
    } catch (error) {
      console.error('Failed to parse NIfTI file:', error);
      
      // If parsing fails, display an error message
      if (this.canvas) {
        const ctx = this.canvas.getContext('2d');
        if (ctx) {
          ctx.fillStyle = '#1a1a1a';
          ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
          
          ctx.fillStyle = '#ff4444';
          ctx.font = '16px Arial';
          ctx.textAlign = 'center';
          ctx.fillText(`Parsing failed: ${file.name}`, this.canvas.width / 2, this.canvas.height / 2 - 10);
          ctx.fillText('This may not be a valid NIfTI file', this.canvas.width / 2, this.canvas.height / 2 + 15);
        }
      }

      // Return basic info
      const volume: NiftiVolume = {
        id: `volume_${Date.now()}`,
        name: file.name,
        image: null,
        isSegmentation: false
      };

      return volume;
    }
  }

  async loadFromArrayBuffer(buffer: ArrayBuffer, filename: string): Promise<NiftiVolume> {
    console.log('Loading NIfTI from buffer:', filename, 'Size:', buffer.byteLength);
    
    const volume: NiftiVolume = {
      id: `volume_${Date.now()}`,
      name: filename,
      image: null,
      isSegmentation: false
    };

    // Draw a message indicating successful data loading
    if (this.canvas) {
      const ctx = this.canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        ctx.fillStyle = '#4CAF50';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(`Data loaded: ${filename}`, this.canvas.width / 2, this.canvas.height / 2 - 10);
        ctx.fillText(`Size: ${(buffer.byteLength / 1024 / 1024).toFixed(2)} MB`, this.canvas.width / 2, this.canvas.height / 2 + 15);
      }
    }

    return volume;
  }

  async addSegmentationOverlay(segmentationData: ArrayBuffer, filename: string): Promise<NiftiVolume> {
    console.log('Adding segmentation overlay:', filename, 'Size:', segmentationData.byteLength);
    
    const volume: NiftiVolume = {
      id: `segmentation_${Date.now()}`,
      name: filename,
      image: null,
      isSegmentation: true
    };

    return volume;
  }

  private renderSlice(): void {
    if (!this.canvas || !this.currentVolume?.niftiData) return;

    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;

    try {
      // Extract current slice
      const imageData = SimpleNiftiParser.extractSlice(
        this.currentVolume.niftiData, 
        this.currentSlice
      );

      if (imageData) {
        // Clear canvas
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Compute scale to fit canvas
        const { width, height } = SimpleNiftiParser.getDimensions(this.currentVolume.niftiData);
        const scaleX = this.canvas.width / width;
        const scaleY = this.canvas.height / height;
        const scale = Math.min(scaleX, scaleY);

        const displayWidth = width * scale;
        const displayHeight = height * scale;
        const offsetX = (this.canvas.width - displayWidth) / 2;
        const offsetY = (this.canvas.height - displayHeight) / 2;

        // Create a temporary canvas to draw image data
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = width;
        tempCanvas.height = height;
        const tempCtx = tempCanvas.getContext('2d');
        
        if (tempCtx) {
          tempCtx.putImageData(imageData, 0, 0);
          
          // Draw the temporary canvas onto the main canvas with scaling
          ctx.drawImage(tempCanvas, offsetX, offsetY, displayWidth, displayHeight);
        }

        // Draw slice information
        ctx.fillStyle = '#ffffff';
        ctx.font = '14px Arial';
        ctx.textAlign = 'left';
        const sliceCount = SimpleNiftiParser.getSliceCount(this.currentVolume.niftiData);
        ctx.fillText(`Slice: ${this.currentSlice + 1}/${sliceCount}`, 10, 25);
        ctx.fillText(`Size: ${width} × ${height}`, 10, 45);
        ctx.fillText(`File: ${this.currentVolume.name}`, 10, 65);
      }
    } catch (error) {
      console.error('Failed to render slice:', error);
      
      // Display error message
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      
      ctx.fillStyle = '#ff4444';
      ctx.font = '16px Arial';
      ctx.textAlign = 'center';
      ctx.fillText('Failed to render slice', this.canvas.width / 2, this.canvas.height / 2);
    }
  }

  setSlice(sliceIndex: number): void {
    if (!this.currentVolume?.niftiData) return;
    
    const sliceCount = SimpleNiftiParser.getSliceCount(this.currentVolume.niftiData);
    this.currentSlice = Math.max(0, Math.min(sliceIndex, sliceCount - 1));
    this.renderSlice();
    console.log('Setting slice:', this.currentSlice);
  }

  setZoom(zoom: number): void {
    console.log('Setting zoom:', zoom);
  }

  setContrast(contrast: number): void {
    console.log('Setting contrast:', contrast);
  }

  setBrightness(brightness: number): void {
    console.log('Setting brightness:', brightness);
  }

  setColormap(colormap: string): void {
    console.log('Setting colormap:', colormap);
  }

  setOverlayOpacity(opacity: number): void {
    console.log('Setting overlay opacity:', opacity);
  }

  setOverlayVisibility(visible: boolean): void {
    console.log('Setting overlay visibility:', visible);
  }

  getCurrentSliceInfo(): { current: number; max: number } {
    if (!this.currentVolume?.niftiData) {
      return { current: 0, max: 0 };
    }
    
    const sliceCount = SimpleNiftiParser.getSliceCount(this.currentVolume.niftiData);
    return { 
      current: this.currentSlice, 
      max: sliceCount - 1 
    };
  }

  getVoxelValue(x: number, y: number): number | null {
    if (!this.currentVolume?.niftiData || !this.canvas) return null;

    try {
      const { width, height } = SimpleNiftiParser.getDimensions(this.currentVolume.niftiData);
      
      // Compute coordinates in the original image
      const scaleX = this.canvas.width / width;
      const scaleY = this.canvas.height / height;
      const scale = Math.min(scaleX, scaleY);
      
      const displayWidth = width * scale;
      const displayHeight = height * scale;
      const offsetX = (this.canvas.width - displayWidth) / 2;
      const offsetY = (this.canvas.height - displayHeight) / 2;
      
      // Convert to image coordinates
      const imageX = Math.floor((x - offsetX) / scale);
      const imageY = Math.floor((y - offsetY) / scale);
      
      if (imageX >= 0 && imageX < width && imageY >= 0 && imageY < height) {
        const { imageData } = this.currentVolume.niftiData;
        const sliceSize = width * height;
        const index = this.currentSlice * sliceSize + imageY * width + imageX;
        
        if (index < imageData.length) {
          return imageData[index];
        }
      }
      
      return null;
    } catch (error) {
      console.error('Error getting voxel value:', error);
      return null;
    }
  }

  resetView(): void {
    console.log('Resetting view');
  }

  removeAllOverlays(): void {
    console.log('Removing all overlays');
  }

  saveVolume(volumeIndex: number = 0, filename?: string): void {
    console.log('Saving volume:', volumeIndex, filename);
  }

  destroy(): void {
    if (this.niivue) {
      // Clean up resources
      this.niivue = null;
    }
    this.canvas = null;
  }
}

// Export a singleton instance
export const niftiService = new NiftiService();