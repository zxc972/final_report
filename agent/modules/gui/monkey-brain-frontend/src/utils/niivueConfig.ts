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

import { Niivue, NVImage } from '@niivue/niivue';

/**
 * NiiVue configuration utility
 * Specialized for brain segmentation visualization optimization
 */
export class NiiVueConfig {
  /**
   * Create a professional brain image viewer configuration
   */
  static createBrainViewerConfig() {
    return {
      backColor: [0.05, 0.05, 0.1, 1], // Dark blue background, professional medical display
      crosshairColor: [1, 0.2, 0.2, 1], // Red crosshair, clearly visible
      show3Dcrosshair: true,
      multiplanarPadPixels: 8, // Increased padding for better visual effect
      multiplanarForceRender: true,
      isRadiologicalConvention: false, // Default neurological view
      isColorbar: true,
      colorbarHeight: 0.06,
      colorbarMargin: 0.02,
      textHeight: 0.03,
      crosshairWidth: 2,
      rulerWidth: 2,
      isRuler: true,
      meshThicknessOn2D: 0.8,
      keyDebounceTime: 50,
      doubleClickTimeout: 500,
      longTouchTimeout: 1000,
      loadingText: 'Loading medical image...',
      dragAndDropEnabled: true,
      drawingEnabled: false,
      penValue: 1,
      floodFillNeighbors: 6,
      isNearestInterpolation: true, // Use nearest neighbor interpolation to preserve medical image sharpness
      isResizeCanvas: true,
      trustCalMinMax: false, // Automatically compute display range
      
      // Medical imaging specific settings - preserve sharpness
      sliceType: 4 // Multiplanar reconstruction mode
    };
  }

  /**
   * Create optimized configuration for segmentation overlay
   */
  static createSegmentationOverlayConfig(opacity: number = 0.5) {
    return {
      opacity: opacity,
      colormap: 'red', // Use red to highlight segmentation regions
      cal_min: 0.1, // Set a minimum threshold to avoid background noise
      cal_max: undefined, // Automatically compute max
      useQFormNotSForm: false,
      colormapNegative: '',
      frame4D: 0,
      imageType: 1, // Overlay image type
      trustCalMinMax: false
    };
  }

  /**
   * Optimize image display parameters
   */
  static optimizeImageDisplay(nvImage: NVImage, imageType: 'T1' | 'T2' | 'FLAIR' | 'segmentation' = 'T1') {
    const robustMin = nvImage.robust_min || 0;
    const robustMax = nvImage.robust_max || 1;
    
    switch (imageType) {
      case 'T1':
        // T1-weighted image optimization - preserve original sharpness
        nvImage.colormap = 'gray';
        nvImage.cal_min = robustMin * 0.1;
        nvImage.cal_max = robustMax * 0.9;
        break;
      
      case 'T2':
        // T2-weighted image optimization
        nvImage.colormap = 'gray';
        nvImage.cal_min = robustMin * 0.05;
        nvImage.cal_max = robustMax * 0.95;
        break;
      
      case 'FLAIR':
        // FLAIR image optimization
        nvImage.colormap = 'gray';
        nvImage.cal_min = robustMin * 0.15;
        nvImage.cal_max = robustMax * 0.85;
        break;
      
      case 'segmentation':
        // Segmentation image optimization - white matter as white, background as black
        nvImage.colormap = 'gray'; // Use grayscale display
        nvImage.cal_min = 0.5; // Higher threshold, only show white matter
        nvImage.cal_max = robustMax; // Ensure white matter is shown as white
        nvImage.opacity = 1.0; // Fully opaque
        console.log(`🎯 Segmentation image config: cal_min=${nvImage.cal_min}, cal_max=${nvImage.cal_max}, robustMax=${robustMax}`);
        break;
    }
    
    return nvImage;
  }

  /**
   * Get professional colormap options
   */
  static getColormapOptions() {
    return [
      { value: 'gray', label: 'Grayscale', description: 'Standard medical image display' },
      { value: 'bone', label: 'Bone', description: 'Suitable for bone structure display' },
      { value: 'viridis', label: 'Viridis', description: 'Perceptually uniform scientific colormap' },
      { value: 'plasma', label: 'Plasma', description: 'High-contrast scientific colormap' },
      { value: 'inferno', label: 'Inferno', description: 'Warm-tone scientific colormap' },
      { value: 'hot', label: 'Hot', description: 'Heatmap display' },
      { value: 'cool', label: 'Cool', description: 'Cool-tone display' },
      { value: 'jet', label: 'Jet', description: 'Rainbow spectrum' },
      { value: 'hsv', label: 'HSV', description: 'HSV color space' },
      { value: 'red', label: 'Red', description: 'For segmentation overlay' },
      { value: 'green', label: 'Green', description: 'For segmentation overlay' },
      { value: 'blue', label: 'Blue', description: 'For segmentation overlay' }
    ];
  }

  /**
   * Get view mode options
   */
  static getViewModeOptions() {
    return [
      { 
        value: 'multiplanar', 
        label: 'Multiplanar reconstruction', 
        description: 'Show axial, sagittal and coronal planes at the same time',
        sliceType: 'multiplanar'
      },
      { 
        value: 'render', 
        label: 'Volume rendering', 
        description: '3D volume rendering',
        sliceType: 'render'
      },
      { 
        value: 'axial', 
        label: 'Axial', 
        description: 'Horizontal slice view',
        sliceType: 'axial'
      },
      { 
        value: 'sagittal', 
        label: 'Sagittal', 
        description: 'Side slice view',
        sliceType: 'sagittal'
      },
      { 
        value: 'coronal', 
        label: 'Coronal', 
        description: 'Frontal slice view',
        sliceType: 'coronal'
      }
    ];
  }

  /**
   * Apply preset display configuration
   */
  static applyPreset(nv: Niivue, preset: 'brain' | 'segmentation' | 'comparison') {
    switch (preset) {
      case 'brain':
        // Standard brain image configuration
        nv.setScale(1.2);
        nv.opts.show3Dcrosshair = true;
        nv.opts.isColorbar = true;
        nv.setSliceType(nv.sliceTypeMultiplanar);
        break;
      
      case 'segmentation':
        // Segmentation result display configuration
        nv.setScale(1.0);
        nv.opts.show3Dcrosshair = false;
        nv.opts.isColorbar = false;
        nv.setSliceType(nv.sliceTypeAxial);
        break;
      
      case 'comparison':
        // Comparison display configuration
        nv.setScale(1.0);
        nv.opts.show3Dcrosshair = true;
        nv.opts.isColorbar = true;
        nv.setSliceType(nv.sliceTypeMultiplanar);
        break;
    }
  }

  /**
   * Get image information
   */
  static getImageInfo(nvImage: NVImage) {
    const dims = nvImage.dims || [0, 0, 0, 0];
    const pixdims = nvImage.pixDims || [0, 1, 1, 1];
    const robustMin = nvImage.robust_min || 0;
    const robustMax = nvImage.robust_max || 1;
    const globalMin = (nvImage as any).global_min;
    const globalMax = (nvImage as any).global_max;
    const datatype = (nvImage as any).datatypeCode || 16;
    
    return {
      dimensions: `${dims[1]} × ${dims[2]} × ${dims[3]}`,
      voxelSize: `${pixdims[1].toFixed(2)} × ${pixdims[2].toFixed(2)} × ${pixdims[3].toFixed(2)} mm`,
      voxelVolume: (pixdims[1] * pixdims[2] * pixdims[3]).toFixed(3),
      totalVoxels: dims[1] * dims[2] * dims[3],
      dataType: this.getDataTypeName(datatype),
      orientation: nvImage.matRAS ? 'Standard orientation (RAS)' : 'Original orientation',
      min: robustMin.toFixed(2),
      max: robustMax.toFixed(2),
      mean: (globalMin !== undefined && globalMax !== undefined) ? 
        ((globalMin + globalMax) / 2).toFixed(2) : 'N/A',
      fileSize: this.formatFileSize(dims[1] * dims[2] * dims[3] * this.getBytesPerVoxel(datatype))
    };
  }

  /**
   * Get data type name
   */
  private static getDataTypeName(datatypeCode: number): string {
    const dataTypes: { [key: number]: string } = {
      2: 'uint8',
      4: 'int16',
      8: 'int32',
      16: 'float32',
      64: 'float64',
      256: 'int8',
      512: 'uint16',
      768: 'uint32'
    };
    return dataTypes[datatypeCode] || `Unknown (${datatypeCode})`;
  }

  /**
   * Get bytes per voxel
   */
  private static getBytesPerVoxel(datatypeCode: number): number {
    const bytesPerVoxel: { [key: number]: number } = {
      2: 1,   // uint8
      4: 2,   // int16
      8: 4,   // int32
      16: 4,  // float32
      64: 8,  // float64
      256: 1, // int8
      512: 2, // uint16
      768: 4  // uint32
    };
    return bytesPerVoxel[datatypeCode] || 4;
  }

  /**
   * Format file size
   */
  private static formatFileSize(bytes: number): string {
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    
    return `${size.toFixed(1)} ${units[unitIndex]}`;
  }

  /**
   * Create screenshot configuration
   */
  static createScreenshotConfig() {
    return {
      filename: `brain_screenshot_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.png`,
      quality: 1.0,
      format: 'image/png'
    };
  }

  /**
   * Validate NIfTI file
   */
  static validateNiftiFile(file: File): { isValid: boolean; message: string } {
    const validExtensions = ['.nii', '.nii.gz', '.hdr', '.img'];
    const fileName = file.name.toLowerCase();
    
    const hasValidExtension = validExtensions.some(ext => fileName.endsWith(ext));
    
    if (!hasValidExtension) {
      return {
        isValid: false,
        message: `Unsupported file format. Supported formats: ${validExtensions.join(', ')}`
      };
    }
    
    if (file.size > 500 * 1024 * 1024) { // 500MB limit
      return {
        isValid: false,
        message: 'File is too large. Please choose a file smaller than 500MB.'
      };
    }
    
    return {
      isValid: true,
      message: 'Valid file format'
    };
  }
}

export default NiiVueConfig;