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

// 简单的 NIfTI 文件解析器
export interface NiftiHeader {
  dims: number[];
  datatype: number;
  bitpix: number;
  pixdim: number[];
  vox_offset: number;
  scl_slope: number;
  scl_inter: number;
  cal_max: number;
  cal_min: number;
  sizeof_hdr: number;
  magic: string;
}

export interface NiftiData {
  header: NiftiHeader;
  data: ArrayBuffer;
  imageData: Uint8Array | Uint16Array | Int16Array | Float32Array | Float64Array;
}

export class SimpleNiftiParser {
  static async parseFile(file: File): Promise<NiftiData> {
    let buffer = await file.arrayBuffer();
    
    // 检查是否是 gzip 压缩文件
    if (file.name.endsWith('.gz')) {
      console.log('Decompressing gzipped NIfTI file...');
      buffer = await this.decompressGzip(buffer);
    }
    
    return this.parseBuffer(buffer);
  }

  // 简单的 gzip 解压缩（使用 DecompressionStream API）
  static async decompressGzip(buffer: ArrayBuffer): Promise<ArrayBuffer> {
    try {
      // 检查浏览器是否支持 DecompressionStream
      if (typeof DecompressionStream === 'undefined') {
        console.warn('DecompressionStream not supported, using fallback...');
        return this.decompressGzipFallback(buffer);
      }

      // 使用现代浏览器的 DecompressionStream API
      const stream = new DecompressionStream('gzip');
      const writer = stream.writable.getWriter();
      const reader = stream.readable.getReader();
      
      // 写入压缩数据
      writer.write(new Uint8Array(buffer));
      writer.close();
      
      // 读取解压缩的数据
      const chunks: Uint8Array[] = [];
      let done = false;
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          chunks.push(value);
        }
      }
      
      // 合并所有块
      const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const result = new Uint8Array(totalLength);
      let offset = 0;
      
      for (const chunk of chunks) {
        result.set(chunk, offset);
        offset += chunk.length;
      }
      
      console.log('Decompression successful. Original:', buffer.byteLength, 'Decompressed:', result.buffer.byteLength);
      return result.buffer;
    } catch (error) {
      console.error('Gzip decompression failed:', error);
      return this.decompressGzipFallback(buffer);
    }
  }

  // 备用解压缩方法（简单的实现）
  static async decompressGzipFallback(buffer: ArrayBuffer): Promise<ArrayBuffer> {
    console.log('Using fallback decompression method...');
    
    // 检查 gzip 魔数
    const view = new Uint8Array(buffer);
    if (view[0] === 0x1f && view[1] === 0x8b) {
      console.log('Detected gzip format, but no decompression available');
      console.log('Attempting to parse compressed data directly (may fail)...');
    }
    
    // 如果无法解压，尝试直接解析
    return buffer;
  }

  static parseBuffer(buffer: ArrayBuffer): NiftiData {
    const view = new DataView(buffer);
    
    // 检查头部大小
    const sizeof_hdr = view.getInt32(0, true);
    console.log('Header size:', sizeof_hdr);
    
    // 检查 NIfTI 魔数
    const magic = new TextDecoder().decode(buffer.slice(344, 348));
    console.log('NIfTI magic:', magic);
    
    // 验证这是一个有效的 NIfTI 文件
    const isValidNifti = sizeof_hdr === 348 && (magic === 'n+1\0' || magic === 'ni1\0');
    if (!isValidNifti) {
      console.warn('Invalid NIfTI header detected, attempting to parse anyway...');
    }
    
    // 读取 NIfTI 头部信息（修正版本）
    const header: NiftiHeader = {
      sizeof_hdr: sizeof_hdr,
      magic: magic,
      dims: [
        view.getInt16(40, true),  // dim[0] - 维度数量
        view.getInt16(42, true),  // dim[1] - x 维度
        view.getInt16(44, true),  // dim[2] - y 维度
        view.getInt16(46, true),  // dim[3] - z 维度
        view.getInt16(48, true),  // dim[4] - t 维度
      ],
      datatype: view.getInt16(70, true),
      bitpix: view.getInt16(72, true),
      pixdim: [
        view.getFloat32(76, true),  // pixdim[0]
        view.getFloat32(80, true),  // pixdim[1] - x 像素尺寸
        view.getFloat32(84, true),  // pixdim[2] - y 像素尺寸
        view.getFloat32(88, true),  // pixdim[3] - z 像素尺寸
      ],
      vox_offset: view.getFloat32(108, true),
      scl_slope: view.getFloat32(112, true) || 1.0,
      scl_inter: view.getFloat32(116, true) || 0.0,
      cal_max: view.getFloat32(124, true),
      cal_min: view.getFloat32(128, true),
    };

    // 验证维度数据的合理性
    console.log('Raw dims:', header.dims);
    
    // 如果维度看起来不合理，尝试不同的字节序
    if (header.dims[1] > 10000 || header.dims[2] > 10000) {
      console.log('Trying big-endian...');
      header.dims = [
        view.getInt16(40, false),  // dim[0] - 维度数量
        view.getInt16(42, false),  // dim[1] - x 维度
        view.getInt16(44, false),  // dim[2] - y 维度
        view.getInt16(46, false),  // dim[3] - z 维度
        view.getInt16(48, false),  // dim[4] - t 维度
      ];
      console.log('Big-endian dims:', header.dims);
    }

    // 如果还是不合理，使用默认值
    if (header.dims[1] <= 0 || header.dims[1] > 2048 || 
        header.dims[2] <= 0 || header.dims[2] > 2048) {
      console.warn('Invalid dimensions detected, using defaults');
      header.dims = [3, 256, 256, 128, 1];
    }

    // 确定数据偏移量
    let dataOffset = 352; // 标准 NIfTI 头部大小
    if (header.vox_offset > 0 && header.vox_offset < buffer.byteLength) {
      dataOffset = Math.floor(header.vox_offset);
    }

    console.log('Data offset:', dataOffset, 'Buffer size:', buffer.byteLength);

    // 提取图像数据
    const imageBuffer = buffer.slice(dataOffset);

    // 计算预期的数据大小
    const expectedVoxels = header.dims[1] * header.dims[2] * header.dims[3];
    const bytesPerVoxel = Math.max(1, header.bitpix / 8);
    const expectedBytes = expectedVoxels * bytesPerVoxel;
    
    console.log('Expected voxels:', expectedVoxels, 'Bytes per voxel:', bytesPerVoxel);
    console.log('Expected bytes:', expectedBytes, 'Available bytes:', imageBuffer.byteLength);

    // 根据数据类型解析图像数据
    let imageData: Uint8Array | Uint16Array | Int16Array | Float32Array | Float64Array;
    switch (header.datatype) {
      case 2: // unsigned char
        imageData = new Uint8Array(imageBuffer);
        break;
      case 4: // signed short
        imageData = new Int16Array(imageBuffer);
        break;
      case 512: // unsigned short
        imageData = new Uint16Array(imageBuffer);
        break;
      case 16: // float
        imageData = new Float32Array(imageBuffer);
        break;
      case 64: // double
        imageData = new Float64Array(imageBuffer);
        break;
      default:
        console.warn('Unknown datatype:', header.datatype, 'using Uint8Array');
        imageData = new Uint8Array(imageBuffer);
    }

    console.log('Image data length:', imageData.length, 'type:', imageData.constructor.name);

    return {
      header,
      data: buffer,
      imageData
    };
  }

  static extractSlice(niftiData: NiftiData, sliceIndex: number): ImageData | null {
    try {
      const { header, imageData } = niftiData;
      const [, width, height, depth] = header.dims;

      console.log('Extracting slice:', sliceIndex, 'Dimensions:', width, height, depth);
      console.log('Data type:', header.datatype, 'Bits per pixel:', header.bitpix);

      if (sliceIndex < 0 || sliceIndex >= depth || width <= 0 || height <= 0) {
        console.error('Invalid slice parameters');
        return null;
      }

      // 创建 ImageData
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;

      const imgData = ctx.createImageData(width, height);
      const pixels = imgData.data;

      // 计算切片在数据中的起始位置
      const sliceSize = width * height;
      const sliceStart = sliceIndex * sliceSize;

      console.log('Slice size:', sliceSize, 'Slice start:', sliceStart, 'Data length:', imageData.length);

      if (sliceStart >= imageData.length) {
        console.error('Slice start beyond data length');
        return null;
      }

      // 找到整个数据集的最大值和最小值用于归一化（更稳定的显示）
      let min = Infinity;
      let max = -Infinity;
      
      // 采样数据来估算范围（避免处理整个数据集）
      const sampleSize = Math.min(imageData.length, 10000);
      const step = Math.max(1, Math.floor(imageData.length / sampleSize));
      
      for (let i = 0; i < imageData.length; i += step) {
        const value = imageData[i];
        if (isFinite(value) && value !== 0) { // 忽略零值（通常是背景）
          if (value < min) min = value;
          if (value > max) max = value;
        }
      }

      console.log('Global value range:', min, 'to', max);

      // 如果没有有效数据，使用当前切片的范围
      if (!isFinite(min) || !isFinite(max) || min === max) {
        console.log('Using slice-specific range...');
        min = Infinity;
        max = -Infinity;
        
        const sliceEnd = Math.min(sliceStart + sliceSize, imageData.length);
        for (let i = sliceStart; i < sliceEnd; i++) {
          const value = imageData[i];
          if (isFinite(value)) {
            if (value < min) min = value;
            if (value > max) max = value;
          }
        }
        
        console.log('Slice value range:', min, 'to', max);
      }

      // 如果还是没有有效数据，创建测试图案
      if (!isFinite(min) || !isFinite(max) || min === max) {
        console.warn('No valid data found, creating test pattern');
        for (let y = 0; y < height; y++) {
          for (let x = 0; x < width; x++) {
            const pixelIndex = (y * width + x) * 4;
            const testValue = ((x + y) % 50 < 25) ? 128 : 64; // 创建棋盘图案
            pixels[pixelIndex] = testValue;     // R
            pixels[pixelIndex + 1] = testValue; // G
            pixels[pixelIndex + 2] = testValue; // B
            pixels[pixelIndex + 3] = 255;       // A
          }
        }
        return imgData;
      }

      const range = max - min;

      // 将数据转换为灰度图像
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const dataIndex = sliceStart + y * width + x;
          const pixelIndex = (y * width + x) * 4;
          
          let normalized = 0;
          if (dataIndex < imageData.length) {
            const value = imageData[dataIndex];
            
            if (isFinite(value) && range > 0) {
              // 应用缩放和偏移
              const scaledValue = value * header.scl_slope + header.scl_inter;
              normalized = Math.floor(((scaledValue - min) / range) * 255);
              normalized = Math.max(0, Math.min(255, normalized));
            }
          }
          
          pixels[pixelIndex] = normalized;     // R
          pixels[pixelIndex + 1] = normalized; // G
          pixels[pixelIndex + 2] = normalized; // B
          pixels[pixelIndex + 3] = 255;        // A
        }
      }

      return imgData;
    } catch (error) {
      console.error('Error extracting slice:', error);
      return null;
    }
  }

  static getSliceCount(niftiData: NiftiData): number {
    return Math.max(1, niftiData.header.dims[3] || 1);
  }

  static getDimensions(niftiData: NiftiData): { width: number; height: number; depth: number } {
    const [, width, height, depth] = niftiData.header.dims;
    return { 
      width: Math.max(1, width || 1), 
      height: Math.max(1, height || 1), 
      depth: Math.max(1, depth || 1) 
    };
  }
}