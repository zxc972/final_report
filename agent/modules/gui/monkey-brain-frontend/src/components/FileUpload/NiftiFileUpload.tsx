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

import React, { useRef } from 'react';
import { Button, message } from 'antd';
import { UploadOutlined } from '@ant-design/icons';

interface NiftiFileUploadProps {
  onFileSelect: (file: File) => void;
  accept?: string;
  disabled?: boolean;
}

const NiftiFileUpload: React.FC<NiftiFileUploadProps> = ({
  onFileSelect,
  accept = '.nii,.nii.gz,.dcm',
  disabled = false
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      console.log('File selected via input:', file.name, file.type, file.size);
      
      // Validate file type - more relaxed validation
      const fileName = file.name.toLowerCase();
      const isValid = fileName.endsWith('.nii') || 
                     fileName.endsWith('.nii.gz') || 
                     fileName.endsWith('.dcm') ||
                     fileName.endsWith('.gz') ||
                     fileName.includes('.nii');
      
      if (isValid) {
        onFileSelect(file);
        message.success(`File selected: ${file.name}`);
      } else {
        message.error('Please select a valid NIfTI file format (.nii, .nii.gz, .dcm)');
      }
    }
    
    // Clear input value to allow selecting the same file again
    if (event.target) {
      event.target.value = '';
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />
      <Button
        icon={<UploadOutlined />}
        onClick={handleButtonClick}
        disabled={disabled}
        type="primary"
      >
        Select NIfTI File
      </Button>
    </>
  );
};

export default NiftiFileUpload;