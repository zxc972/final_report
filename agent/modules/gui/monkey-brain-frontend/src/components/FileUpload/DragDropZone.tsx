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

import React, { useState } from 'react';
import { message } from 'antd';

interface DragDropZoneProps {
  onFilesDrop: (files: File[]) => void;
  children: React.ReactNode;
  accept?: string[];
  className?: string;
}

const DragDropZone: React.FC<DragDropZoneProps> = ({
  onFilesDrop,
  children,
  accept = ['.nii', '.nii.gz', '.dcm', '.gz'],
  className = ''
}) => {
  const [isDragOver, setIsDragOver] = useState(false);

  const validateFile = (file: File): boolean => {
    return accept.some(ext => file.name.toLowerCase().endsWith(ext));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    console.log('Files dropped:', files.map(f => f.name));

    const validFiles = files.filter(validateFile);
    const invalidFiles = files.filter(f => !validateFile(f));

    if (invalidFiles.length > 0) {
      message.warning(`Ignored ${invalidFiles.length} unsupported file(s).`);
    }

    if (validFiles.length > 0) {
      console.log('Valid files:', validFiles.map(f => f.name));
      onFilesDrop(validFiles);
      message.success(`Successfully dropped ${validFiles.length} file(s).`);
    } else if (files.length > 0) {
      message.error(`Please drop supported file formats: ${accept.join(', ')}`);
    }
  };

  return (
    <div
      className={`${className} ${isDragOver ? 'drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{
        position: 'relative',
        transition: 'all 0.2s ease',
        ...(isDragOver && {
          backgroundColor: 'rgba(24, 144, 255, 0.1)',
          borderColor: '#1890ff',
        })
      }}
    >
      {children}
      {isDragOver && (
        <div className="absolute inset-0 flex items-center justify-center bg-blue-500 bg-opacity-20 border-2 border-dashed border-blue-500 rounded-lg z-10">
          <div className="text-blue-600 text-lg font-medium">
            Drop files to load
          </div>
        </div>
      )}
    </div>
  );
};

export default DragDropZone;