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

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InputArea from './InputArea';
import { pipelineService } from '../../services/pipelineService';
import { agentService } from '../../services/agentService';
import { useAgentStore } from '../../stores/agentStore';
import { useConfigStore } from '../../stores/configStore';

describe('Agent InputArea file upload', () => {
  beforeEach(() => {
    useAgentStore.setState({
      messages: [],
      filteredMessages: [],
      isLoading: false,
      isConnected: true,
      streamingMessageId: null,
    });
    useConfigStore.setState({
      config: {
        userId: 'researcher',
        workspaceDirectory: '/data/workspace',
        modelDir: '/data/models',
        maxConcurrentTasks: 2,
        processingOptions: {
          enablePreprocessing: true,
          qualityLevel: 'standard',
          threads: 2,
        },
      },
      userToken: 'test-token',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('asks the user to confirm and edit the subject ID before uploading', async () => {
    const uploadSpy = vi.spyOn(pipelineService, 'uploadFile').mockResolvedValue({
      savedPath: '/data/workspace/researcher/input/S7/T1/S7_T1_TFL_New.nii.gz',
      inputDir: '/data/workspace/researcher/input/S7/T1',
      subjectId: 'S7',
      fileName: 'S7_T1_TFL_New.nii.gz',
    });
    const recentUploadSpy = vi.spyOn(agentService, 'setRecentUpload').mockImplementation(() => {});
    const { container } = render(<InputArea />);
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();

    const file = new File(['nifti'], 'S7_T1_TFL_New.nii.gz', { type: 'application/gzip' });
    fireEvent.change(fileInput!, { target: { files: [file] } });

    expect(await screen.findByRole('dialog', { name: 'Confirm subject ID' })).toBeInTheDocument();
    const subjectInput = screen.getByLabelText('Subject ID');
    expect(subjectInput).toHaveValue('S7_T1_TFL_New');
    expect(uploadSpy).not.toHaveBeenCalled();

    fireEvent.change(subjectInput, { target: { value: 'S7' } });
    expect(screen.getByText('/data/workspace/researcher/input/S7/T1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and upload' }));

    await waitFor(() => {
      expect(uploadSpy).toHaveBeenCalledWith(
        file,
        'researcher',
        'S7',
        '/data/workspace',
        expect.any(Function),
      );
    });
    expect(recentUploadSpy).toHaveBeenCalledWith(expect.objectContaining({
      fileName: 'S7_T1_TFL_New.nii.gz',
      subjectId: 'S7',
    }));
  });
});
